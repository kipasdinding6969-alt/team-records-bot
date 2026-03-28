"""Reminder engine for automated reminder processing."""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import asyncio

from database import database
from models import Reminder, BotTask, ClientRecord
from telegram_handler import telegram_handler
from config import config
from i18n import t


async def _get_lang(user_id):
    from database import database
    return (await database.get_user_language(user_id)) or 'zh'

logger = logging.getLogger(__name__)


class ReminderEngine:
    """Automated reminder processing engine."""

    def __init__(self):
        self.reminder_templates = {
            'day1': self._create_day1_reminder_message,
            'day2': self._create_day2_reminder_message,
            'followup': self._create_followup_reminder_message,
            'deadline': self._create_deadline_reminder_message
        }

    async def process_pending_reminders(self) -> Dict[str, Any]:
        """Process all pending reminders that are due."""
        try:
            current_time = datetime.now()
            pending_reminders = await database.get_pending_reminders(current_time)

            if not pending_reminders:
                logger.info("No pending reminders to process")
                return {
                    'processed': 0,
                    'failed': 0,
                    'skipped': 0,
                    'details': []
                }

            results = {
                'processed': 0,
                'failed': 0,
                'skipped': 0,
                'details': []
            }

            logger.info(f"Processing {len(pending_reminders)} pending reminders")

            for reminder in pending_reminders:
                try:
                    success = await self._send_reminder(reminder)
                    if success:
                        await database.mark_reminder_sent(reminder.id)
                        results['processed'] += 1
                        results['details'].append({
                            'id': reminder.id,
                            'type': reminder.reminder_type,
                            'status': 'sent',
                            'user_id': reminder.frontdesk_user_id
                        })
                    else:
                        results['failed'] += 1
                        results['details'].append({
                            'id': reminder.id,
                            'type': reminder.reminder_type,
                            'status': 'failed',
                            'user_id': reminder.frontdesk_user_id
                        })

                    # Small delay to avoid rate limiting
                    await asyncio.sleep(0.5)

                except Exception as e:
                    logger.error(f"Failed to process reminder {reminder.id}: {e}")
                    results['failed'] += 1
                    results['details'].append({
                        'id': reminder.id,
                        'type': reminder.reminder_type,
                        'status': 'error',
                        'error': str(e),
                        'user_id': reminder.frontdesk_user_id
                    })

            logger.info(f"Reminder processing complete: {results['processed']} sent, {results['failed']} failed")
            return results

        except Exception as e:
            logger.error(f"Failed to process pending reminders: {e}")
            raise

    async def _send_reminder(self, reminder: Reminder) -> bool:
        """Send an individual reminder."""
        try:
            # Get member info
            member = await database.get_team_member_by_user_id(reminder.frontdesk_user_id)
            if not member or not member.is_active:
                logger.warning(f"Reminder {reminder.id}: member {reminder.frontdesk_user_id} not found or inactive")
                return False

            # Generate reminder message
            message = await self._generate_reminder_message(reminder)

            # Send reminder
            await telegram_handler.send_message(
                member.chat_id,
                message,
                parse_mode='markdown'
            )

            logger.info(f"Sent reminder {reminder.id} to user {reminder.frontdesk_user_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to send reminder {reminder.id}: {e}")
            return False

    async def _generate_reminder_message(self, reminder: Reminder) -> str:
        """Generate reminder message content."""
        # Use custom message if provided
        if reminder.message:
            return f"🔔 **提醒 / Reminder**\n\n{reminder.message}"

        # Generate based on type
        generator = self.reminder_templates.get(reminder.reminder_type)
        if generator:
            return await generator(reminder)

        # Default reminder message
        return f"🔔 **提醒 / Reminder**\n\n您有一个待处理的任务，请及时处理。\nYou have a pending task, please handle it promptly."

    async def _create_day1_reminder_message(self, reminder: Reminder) -> str:
        """Create Day 1 reminder message."""
        # Get client record details
        client_record = await self._get_client_record(reminder.client_record_id)

        # Get user language
        lang = await _get_lang(reminder.frontdesk_user_id)

        if not client_record:
            return f"""
{t('reminder_day1_title', lang)}

{t('update_day1_status', lang)}

{t('use_clients_view_pending', lang)}
            """.strip()

        return f"""
{t('reminder_day1_title', lang)}

{t('client_info_label', lang)}:
{t('client_number_label', lang)}: {client_record.client_number}
{t('account_id_label', lang)}: {client_record.account_id}
{t('category_label', lang)}: {client_record.category}
{t('date_entered_label', lang)}: {client_record.date}

{t('update_day1_status_prompt', lang)}

{t('current_status_label', lang)}: {client_record.first_day}

{t('update_status_instruction', lang)}
        """.strip()

    async def _create_day2_reminder_message(self, reminder: Reminder) -> str:
        """Create Day 2 reminder message."""
        client_record = await self._get_client_record(reminder.client_record_id)

        # Get user language
        lang = await _get_lang(reminder.frontdesk_user_id)

        if not client_record:
            return f"""
{t('reminder_day2_title', lang)}

{t('update_day2_status', lang)}

{t('use_clients_view_pending', lang)}
            """.strip()

        return f"""
{t('reminder_day2_title', lang)}

{t('client_info_label', lang)}:
{t('client_number_label', lang)}: {client_record.client_number}
{t('account_id_label', lang)}: {client_record.account_id}
{t('day1_status_label', lang)}: {client_record.first_day}
{t('date_entered_label', lang)}: {client_record.date}

{t('update_day2_status_prompt', lang)}

{t('current_status_label', lang)}: {client_record.second_day}

{t('reminder_tips_label', lang)}
{t('training_complete_tip', lang)}

{t('update_status_instruction', lang)}
        """.strip()

    async def _create_followup_reminder_message(self, reminder: Reminder) -> str:
        """Create follow-up reminder message."""
        return """
🔔 **客户跟进提醒 / Client Follow-up Reminder**

请主动联系您的客户：
Please proactively contact your clients:

📞 **行动清单 / Action List:**
• 联系未响应的潜在客户
• 确认已注册客户的培训进度
• 协助客户完成必要步骤
• 记录客户反馈和状态

💡 **提示 / Tips:**
定期跟进是提高转换率的关键！
Regular follow-up is key to improving conversion rates!

使用 /clients 查看客户列表。
Use /clients to view your client list.
        """.strip()

    async def _create_deadline_reminder_message(self, reminder: Reminder) -> str:
        """Create deadline reminder message."""
        return """
⏰ **截止日期提醒 / Deadline Reminder**

重要任务即将到达截止时间！
Important task deadline approaching!

📋 **请检查 / Please Check:**
• 待提交的报告
• 未完成的客户状态更新
• 待处理的培训记录

⚡ **立即行动 / Take Action Now:**
使用 /dashboard 查看总体进度
Use /dashboard to view overall progress

如需帮助，请联系管理团队。
Contact management team if you need help.
        """.strip()

    async def _get_client_record(self, record_id: Optional[int]) -> Optional[ClientRecord]:
        """Get client record by ID."""
        if not record_id:
            return None

        try:
            async with database.get_connection() as db:
                cursor = await db.execute("""
                    SELECT * FROM client_records WHERE id = ?
                """, (record_id,))
                row = await cursor.fetchone()
                return database._row_to_client_record(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get client record {record_id}: {e}")
            return None

    async def create_automatic_reminders(self, client_record_id: int, frontdesk_user_id: int) -> List[int]:
        """Create automatic reminders for a new client record."""
        try:
            now = datetime.now()
            reminder_ids = []

            # Day 1 reminder (24 hours)
            day1_reminder = Reminder(
                client_record_id=client_record_id,
                frontdesk_user_id=frontdesk_user_id,
                reminder_type='day1',
                scheduled_time=now + timedelta(hours=config.bot.day1_reminder_hours),
                message=None  # Will use template
            )
            day1_id = await database.create_reminder(day1_reminder)
            reminder_ids.append(day1_id)

            # Day 2 reminder (48 hours)
            day2_reminder = Reminder(
                client_record_id=client_record_id,
                frontdesk_user_id=frontdesk_user_id,
                reminder_type='day2',
                scheduled_time=now + timedelta(hours=config.bot.day2_reminder_hours),
                message=None  # Will use template
            )
            day2_id = await database.create_reminder(day2_reminder)
            reminder_ids.append(day2_id)

            logger.info(f"Created automatic reminders for client record {client_record_id}: {reminder_ids}")
            return reminder_ids

        except Exception as e:
            logger.error(f"Failed to create automatic reminders for client record {client_record_id}: {e}")
            return []

    async def create_manual_reminder(self, frontdesk_user_id: int, reminder_type: str,
                                   scheduled_time: datetime, message: str) -> Optional[int]:
        """Create a manual reminder."""
        try:
            manual_reminder = Reminder(
                client_record_id=None,  # No specific client record
                frontdesk_user_id=frontdesk_user_id,
                reminder_type=reminder_type,
                scheduled_time=scheduled_time,
                message=message
            )

            reminder_id = await database.create_reminder(manual_reminder)
            logger.info(f"Created manual reminder {reminder_id} for user {frontdesk_user_id}")
            return reminder_id

        except Exception as e:
            logger.error(f"Failed to create manual reminder: {e}")
            return None

    async def cancel_reminders_for_client(self, client_record_id: int) -> int:
        """Cancel all pending reminders for a client record."""
        try:
            async with database.get_connection() as db:
                cursor = await db.execute("""
                    UPDATE reminders
                    SET is_sent = TRUE, sent_at = CURRENT_TIMESTAMP
                    WHERE client_record_id = ? AND is_sent = FALSE
                """, (client_record_id,))
                await db.commit()

                cancelled_count = cursor.rowcount
                logger.info(f"Cancelled {cancelled_count} reminders for client record {client_record_id}")
                return cancelled_count

        except Exception as e:
            logger.error(f"Failed to cancel reminders for client record {client_record_id}: {e}")
            return 0

    async def update_reminder_schedule(self, reminder_id: int, new_scheduled_time: datetime) -> bool:
        """Update reminder schedule time."""
        try:
            async with database.get_connection() as db:
                await db.execute("""
                    UPDATE reminders
                    SET scheduled_time = ?
                    WHERE id = ? AND is_sent = FALSE
                """, (new_scheduled_time, reminder_id))
                await db.commit()

            logger.info(f"Updated reminder {reminder_id} schedule to {new_scheduled_time}")
            return True

        except Exception as e:
            logger.error(f"Failed to update reminder {reminder_id} schedule: {e}")
            return False

    async def get_reminder_statistics(self) -> Dict[str, Any]:
        """Get reminder system statistics."""
        try:
            stats = {}
            async with database.get_connection() as db:
                # Pending reminders
                cursor = await db.execute("SELECT COUNT(*) FROM reminders WHERE is_sent = FALSE")
                stats['pending'] = (await cursor.fetchone())[0]

                # Sent reminders (last 7 days)
                week_ago = datetime.now() - timedelta(days=7)
                cursor = await db.execute("""
                    SELECT COUNT(*) FROM reminders
                    WHERE is_sent = TRUE AND sent_at >= ?
                """, (week_ago,))
                stats['sent_week'] = (await cursor.fetchone())[0]

                # Overdue reminders
                cursor = await db.execute("""
                    SELECT COUNT(*) FROM reminders
                    WHERE is_sent = FALSE AND scheduled_time < ?
                """, (datetime.now(),))
                stats['overdue'] = (await cursor.fetchone())[0]

                # By type
                cursor = await db.execute("""
                    SELECT reminder_type, COUNT(*) FROM reminders
                    WHERE is_sent = FALSE
                    GROUP BY reminder_type
                """)
                stats['by_type'] = dict(await cursor.fetchall())

                # Success rate (last 7 days)
                cursor = await db.execute("""
                    SELECT
                        COUNT(CASE WHEN is_sent = TRUE THEN 1 END) as sent,
                        COUNT(*) as total
                    FROM reminders
                    WHERE created_at >= ?
                """, (week_ago,))
                sent, total = await cursor.fetchone()
                stats['success_rate'] = (sent / total * 100) if total > 0 else 0

            return stats

        except Exception as e:
            logger.error(f"Failed to get reminder statistics: {e}")
            return {}

    async def cleanup_old_reminders(self, days_old: int = 30) -> int:
        """Clean up old sent reminders."""
        try:
            cutoff_date = datetime.now() - timedelta(days=days_old)

            async with database.get_connection() as db:
                cursor = await db.execute("""
                    DELETE FROM reminders
                    WHERE is_sent = TRUE AND sent_at < ?
                """, (cutoff_date,))
                await db.commit()

                cleaned_count = cursor.rowcount
                logger.info(f"Cleaned up {cleaned_count} old reminders (older than {days_old} days)")
                return cleaned_count

        except Exception as e:
            logger.error(f"Failed to cleanup old reminders: {e}")
            return 0

    async def process_overdue_reminders(self) -> Dict[str, Any]:
        """Process overdue reminders with special handling."""
        try:
            overdue_time = datetime.now() - timedelta(hours=1)  # 1 hour overdue
            overdue_reminders = await database.get_pending_reminders()
            overdue_reminders = [r for r in overdue_reminders if r.scheduled_time < overdue_time]

            if not overdue_reminders:
                return {'processed': 0, 'escalated': 0, 'cancelled': 0}

            results = {'processed': 0, 'escalated': 0, 'cancelled': 0}

            for reminder in overdue_reminders:
                # Check how overdue the reminder is
                overdue_hours = (datetime.now() - reminder.scheduled_time).total_seconds() / 3600

                if overdue_hours > 24:  # More than 24 hours overdue
                    # Cancel very old reminders
                    await database.mark_reminder_sent(reminder.id)
                    results['cancelled'] += 1
                    logger.warning(f"Cancelled very old reminder {reminder.id} ({overdue_hours:.1f}h overdue)")

                elif overdue_hours > 6:  # 6+ hours overdue - escalate to managers
                    await self._escalate_reminder(reminder)
                    await database.mark_reminder_sent(reminder.id)
                    results['escalated'] += 1

                else:  # Send immediately
                    success = await self._send_reminder(reminder)
                    if success:
                        await database.mark_reminder_sent(reminder.id)
                        results['processed'] += 1

            return results

        except Exception as e:
            logger.error(f"Failed to process overdue reminders: {e}")
            return {'error': str(e)}

    async def _escalate_reminder(self, reminder: Reminder):
        """Escalate overdue reminder to managers."""
        try:
            member = await database.get_team_member_by_user_id(reminder.frontdesk_user_id)
            member_name = member.frontdesk_name if member else f"User {reminder.frontdesk_user_id}"

            escalation_message = f"""
⚠️ **提醒升级 / Reminder Escalation**

前台成员 {member_name} 有一个严重过期的提醒：
Frontdesk member {member_name} has a severely overdue reminder:

• 类型 / Type: {reminder.reminder_type}
• 计划时间 / Scheduled: {reminder.scheduled_time.strftime('%Y-%m-%d %H:%M')}
• 过期时长 / Overdue: {(datetime.now() - reminder.scheduled_time).total_seconds() / 3600:.1f} 小时

请及时跟进。
Please follow up promptly.
            """.strip()

            await telegram_handler.broadcast_to_managers(escalation_message)
            logger.info(f"Escalated overdue reminder {reminder.id} to managers")

        except Exception as e:
            logger.error(f"Failed to escalate reminder {reminder.id}: {e}")

    async def scan_stale_clients(self) -> Dict[str, Any]:
        """Scan for stale clients and create auto-reminders for responsible frontdesk."""
        try:
            from working_hours import is_working_hours

            # Only run during working hours
            if not is_working_hours():
                return {'processed': 0, 'message': 'Outside working hours, skipping stale client scan'}

            cutoff_date = datetime.now() - timedelta(days=config.bot.stale_client_days)
            results = {'processed': 0, 'reminders_created': 0, 'errors': []}

            logger.info(f"Scanning for stale clients older than {config.bot.stale_client_days} days")

            async with database.get_connection() as db:
                # Find records with stale status
                cursor = await db.execute("""
                    SELECT * FROM client_records
                    WHERE (
                        (first_day IN ('不注册', '') OR first_day IS NULL OR
                         second_day IN ('不注册', '') OR second_day IS NULL)
                        AND created_at < ?
                    )
                    ORDER BY frontdesk, created_at DESC
                """, (cutoff_date.isoformat(),))

                stale_records = await cursor.fetchall()

            if not stale_records:
                logger.info("No stale client records found")
                return results

            # Group by frontdesk to avoid spam
            frontdesk_groups = {}
            for row in stale_records:
                record = database._row_to_client_record(row)
                if not record:
                    continue

                frontdesk = record.frontdesk
                if frontdesk not in frontdesk_groups:
                    frontdesk_groups[frontdesk] = []
                frontdesk_groups[frontdesk].append(record)

            # Create reminders for each frontdesk
            for frontdesk, records in frontdesk_groups.items():
                try:
                    # Get frontdesk user ID
                    member = await self._get_frontdesk_member(frontdesk)
                    if not member:
                        logger.warning(f"Frontdesk member not found: {frontdesk}")
                        results['errors'].append(f"Frontdesk member not found: {frontdesk}")
                        continue

                    # Create stale client reminder
                    stale_count = len(records)
                    message = await self._create_stale_client_reminder_message(frontdesk, records)

                    reminder_id = await self.create_manual_reminder(
                        frontdesk_user_id=member.user_id,
                        reminder_type='stale_client',
                        scheduled_time=datetime.now(),  # Send immediately
                        message=message
                    )

                    if reminder_id:
                        results['reminders_created'] += 1
                        logger.info(f"Created stale client reminder for {frontdesk}: {stale_count} clients")
                    else:
                        results['errors'].append(f"Failed to create reminder for {frontdesk}")

                    results['processed'] += stale_count

                except Exception as e:
                    error_msg = f"Failed to process stale clients for {frontdesk}: {e}"
                    logger.error(error_msg)
                    results['errors'].append(error_msg)

            logger.info(f"Stale client scan complete: {results}")
            return results

        except Exception as e:
            logger.error(f"Failed to scan stale clients: {e}")
            return {'error': str(e), 'processed': 0, 'reminders_created': 0}

    async def _get_frontdesk_member(self, frontdesk_name: str) -> Optional[Any]:
        """Get team member by frontdesk name."""
        try:
            async with database.get_connection() as db:
                cursor = await db.execute("""
                    SELECT * FROM team_members
                    WHERE frontdesk_name = ? AND is_active = TRUE
                    LIMIT 1
                """, (frontdesk_name,))
                row = await cursor.fetchone()
                return database._row_to_team_member(row) if row else None

        except Exception as e:
            logger.error(f"Failed to get frontdesk member {frontdesk_name}: {e}")
            return None

    async def _create_stale_client_reminder_message(self, frontdesk: str, stale_records: List[ClientRecord]) -> str:
        """Create stale client reminder message."""
        stale_count = len(stale_records)

        # Get user's language preference if available
        if stale_records:
            member = await self._get_frontdesk_member(frontdesk)
            user_language = await database.get_user_language(member.user_id) if member else None
        else:
            user_language = None

        # Use i18n when available, fallback to dual-language for now
        from i18n import t

        if user_language:
            message = f"""⚠️ **{t('stale_clients_title', user_language)}**

{t('stale_clients_found', user_language).format(count=stale_count, days=config.bot.stale_client_days)}

{t('stale_clients_list', user_language)}:"""
        else:
            # Fallback dual-language message
            message = f"""⚠️ **逾期客户提醒 / Stale Clients Reminder**

发现 {stale_count} 个超过 {config.bot.stale_client_days} 天未更新状态的客户。
Found {stale_count} clients with no status updates for over {config.bot.stale_client_days} days.

客户列表 / Client List:"""

        # Add up to 5 client details
        for i, record in enumerate(stale_records[:5]):
            days_old = (datetime.now() - datetime.fromisoformat(record.created_at if hasattr(record, 'created_at') else datetime.now().isoformat())).days
            message += f"\n• {record.client_number} ({record.account_id}) - {days_old}天前 / {days_old}d ago"

        if len(stale_records) > 5:
            remaining = len(stale_records) - 5
            if user_language:
                message += f"\n{t('and_more_clients', user_language).format(count=remaining)}"
            else:
                message += f"\n...还有 {remaining} 个客户 / ...and {remaining} more clients"

        if user_language:
            message += f"\n\n{t('please_update_status', user_language)}"
            message += f"\n{t('use_clients_command', user_language)}"
        else:
            message += "\n\n请及时更新这些客户的注册状态！"
            message += "\nPlease update the registration status of these clients promptly!"
            message += "\n\n使用 /clients 查看详细信息。"
            message += "\nUse /clients to view details."

        return message


# Global reminder engine instance
reminder_engine = ReminderEngine()