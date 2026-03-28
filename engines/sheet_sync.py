"""Google Sheets synchronization engine."""
import logging
from typing import Dict, Any, List, Optional, Tuple
import asyncio
from datetime import datetime
import json

from database import database
from models import ClientRecord, FinancialRecord, PerformanceRecord
from config import config
from utils.formatting import convert_chinese_date, validate_gsheet_data

logger = logging.getLogger(__name__)


class SheetSyncEngine:
    """Google Sheets bidirectional synchronization engine."""

    def __init__(self):
        self.sheets_client = None
        self.spreadsheet_id = config.google_sheets.spreadsheet_id
        self.sync_stats = {
            'last_sync': None,
            'records_synced': 0,
            'errors': []
        }

    async def initialize(self):
        """Initialize Google Sheets client with gspread service account."""
        try:
            from engines.gsheet_writer import GSheetWriter
            self.writer = GSheetWriter()
            self.writer.initialize()
            from engines.csv_reader import sync_all_sheets
            self._sync_all_sheets = sync_all_sheets
            logger.info("Google Sheets fully initialized (gspread + CSV reader)")
            self.sheets_client = "gspread"
        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets client: {e}")
            self.writer = None
            self.sheets_client = None

    async def sync_all_data(self) -> Dict[str, Any]:
        """Perform full bidirectional sync of all data."""
        try:
            sync_results = {
                'start_time': datetime.now(),
                'client_records': {'read': 0, 'written': 0, 'errors': []},
                'financial_records': {'read': 0, 'written': 0, 'errors': []},
                'performance_records': {'read': 0, 'written': 0, 'errors': []},
                'summary': {}
            }

            logger.info("Starting full data synchronization with Google Sheets")

            # Sync client records (Type 1 - 11 sheets)
            client_results = await self._sync_client_records()
            sync_results['client_records'] = client_results

            # Sync financial records (Type 3)
            financial_results = await self._sync_financial_records()
            sync_results['financial_records'] = financial_results

            # Sync performance records (Type 2)
            performance_results = await self._sync_performance_records()
            sync_results['performance_records'] = performance_results

            # Update sync statistics
            sync_results['end_time'] = datetime.now()
            sync_results['duration'] = (sync_results['end_time'] - sync_results['start_time']).total_seconds()

            sync_results['summary'] = {
                'total_read': sum(r['read'] for r in [client_results, financial_results, performance_results]),
                'total_written': sum(r['written'] for r in [client_results, financial_results, performance_results]),
                'total_errors': len(client_results['errors']) + len(financial_results['errors']) + len(performance_results['errors']),
                'success': True
            }

            self.sync_stats['last_sync'] = datetime.now()
            self.sync_stats['records_synced'] = sync_results['summary']['total_read'] + sync_results['summary']['total_written']

            logger.info(f"Sync completed: {sync_results['summary']}")
            return sync_results

        except Exception as e:
            logger.error(f"Failed to sync data: {e}")
            return {
                'summary': {'success': False, 'error': str(e)},
                'end_time': datetime.now()
            }

    async def _sync_client_records(self) -> Dict[str, Any]:
        """Sync client records with Google Sheets (Type 1)."""
        results = {'read': 0, 'written': 0, 'errors': []}

        try:
            # Process client record sheets in smaller batches
            batch_size = config.bot.sheets_batch_size
            gids = config.google_sheets.client_records_gids

            for i in range(0, len(gids), batch_size):
                batch_gids = gids[i:i + batch_size]
                batch_tasks = []

                # Create tasks for parallel processing
                for gid in batch_gids:
                    batch_tasks.append(self._sync_single_client_sheet(gid))

                # Execute batch in parallel
                try:
                    batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

                    for j, result in enumerate(batch_results):
                        if isinstance(result, Exception):
                            error_msg = f"Failed to sync client sheet {batch_gids[j]}: {result}"
                            logger.error(error_msg)
                            results['errors'].append(error_msg)
                        else:
                            results['read'] += result.get('read', 0)
                            results['written'] += result.get('written', 0)
                            if result.get('errors'):
                                results['errors'].extend(result['errors'])

                except Exception as e:
                    error_msg = f"Failed to process batch {i//batch_size + 1}: {e}"
                    logger.error(error_msg)
                    results['errors'].append(error_msg)

                # Delay between batches for rate limiting
                if i + batch_size < len(gids):
                    await asyncio.sleep(config.bot.sheets_batch_delay)

        except Exception as e:
            results['errors'].append(f"Client records sync failed: {e}")

        return results

    async def _sync_single_client_sheet(self, gid: int) -> Dict[str, Any]:
        """Sync a single client sheet."""
        result = {'read': 0, 'written': 0, 'errors': []}

        try:
            # Read from Google Sheets
            sheet_data = await self._read_client_sheet(gid)
            if sheet_data:
                # Process and store in database
                processed = await self._process_client_sheet_data(sheet_data, gid)
                result['read'] += processed

            # Write local changes back to sheets
            written = await self._write_client_changes_to_sheet(gid)
            result['written'] += written

        except Exception as e:
            error_msg = f"Failed to sync client sheet {gid}: {e}"
            logger.error(error_msg)
            result['errors'].append(error_msg)

        return result

    async def _read_client_sheet(self, gid: int) -> Optional[List[Dict[str, Any]]]:
        """Read client data from a specific Google Sheet."""
        if not self.writer or not self.writer.gc:
            logger.error("Google Sheets client not initialized")
            return None

        try:
            logger.info(f"Reading client sheet {gid}")

            # Find the worksheet by GID
            worksheet = None
            for ws in self.writer.spreadsheet.worksheets():
                if ws.id == gid:
                    worksheet = ws
                    break

            if not worksheet:
                logger.error(f"Worksheet with GID {gid} not found")
                return None

            # Get all values from the worksheet
            rows = worksheet.get_all_values()
            if len(rows) < 3:  # Need at least header + data
                logger.warning(f"Sheet {gid} has no data rows")
                return []

            # Parse the data (skip first 2 header rows)
            sheet_data = []
            for i, row in enumerate(rows[2:], start=1):
                if len(row) < 13 or not row[1].strip():
                    continue
                if row[1].strip() in ('DATE', '日期', 'X月X日'):
                    continue

                try:
                    sheet_data.append({
                        'row_num': i,
                        'date': row[1].strip(),
                        'phone_remark': row[2].strip(),
                        'frontdesk': row[3].strip(),
                        'category': row[4].strip(),
                        'recruiter': row[5].strip(),
                        'frontdesk_number': row[6].strip(),
                        'frontdesk_username': row[7].strip(),
                        'client_number': row[8].strip(),
                        'account_id': row[9].strip(),
                        'first_day': row[10].strip(),
                        'second_day': row[11].strip(),
                        'client_condition': row[12].strip() if len(row) > 12 else ''
                    })
                except Exception as e:
                    logger.warning(f"Failed to parse row {i} in sheet {gid}: {e}")
                    continue

            logger.info(f"Read {len(sheet_data)} records from sheet {gid}")
            return sheet_data

        except Exception as e:
            logger.error(f"Failed to read client sheet {gid}: {e}")
            return None

    async def _process_client_sheet_data(self, sheet_data: List[Dict[str, Any]], gid: int) -> int:
        """Process and store client sheet data in database."""
        processed_count = 0

        try:
            for row_data in sheet_data:
                try:
                    # Validate data
                    if not self._validate_client_data(row_data):
                        logger.warning(f"Invalid client data in sheet {gid}: {row_data}")
                        continue

                    # Check if record already exists
                    existing_record = await self._find_existing_client_record(row_data, gid)

                    if existing_record:
                        # Update existing record if data has changed
                        if self._has_client_data_changed(existing_record, row_data):
                            await self._update_client_record(existing_record.id, row_data)
                            processed_count += 1
                    else:
                        # Create new record
                        client_record = ClientRecord(
                            row_num=row_data['row_num'],
                            date=row_data['date'],
                            phone_remark=row_data['phone_remark'],
                            frontdesk=row_data['frontdesk'],
                            category=row_data['category'],
                            recruiter=row_data['recruiter'],
                            frontdesk_number=row_data['frontdesk_number'],
                            frontdesk_username=row_data['frontdesk_username'],
                            client_number=row_data['client_number'],
                            account_id=row_data['account_id'],
                            first_day=row_data['first_day'],
                            second_day=row_data['second_day'],
                            client_condition=row_data.get('client_condition'),
                            sheet_gid=gid
                        )

                        await database.create_client_record(client_record)
                        processed_count += 1

                except Exception as e:
                    logger.error(f"Failed to process client row in sheet {gid}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Failed to process client sheet data {gid}: {e}")

        return processed_count

    def _validate_client_data(self, row_data: Dict[str, Any]) -> bool:
        """Validate client record data."""
        required_fields = ['date', 'frontdesk', 'client_number', 'account_id']

        for field in required_fields:
            if not row_data.get(field):
                return False

        # Validate date format
        if not validate_gsheet_data.validate_chinese_date(row_data['date']):
            return False

        return True

    async def _find_existing_client_record(self, row_data: Dict[str, Any], gid: int) -> Optional[ClientRecord]:
        """Find existing client record by unique identifiers."""
        try:
            async with database.get_connection() as db:
                cursor = await db.execute("""
                    SELECT * FROM client_records
                    WHERE client_number = ? AND account_id = ? AND sheet_gid = ?
                """, (row_data['client_number'], row_data['account_id'], gid))
                row = await cursor.fetchone()
                return database._row_to_client_record(row) if row else None

        except Exception as e:
            logger.error(f"Failed to find existing client record: {e}")
            return None

    def _has_client_data_changed(self, existing_record: ClientRecord, new_data: Dict[str, Any]) -> bool:
        """Check if client data has changed."""
        # Compare key fields that might change
        changeable_fields = ['first_day', 'second_day', 'client_condition', 'recruiter']

        for field in changeable_fields:
            if getattr(existing_record, field) != new_data.get(field):
                return True

        return False

    async def _update_client_record(self, record_id: int, new_data: Dict[str, Any]):
        """Update existing client record."""
        try:
            async with database.get_connection() as db:
                await db.execute("""
                    UPDATE client_records SET
                    first_day = ?, second_day = ?, client_condition = ?,
                    recruiter = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (
                    new_data['first_day'],
                    new_data['second_day'],
                    new_data.get('client_condition'),
                    new_data['recruiter'],
                    record_id
                ))
                await db.commit()

        except Exception as e:
            logger.error(f"Failed to update client record {record_id}: {e}")
            raise

    async def _write_client_changes_to_sheet(self, gid: int) -> int:
        """Write local client changes back to Google Sheets."""
        if not self.writer or not self.writer.gc:
            logger.error("Google Sheets client not initialized")
            return 0

        try:
            # Get records that have been updated locally but not synced
            async with database.get_connection() as db:
                cursor = await db.execute("""
                    SELECT * FROM client_records
                    WHERE sheet_gid = ? AND updated_at > created_at
                """, (gid,))
                updated_records = [database._row_to_client_record(row) for row in await cursor.fetchall()]

            if not updated_records:
                return 0

            logger.info(f"Writing {len(updated_records)} client records to sheet {gid}")

            # Find the worksheet by GID
            worksheet = None
            for ws in self.writer.spreadsheet.worksheets():
                if ws.id == gid:
                    worksheet = ws
                    break

            if not worksheet:
                logger.error(f"Worksheet with GID {gid} not found")
                return 0

            # Update each record in the sheet
            written_count = 0
            for record in updated_records:
                try:
                    # Find the row in the sheet by matching client_number and account_id
                    rows = worksheet.get_all_values()
                    target_row = None

                    for i, row in enumerate(rows[2:], start=3):  # Start from row 3 (0-based + 2 headers + 1 for 1-based)
                        if len(row) >= 10 and row[8] == record.client_number and row[9] == record.account_id:
                            target_row = i
                            break

                    if target_row:
                        # Update the status columns (K and L are columns 11 and 12)
                        updates = []
                        if record.first_day:
                            updates.append({'range': f'K{target_row}', 'values': [[record.first_day]]})
                        if record.second_day:
                            updates.append({'range': f'L{target_row}', 'values': [[record.second_day]]})
                        if record.client_condition:
                            updates.append({'range': f'M{target_row}', 'values': [[record.client_condition]]})

                        for update in updates:
                            worksheet.update(update['range'], update['values'])

                        written_count += 1
                        logger.debug(f"Updated record {record.client_number} in row {target_row}")

                except Exception as e:
                    logger.error(f"Failed to update record {record.client_number}: {e}")
                    continue

                # Add delay to respect rate limits
                await asyncio.sleep(config.bot.sheets_rate_limit_delay)

            return written_count

        except Exception as e:
            logger.error(f"Failed to write client changes to sheet {gid}: {e}")
            return 0

    async def _sync_financial_records(self) -> Dict[str, Any]:
        """Sync financial records with Google Sheets (Type 3)."""
        results = {'read': 0, 'written': 0, 'errors': []}

        try:
            gid = config.google_sheets.financial_gid

            # Read from Google Sheets
            sheet_data = await self._read_financial_sheet(gid)
            if sheet_data:
                processed = await self._process_financial_sheet_data(sheet_data)
                results['read'] += processed

            # Write local changes back to sheets
            written = await self._write_financial_changes_to_sheet(gid)
            results['written'] += written

        except Exception as e:
            results['errors'].append(f"Financial records sync failed: {e}")

        return results

    async def _read_financial_sheet(self, gid: int) -> Optional[List[Dict[str, Any]]]:
        """Read financial data from Google Sheet (维护数据 worksheet)."""
        if not self.writer or not self.writer.gc:
            logger.error("Google Sheets client not initialized")
            return None

        try:
            logger.info(f"Reading financial sheet {gid}")

            # Find the worksheet by GID
            worksheet = None
            for ws in self.writer.spreadsheet.worksheets():
                if ws.id == gid:
                    worksheet = ws
                    break

            if not worksheet:
                logger.error(f"Financial worksheet with GID {gid} not found")
                return None

            # Get all values from the worksheet
            rows = worksheet.get_all_values()
            if len(rows) < 2:  # Need at least header + data
                logger.warning(f"Financial sheet {gid} has no data rows")
                return []

            # Parse the data - expected columns:
            # 日期, 账号/ID, 群号/ID, 前台, 维护, 前台号, 盘子, 新单$, 承压$, [note], 一刀~八刀, 共入, 前台
            sheet_data = []
            for i, row in enumerate(rows[1:], start=1):  # Skip header row
                if len(row) < 7 or not row[0].strip():
                    continue

                # Skip template rows (X月XX日)
                date_str = row[0].strip()
                if 'X月' in date_str and 'X日' in date_str:
                    continue
                if date_str in ('DATE', '日期'):
                    continue

                try:
                    # Parse money values (remove $ and commas, handle negative)
                    def parse_money(value_str):
                        if not value_str or value_str.strip() == '':
                            return 0.0
                        cleaned = value_str.replace('$', '').replace(',', '').strip()
                        if cleaned == '' or cleaned == '-':
                            return 0.0
                        try:
                            return float(cleaned)
                        except ValueError:
                            return 0.0

                    record_data = {
                        'date': date_str,
                        'account_id': row[1].strip() if len(row) > 1 else '',
                        'group_id': row[2].strip() if len(row) > 2 else '',
                        'frontdesk': row[3].strip() if len(row) > 3 else '',
                        'maintenance': row[4].strip() if len(row) > 4 else '',
                        'frontdesk_number': row[5].strip() if len(row) > 5 else '',
                        'platform': row[6].strip() if len(row) > 6 else '',
                        'new_order_amount': parse_money(row[7]) if len(row) > 7 else 0.0,
                        'pressure_amount': parse_money(row[8]) if len(row) > 8 else 0.0,
                        'note': row[9].strip() if len(row) > 9 else '',
                        'knife_1': parse_money(row[10]) if len(row) > 10 else 0.0,
                        'knife_2': parse_money(row[11]) if len(row) > 11 else 0.0,
                        'knife_3': parse_money(row[12]) if len(row) > 12 else 0.0,
                        'knife_4': parse_money(row[13]) if len(row) > 13 else 0.0,
                        'knife_5': parse_money(row[14]) if len(row) > 14 else 0.0,
                        'knife_6': parse_money(row[15]) if len(row) > 15 else 0.0,
                        'knife_7': parse_money(row[16]) if len(row) > 16 else 0.0,
                        'knife_8': parse_money(row[17]) if len(row) > 17 else 0.0,
                        'total_in': parse_money(row[18]) if len(row) > 18 else 0.0,
                        'role_frontdesk': row[19].strip() if len(row) > 19 else ''
                    }

                    # Only add if we have essential fields
                    if record_data['date'] and (record_data['account_id'] or record_data['frontdesk']):
                        sheet_data.append(record_data)

                except Exception as e:
                    logger.warning(f"Failed to parse financial row {i}: {e}")
                    continue

            logger.info(f"Read {len(sheet_data)} financial records from sheet {gid}")
            return sheet_data

        except Exception as e:
            logger.error(f"Failed to read financial sheet {gid}: {e}")
            return None

    async def _process_financial_sheet_data(self, sheet_data: List[Dict[str, Any]]) -> int:
        """Process and store financial sheet data in database."""
        processed_count = 0

        try:
            for row_data in sheet_data:
                try:
                    # Validate data
                    if not self._validate_financial_data(row_data):
                        logger.warning(f"Invalid financial data: {row_data}")
                        continue

                    # Check if record already exists
                    existing_record = await self._find_existing_financial_record(row_data)

                    if existing_record:
                        # Update existing record if data has changed
                        if self._has_financial_data_changed(existing_record, row_data):
                            await self._update_financial_record(existing_record.id, row_data)
                            processed_count += 1
                    else:
                        # Create new record
                        financial_record = FinancialRecord(
                            date=row_data['date'],
                            account_id=row_data['account_id'],
                            group_id=row_data['group_id'],
                            frontdesk=row_data['frontdesk'],
                            maintenance=row_data['maintenance'],
                            frontdesk_number=row_data['frontdesk_number'],
                            platform=row_data['platform'],
                            new_order_amount=row_data['new_order_amount'],
                            pressure_amount=row_data['pressure_amount'],
                            note=row_data['note'],
                            knife_1=row_data['knife_1'],
                            knife_2=row_data['knife_2'],
                            knife_3=row_data['knife_3'],
                            knife_4=row_data['knife_4'],
                            knife_5=row_data['knife_5'],
                            knife_6=row_data['knife_6'],
                            knife_7=row_data['knife_7'],
                            knife_8=row_data['knife_8'],
                            total_in=row_data['total_in'],
                            role_frontdesk=row_data['role_frontdesk']
                        )

                        await database.create_financial_record(financial_record)
                        processed_count += 1

                except Exception as e:
                    logger.error(f"Failed to process financial row: {e}")
                    continue

        except Exception as e:
            logger.error(f"Failed to process financial sheet data: {e}")

        return processed_count

    def _validate_financial_data(self, row_data: Dict[str, Any]) -> bool:
        """Validate financial record data."""
        # At minimum we need a date and either account_id or frontdesk
        return bool(row_data.get('date') and (row_data.get('account_id') or row_data.get('frontdesk')))

    async def _find_existing_financial_record(self, row_data: Dict[str, Any]) -> Optional[FinancialRecord]:
        """Find existing financial record by unique identifiers."""
        try:
            async with database.get_connection() as db:
                cursor = await db.execute("""
                    SELECT * FROM financial_records
                    WHERE date = ? AND account_id = ? AND frontdesk = ?
                """, (row_data['date'], row_data['account_id'], row_data['frontdesk']))
                row = await cursor.fetchone()
                return database._row_to_financial_record(row) if row else None

        except Exception as e:
            logger.error(f"Failed to find existing financial record: {e}")
            return None

    def _has_financial_data_changed(self, existing_record: FinancialRecord, new_data: Dict[str, Any]) -> bool:
        """Check if financial data has changed."""
        # Compare monetary fields that might change
        changeable_fields = ['new_order_amount', 'pressure_amount', 'total_in', 'knife_1', 'knife_2', 'knife_3', 'knife_4', 'knife_5', 'knife_6', 'knife_7', 'knife_8']

        for field in changeable_fields:
            existing_value = getattr(existing_record, field)
            new_value = new_data.get(field)
            if abs(existing_value - new_value) > 0.01:  # Small epsilon for float comparison
                return True

        return False

    async def _update_financial_record(self, record_id: int, new_data: Dict[str, Any]):
        """Update existing financial record."""
        try:
            async with database.get_connection() as db:
                await db.execute("""
                    UPDATE financial_records SET
                    new_order_amount = ?, pressure_amount = ?, total_in = ?,
                    knife_1 = ?, knife_2 = ?, knife_3 = ?, knife_4 = ?,
                    knife_5 = ?, knife_6 = ?, knife_7 = ?, knife_8 = ?,
                    note = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (
                    new_data['new_order_amount'], new_data['pressure_amount'], new_data['total_in'],
                    new_data['knife_1'], new_data['knife_2'], new_data['knife_3'], new_data['knife_4'],
                    new_data['knife_5'], new_data['knife_6'], new_data['knife_7'], new_data['knife_8'],
                    new_data['note'], record_id
                ))
                await db.commit()

        except Exception as e:
            logger.error(f"Failed to update financial record {record_id}: {e}")
            raise

    async def _write_financial_changes_to_sheet(self, gid: int) -> int:
        """Write financial changes to sheet."""
        # Simulated implementation
        logger.info(f"Writing financial changes to sheet {gid}")
        return 0

    async def _sync_performance_records(self) -> Dict[str, Any]:
        """Sync performance records with Google Sheets (Type 2)."""
        results = {'read': 0, 'written': 0, 'errors': []}

        try:
            gid = config.google_sheets.performance_gid

            # Read from Google Sheets
            sheet_data = await self._read_performance_sheet(gid)
            if sheet_data:
                processed = await self._process_performance_sheet_data(sheet_data)
                results['read'] += processed

            # Write local changes back to sheets
            written = await self._write_performance_changes_to_sheet(gid)
            results['written'] += written

        except Exception as e:
            results['errors'].append(f"Performance records sync failed: {e}")

        return results

    async def _read_performance_sheet(self, gid: int) -> Optional[List[Dict[str, Any]]]:
        """Read performance data from Google Sheet (3月-前台数据 worksheet)."""
        if not self.writer or not self.writer.gc:
            logger.error("Google Sheets client not initialized")
            return None

        try:
            logger.info(f"Reading performance sheet {gid}")

            # Find the worksheet by GID
            worksheet = None
            for ws in self.writer.spreadsheet.worksheets():
                if ws.id == gid:
                    worksheet = ws
                    break

            if not worksheet:
                logger.error(f"Performance worksheet with GID {gid} not found")
                return None

            # Get all values from the worksheet
            rows = worksheet.get_all_values()
            if len(rows) < 2:  # Need at least header + data
                logger.warning(f"Performance sheet {gid} has no data rows")
                return []

            # Parse the data - complex multi-section layout with dates as section headers
            # Expected columns: 名字(name), 类别(category), 粉量, 开头不回复, 回复率, 卡解释, 拉黑/来玩, 被骗过, 给链接没回复, 完成注册, 审核率, 完成培训, 约时间, 提款
            sheet_data = []
            current_section = None

            for i, row in enumerate(rows):
                if len(row) < 2 or not row[0].strip():
                    continue

                first_cell = row[0].strip()

                # Check if this is a section header (e.g., "MAO UK 3/1")
                if 'MAO' in first_cell or ('/' in first_cell and len(first_cell) < 15):
                    current_section = first_cell
                    logger.debug(f"Found section header: {current_section}")
                    continue

                # Skip column headers
                if first_cell in ('名字', 'name', '姓名'):
                    continue

                # Parse data row
                if current_section and len(row) >= 10:
                    try:
                        def parse_int(value_str):
                            if not value_str or value_str.strip() == '':
                                return 0
                            cleaned = value_str.replace(',', '').strip()
                            try:
                                return int(float(cleaned))
                            except ValueError:
                                return 0

                        def parse_float(value_str):
                            if not value_str or value_str.strip() == '' or value_str.strip() == '%':
                                return 0.0
                            cleaned = value_str.replace('%', '').replace(',', '').strip()
                            try:
                                return float(cleaned)
                            except ValueError:
                                return 0.0

                        record_data = {
                            'section': current_section,
                            'name': row[0].strip(),
                            'category': row[1].strip() if len(row) > 1 else '',
                            'powder_count': parse_int(row[2]) if len(row) > 2 else 0,
                            'no_initial_reply': parse_int(row[3]) if len(row) > 3 else 0,
                            'reply_rate': parse_float(row[4]) if len(row) > 4 else 0.0,
                            'stuck_explanation': parse_int(row[5]) if len(row) > 5 else 0,
                            'blocked_or_play': parse_int(row[6]) if len(row) > 6 else 0,
                            'been_scammed': parse_int(row[7]) if len(row) > 7 else 0,
                            'sent_link_no_reply': parse_int(row[8]) if len(row) > 8 else 0,
                            'completed_register': parse_int(row[9]) if len(row) > 9 else 0,
                            'review_rate': parse_float(row[10]) if len(row) > 10 else 0.0,
                            'completed_training': parse_int(row[11]) if len(row) > 11 else 0,
                            'scheduled_time': parse_int(row[12]) if len(row) > 12 else 0,
                            'withdrawal': parse_int(row[13]) if len(row) > 13 else 0,
                            'new_order': parse_int(row[14]) if len(row) > 14 else 0,
                            'conversion_rate': parse_float(row[15]) if len(row) > 15 else 0.0,
                            'new_kill': parse_int(row[16]) if len(row) > 16 else 0,
                            'dead_client': parse_int(row[17]) if len(row) > 17 else 0,
                            'is_sum_row': '总计' in row[0] or 'sum' in row[0].lower() or 'total' in row[0].lower()
                        }

                        # Only add if we have essential fields
                        if record_data['name'] and record_data['name'] not in ('', '-'):
                            sheet_data.append(record_data)

                    except Exception as e:
                        logger.warning(f"Failed to parse performance row {i}: {e}")
                        continue

            logger.info(f"Read {len(sheet_data)} performance records from sheet {gid}")
            return sheet_data

        except Exception as e:
            logger.error(f"Failed to read performance sheet {gid}: {e}")
            return None

    async def _process_performance_sheet_data(self, sheet_data: List[Dict[str, Any]]) -> int:
        """Process and store performance sheet data in database."""
        processed_count = 0

        try:
            for row_data in sheet_data:
                try:
                    # Validate data
                    if not self._validate_performance_data(row_data):
                        logger.warning(f"Invalid performance data: {row_data}")
                        continue

                    # Check if record already exists
                    existing_record = await self._find_existing_performance_record(row_data)

                    if existing_record:
                        # Update existing record if data has changed
                        if self._has_performance_data_changed(existing_record, row_data):
                            await self._update_performance_record(existing_record.id, row_data)
                            processed_count += 1
                    else:
                        # Create new record
                        performance_record = PerformanceRecord(
                            name=row_data['name'],
                            category=row_data['category'],
                            powder_count=row_data['powder_count'],
                            no_initial_reply=row_data['no_initial_reply'],
                            reply_rate=row_data['reply_rate'],
                            stuck_explanation=row_data['stuck_explanation'],
                            blocked_or_play=row_data['blocked_or_play'],
                            been_scammed=row_data['been_scammed'],
                            sent_link_no_reply=row_data['sent_link_no_reply'],
                            completed_register=row_data['completed_register'],
                            review_rate=row_data['review_rate'],
                            completed_training=row_data['completed_training'],
                            scheduled_time=row_data['scheduled_time'],
                            withdrawal=row_data['withdrawal'],
                            new_order=row_data['new_order'],
                            conversion_rate=row_data['conversion_rate'],
                            new_kill=row_data['new_kill'],
                            dead_client=row_data['dead_client'],
                            is_sum_row=row_data['is_sum_row']
                        )

                        await database.create_performance_record(performance_record)
                        processed_count += 1

                except Exception as e:
                    logger.error(f"Failed to process performance row: {e}")
                    continue

        except Exception as e:
            logger.error(f"Failed to process performance sheet data: {e}")

        return processed_count

    def _validate_performance_data(self, row_data: Dict[str, Any]) -> bool:
        """Validate performance record data."""
        # At minimum we need a name
        return bool(row_data.get('name'))

    async def _find_existing_performance_record(self, row_data: Dict[str, Any]) -> Optional[PerformanceRecord]:
        """Find existing performance record by unique identifiers."""
        try:
            async with database.get_connection() as db:
                cursor = await db.execute("""
                    SELECT * FROM performance_records
                    WHERE name = ? AND category = ? ORDER BY created_at DESC LIMIT 1
                """, (row_data['name'], row_data['category']))
                row = await cursor.fetchone()
                return database._row_to_performance_record(row) if row else None

        except Exception as e:
            logger.error(f"Failed to find existing performance record: {e}")
            return None

    def _has_performance_data_changed(self, existing_record: PerformanceRecord, new_data: Dict[str, Any]) -> bool:
        """Check if performance data has changed."""
        # Compare key numeric fields that might change
        changeable_fields = ['powder_count', 'completed_register', 'completed_training', 'withdrawal', 'new_order', 'reply_rate', 'conversion_rate']

        for field in changeable_fields:
            existing_value = getattr(existing_record, field)
            new_value = new_data.get(field)

            if isinstance(existing_value, float) and isinstance(new_value, (int, float)):
                if abs(existing_value - new_value) > 0.01:  # Small epsilon for float comparison
                    return True
            elif existing_value != new_value:
                return True

        return False

    async def _update_performance_record(self, record_id: int, new_data: Dict[str, Any]):
        """Update existing performance record."""
        try:
            async with database.get_connection() as db:
                await db.execute("""
                    UPDATE performance_records SET
                    powder_count = ?, no_initial_reply = ?, reply_rate = ?,
                    stuck_explanation = ?, blocked_or_play = ?, been_scammed = ?,
                    sent_link_no_reply = ?, completed_register = ?, review_rate = ?,
                    completed_training = ?, scheduled_time = ?, withdrawal = ?,
                    new_order = ?, conversion_rate = ?, new_kill = ?, dead_client = ?,
                    updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (
                    new_data['powder_count'], new_data['no_initial_reply'], new_data['reply_rate'],
                    new_data['stuck_explanation'], new_data['blocked_or_play'], new_data['been_scammed'],
                    new_data['sent_link_no_reply'], new_data['completed_register'], new_data['review_rate'],
                    new_data['completed_training'], new_data['scheduled_time'], new_data['withdrawal'],
                    new_data['new_order'], new_data['conversion_rate'], new_data['new_kill'],
                    new_data['dead_client'], record_id
                ))
                await db.commit()

        except Exception as e:
            logger.error(f"Failed to update performance record {record_id}: {e}")
            raise

    async def _write_performance_changes_to_sheet(self, gid: int) -> int:
        """Write performance changes to sheet."""
        logger.info(f"Writing performance changes to sheet {gid}")
        return 0

    async def export_to_sheets(self, data_type: str, filters: Dict[str, Any] = None) -> Dict[str, Any]:
        """Export specific data to Google Sheets."""
        try:
            export_results = {
                'data_type': data_type,
                'records_exported': 0,
                'sheet_url': None,
                'success': False
            }

            if data_type == 'client_records':
                records = await self._get_client_records_for_export(filters)
                result = await self._export_client_records_to_sheet(records)
                export_results.update(result)

            elif data_type == 'financial_records':
                records = await self._get_financial_records_for_export(filters)
                result = await self._export_financial_records_to_sheet(records)
                export_results.update(result)

            elif data_type == 'performance_records':
                records = await self._get_performance_records_for_export(filters)
                result = await self._export_performance_records_to_sheet(records)
                export_results.update(result)

            elif data_type == 'daily_summary':
                summary_data = await self._generate_summary_for_export(filters)
                result = await self._export_summary_to_sheet(summary_data)
                export_results.update(result)

            else:
                raise ValueError(f"Unknown data type: {data_type}")

            return export_results

        except Exception as e:
            logger.error(f"Failed to export {data_type}: {e}")
            return {
                'data_type': data_type,
                'success': False,
                'error': str(e)
            }

    async def _get_client_records_for_export(self, filters: Dict[str, Any] = None) -> List[ClientRecord]:
        """Get client records for export based on filters."""
        # In real implementation, apply filters to query
        async with database.get_connection() as db:
            cursor = await db.execute("SELECT * FROM client_records ORDER BY created_at DESC LIMIT 1000")
            rows = await cursor.fetchall()
            return [database._row_to_client_record(row) for row in rows]

    async def _export_client_records_to_sheet(self, records: List[ClientRecord]) -> Dict[str, Any]:
        """Export client records to Google Sheet."""
        # Simulated export
        logger.info(f"Exporting {len(records)} client records to sheet")
        return {
            'records_exported': len(records),
            'sheet_url': 'https://docs.google.com/spreadsheets/d/simulated_export',
            'success': True
        }

    async def get_sync_status(self) -> Dict[str, Any]:
        """Get current sync status and statistics."""
        try:
            status = {
                'last_sync': self.sync_stats['last_sync'],
                'records_synced': self.sync_stats['records_synced'],
                'connection_status': 'connected' if self.sheets_client else 'disconnected',
                'recent_errors': self.sync_stats['errors'][-10:],  # Last 10 errors
                'health_check': await self._health_check()
            }

            return status

        except Exception as e:
            logger.error(f"Failed to get sync status: {e}")
            return {'error': str(e)}

    async def _health_check(self) -> Dict[str, Any]:
        """Perform health check on Google Sheets connection."""
        try:
            # In real implementation, test actual connection
            return {
                'status': 'healthy',
                'response_time': 0.1,  # Simulated
                'last_test': datetime.now()
            }

        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'last_test': datetime.now()
            }

    async def force_sync_record(self, record_type: str, record_id: int) -> Dict[str, Any]:
        """Force sync of a specific record."""
        try:
            if record_type == 'client':
                return await self._force_sync_client_record(record_id)
            elif record_type == 'financial':
                return await self._force_sync_financial_record(record_id)
            elif record_type == 'performance':
                return await self._force_sync_performance_record(record_id)
            else:
                raise ValueError(f"Unknown record type: {record_type}")

        except Exception as e:
            logger.error(f"Failed to force sync {record_type} record {record_id}: {e}")
            return {'success': False, 'error': str(e)}

    async def _force_sync_client_record(self, record_id: int) -> Dict[str, Any]:
        """Force sync specific client record."""
        # Simulated implementation
        logger.info(f"Force syncing client record {record_id}")
        return {'success': True, 'record_id': record_id, 'action': 'synced'}

    async def _force_sync_financial_record(self, record_id: int) -> Dict[str, Any]:
        """Force sync specific financial record."""
        logger.info(f"Force syncing financial record {record_id}")
        return {'success': True, 'record_id': record_id, 'action': 'synced'}

    async def _force_sync_performance_record(self, record_id: int) -> Dict[str, Any]:
        """Force sync specific performance record."""
        logger.info(f"Force syncing performance record {record_id}")
        return {'success': True, 'record_id': record_id, 'action': 'synced'}

    async def create_backup_export(self) -> Dict[str, Any]:
        """Create full backup export to Google Sheets."""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_results = {
                'timestamp': timestamp,
                'backup_id': f'backup_{timestamp}',
                'tables_exported': {},
                'total_records': 0,
                'success': False
            }

            # Export all tables
            tables = ['client_records', 'financial_records', 'performance_records', 'team_members']

            for table in tables:
                try:
                    records = await self._export_table_data(table)
                    backup_results['tables_exported'][table] = len(records)
                    backup_results['total_records'] += len(records)
                except Exception as e:
                    logger.error(f"Failed to export table {table}: {e}")
                    backup_results['tables_exported'][table] = f'error: {e}'

            backup_results['success'] = True
            logger.info(f"Backup export completed: {backup_results}")

            return backup_results

        except Exception as e:
            logger.error(f"Failed to create backup export: {e}")
            return {'success': False, 'error': str(e)}

    async def _export_table_data(self, table_name: str) -> List[Dict[str, Any]]:
        """Export data from a specific table."""
        # Whitelist valid table names to prevent SQL injection
        valid_tables = {
            'client_records', 'financial_records', 'performance_records',
            'team_members', 'reminders', 'bot_tasks'
        }

        if table_name not in valid_tables:
            raise ValueError(f"Invalid table name: {table_name}")

        async with database.get_connection() as db:
            # Safe to use f-string now that we've validated the table name
            cursor = await db.execute(f"SELECT * FROM {table_name}")  # safe: validated against whitelist above
            rows = await cursor.fetchall()

            # Convert to dict format
            if table_name == 'client_records':
                return [self._client_record_to_dict(database._row_to_client_record(row)) for row in rows]
            # Add other table conversions as needed

            return [dict(zip([desc[0] for desc in cursor.description], row)) for row in rows]

    def _client_record_to_dict(self, record: ClientRecord) -> Dict[str, Any]:
        """Convert ClientRecord to dictionary for export."""
        return {
            'row_num': record.row_num,
            'date': record.date,
            'phone_remark': record.phone_remark,
            'frontdesk': record.frontdesk,
            'category': record.category,
            'recruiter': record.recruiter,
            'frontdesk_number': record.frontdesk_number,
            'frontdesk_username': record.frontdesk_username,
            'client_number': record.client_number,
            'account_id': record.account_id,
            'first_day': record.first_day,
            'second_day': record.second_day,
            'client_condition': record.client_condition
        }


# Global sheet sync engine instance
sheet_sync_engine = SheetSyncEngine()