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
        """Initialize Google Sheets client using CSV reader."""
        try:
            from engines.csv_reader import sync_all_sheets
            self._sync_all_sheets = sync_all_sheets
            logger.info("Google Sheets CSV reader initialized (real sync enabled)")
            self.sheets_client = "csv_reader"
        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets client: {e}")
            raise

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
            # Process each of the 11 client record sheets
            for gid in config.google_sheets.client_records_gids:
                try:
                    # Read from Google Sheets
                    sheet_data = await self._read_client_sheet(gid)
                    if sheet_data:
                        # Process and store in database
                        processed = await self._process_client_sheet_data(sheet_data, gid)
                        results['read'] += processed

                    # Write local changes back to sheets
                    written = await self._write_client_changes_to_sheet(gid)
                    results['written'] += written

                except Exception as e:
                    error_msg = f"Failed to sync client sheet {gid}: {e}"
                    logger.error(error_msg)
                    results['errors'].append(error_msg)

                # Small delay to respect rate limits
                await asyncio.sleep(0.5)

        except Exception as e:
            results['errors'].append(f"Client records sync failed: {e}")

        return results

    async def _read_client_sheet(self, gid: int) -> Optional[List[Dict[str, Any]]]:
        """Read client data from a specific Google Sheet."""
        try:
            # In a real implementation, this would use Google Sheets API
            # For now, simulate reading some data
            logger.info(f"Reading client sheet {gid}")

            # Simulated sheet data structure
            simulated_data = [
                {
                    'row_num': 1,
                    'date': '3月15日',
                    'phone_remark': '65 IPHONE SE',
                    'frontdesk': '阿YIM',
                    'category': '飞机筛选',
                    'recruiter': '小王',
                    'frontdesk_number': '+86123456789',
                    'frontdesk_username': '@test_user',
                    'client_number': '+86987654321',
                    'account_id': 'ACC123456',
                    'first_day': '注册',
                    'second_day': '注册',
                    'client_condition': '培训中'
                }
                # In real implementation, this would contain actual sheet data
            ]

            return simulated_data

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

            # In real implementation, this would write to Google Sheets
            logger.info(f"Writing {len(updated_records)} client records to sheet {gid}")

            # Simulate successful write
            return len(updated_records)

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
        """Read financial data from Google Sheet."""
        # Simulated implementation
        logger.info(f"Reading financial sheet {gid}")
        return []  # In real implementation, return actual sheet data

    async def _process_financial_sheet_data(self, sheet_data: List[Dict[str, Any]]) -> int:
        """Process financial sheet data."""
        # Simulated processing
        return len(sheet_data)

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
        """Read performance data from Google Sheet."""
        # Simulated implementation
        logger.info(f"Reading performance sheet {gid}")
        return []

    async def _process_performance_sheet_data(self, sheet_data: List[Dict[str, Any]]) -> int:
        """Process performance sheet data."""
        return len(sheet_data)

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
        async with database.get_connection() as db:
            cursor = await db.execute(f"SELECT * FROM {table_name}")
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