"""Bidirectional Google Sheets ↔ V2 DB sync engine.

Phase 37: Enhanced to populate Phase 26 tables from 維護數據 sheet:
  - knife_deposits (columns K-R: knife 1-8 amounts)
  - client_pipeline_status (columns H-I: new_order/pressure, + kill detection)
  - client_role_assignments (columns D+E: frontdesk + maintenance pairing)
  - cross_role_notes (columns T-Z: 前台/开单/小白/炒群/客服/维护/等等)
"""
import asyncio
import hashlib
import logging
import sqlite3
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple

from engines.gsheet_writer import GSheetWriter, FRONTDESK_SHEETS, SHEET_MAP
from database_v2 import database_v2, NAME_ALIASES
from models_v2 import Client, ClientStatus, Deposit, Staff, StaffRole

# Module-level singleton — initialized by main.py
sheet_sync_v2: Optional['SheetSyncV2'] = None

logger = logging.getLogger(__name__)

FRONTDESK_NAMES = list(FRONTDESK_SHEETS.keys())

# Cross-role note column mapping: sheet column index → role name
_CROSS_ROLE_COLUMNS = {
    19: 'frontdesk',    # T
    20: 'opener',       # U (开单 — legacy)
    21: 'newbie',       # V (小白)
    22: 'hype',         # W (炒群)
    23: 'cs',           # X (客服)
    24: 'maintenance',  # Y (维护)
    25: 'etc',          # Z (等等)
}

# Kill type detection patterns in note/condition text
_KILL_PATTERNS = {
    '注册杀': 'register_kill',
    '新单杀': 'new_order_kill',
    '承压杀': 'pressure_kill',
    '工资杀': 'salary_kill',
}


def _parse_money(value: str) -> float:
    """Parse sheet money string like '$1,234' or '-$1,234' to float."""
    if not value or not value.strip():
        return 0.0
    v = value.strip().replace(',', '')
    negative = False
    if v.startswith('-'):
        negative = True
        v = v[1:]
    v = v.lstrip('$')
    try:
        result = float(v)
        return -result if negative else result
    except ValueError:
        return 0.0


def _map_days_to_status(first_day: str, second_day: str) -> ClientStatus:
    """Map first_day/second_day sheet values to ClientStatus."""
    if '注册' in first_day or '注册' in second_day:
        return ClientStatus.REGISTERED
    if '不注册' in first_day and '不注册' in second_day:
        return ClientStatus.CONTACTED
    if '不注册' in first_day:
        return ClientStatus.CONTACTED
    return ClientStatus.NEW


def _map_status_to_days(status: ClientStatus) -> Tuple[str, str]:
    """Map ClientStatus to (first_day, second_day) sheet strings."""
    if status in (ClientStatus.TRAINING, ClientStatus.WITHDREW, ClientStatus.ORDERED):
        return ('注册', '注册')
    if status == ClientStatus.REGISTERED:
        return ('注册', '')
    if status in (ClientStatus.GHOSTED, ClientStatus.BLOCKED, ClientStatus.SCAMMED, ClientStatus.DEAD):
        return ('不注册', '不注册')
    # new/contacted/replied/scheduled — leave blank
    return ('', '')


def _synthetic_tg_id(name: str) -> int:
    """Deterministic negative tg_user_id for sheet-imported staff (no real TG account)."""
    h = int(hashlib.md5(name.encode()).hexdigest()[:8], 16)
    return -(h % 10_000_000 + 1)  # negative, 1–10M range


class SheetSyncV2:
    def __init__(self, writer: GSheetWriter):
        self.writer = writer

    # ─── Helpers ─────────────────────────────────────────────────────────────

    async def _ensure_sheet_row_column(self):
        """Add sheet_row column to clients if not exists (safe migration)."""
        async with database_v2.get_connection() as db:
            try:
                await db.execute('ALTER TABLE clients ADD COLUMN sheet_row INTEGER')
                await db.commit()
                logger.info('Migration: added sheet_row to clients')
            except Exception:
                pass  # column already exists

    async def _get_or_create_staff(self, display_name: str) -> Optional[Staff]:
        """Find staff by display_name or create a synthetic sheet-import record."""
        staff = await database_v2.get_staff_by_display_name(display_name)
        if staff:
            return staff
        synth_id = _synthetic_tg_id(display_name)
        new_staff = Staff(
            tg_user_id=synth_id,
            tg_chat_id=synth_id,
            display_name=display_name,
            role=StaffRole.FRONTDESK,
        )
        try:
            staff_id = await database_v2.create_staff(new_staff)
            new_staff.id = staff_id
            logger.info(f'Created synthetic staff for sheet import: {display_name}')
            return new_staff
        except Exception as e:
            logger.error(f'Failed to create staff for {display_name}: {e}')
            return None

    async def _upsert_client_from_row(
        self, row: Dict[str, Any], frontdesk_id: int, sheet_gid: int
    ) -> bool:
        """Upsert a single sheet row into V2 clients table.

        Also creates: client_pipeline_status (from day statuses),
        client_role_assignments (frontdesk link).
        """
        phone = row.get('client_number', '').strip()
        date_val = row.get('date', '').strip()

        # Skip template placeholder rows
        if not phone or phone.upper().replace('X', '') == '':
            return False
        if set(phone.upper()) <= {'X', '-', ' '}:
            return False
        if 'X月' in date_val and ('X日' in date_val or date_val.endswith('X')):
            return False
        frontdesk_raw = row.get('frontdesk', '').strip()
        if frontdesk_raw and set(frontdesk_raw.upper()) <= {'X', '-', ' '}:
            return False

        first_day = row.get('first_day', '')
        second_day = row.get('second_day', '')
        status = _map_days_to_status(first_day, second_day)
        account_id = row.get('account_id', '').strip() or None
        phone_remark = row.get('phone_remark', '').strip() or None
        nickname = row.get('frontdesk_username', '').strip() or None
        source = row.get('category', '').strip() or ''
        recruiter = row.get('recruiter', '').strip() or None
        status_note = row.get('client_condition', '').strip() or None
        row_index = row.get('row_index')

        existing = await database_v2.get_client_by_phone(phone, frontdesk_id)
        client_id = None
        if existing:
            client_id = existing.id
            async with database_v2.get_connection() as db:
                await db.execute(
                    """UPDATE clients
                       SET status=?, status_note=?, account_id=?, phone_remark=?,
                           nickname=?, source=?, recruiter=?, sheet_gid=?, sheet_row=?,
                           first_day_status=?, second_day_status=?, client_condition=?,
                           updated_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (status.value, status_note, account_id, phone_remark,
                     nickname, source, recruiter, sheet_gid, row_index,
                     first_day, second_day, status_note,
                     existing.id)
                )
                await db.commit()
        else:
            client = Client(
                frontdesk_id=frontdesk_id,
                phone=phone,
                source=source,
                account_id=account_id,
                phone_remark=phone_remark,
                nickname=nickname,
                recruiter=recruiter,
                status=status,
                status_note=status_note,
                sheet_gid=sheet_gid,
            )
            client_id = await database_v2.create_client(client)
            async with database_v2.get_connection() as db:
                await db.execute(
                    'UPDATE clients SET sheet_row=?, first_day_status=?, second_day_status=?, client_condition=? WHERE id=?',
                    (row_index, first_day, second_day, status_note, client_id)
                )
                await db.commit()

        # Phase 37: Auto-create pipeline status + frontdesk role assignment
        if client_id:
            async with database_v2.get_connection() as db:
                # Pipeline: map status to pipeline milestones
                contacted = status in (
                    ClientStatus.CONTACTED, ClientStatus.REPLIED,
                    ClientStatus.REGISTERED, ClientStatus.TRAINING,
                    ClientStatus.WITHDREW, ClientStatus.ORDERED,
                )
                registered = '注册' in first_day or '注册' in second_day
                try:
                    await db.execute(
                        '''INSERT INTO client_pipeline_status (client_id, contacted_at, registered_at)
                           VALUES (?, CASE WHEN ? THEN CURRENT_TIMESTAMP END, CASE WHEN ? THEN CURRENT_TIMESTAMP END)
                           ON CONFLICT(client_id) DO UPDATE SET
                             contacted_at = CASE WHEN excluded.contacted_at IS NOT NULL AND client_pipeline_status.contacted_at IS NULL THEN excluded.contacted_at ELSE client_pipeline_status.contacted_at END,
                             registered_at = CASE WHEN excluded.registered_at IS NOT NULL AND client_pipeline_status.registered_at IS NULL THEN excluded.registered_at ELSE client_pipeline_status.registered_at END,
                             updated_at = CURRENT_TIMESTAMP''',
                        (client_id, contacted, registered)
                    )
                except Exception as e:
                    logger.debug(f'_upsert pipeline for client {client_id}: {e}')

                # Frontdesk role assignment
                await self._sync_role_assignment(db, client_id, frontdesk_id, 'frontdesk')
                await db.commit()

        return True

    # ─── Direction 1: Sheets → V2 DB ─────────────────────────────────────────

    async def import_client_sheet(self, frontdesk_name: str) -> int:
        """Import one frontdesk sheet into V2 clients table. Returns count upserted."""
        staff = await self._get_or_create_staff(frontdesk_name)
        if not staff:
            logger.error(f'import_client_sheet: no staff record for {frontdesk_name}')
            return 0

        sheet_gid = SHEET_MAP.get(frontdesk_name, 0)
        loop = asyncio.get_event_loop()
        rows: List[Dict] = await loop.run_in_executor(
            None, self.writer.read_client_sheet, frontdesk_name
        )

        count = 0
        for row in rows:
            try:
                ok = await self._upsert_client_from_row(row, staff.id, sheet_gid)
                if ok:
                    count += 1
            except Exception as e:
                logger.error(
                    f'import_client_sheet {frontdesk_name} row {row.get("row_index")}: {e}'
                )
            await asyncio.sleep(0)  # yield to event loop
        logger.info(f'import_client_sheet: {frontdesk_name} → {count} rows')
        return count

    async def _sync_knives_for_client(self, db, client_id: int, row: list):
        """Parse knife columns K-R (indices 10-17) → knife_deposits table."""
        for knife_num in range(1, 9):
            col_idx = 9 + knife_num  # knife_1=10, knife_2=11, ..., knife_8=17
            if len(row) <= col_idx:
                break
            amount = _parse_money(row[col_idx])
            if amount == 0.0:
                continue
            try:
                await db.execute(
                    'INSERT INTO knife_deposits (client_id, knife_number, amount) '
                    'VALUES (?, ?, ?) '
                    'ON CONFLICT(client_id, knife_number) DO UPDATE SET amount=excluded.amount',
                    (client_id, knife_num, amount)
                )
            except Exception as e:
                logger.debug(f'_sync_knives knife {knife_num} client {client_id}: {e}')

    async def _sync_pipeline_for_client(self, db, client_id: int, row: list, note: str):
        """Parse new_order/pressure + detect kill type → client_pipeline_status."""
        new_order = _parse_money(row[7]) if len(row) > 7 else 0.0
        pressure = _parse_money(row[8]) if len(row) > 8 else 0.0
        total_in = _parse_money(row[18]) if len(row) > 18 else 0.0

        # Detect kill type from note text
        kill_type = None
        kill_knife = None
        for pattern, ktype in _KILL_PATTERNS.items():
            if pattern in note:
                kill_type = ktype
                # Extract knife number: "工资杀6刀" → 6
                idx = note.find(pattern)
                after = note[idx + len(pattern):]
                digits = ''
                for ch in after:
                    if ch.isdigit():
                        digits += ch
                    else:
                        break
                if digits:
                    kill_knife = int(digits)
                break

        # Upsert pipeline status
        try:
            await db.execute(
                '''INSERT INTO client_pipeline_status (client_id, new_order_amount, new_order_at, pressure_amount, pressure_at, kill_type, kill_knife, total_deposited)
                   VALUES (?, ?, CASE WHEN ? > 0 THEN CURRENT_TIMESTAMP END, ?, CASE WHEN ? > 0 THEN CURRENT_TIMESTAMP END, ?, ?, ?)
                   ON CONFLICT(client_id) DO UPDATE SET
                     new_order_amount = CASE WHEN excluded.new_order_amount > 0 THEN excluded.new_order_amount ELSE client_pipeline_status.new_order_amount END,
                     new_order_at = CASE WHEN excluded.new_order_amount > 0 AND client_pipeline_status.new_order_at IS NULL THEN CURRENT_TIMESTAMP ELSE client_pipeline_status.new_order_at END,
                     pressure_amount = CASE WHEN excluded.pressure_amount > 0 THEN excluded.pressure_amount ELSE client_pipeline_status.pressure_amount END,
                     pressure_at = CASE WHEN excluded.pressure_amount > 0 AND client_pipeline_status.pressure_at IS NULL THEN CURRENT_TIMESTAMP ELSE client_pipeline_status.pressure_at END,
                     kill_type = COALESCE(excluded.kill_type, client_pipeline_status.kill_type),
                     kill_knife = COALESCE(excluded.kill_knife, client_pipeline_status.kill_knife),
                     total_deposited = CASE WHEN excluded.total_deposited > client_pipeline_status.total_deposited THEN excluded.total_deposited ELSE client_pipeline_status.total_deposited END,
                     updated_at = CURRENT_TIMESTAMP''',
                (client_id, new_order, new_order, pressure, pressure, kill_type, kill_knife, total_in)
            )
        except Exception as e:
            logger.debug(f'_sync_pipeline client {client_id}: {e}')

    async def _sync_role_assignment(self, db, client_id: int, staff_id: int, role_type: str):
        """Create client_role_assignments if not already exists."""
        try:
            cur = await db.execute(
                'SELECT id FROM client_role_assignments WHERE client_id=? AND staff_id=? AND role_type=?',
                (client_id, staff_id, role_type)
            )
            if await cur.fetchone():
                return  # already assigned
            await db.execute(
                'INSERT INTO client_role_assignments (client_id, staff_id, role_type) VALUES (?, ?, ?)',
                (client_id, staff_id, role_type)
            )
        except sqlite3.IntegrityError:
            pass  # race condition or constraint violation
        except Exception as e:
            logger.debug(f'_sync_role_assignment client {client_id} staff {staff_id} {role_type}: {e}')

    async def _sync_cross_role_notes(self, db, client_id: int, row: list):
        """Parse cross-role note columns T-Z (indices 19-25) → cross_role_notes."""
        for col_idx, role_name in _CROSS_ROLE_COLUMNS.items():
            if len(row) <= col_idx:
                break
            content = row[col_idx].strip() if row[col_idx] else ''
            if not content:
                continue
            # Only insert if not already exists (avoid duplicates on re-sync)
            try:
                cur = await db.execute(
                    'SELECT id FROM cross_role_notes WHERE client_id=? AND from_role=? AND content=?',
                    (client_id, role_name, content)
                )
                if await cur.fetchone():
                    continue
                await db.execute(
                    'INSERT INTO cross_role_notes (client_id, from_role, content) VALUES (?, ?, ?)',
                    (client_id, role_name, content)
                )
            except Exception as e:
                logger.debug(f'_sync_cross_role_notes client {client_id} {role_name}: {e}')

    async def import_financial_sheet(self) -> int:
        """Import 维护数据 sheet into V2 DB.

        Populates: deposits, knife_deposits, client_pipeline_status,
        client_role_assignments, cross_role_notes.
        """
        loop = asyncio.get_event_loop()
        try:
            ws = await loop.run_in_executor(
                None, lambda: self.writer.spreadsheet.worksheet('维护数据')
            )
            all_rows = await loop.run_in_executor(None, ws.get_all_values)
        except Exception as e:
            logger.error(f'import_financial_sheet: failed to read 维护数据: {e}')
            return 0

        count = 0
        knives_count = 0
        pipeline_count = 0
        roles_count = 0
        notes_count = 0

        for i, row in enumerate(all_rows[1:], start=2):  # skip header row
            if len(row) < 8 or not row[0].strip():
                continue
            if row[0].strip() in ('X月XX日', '日期', 'DATE'):
                continue
            try:
                frontdesk_name = row[3].strip() if len(row) > 3 else ''
                account_id = row[1].strip() if len(row) > 1 else ''
                maintenance_name = row[4].strip() if len(row) > 4 else ''
                note = row[9].strip() if len(row) > 9 else ''

                if not frontdesk_name:
                    continue

                frontdesk_name = NAME_ALIASES.get(frontdesk_name, frontdesk_name)
                staff = await database_v2.get_staff_by_display_name(frontdesk_name)
                if not staff:
                    continue

                # Match client by frontdesk + account_id
                client = None
                if account_id:
                    async with database_v2.get_connection() as db:
                        cur = await db.execute(
                            'SELECT id, frontdesk_id, phone, account_id, status FROM clients '
                            'WHERE frontdesk_id=? AND account_id=? LIMIT 1',
                            (staff.id, account_id)
                        )
                        row_data = await cur.fetchone()
                        if row_data:
                            client = dict(row_data)

                if not client:
                    continue

                client_id = client['id']

                # Parse date
                date_str = row[0].strip()
                try:
                    deposit_date = datetime.strptime(date_str, '%m/%d/%Y').date()
                except ValueError:
                    try:
                        deposit_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    except ValueError:
                        deposit_date = date.today()

                async with database_v2.get_connection() as db:
                    # 1. Deposit (total_in, column S index 18)
                    total_str = row[18].strip() if len(row) > 18 else ''
                    total = _parse_money(total_str)
                    if total > 0:
                        try:
                            deposit = Deposit(
                                client_id=client_id,
                                frontdesk_id=staff.id,
                                amount=total,
                                deposit_date=deposit_date,
                                platform=row[6].strip() if len(row) > 6 else 'Iconnect',
                                note=note or None,
                            )
                            await database_v2.create_deposit(deposit)
                            count += 1
                        except Exception:
                            pass  # duplicate deposit

                    # 2. Knife deposits (columns K-R, indices 10-17)
                    await self._sync_knives_for_client(db, client_id, row)
                    knives_count += 1

                    # 3. Pipeline status (new_order, pressure, kill detection)
                    await self._sync_pipeline_for_client(db, client_id, row, note)
                    pipeline_count += 1

                    # 4. Role assignments — frontdesk
                    await self._sync_role_assignment(db, client_id, staff.id, 'frontdesk')

                    # 4b. Role assignments — maintenance (if column E has a name)
                    if maintenance_name:
                        maintenance_name = NAME_ALIASES.get(maintenance_name, maintenance_name)
                        mt_staff = await database_v2.get_staff_by_display_name(maintenance_name)
                        if mt_staff:
                            await self._sync_role_assignment(db, client_id, mt_staff.id, 'maintainer')
                            # Also update client.maintenance_id
                            await db.execute(
                                'UPDATE clients SET maintenance_id=? WHERE id=? AND maintenance_id IS NULL',
                                (mt_staff.id, client_id)
                            )
                            roles_count += 1

                    # 5. Cross-role notes (columns T-Z, indices 19-25)
                    await self._sync_cross_role_notes(db, client_id, row)
                    notes_count += 1

                    await db.commit()

            except Exception as e:
                logger.error(f'import_financial_sheet row {i}: {e}')
            await asyncio.sleep(0)

        logger.info(
            f'import_financial_sheet: {count} deposits, {knives_count} knife rows, '
            f'{pipeline_count} pipeline rows, {roles_count} role assignments, {notes_count} note rows'
        )
        return count

    async def import_performance_sheet(self) -> int:
        """Import 前台数据 sheet into daily_performance table."""
        loop = asyncio.get_event_loop()
        try:
            # Try current month sheet name
            sheet_name = None
            for name in SHEET_MAP:
                if '前台数据' in name or '前台數據' in name:
                    sheet_name = name
                    break
            if not sheet_name:
                sheet_name = '3月-前台数据'  # fallback

            ws = await loop.run_in_executor(
                None, lambda: self.writer.spreadsheet.worksheet(sheet_name)
            )
            all_rows = await loop.run_in_executor(None, ws.get_all_values)
        except Exception as e:
            logger.error(f'import_performance_sheet: failed to read: {e}')
            return 0

        if len(all_rows) < 3:
            return 0

        # Header row expected at row 1 or 2 — detect columns dynamically
        header = all_rows[0] if all_rows[0] and any(c.strip() for c in all_rows[0]) else all_rows[1]

        count = 0
        for i, row in enumerate(all_rows[2:], start=3):
            if len(row) < 5 or not row[0].strip():
                continue
            if row[0].strip() in ('日期', 'DATE', 'X月X日'):
                continue

            try:
                date_str = row[0].strip()
                staff_name = row[1].strip() if len(row) > 1 else ''
                category = row[2].strip() if len(row) > 2 else ''
                if not staff_name:
                    continue

                staff_name = NAME_ALIASES.get(staff_name, staff_name)
                staff = await database_v2.get_staff_by_display_name(staff_name)
                if not staff:
                    continue

                # Parse date
                try:
                    stat_date = datetime.strptime(date_str, '%m/%d/%Y').strftime('%Y-%m-%d')
                except ValueError:
                    try:
                        stat_date = datetime.strptime(date_str, '%Y-%m-%d').strftime('%Y-%m-%d')
                    except ValueError:
                        continue

                # Parse numeric columns — positions may vary but typically:
                # powder_count, reply_rate, completed_registration, completed_training, withdrawal, new_order
                powder = int(row[3]) if len(row) > 3 and row[3].strip().isdigit() else 0
                reply_rate = float(row[4].replace('%', '')) if len(row) > 4 and row[4].strip() else 0.0
                reg = int(row[5]) if len(row) > 5 and row[5].strip().isdigit() else 0
                training = int(row[6]) if len(row) > 6 and row[6].strip().isdigit() else 0
                withdrawal = int(row[7]) if len(row) > 7 and row[7].strip().isdigit() else 0
                new_order = int(row[8]) if len(row) > 8 and row[8].strip().isdigit() else 0
                conversion = float(row[9].replace('%', '')) if len(row) > 9 and row[9].strip() else 0.0

                async with database_v2.get_connection() as db:
                    await db.execute(
                        '''INSERT INTO daily_performance (staff_id, stat_date, category, powder_count, reply_rate,
                             completed_registration, completed_training, withdrawal, new_order, conversion_rate)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT(staff_id, stat_date, category) DO UPDATE SET
                             powder_count=excluded.powder_count, reply_rate=excluded.reply_rate,
                             completed_registration=excluded.completed_registration,
                             completed_training=excluded.completed_training,
                             withdrawal=excluded.withdrawal, new_order=excluded.new_order,
                             conversion_rate=excluded.conversion_rate, updated_at=CURRENT_TIMESTAMP''',
                        (staff.id, stat_date, category or 'default', powder, reply_rate,
                         reg, training, withdrawal, new_order, conversion)
                    )
                    await db.commit()
                count += 1
            except Exception as e:
                logger.debug(f'import_performance_sheet row {i}: {e}')
            await asyncio.sleep(0)

        logger.info(f'import_performance_sheet: {count} rows')
        return count

    async def import_from_sheets(self) -> Dict[str, int]:
        """Full import: Sheets → V2 DB. Returns counts per sheet."""
        await self._ensure_sheet_row_column()
        results: Dict[str, int] = {}

        # 1. Frontdesk sheets → clients + pipeline + role assignments
        for name in FRONTDESK_NAMES:
            try:
                results[name] = await self.import_client_sheet(name)
            except Exception as e:
                logger.error(f'import_from_sheets: {name} failed: {e}')
                results[name] = 0
            await asyncio.sleep(0.5)  # rate limit between sheets

        # 2. 维护数据 → deposits + knives + pipeline + roles + cross-role notes
        try:
            results['维护数据'] = await self.import_financial_sheet()
        except Exception as e:
            logger.error(f'import_from_sheets: 维护数据 failed: {e}')
            results['维护数据'] = 0

        # 3. 前台数据 → daily_performance (for Group Overview)
        try:
            results['前台数据'] = await self.import_performance_sheet()
        except Exception as e:
            logger.error(f'import_from_sheets: 前台数据 failed: {e}')
            results['前台数据'] = 0

        return results

    # ─── Direction 2: V2 DB → Sheets ─────────────────────────────────────────

    async def export_client_to_sheet(self, client_id: int):
        """Push one client's current status back to their Google Sheet row."""
        client = await database_v2.get_client_by_id(client_id)
        if not client:
            return

        staff = await database_v2.get_staff_by_id(client.frontdesk_id)
        if not staff or staff.display_name not in FRONTDESK_SHEETS:
            return

        first_day, second_day = _map_status_to_days(client.status)
        condition = client.status_note or ''
        loop = asyncio.get_event_loop()

        # Fetch sheet_row from DB (may not be on the dataclass if column added post-init)
        sheet_row = getattr(client, 'sheet_row', None)
        if sheet_row is None:
            async with database_v2.get_connection() as db:
                cur = await db.execute(
                    'SELECT sheet_row FROM clients WHERE id=?', (client_id,)
                )
                row = await cur.fetchone()
                sheet_row = row['sheet_row'] if row and row['sheet_row'] else None

        if sheet_row:
            await loop.run_in_executor(
                None,
                lambda: self.writer.update_client_status(
                    staff.display_name, sheet_row, first_day, second_day, condition
                )
            )
            logger.info(f'export_client_to_sheet: {client.phone} → row {sheet_row}')
        else:
            # Append new row
            record = {
                'date': datetime.now().strftime('%-m月%-d日'),
                'phone_remark': client.phone_remark or '',
                'frontdesk': staff.display_name,
                'category': client.source,
                'recruiter': client.recruiter or '',
                'frontdesk_number': staff.phone or '',
                'frontdesk_username': client.nickname or '',
                'client_number': client.phone,
                'account_id': client.account_id or '',
                'first_day': first_day,
                'second_day': second_day,
                'client_condition': condition,
            }
            ok = await loop.run_in_executor(
                None,
                lambda: self.writer.append_client_record(staff.display_name, record)
            )
            if ok:
                # Read back to locate the row we just appended
                rows: List[Dict] = await loop.run_in_executor(
                    None, lambda: self.writer.read_client_sheet(staff.display_name)
                )
                for row in reversed(rows):
                    if row.get('client_number') == client.phone:
                        async with database_v2.get_connection() as db:
                            await db.execute(
                                'UPDATE clients SET sheet_row=? WHERE id=?',
                                (row['row_index'], client_id)
                            )
                            await db.commit()
                        logger.info(
                            f'export_client_to_sheet: appended {client.phone} → row {row["row_index"]}'
                        )
                        break

    async def export_all_to_sheets(self) -> Dict[str, int]:
        """Full export: V2 DB → Sheets for all frontdesk clients."""
        # Skip export if we already know the service account is read-only
        if getattr(self, '_sheets_readonly', False):
            return {}

        results: Dict[str, int] = {}
        all_staff = await database_v2.get_all_staff(active_only=False)

        for staff in all_staff:
            if staff.display_name not in FRONTDESK_SHEETS:
                continue
            exported = 0
            try:
                clients = await database_v2.get_clients_by_frontdesk(staff.id, limit=500)
                for client in clients:
                    try:
                        await self.export_client_to_sheet(client.id)
                        exported += 1
                        await asyncio.sleep(0.5)  # rate limit
                    except Exception as e:
                        if '403' in str(e) or 'permission' in str(e).lower():
                            logger.warning('SheetSyncV2: service account has read-only access — '
                                           'export disabled (NocoDB is primary)')
                            self._sheets_readonly = True
                            return results
                        logger.error(f'export_all_to_sheets client {client.id}: {e}')
            except Exception as e:
                logger.error(f'export_all_to_sheets {staff.display_name}: {e}')
            results[staff.display_name] = exported

        return results

    # ─── Full bidirectional sync ──────────────────────────────────────────────

    async def full_sync(self) -> Dict[str, Any]:
        """Import then export. Returns combined stats."""
        logger.info('SheetSyncV2: full_sync start')
        imported = await self.import_from_sheets()
        exported = await self.export_all_to_sheets()
        stats = {
            'imported': imported,
            'exported': exported,
            'total_imported': sum(imported.values()),
            'total_exported': sum(exported.values()),
            'timestamp': datetime.now().isoformat(),
        }
        logger.info(
            f'SheetSyncV2: full_sync done — '
            f'{stats["total_imported"]} imported, {stats["total_exported"]} exported'
        )
        return stats
