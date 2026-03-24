"""Team Records Bot - Main Ralph Loop Implementation."""
import asyncio
import logging
import signal
import sys
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timedelta
import traceback

from config import config
from database import database
from telegram_handler import telegram_handler
from models import BotTask, ReportTemplate
from engines.report_engine import report_engine
from engines.reminder_engine import reminder_engine
from engines.sheet_sync import sheet_sync_engine
from engines.chart_engine import chart_engine

# Import all handlers
from handlers.registration import REGISTRATION_COMMANDS, REGISTRATION_CALLBACKS, REGISTRATION_CONVERSATIONS
from handlers.reporting import REPORTING_COMMANDS, REPORTING_CALLBACKS, REPORTING_CONVERSATIONS
from handlers.dashboard import DASHBOARD_COMMANDS, DASHBOARD_CALLBACKS, DASHBOARD_CONVERSATIONS
from handlers.finance import FINANCE_COMMANDS, FINANCE_CALLBACKS, FINANCE_CONVERSATIONS
from handlers.performance import PERFORMANCE_COMMANDS, PERFORMANCE_CALLBACKS, PERFORMANCE_CONVERSATIONS
from handlers.reminders import REMINDERS_COMMANDS, REMINDERS_CALLBACKS, REMINDERS_CONVERSATIONS

# Import new chart and UI handlers
from handlers.menu import MENU_COMMANDS, MENU_CALLBACKS, MENU_CONVERSATIONS
from handlers.analytics import ANALYTICS_COMMANDS, ANALYTICS_CALLBACKS, ANALYTICS_CONVERSATIONS
from handlers.help_guide import HELP_COMMANDS, HELP_CALLBACKS, HELP_CONVERSATIONS

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('team_records_bot.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


class RalphLoop:
    """Main Ralph Loop orchestrator - single process, one task per iteration."""

    def __init__(self):
        self.running = False
        self.loop_counter = 0
        self.last_health_check = None
        self.last_sync = None
        self.last_reminder_check = None
        self.last_report_generation = None

        # Command and callback handlers registry
        self.command_handlers = {}
        self.callback_handlers = {}
        self.conversation_handlers = {}

        # Performance metrics
        self.metrics = {
            'tasks_processed': 0,
            'tasks_failed': 0,
            'messages_handled': 0,
            'reminders_sent': 0,
            'reports_generated': 0,
            'sync_operations': 0,
            'uptime_start': datetime.now()
        }

    async def initialize(self):
        """Initialize all components of the bot."""
        try:
            logger.info("Initializing Team Records Bot...")

            # Initialize database
            await database.initialize()
            logger.info("Database initialized")

            # Initialize Telegram handler
            await telegram_handler.initialize()
            logger.info("Telegram handler initialized")

            # Initialize engines
            await report_engine.initialize() if hasattr(report_engine, 'initialize') else None
            await sheet_sync_engine.initialize()
            logger.info("Engines initialized")

            # Register all command and callback handlers
            await self._register_handlers()
            logger.info("Handlers registered")

            # Set up signal handlers for graceful shutdown
            self._setup_signal_handlers()

            # Perform initial health checks
            await self._perform_health_checks()

            logger.info("Team Records Bot initialization completed successfully")

        except Exception as e:
            logger.error(f"Failed to initialize bot: {e}")
            logger.error(traceback.format_exc())
            raise

    def _setup_signal_handlers(self):
        """Set up signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            self.running = False

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    async def _register_handlers(self):
        """Register all command, callback, and conversation handlers."""
        # Merge all command handlers
        all_commands = {}
        all_commands.update(REGISTRATION_COMMANDS)
        all_commands.update(REPORTING_COMMANDS)
        all_commands.update(DASHBOARD_COMMANDS)
        all_commands.update(FINANCE_COMMANDS)
        all_commands.update(PERFORMANCE_COMMANDS)
        all_commands.update(REMINDERS_COMMANDS)
        # Add new handlers
        all_commands.update(MENU_COMMANDS)
        all_commands.update(ANALYTICS_COMMANDS)
        all_commands.update(HELP_COMMANDS)

        # Merge all callback handlers
        all_callbacks = {}
        all_callbacks.update(REGISTRATION_CALLBACKS)
        all_callbacks.update(REPORTING_CALLBACKS)
        all_callbacks.update(DASHBOARD_CALLBACKS)
        all_callbacks.update(FINANCE_CALLBACKS)
        all_callbacks.update(PERFORMANCE_CALLBACKS)
        all_callbacks.update(REMINDERS_CALLBACKS)
        # Add new handlers
        all_callbacks.update(MENU_CALLBACKS)
        all_callbacks.update(ANALYTICS_CALLBACKS)
        all_callbacks.update(HELP_CALLBACKS)

        # Merge all conversation handlers
        all_conversations = {}
        all_conversations.update(REGISTRATION_CONVERSATIONS)
        all_conversations.update(REPORTING_CONVERSATIONS)
        all_conversations.update(DASHBOARD_CONVERSATIONS)
        all_conversations.update(FINANCE_CONVERSATIONS)
        all_conversations.update(PERFORMANCE_CONVERSATIONS)
        all_conversations.update(REMINDERS_CONVERSATIONS)
        # Add new handlers
        all_conversations.update(MENU_CONVERSATIONS)
        all_conversations.update(ANALYTICS_CONVERSATIONS)
        all_conversations.update(HELP_CONVERSATIONS)

        self.command_handlers = all_commands
        self.callback_handlers = all_callbacks
        self.conversation_handlers = all_conversations

        logger.info(f"Registered {len(all_commands)} commands, {len(all_callbacks)} callbacks, {len(all_conversations)} conversation handlers")

    async def _perform_health_checks(self):
        """Perform initial health checks."""
        try:
            # Check database connection
            stats = await database.get_stats()
            logger.info(f"Database health check: {stats}")

            # Check Telegram connection
            telegram_healthy = await telegram_handler.health_check()
            logger.info(f"Telegram health check: {'OK' if telegram_healthy else 'FAILED'}")

            self.last_health_check = datetime.now()

        except Exception as e:
            logger.error(f"Health check failed: {e}")

    async def run(self):
        """Main Ralph Loop - single process, one task per iteration."""
        try:
            self.running = True
            logger.info("Starting Ralph Loop...")

            while self.running:
                self.loop_counter += 1

                try:
                    # Refresh context (load fresh DB state)
                    await self.refresh_context()

                    # Select and execute next task
                    task = await self.select_task()
                    if task:
                        await self.execute_task(task)
                    else:
                        # No urgent tasks, perform maintenance operations
                        await self.perform_maintenance()

                    # Brief pause between iterations
                    await asyncio.sleep(config.bot.loop_interval)

                except Exception as e:
                    logger.error(f"Error in loop iteration {self.loop_counter}: {e}")
                    logger.error(traceback.format_exc())
                    self.metrics['tasks_failed'] += 1

                    # Brief pause before next iteration to prevent tight error loops
                    await asyncio.sleep(min(config.bot.loop_interval * 2, 10))

            logger.info("Ralph Loop stopped")

        except Exception as e:
            logger.error(f"Fatal error in Ralph Loop: {e}")
            logger.error(traceback.format_exc())
            raise
        finally:
            await self.shutdown()

    async def refresh_context(self):
        """Refresh context - load fresh database state."""
        # This is where we would refresh any cached data if needed
        # For now, we rely on fresh database queries in each task
        pass

    async def select_task(self) -> Optional[BotTask]:
        """Select the next highest priority task to execute."""
        try:
            # Get the next task from database (ordered by priority and creation time)
            task = await database.get_next_task()

            if task:
                # Mark task as processing
                await database.update_task_status(task.id, 'processing')
                logger.debug(f"Selected task {task.id}: {task.task_type}")

            return task

        except Exception as e:
            logger.error(f"Failed to select task: {e}")
            return None

    async def execute_task(self, task: BotTask):
        """Execute exactly ONE task."""
        try:
            logger.info(f"Executing task {task.id}: {task.task_type}")

            success = False

            if task.task_type == 'message':
                success = await self._handle_message_task(task)
            elif task.task_type == 'reminder':
                success = await self._handle_reminder_task(task)
            elif task.task_type == 'report':
                success = await self._handle_report_task(task)
            elif task.task_type == 'sync':
                success = await self._handle_sync_task(task)
            elif task.task_type == 'maintenance':
                success = await self._handle_maintenance_task(task)
            else:
                logger.warning(f"Unknown task type: {task.task_type}")
                success = False

            # Update task status
            if success:
                await database.update_task_status(task.id, 'completed')
                self.metrics['tasks_processed'] += 1
                logger.info(f"Task {task.id} completed successfully")
            else:
                # Check if we should retry
                if task.attempts < task.max_attempts:
                    await database.update_task_status(task.id, 'pending')
                    logger.info(f"Task {task.id} failed, will retry (attempt {task.attempts + 1})")
                else:
                    await database.update_task_status(task.id, 'failed', 'Max attempts exceeded')
                    logger.error(f"Task {task.id} failed permanently after {task.attempts} attempts")

        except Exception as e:
            logger.error(f"Error executing task {task.id}: {e}")
            await database.update_task_status(task.id, 'failed', str(e))
            self.metrics['tasks_failed'] += 1

    async def _handle_message_task(self, task: BotTask) -> bool:
        """Handle message-related tasks."""
        try:
            data = task.data
            event_type = data.get('event_type')

            if event_type == 'command':
                return await self._handle_command(data)
            elif event_type == 'callback':
                return await self._handle_callback(data)
            elif event_type == 'conversation':
                return await self._handle_conversation(data)
            else:
                logger.warning(f"Unknown message event type: {event_type}")
                return False

        except Exception as e:
            logger.error(f"Error handling message task: {e}")
            return False

    async def _handle_command(self, data: Dict[str, Any]) -> bool:
        """Handle command execution."""
        try:
            command = data.get('command')
            handler = self.command_handlers.get(command)

            if handler:
                await handler(data)
                self.metrics['messages_handled'] += 1
                return True
            else:
                # Unknown command - send help message
                chat_id = data.get('chat_id')
                if chat_id:
                    help_text = """
❓ **未知命令 / Unknown Command**

可用命令 / Available Commands:
• /start - 注册账户 / Register account
• /menu - 主菜单 / Main menu
• /report - 提交客户记录 / Submit client record
• /status - 查看个人统计 / View personal stats
• /clients - 查看客户列表 / View client list
• /analytics - 数据分析图表 / Data analytics charts
• /charts - 图表分析 / Chart analysis
• /help - 帮助中心 / Help center

管理命令 / Admin Commands:
• /dashboard - 团队概览 / Team dashboard
• /summary - 生成日报 / Generate daily report
• /finance - 财务概览 / Financial overview
                    """.strip()

                    await telegram_handler.send_message(chat_id, help_text, parse_mode='markdown')

                return True

        except Exception as e:
            logger.error(f"Error handling command: {e}")
            return False

    async def _handle_callback(self, data: Dict[str, Any]) -> bool:
        """Handle callback query execution."""
        try:
            callback_data = data.get('callback_data')

            # Try exact match first
            handler = self.callback_handlers.get(callback_data)

            if not handler:
                # Try pattern matching for dynamic callbacks
                for pattern, callback_handler in self.callback_handlers.items():
                    if '*' in pattern:
                        # Convert pattern to regex
                        import re
                        regex_pattern = pattern.replace('*', r'.*')
                        if re.match(regex_pattern, callback_data):
                            handler = callback_handler
                            break

            if handler:
                await handler(data)
                return True
            else:
                logger.warning(f"No handler found for callback: {callback_data}")
                return True  # Don't fail the task for unknown callbacks

        except Exception as e:
            logger.error(f"Error handling callback: {e}")
            return False

    async def _handle_conversation(self, data: Dict[str, Any]) -> bool:
        """Handle conversation state execution."""
        try:
            state = data.get('state', {})
            step = state.get('step')

            handler = self.conversation_handlers.get(step)

            if handler:
                await handler(data)
                return True
            else:
                # Clear conversation state for unknown steps
                user_id = data.get('user_id')
                if user_id:
                    telegram_handler.clear_conversation_state(user_id)
                return True

        except Exception as e:
            logger.error(f"Error handling conversation: {e}")
            return False

    async def _handle_reminder_task(self, task: BotTask) -> bool:
        """Handle reminder-related tasks."""
        try:
            action = task.data.get('action', 'process_pending')

            if action == 'process_pending':
                results = await reminder_engine.process_pending_reminders()
                self.metrics['reminders_sent'] += results.get('processed', 0)
                return True
            elif action == 'send_all_pending':
                results = await reminder_engine.process_pending_reminders()
                self.metrics['reminders_sent'] += results.get('processed', 0)
                return True
            elif action == 'process_overdue':
                results = await reminder_engine.process_overdue_reminders()
                return True
            else:
                logger.warning(f"Unknown reminder action: {action}")
                return False

        except Exception as e:
            logger.error(f"Error handling reminder task: {e}")
            return False

    async def _handle_report_task(self, task: BotTask) -> bool:
        """Handle report generation tasks."""
        try:
            report_type = task.data.get('report_type')
            parameters = task.data.get('parameters', {})

            template = ReportTemplate(
                template_type=report_type,
                parameters=parameters
            )

            report_data = await report_engine.generate_report(template)

            # Send report to specified recipients
            recipients = task.data.get('recipients', [])
            for chat_id in recipients:
                await telegram_handler.send_message(
                    chat_id,
                    report_data.get('formatted_report', 'Report generated successfully'),
                    parse_mode='markdown'
                )

            self.metrics['reports_generated'] += 1
            return True

        except Exception as e:
            logger.error(f"Error handling report task: {e}")
            return False

    async def _handle_sync_task(self, task: BotTask) -> bool:
        """Handle synchronization tasks."""
        try:
            sync_type = task.data.get('sync_type', 'full')

            if sync_type == 'full':
                results = await sheet_sync_engine.sync_all_data()
                self.metrics['sync_operations'] += 1
                return results.get('summary', {}).get('success', False)
            elif sync_type == 'export':
                data_type = task.data.get('data_type')
                filters = task.data.get('filters', {})
                results = await sheet_sync_engine.export_to_sheets(data_type, filters)
                return results.get('success', False)
            else:
                logger.warning(f"Unknown sync type: {sync_type}")
                return False

        except Exception as e:
            logger.error(f"Error handling sync task: {e}")
            return False

    async def _handle_maintenance_task(self, task: BotTask) -> bool:
        """Handle maintenance tasks."""
        try:
            action = task.data.get('action')

            if action == 'cleanup_old_tasks':
                await database.cleanup_old_tasks()
            elif action == 'cleanup_old_reminders':
                await reminder_engine.cleanup_old_reminders()
            elif action == 'backup_database':
                await database.backup_database()
            elif action == 'health_check':
                await self._perform_health_checks()
            else:
                logger.warning(f"Unknown maintenance action: {action}")
                return False

            return True

        except Exception as e:
            logger.error(f"Error handling maintenance task: {e}")
            return False

    async def perform_maintenance(self):
        """Perform periodic maintenance operations when no urgent tasks."""
        current_time = datetime.now()

        # Check for scheduled maintenance operations
        if not self.last_reminder_check or (current_time - self.last_reminder_check).total_seconds() > 300:  # 5 minutes
            # Check for pending reminders
            pending_reminders = await database.get_pending_reminders(current_time)
            if pending_reminders:
                # Create reminder processing task
                reminder_task = BotTask(
                    task_type='reminder',
                    priority=2,
                    data={'action': 'process_pending'}
                )
                await database.create_task(reminder_task)

            self.last_reminder_check = current_time

        if not self.last_sync or (current_time - self.last_sync).total_seconds() > config.bot.sync_interval:  # 1 hour
            # Schedule sync task
            sync_task = BotTask(
                task_type='sync',
                priority=3,
                data={'sync_type': 'full'}
            )
            await database.create_task(sync_task)
            self.last_sync = current_time

        if not self.last_health_check or (current_time - self.last_health_check).total_seconds() > 1800:  # 30 minutes
            # Schedule health check
            health_task = BotTask(
                task_type='maintenance',
                priority=4,
                data={'action': 'health_check'}
            )
            await database.create_task(health_task)
            self.last_health_check = current_time

        # Schedule daily reports if needed
        if self._should_generate_daily_report():
            daily_report_task = BotTask(
                task_type='report',
                priority=2,
                data={
                    'report_type': 'daily_summary',
                    'parameters': {'date': current_time.date()},
                    'recipients': config.bot.manager_chat_ids
                }
            )
            await database.create_task(daily_report_task)
            self.last_report_generation = current_time.date()

    def _should_generate_daily_report(self) -> bool:
        """Check if daily report should be generated."""
        if not config.bot.daily_report_time:
            return False

        current_time = datetime.now()
        report_time_str = config.bot.daily_report_time  # e.g., "18:00"
        report_hour, report_minute = map(int, report_time_str.split(':'))

        # Check if it's time for daily report and we haven't generated one today
        is_time = (
            current_time.hour == report_hour and
            current_time.minute >= report_minute and
            (not self.last_report_generation or self.last_report_generation < current_time.date())
        )

        return is_time

    async def shutdown(self):
        """Perform graceful shutdown."""
        try:
            logger.info("Starting graceful shutdown...")

            # Mark any processing tasks as pending for retry on restart
            async with database.get_connection() as db:
                await db.execute("""
                    UPDATE bot_tasks SET status = 'pending' WHERE status = 'processing'
                """)
                await db.commit()

            # Disconnect Telegram client
            await telegram_handler.disconnect()

            # Log final metrics
            uptime = datetime.now() - self.metrics['uptime_start']
            logger.info(f"Shutdown metrics: {self.metrics}")
            logger.info(f"Total uptime: {uptime}")

            logger.info("Graceful shutdown completed")

        except Exception as e:
            logger.error(f"Error during shutdown: {e}")

    async def get_status(self) -> Dict[str, Any]:
        """Get current bot status and metrics."""
        current_time = datetime.now()
        uptime = current_time - self.metrics['uptime_start']

        status = {
            'running': self.running,
            'loop_counter': self.loop_counter,
            'uptime_seconds': uptime.total_seconds(),
            'uptime_formatted': str(uptime),
            'metrics': self.metrics.copy(),
            'last_health_check': self.last_health_check.isoformat() if self.last_health_check else None,
            'last_sync': self.last_sync.isoformat() if self.last_sync else None,
            'telegram_connected': await telegram_handler.health_check(),
            'database_stats': await database.get_stats(),
            'task_queue_size': len(await database.get_pending_reminders()) + 1  # Approximate
        }

        return status


# Global ralph loop instance
ralph_loop = RalphLoop()


async def main():
    """Main entry point."""
    try:
        # Initialize and run the Ralph Loop
        await ralph_loop.initialize()
        await ralph_loop.run()
    except KeyboardInterrupt:
        logger.info("Received KeyboardInterrupt, shutting down...")
    except Exception as e:
        logger.error(f"Fatal error in main: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == '__main__':
    # Run the bot
    asyncio.run(main())