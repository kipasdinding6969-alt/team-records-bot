"""Standalone migration: old DB → V2 schema."""
import asyncio
import logging
import re
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import aiosqlite

from database_v2 import DatabaseV2
from models_v2 import Client, ClientStatus, Deposit, Staff, StaffRole

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

OLD_DB_PATH = 'team_records.db'
NEW_DB_PATH = 'team_records_v2.db'
BACKUP_PATH = f'team_records.db.bak_{datetime.now().strftime("%Y%m%d_%H%M%S")}'

_MONTH_DAY_RE = re.compile(r'(\d{1,2})月(\d{1,2})日')


def _map_status(first_day: str, second_day: str) -> ClientStatus:
    """Map old 注册/不注册 to new ClientStatus."""
    first = (first_day or '').strip()
    second = (second_day or '').strip()
    if not first and not second:
        return ClientStatus.NEW
    if second == '注册' or first == '注册':
        return ClientStatus.REGISTERED
    return ClientStatus.CONTACTED


def _parse_date(date_str: Optional[str], fallback: date) -> date:
    """Parse 'X月X日' format. Falls back to provided date on failure."""
    if not date_str:
        return fallback
    m = _MONTH_DAY_RE.search(date_str)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        try:
            return date(fallback.year, month, day)
        except ValueError:
            pass
    return fallback


async def migrate():
    """Run full migration from old DB to V2."""
    old_path = Path(OLD_DB_PATH)
    if not old_path.exists():
        logger.warning(f'Old DB not found at {OLD_DB_PATH} — skipping data migration')
        db_v2 = DatabaseV2(NEW_DB_PATH)
        await db_v2.initialize()
        logger.info('V2 DB initialized (empty)')
        return

    # 1. Backup old DB
    shutil.copy2(OLD_DB_PATH, BACKUP_PATH)
    logger.info(f'Backed up old DB to {BACKUP_PATH}')

    # 2. Initialize V2 DB
    db_v2 = DatabaseV2(NEW_DB_PATH)
    await db_v2.initialize()
    logger.info('V2 DB initialized')

    async with aiosqlite.connect(OLD_DB_PATH) as old_db:
        old_db.row_factory = aiosqlite.Row

        # 3. Migrate team_members → staff
        staff_id_map: dict = {}   # old display_name → new V2 id
        staff_tgid_map: dict = {} # old tg_user_id → new V2 id (for deposit lookup)
        try:
            cur = await old_db.execute(
                'SELECT * FROM team_members WHERE is_active = 1')
            members = await cur.fetchall()
        except Exception:
            members = []

        for m in members:
            keys = m.keys()
            # Old schema may use 'display_name' or 'frontdesk_name'
            display_name = (
                m['display_name'] if 'display_name' in keys else
                m['frontdesk_name'] if 'frontdesk_name' in keys else
                str(m['id'])
            )
            tg_user_id = (
                m['tg_user_id'] if 'tg_user_id' in keys else
                m['user_id'] if 'user_id' in keys else
                m['id']
            )
            tg_chat_id = m['tg_chat_id'] if 'tg_chat_id' in keys else tg_user_id

            role_str = m['role'] if 'role' in keys else 'frontdesk'
            try:
                role = StaffRole(role_str)
            except ValueError:
                role = StaffRole.FRONTDESK

            s = Staff(
                tg_user_id=tg_user_id,
                tg_chat_id=tg_chat_id,
                tg_username=m['tg_username'] if 'tg_username' in keys else None,
                display_name=display_name,
                role=role,
                language=m['language'] if 'language' in keys else 'zh',
            )
            new_id = await db_v2.upsert_staff(s)
            staff_id_map[display_name] = new_id
            staff_tgid_map[tg_user_id] = new_id
            logger.info(f'Migrated staff: {display_name} → id={new_id}')

        logger.info(f'Staff migrated: {len(staff_id_map)}')

        # 4. Migrate client_records → clients (with deduplication)
        client_count = 0
        client_id_map: dict = {}       # old_id → new V2 client id
        phone_fd_seen: set = set()     # (phone, frontdesk_id) dedup set

        try:
            cur = await old_db.execute('SELECT * FROM client_records')
            records = await cur.fetchall()
        except Exception:
            records = []

        for r in records:
            keys = r.keys()
            # Resolve frontdesk_id
            frontdesk_name = r['frontdesk'] if 'frontdesk' in keys else ''
            frontdesk_id = staff_id_map.get(frontdesk_name)
            if not frontdesk_id:
                if staff_id_map:
                    frontdesk_id = list(staff_id_map.values())[0]
                else:
                    continue

            phone = r['client_number'] if 'client_number' in keys else ''
            if not phone:
                continue

            # Deduplication: skip if (phone, frontdesk_id) already migrated
            dedup_key = (phone, frontdesk_id)
            if dedup_key in phone_fd_seen:
                logger.debug(f'Skipping duplicate client {phone} for frontdesk {frontdesk_id}')
                continue
            phone_fd_seen.add(dedup_key)

            source = r['category'] if 'category' in keys else '未知'
            first_day = r['first_day'] if 'first_day' in keys else ''
            second_day = r['second_day'] if 'second_day' in keys else ''

            status = _map_status(first_day, second_day)
            status_note = r['client_condition'] if 'client_condition' in keys else None

            client = Client(
                frontdesk_id=frontdesk_id,
                phone=phone,
                source=source,
                account_id=r['account_id'] if 'account_id' in keys else None,
                phone_remark=r['phone_remark'] if 'phone_remark' in keys else None,
                recruiter=r['recruiter'] if 'recruiter' in keys else None,
                status=status,
                status_note=status_note,
                sheet_gid=r['sheet_gid'] if 'sheet_gid' in keys else None,
            )
            new_id = await db_v2.create_client(client)
            old_row_id = r['id'] if 'id' in keys else None
            if old_row_id:
                client_id_map[old_row_id] = new_id
            client_count += 1

        logger.info(f'Clients migrated: {client_count}')

        # 5. Migrate financial_records → deposits
        deposit_count = 0
        try:
            cur = await old_db.execute('SELECT * FROM financial_records')
            fin_records = await cur.fetchall()
        except Exception:
            fin_records = []

        for f in fin_records:
            keys = f.keys()
            frontdesk_name = f['frontdesk'] if 'frontdesk' in keys else ''
            frontdesk_id = staff_id_map.get(frontdesk_name)
            if not frontdesk_id:
                continue

            # Try to match deposit to a client by frontdesk + account_id
            account_id = f['account_id'] if 'account_id' in keys else None
            matched_client_id: Optional[int] = None
            if account_id:
                # Search V2 clients for this frontdesk+account_id
                all_clients = await db_v2.get_clients_by_frontdesk(frontdesk_id, limit=500)
                for c in all_clients:
                    if c.account_id and str(c.account_id) == str(account_id):
                        matched_client_id = c.id
                        break

            if matched_client_id is None:
                logger.warning(
                    f'Deposit skipped: no client match for frontdesk={frontdesk_name} account_id={account_id}')
                continue

            # Extract amount from knife_1..knife_8 or new_order_amount
            amount = 0.0
            for knife_col in [f'knife_{i}' for i in range(1, 9)] + ['new_order_amount']:
                try:
                    val = f[knife_col] if knife_col in keys else None
                    if val:
                        val_str = str(val).replace('$', '').replace(',', '').strip()
                        if val_str.startswith('-'):
                            continue
                        amount = float(val_str)
                        break
                except (ValueError, TypeError):
                    continue

            if amount <= 0:
                continue

            # Parse date from 'X月X日' format
            raw_date = f['date'] if 'date' in keys else None
            created_at_str = f['created_at'] if 'created_at' in keys else None
            fallback_date = date.today()
            if created_at_str:
                try:
                    fallback_date = datetime.fromisoformat(created_at_str).date()
                except Exception:
                    pass
            dep_date = _parse_date(raw_date, fallback_date)

            d = Deposit(
                client_id=matched_client_id,
                frontdesk_id=frontdesk_id,
                amount=amount,
                deposit_date=dep_date,
                platform=f['platform'] if 'platform' in keys else None,
                note=f['note'] if 'note' in keys else None,
            )
            await db_v2.create_deposit(d)
            deposit_count += 1

        logger.info(f'Deposits migrated: {deposit_count}')

        # 6. Calculate initial daily_stats
        await db_v2.recalculate_all_today_stats()
        logger.info('Initial daily_stats calculated')

        # 7. Index all notes into RAG
        try:
            from engines.rag_engine import rebuild_index
            indexed = await rebuild_index()
            logger.info(f'RAG index built: {indexed} clients')
        except Exception as e:
            logger.warning(f'RAG indexing skipped (Ollama may not be running): {e}')

    # 8. Verify counts
    all_staff = await db_v2.get_all_staff(active_only=False)
    logger.info(f'Verification — Staff: {len(all_staff)}, Clients: {client_count}, Deposits: {deposit_count}')
    print(f'\n✅ Migration complete!')
    print(f'   Staff:    {len(all_staff)}')
    print(f'   Clients:  {client_count}')
    print(f'   Deposits: {deposit_count}')
    print(f'   Backup:   {BACKUP_PATH}')
    print(f'   New DB:   {NEW_DB_PATH}')


if __name__ == '__main__':
    asyncio.run(migrate())
