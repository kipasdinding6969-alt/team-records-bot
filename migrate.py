"""Standalone migration: old DB → V2 schema."""
import asyncio
import logging
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


def _map_status(first_day: str, second_day: str) -> ClientStatus:
    """Map old 注册/不注册 to new ClientStatus."""
    first = (first_day or '').strip()
    second = (second_day or '').strip()
    if second == '注册' or first == '注册':
        return ClientStatus.REGISTERED
    return ClientStatus.CONTACTED


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
        staff_id_map = {}  # old_name → new_id
        try:
            cur = await old_db.execute(
                'SELECT * FROM team_members WHERE is_active = 1')
            members = await cur.fetchall()
        except Exception:
            members = []

        for m in members:
            display_name = m['display_name'] if 'display_name' in m.keys() else str(m['id'])
            tg_user_id = m['tg_user_id'] if 'tg_user_id' in m.keys() else m['id']
            tg_chat_id = m['tg_chat_id'] if 'tg_chat_id' in m.keys() else tg_user_id

            role_str = m['role'] if 'role' in m.keys() else 'frontdesk'
            try:
                role = StaffRole(role_str)
            except ValueError:
                role = StaffRole.FRONTDESK

            s = Staff(
                tg_user_id=tg_user_id,
                tg_chat_id=tg_chat_id,
                tg_username=m['tg_username'] if 'tg_username' in m.keys() else None,
                display_name=display_name,
                role=role,
                language=m['language'] if 'language' in m.keys() else 'zh',
            )
            new_id = await db_v2.upsert_staff(s)
            staff_id_map[display_name] = new_id
            logger.info(f'Migrated staff: {display_name} → id={new_id}')

        logger.info(f'Staff migrated: {len(staff_id_map)}')

        # 4. Migrate client_records → clients
        client_count = 0
        client_id_map = {}  # old_id → new_id

        try:
            cur = await old_db.execute('SELECT * FROM client_records')
            records = await cur.fetchall()
        except Exception:
            records = []

        for r in records:
            # Find frontdesk_id
            frontdesk_name = r['frontdesk'] if 'frontdesk' in r.keys() else ''
            frontdesk_id = staff_id_map.get(frontdesk_name)
            if not frontdesk_id:
                # Use first staff as fallback
                if staff_id_map:
                    frontdesk_id = list(staff_id_map.values())[0]
                else:
                    continue

            phone = r['client_number'] if 'client_number' in r.keys() else ''
            if not phone:
                continue

            source = r['category'] if 'category' in r.keys() else '未知'
            first_day = r['first_day'] if 'first_day' in r.keys() else ''
            second_day = r['second_day'] if 'second_day' in r.keys() else ''

            status = _map_status(first_day, second_day)
            status_note = r['client_condition'] if 'client_condition' in r.keys() else None

            client = Client(
                frontdesk_id=frontdesk_id,
                phone=phone,
                source=source,
                account_id=r['account_id'] if 'account_id' in r.keys() else None,
                phone_remark=r['phone_remark'] if 'phone_remark' in r.keys() else None,
                recruiter=r['recruiter'] if 'recruiter' in r.keys() else None,
                status=status,
                status_note=status_note,
                sheet_gid=r['sheet_gid'] if 'sheet_gid' in r.keys() else None,
            )
            new_id = await db_v2.create_client(client)
            old_row_id = r['id'] if 'id' in r.keys() else None
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
            frontdesk_name = f['frontdesk'] if 'frontdesk' in f.keys() else ''
            frontdesk_id = staff_id_map.get(frontdesk_name)
            if not frontdesk_id:
                continue

            # Find or create a placeholder client
            amount = 0.0
            for knife_col in [f'knife_{i}' for i in range(1, 9)] + ['new_order_amount']:
                try:
                    val = f[knife_col] if knife_col in f.keys() else None
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

            dep_date_str = f['date'] if 'date' in f.keys() else None
            try:
                dep_date = date.today()
                if dep_date_str:
                    # Try parse "X月X日" → today as fallback
                    dep_date = date.today()
            except Exception:
                dep_date = date.today()

            # Use a placeholder client_id = 1 (or skip if no clients)
            if not client_id_map:
                continue
            client_id = list(client_id_map.values())[0]

            d = Deposit(
                client_id=client_id,
                frontdesk_id=frontdesk_id,
                amount=amount,
                deposit_date=dep_date,
                platform=f['platform'] if 'platform' in f.keys() else None,
                note=f['note'] if 'note' in f.keys() else None,
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
