"""Bidirectional Google Sheets ↔ V2 DB sync engine."""
import asyncio
import hashlib
import logging
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple

from engines.gsheet_writer import GSheetWriter, FRONTDESK_SHEETS, SHEET_MAP
from database_v2 import database_v2
from models_v2 import Client, ClientStatus, Deposit, Staff, StaffRole

# Module-level singleton — initialized by main.py
sheet_sync_v2: Optional['SheetSyncV2'] = None

logger = logging.getLogger(__name__)

FRONTDESK_NAMES = list(FRONTDESK_SHEETS.keys())


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
        """Upsert a single sheet row into V2 clients table."""
        phone = row.get('client_number', '').strip()
        if not phone:
            return False

        status = _map_days_to_status(
            row.get('first_day', ''), row.get('second_day', '')
        )
        account_id = row.get('account_id', '').strip() or None
        phone_remark = row.get('phone_remark', '').strip() or None
        nickname = row.get('frontdesk_username', '').strip() or None
        source = row.get('category', '').strip() or ''
        recruiter = row.get('recruiter', '').strip() or None
        status_note = row.get('client_condition', '').strip() or None
        row_index = row.get('row_index')

        existing = await database_v2.get_client_by_phone(phone, frontdesk_id)
        if existing:
            async with database_v2.get_connection() as db:
                await db.execute(
                    """UPDATE clients
                       SET status=?, status_note=?, account_id=?, phone_remark=?,
                           nickname=?, source=?, recruiter=?, sheet_gid=?, sheet_row=?,
                           updated_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (status.value, status_note, account_id, phone_remark,
                     nickname, source, recruiter, sheet_gid, row_index, existing.id)
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
                    'UPDATE clients SET sheet_row=? WHERE id=?',
                    (row_index, client_id)
                )
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

    async def import_financial_sheet(self) -> int:
        """Import 维护数据 sheet into V2 deposits table. Returns count imported."""
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
        for i, row in enumerate(all_rows[1:], start=2):  # skip header row
            if len(row) < 8 or not row[0].strip():
                continue
            if row[0].strip() in ('X月XX日', '日期', 'DATE'):
                continue
            try:
                frontdesk_name = row[3].strip() if len(row) > 3 else ''
                account_id = row[1].strip() if len(row) > 1 else ''

                if not frontdesk_name:
                    continue

                staff = await database_v2.get_staff_by_display_name(frontdesk_name)
                if not staff:
                    continue

                # Match client by frontdesk + account_id
                client = None
                if account_id:
                    async with database_v2.get_connection() as db:
                        cur = await db.execute(
                            'SELECT * FROM clients WHERE frontdesk_id=? AND account_id=? LIMIT 1',
                            (staff.id, account_id)
                        )
                        row_data = await cur.fetchone()
                        if row_data:
                            client = database_v2._row_to_client(row_data)

                if not client:
                    continue

                # Parse date
                date_str = row[0].strip()
                try:
                    deposit_date = datetime.strptime(date_str, '%m/%d/%Y').date()
                except ValueError:
                    try:
                        deposit_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    except ValueError:
                        deposit_date = date.today()

                # total_in is column S (index 18)
                total_str = row[18].strip() if len(row) > 18 else ''
                total = _parse_money(total_str)
                if total == 0.0:
                    continue

                deposit = Deposit(
                    client_id=client.id,
                    frontdesk_id=staff.id,
                    amount=total,
                    deposit_date=deposit_date,
                    platform=row[6].strip() if len(row) > 6 else 'Iconnect',
                    note=row[9].strip() if len(row) > 9 else None,
                )
                await database_v2.create_deposit(deposit)
                count += 1
            except Exception as e:
                logger.error(f'import_financial_sheet row {i}: {e}')
            await asyncio.sleep(0)

        logger.info(f'import_financial_sheet: {count} deposits imported')
        return count

    async def import_from_sheets(self) -> Dict[str, int]:
        """Full import: Sheets → V2 DB. Returns counts per sheet."""
        await self._ensure_sheet_row_column()
        results: Dict[str, int] = {}

        for name in FRONTDESK_NAMES:
            try:
                results[name] = await self.import_client_sheet(name)
            except Exception as e:
                logger.error(f'import_from_sheets: {name} failed: {e}')
                results[name] = 0
            await asyncio.sleep(0.5)  # rate limit between sheets

        try:
            results['维护数据'] = await self.import_financial_sheet()
        except Exception as e:
            logger.error(f'import_from_sheets: 维护数据 failed: {e}')
            results['维护数据'] = 0

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
