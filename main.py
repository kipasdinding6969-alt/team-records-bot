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

# Import V2 handlers
from handlers_v2.quick_actions import QUICK_ACTIONS_COMMANDS, QUICK_ACTIONS_CALLBACKS, QUICK_ACTIONS_CONVERSATIONS
from handlers_v2.pipeline import PIPELINE_COMMANDS, PIPELINE_CALLBACKS, PIPELINE_CONVERSATIONS
from handlers_v2.management import MANAGEMENT_COMMANDS, MANAGEMENT_CALLBACKS, MANAGEMENT_CONVERSATIONS
from handlers_v2.registration_v2 import REGISTRATION_V2_COMMANDS, REGISTRATION_V2_CALLBACKS, REGISTRATION_V2_CONVERSATIONS
from handlers_v2.group_chat import GROUP_COMMANDS, GROUP_CALLBACKS, GROUP_CONVERSATIONS
from database_v2 import database_v2
import engines.sheet_sync_v2 as _sheet_sync_v2_mod
import engines.dashboard_sheets as _dashboard_mod

# NocoDB private sheets engine (optional, parallel to Google Sheets)
_nocodb_writer = None

# NocoDB webhook runner (optional)
_nocodb_webhook_runner = None

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
        self.last_channel_post = None
        self.last_v2_stale_check = None
        self.last_v2_stats_calc = None
        self.last_rag_reindex = None
        self.last_v2_sheet_sync = None
        self.last_policy_dead_check = None
        self.last_policy_target_check = None
        self.last_obsidian_daily_report = None

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

            # Validate configuration first
            await self._validate_configuration()
            logger.info("Configuration validated")

            # Initialize database
            await database.initialize()
            logger.info("Database initialized")

            # Initialize V2 database with persistent connection
            await database_v2.initialize()
            await database_v2.connect()
            logger.info("DatabaseV2 initialized (persistent connection)")

            # Initialize Telegram handler
            await telegram_handler.initialize()
            logger.info("Telegram handler initialized")

            # Initialize engines
            if hasattr(report_engine, 'initialize'):
                await report_engine.initialize()

            # Initialize V2 bidirectional sheet sync + dashboard
            try:
                from engines.gsheet_writer import GSheetWriter
                from engines.sheet_sync_v2 import SheetSyncV2
                from engines.dashboard_sheets import DashboardSheets
                _writer = GSheetWriter()
                _writer.initialize()
                _sheet_sync_v2_mod.sheet_sync_v2 = SheetSyncV2(_writer)
                _dashboard_mod.dashboard_sheets = DashboardSheets(_writer)
                logger.info("SheetSyncV2 + DashboardSheets initialized")
            except Exception as e:
                logger.warning(f"SheetSyncV2 init failed (sheets may be unavailable): {e}")

            # Initialize NocoDB private sheets (runs parallel, non-blocking)
            global _nocodb_writer
            try:
                from engines.nocodb_writer import NocoDBWriter
                _nocodb_writer = NocoDBWriter()
                await _nocodb_writer.connect()
                logger.info("NocoDB writer initialized (private sheets active)")
            except Exception as e:
                logger.warning(f"NocoDB init failed (private sheets unavailable): {e}")
                _nocodb_writer = None

            logger.info("Engines initialized")

            # Register all command and callback handlers
            await self._register_handlers()
            logger.info("Handlers registered")

            # Set up signal handlers for graceful shutdown
            self._setup_signal_handlers()

            # Perform initial health checks
            await self._perform_health_checks()

            # Seed additional staff (TINO, KUYA, 阿文) — idempotent
            try:
                await database_v2.seed_additional_staff()
            except Exception as e:
                logger.warning(f"seed_additional_staff failed: {e}")

            # Register V2 bot commands with Telegram (visible in command menu)
            await self._register_bot_commands()

            # First-boot: populate dashboard tabs if never done
            await self._init_dashboard_if_needed()

            # Start NocoDB webhook server (optional — requires aiohttp + NOCODB_WEBHOOK_SECRET)
            try:
                from engines.nocodb_webhook import start_webhook_server
                global _nocodb_webhook_runner
                _nocodb_webhook_runner = await start_webhook_server()
            except Exception as e:
                logger.warning(f"NocoDB webhook server not started: {e}")

            logger.info("Team Records Bot initialization completed successfully")

        except Exception as e:
            logger.error(f"Failed to initialize bot: {e}")
            logger.error(traceback.format_exc())
            raise

    async def _validate_configuration(self):
        """Validate all configuration requirements."""
        errors = []

        # Validate Telegram configuration
        if not config.telegram.api_id or not config.telegram.api_hash or not config.telegram.phone:
            errors.append("Missing required Telegram configuration (TG_API_ID, TG_API_HASH, TG_PHONE)")

        # Bot token is optional - if not provided, will run in user-only mode
        if not config.telegram.bot_token:
            logger.warning("No bot token provided - running in user-only mode (inline buttons will not work)")

        # Validate Google Sheets configuration
        if not config.google_sheets.spreadsheet_id:
            errors.append("Missing required Google Sheets spreadsheet ID (SHEETS_ID)")

        # Validate database configuration
        if not config.database.db_path:
            errors.append("Missing database path configuration")

        # Test database connection
        try:
            async with database.get_connection() as db:
                await db.execute("SELECT 1")
        except Exception as e:
            errors.append(f"Database connection failed: {e}")

        # Test Telegram configuration
        try:
            config.telegram.validate()
        except Exception as e:
            errors.append(f"Telegram configuration invalid: {e}")

        if errors:
            error_msg = "Configuration validation failed:\n" + "\n".join(f"- {error}" for error in errors)
            raise ValueError(error_msg)

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
        # V2 handlers
        all_commands.update(QUICK_ACTIONS_COMMANDS)
        all_commands.update(PIPELINE_COMMANDS)
        all_commands.update(MANAGEMENT_COMMANDS)
        all_commands.update(REGISTRATION_V2_COMMANDS)
        all_commands.update(GROUP_COMMANDS)

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
        # V2 handlers
        all_callbacks.update(QUICK_ACTIONS_CALLBACKS)
        all_callbacks.update(PIPELINE_CALLBACKS)
        all_callbacks.update(MANAGEMENT_CALLBACKS)
        all_callbacks.update(REGISTRATION_V2_CALLBACKS)
        all_callbacks.update(GROUP_CALLBACKS)

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
        # V2 handlers
        all_conversations.update(QUICK_ACTIONS_CONVERSATIONS)
        all_conversations.update(PIPELINE_CONVERSATIONS)
        all_conversations.update(MANAGEMENT_CONVERSATIONS)
        all_conversations.update(REGISTRATION_V2_CONVERSATIONS)
        all_conversations.update(GROUP_CONVERSATIONS)

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

    async def _register_bot_commands(self):
        """Register V2 bot commands with Telegram so they appear in the command menu."""
        bot_client = telegram_handler.bot_client
        if bot_client is None:
            logger.warning("_register_bot_commands: no bot_client, skipping")
            return
        try:
            from telethon.tl.functions.bots import SetBotCommandsRequest
            from telethon.tl.types import BotCommand, BotCommandScopeDefault

            commands = [
                BotCommand('start',    '🚀 Start / Register'),
                BotCommand('me',       '📊 My dashboard (all-in-one)'),
                BotCommand('overview', '🏢 Team overview (managers)'),
                BotCommand('add',      '➕ Add client: /add <phone> <source>'),
                BotCommand('u',        '🔄 Update status: /u <phone> <status>'),
                BotCommand('pipeline', '📊 Pipeline funnel view'),
                BotCommand('followup', '🔥 Clients needing follow-up'),
                BotCommand('today',    '📈 Today\'s stats'),
                BotCommand('search',   '🔍 Search: /search <query>'),
                BotCommand('note',     '📝 Add note: /note <phone> <text>'),
                BotCommand('remind',   '⏰ Set reminder: /remind <phone> <time> <msg>'),
                BotCommand('handoff',  '🤝 Handoff to maintenance'),
                BotCommand('export',   '📥 Export CSV'),
                BotCommand('profile',  '👤 View profile'),
                BotCommand('sync',     '🔄 Force sync (managers)'),
                BotCommand('help',     '❓ Help guide'),
                BotCommand('menu',     '📋 Legacy menu'),
            ]
            await bot_client(SetBotCommandsRequest(
                scope=BotCommandScopeDefault(),
                lang_code='',
                commands=commands,
            ))
            logger.info(f"Registered {len(commands)} bot commands with Telegram")
        except Exception as e:
            logger.warning(f"_register_bot_commands failed: {e}")

    async def _init_dashboard_if_needed(self):
        """On first boot (or reset), populate all 5 dashboard tabs immediately."""
        if _dashboard_mod.dashboard_sheets is None:
            return
        initialized = await database_v2.get_setting('dashboard_initialized')
        if initialized == '1':
            return
        logger.info("First-boot: running dashboard initialization...")
        try:
            await _dashboard_mod.dashboard_sheets.refresh_all_tabs()
            await database_v2.set_setting('dashboard_initialized', '1', 'Dashboard tabs created on first boot')
            logger.info("First-boot dashboard initialization complete")
        except Exception as e:
            logger.error(f"First-boot dashboard init failed: {e}")

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
            elif task.task_type == 'channel_post':
                success = await self._handle_channel_post_task(task)
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
                # Add timeout protection for command handlers
                try:
                    await asyncio.wait_for(handler(data), timeout=30.0)
                    self.metrics['messages_handled'] += 1
                    return True
                except asyncio.TimeoutError:
                    logger.error(f"Command handler timeout for: {command}")
                    return False
            else:
                # Unknown command - send help message
                chat_id = data.get('chat_id')
                user_id = data.get('user_id')
                if chat_id:
                    from i18n import t
                    # Get user language preference
                    user_language = await database.get_user_language(user_id) if user_id else None
                    lang = user_language or config.bot.default_language

                    help_text = f"""{t('unknown_command_title', lang)}

{t('available_commands', lang)}
{t('cmd_start', lang)}
{t('cmd_menu', lang)}
{t('cmd_report', lang)}
{t('cmd_status', lang)}
{t('cmd_clients', lang)}
{t('cmd_analytics', lang)}
{t('cmd_charts', lang)}
{t('cmd_help', lang)}

{t('admin_commands', lang)}
{t('cmd_dashboard', lang)}
{t('cmd_summary', lang)}
{t('cmd_finance', lang)}"""

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
                try:
                    await asyncio.wait_for(handler(data), timeout=30.0)
                    return True
                except asyncio.TimeoutError:
                    logger.error(f"Callback handler timeout for: {callback_data}")
                    return False
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
                try:
                    await asyncio.wait_for(handler(data), timeout=30.0)
                    return True
                except asyncio.TimeoutError:
                    logger.error(f"Conversation handler timeout for step: {step}")
                    return False
            else:
                # Clear conversation state for unknown steps
                user_id = data.get('user_id')
                if user_id:
                    await telegram_handler.clear_conversation_state(user_id)
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
            elif action == 'scan_stale_clients':
                results = await reminder_engine.scan_stale_clients()
                self.metrics['reminders_sent'] += results.get('reminders_created', 0)
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
        """Handle synchronization tasks (V2 only)."""
        try:
            sync_type = task.data.get('sync_type', 'full')

            if _sheet_sync_v2_mod.sheet_sync_v2 is None:
                logger.warning('Sync task skipped: SheetSyncV2 not initialized')
                return False

            if sync_type == 'full':
                stats = await _sheet_sync_v2_mod.sheet_sync_v2.full_sync()
                self.metrics['sync_operations'] += 1
                logger.info(f'V2 sync: {stats["total_imported"]} imported, {stats["total_exported"]} exported')
                return True
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

    async def _handle_channel_post_task(self, task: BotTask) -> bool:
        """Handle channel posting tasks."""
        try:
            action = task.data.get('action')

            if action == 'post_summary':
                results = await telegram_handler.post_channel_summary()
                return results.get('success', False)
            else:
                logger.warning(f"Unknown channel post action: {action}")
                return False

        except Exception as e:
            logger.error(f"Error handling channel post task: {e}")
            return False

    async def perform_maintenance(self):
        """Perform periodic maintenance operations when no urgent tasks."""
        current_time = datetime.now()

        # Check for scheduled maintenance operations
        if not self.last_reminder_check or (current_time - self.last_reminder_check).total_seconds() > config.bot.reminder_check_interval:
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

            # Scan for stale clients during working hours
            stale_scan_task = BotTask(
                task_type='reminder',
                priority=3,
                data={'action': 'scan_stale_clients'}
            )
            await database.create_task(stale_scan_task)

            self.last_reminder_check = current_time

        if not self.last_health_check or (current_time - self.last_health_check).total_seconds() > config.bot.health_check_interval:
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
                    'parameters': {'date': current_time.strftime('%Y-%m-%d')},
                    'recipients': config.bot.manager_chat_ids
                }
            )
            await database.create_task(daily_report_task)
            self.last_report_generation = current_time.date()

        # Schedule channel posts during working hours
        # Use broadcast_channel_id first; fall back to report_channel_id
        _post_channel_id = config.bot.broadcast_channel_id or config.bot.report_channel_id
        if _post_channel_id and self._should_post_channel_summary():
            channel_post_task = BotTask(
                task_type='channel_post',
                priority=3,
                data={'action': 'post_summary'}
            )
            await database.create_task(channel_post_task)
            self.last_channel_post = current_time

        # V2: Process pending reminders
        try:
            pending_v2 = await database_v2.get_pending_reminders_v2(before=current_time)
            for reminder in pending_v2:
                staff = await database_v2.get_staff_by_id(reminder.staff_id)
                if staff:
                    await telegram_handler.send_message(staff.tg_chat_id, reminder.message)
                    await database_v2.mark_reminder_sent(reminder.id)
                    self.metrics['reminders_sent'] += 1
        except Exception as e:
            logger.error(f'V2 reminder processing error: {e}')

        # V2: Stale client detection every 5 minutes — auto-create reminders
        if not self.last_v2_stale_check or (current_time - self.last_v2_stale_check).total_seconds() > 300:
            try:
                from working_hours import is_working_hours
                if is_working_hours():
                    stale = await database_v2.get_all_stale_clients(hours=72)
                    if stale:
                        logger.info(f'V2: {len(stale)} stale clients detected')
                        from models_v2 import Reminder as ReminderV2
                        for client in stale:
                            # Check if we already sent a stale reminder for this client today
                            existing = await database_v2.get_pending_reminders_v2()
                            already_reminded = any(
                                r.client_id == client.id and r.source == 'auto_stale'
                                for r in existing
                            )
                            if not already_reminded:
                                reminder = ReminderV2(
                                    staff_id=client.frontdesk_id,
                                    client_id=client.id,
                                    remind_at=current_time,
                                    message=f'⚠️ Client {client.phone} ({client.status.value}) has been stale for 72+ hours. Follow up!',
                                    source='auto_stale',
                                )
                                await database_v2.create_reminder(reminder)
                                logger.info(f'V2: Auto-reminder created for stale client {client.phone}')
            except Exception as e:
                logger.error(f'V2 stale check error: {e}')
            self.last_v2_stale_check = current_time

        # V2: Daily stats auto-calculation (end of day ~22:00)
        if not self.last_v2_stats_calc or self.last_v2_stats_calc.date() < current_time.date():
            if current_time.hour >= 21:
                try:
                    await database_v2.recalculate_all_today_stats()
                    logger.info('V2: Daily stats recalculated')
                    self.last_v2_stats_calc = current_time
                except Exception as e:
                    logger.error(f'V2 daily stats error: {e}')

        # V2: RAG re-indexing hourly
        if not self.last_rag_reindex or (current_time - self.last_rag_reindex).total_seconds() > 3600:
            try:
                from engines.rag_engine import rebuild_index
                await rebuild_index()
                logger.info('V2: RAG index refreshed')
            except Exception as e:
                logger.debug(f'V2 RAG reindex skipped (Ollama may be down): {e}')
            self.last_rag_reindex = current_time

        # Policy: auto-mark dead clients every 6 hours
        if not self.last_policy_dead_check or (current_time - self.last_policy_dead_check).total_seconds() > 21600:
            try:
                from engines.policy_engine import auto_mark_dead_clients
                count = await auto_mark_dead_clients()
                if count > 0:
                    logger.info(f'Policy: auto-marked {count} clients as dead (14d inactive)')
            except Exception as e:
                logger.error(f'Policy auto_mark_dead_clients error: {e}')
            self.last_policy_dead_check = current_time

        # Policy: daily target check at end of day (~21:00)
        if (
            not self.last_policy_target_check
            or self.last_policy_target_check.date() < current_time.date()
        ) and current_time.hour >= 21:
            try:
                from engines.policy_engine import check_daily_targets_missed
                missed = await check_daily_targets_missed()
                for m in missed:
                    logger.warning(f'Policy: daily target missed — {m["team"]}: {m["actual"]}/{m["target"]}')
                self.last_policy_target_check = current_time
            except Exception as e:
                logger.error(f'Policy daily target check error: {e}')

        # Obsidian: save daily report at end of day (~21:30)
        if (
            not self.last_obsidian_daily_report
            or self.last_obsidian_daily_report.date() < current_time.date()
        ) and current_time.hour >= 21 and current_time.minute >= 30:
            try:
                from engines.obsidian_brain import obsidian_brain
                await database_v2.recalculate_all_today_stats()
                all_staff = await database_v2.get_all_staff()
                lines = [f'# Daily Report — {current_time.strftime("%Y-%m-%d")}', '']
                total_leads = total_reg = total_orders = 0
                for s in all_staff:
                    stat = await database_v2.get_daily_stats(s.id, current_time.date())
                    if stat:
                        lines.append(f'- {s.display_name}: 🆕{stat.new_leads} ✅{stat.registered} 🎯{stat.new_orders}')
                        total_leads += stat.new_leads
                        total_reg += stat.registered
                        total_orders += stat.new_orders
                lines.append(f'\n**TOTAL**: 🆕{total_leads} ✅{total_reg} 🎯{total_orders}')
                report_text = '\n'.join(lines)
                await obsidian_brain.save_daily_report(current_time.strftime('%Y-%m-%d'), report_text)
                logger.info('Obsidian: daily report saved')
                self.last_obsidian_daily_report = current_time
            except Exception as e:
                logger.error(f'Obsidian daily report error: {e}')

        # V2: Bidirectional Sheets sync on sync_interval (default 3600s)
        if (
            _sheet_sync_v2_mod.sheet_sync_v2 is not None
            and (
                not self.last_v2_sheet_sync
                or (current_time - self.last_v2_sheet_sync).total_seconds() >= config.bot.sync_interval
            )
        ):
            try:
                stats = await _sheet_sync_v2_mod.sheet_sync_v2.full_sync()
                self.metrics['sync_operations'] += 1
                logger.info(
                    f'V2 Sheets full_sync: {stats["total_imported"]} imported, '
                    f'{stats["total_exported"]} exported'
                )
            except Exception as e:
                logger.error(f'V2 Sheets full_sync error: {e}')

            # Refresh all 5 dashboard tabs after sync
            if _dashboard_mod.dashboard_sheets is not None:
                try:
                    await _dashboard_mod.dashboard_sheets.refresh_all_tabs()
                    logger.info('V2: Dashboard tabs refreshed')
                except Exception as e:
                    logger.error(f'V2 dashboard refresh error: {e}')

            # NocoDB parallel sync — mirror SQLite → NocoDB on same interval
            if _nocodb_writer is not None:
                try:
                    noco_stats = await _nocodb_writer.sync_all_from_sqlite()
                    logger.info(f'NocoDB sync: {noco_stats}')
                except Exception as e:
                    logger.error(f'NocoDB sync error: {e}')

            self.last_v2_sheet_sync = current_time

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

    def _should_post_channel_summary(self) -> bool:
        """Check if channel summary should be posted."""
        from working_hours import is_working_hours

        if not is_working_hours():
            return False

        if not (config.bot.broadcast_channel_id or config.bot.report_channel_id) or not config.bot.report_interval_hours:
            return False

        current_time = datetime.now()
        interval_seconds = config.bot.report_interval_hours * 3600

        # Check if enough time has passed since last post
        should_post = (
            not self.last_channel_post or
            (current_time - self.last_channel_post).total_seconds() >= interval_seconds
        )

        return should_post

    async def shutdown(self):
        """Perform graceful shutdown with transaction safety."""
        try:
            logger.info("Starting graceful shutdown...")

            # Stop accepting new tasks first
            self.running = False

            # Wait for current tasks to complete (with timeout)
            await asyncio.sleep(2.0)  # Give current tasks time to finish

            # Mark any processing tasks as pending for retry on restart
            try:
                async with database.get_connection() as db:
                    # Use a transaction for safety
                    await db.execute("BEGIN TRANSACTION")

                    # Get count of tasks being reset
                    cursor = await db.execute("""
                        SELECT COUNT(*) FROM bot_tasks WHERE status = 'processing'
                    """)
                    count = (await cursor.fetchone())[0]

                    if count > 0:
                        await db.execute("""
                            UPDATE bot_tasks SET status = 'pending', updated_at = CURRENT_TIMESTAMP
                            WHERE status = 'processing'
                        """)
                        logger.info(f"Reset {count} processing tasks to pending")

                    await db.execute("COMMIT")

            except Exception as e:
                logger.error(f"Error resetting tasks during shutdown: {e}")
                # Continue with shutdown even if task reset fails

            # Disconnect Telegram client safely
            try:
                await telegram_handler.disconnect()
                logger.info("Telegram client disconnected")
            except Exception as e:
                logger.error(f"Error disconnecting Telegram: {e}")

            # Close NocoDB writer session
            global _nocodb_writer
            if _nocodb_writer is not None:
                try:
                    await _nocodb_writer.close()
                    logger.info("NocoDB writer closed")
                except Exception as e:
                    logger.error(f"Error closing NocoDB writer: {e}")

            # Close V2 persistent DB connection
            try:
                await database_v2.close()
                logger.info("DatabaseV2 connection closed")
            except Exception as e:
                logger.error(f"Error closing DatabaseV2: {e}")

            # Clear any remaining conversation states
            try:
                await database.cleanup_old_conversation_states(hours_old=1)  # Clear old states
            except Exception as e:
                logger.error(f"Error clearing conversation states: {e}")

            # Log final metrics
            uptime = datetime.now() - self.metrics['uptime_start']
            logger.info(f"Shutdown metrics: {self.metrics}")
            logger.info(f"Total uptime: {uptime}")

            logger.info("Graceful shutdown completed")

        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
            # Don't re-raise to ensure shutdown completes

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

    async def health_check(self) -> Dict[str, Any]:
        """Comprehensive health check for monitoring."""
        health = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'checks': {},
            'version': '1.0.0'
        }

        # Check database
        try:
            stats = await database.get_stats()
            health['checks']['database'] = {
                'status': 'healthy',
                'tables': len(stats),
                'records': sum(stats.values())
            }
        except Exception as e:
            health['checks']['database'] = {
                'status': 'unhealthy',
                'error': str(e)
            }
            health['status'] = 'degraded'

        # Check Telegram connection
        try:
            telegram_healthy = await telegram_handler.health_check()
            health['checks']['telegram'] = {
                'status': 'healthy' if telegram_healthy else 'unhealthy',
                'connected': telegram_healthy
            }
            if not telegram_healthy:
                health['status'] = 'degraded'
        except Exception as e:
            health['checks']['telegram'] = {
                'status': 'unhealthy',
                'error': str(e)
            }
            health['status'] = 'degraded'

        # Check Google Sheets sync (V2)
        health['checks']['sheets_sync'] = {
            'status': 'healthy' if _sheet_sync_v2_mod.sheet_sync_v2 is not None else 'degraded',
            'last_sync': self.last_v2_sheet_sync.isoformat() if self.last_v2_sheet_sync else None,
            'engine': 'v2',
        }

        # Check NocoDB private sheets
        health['checks']['nocodb'] = {
            'status': 'healthy' if _nocodb_writer is not None else 'unavailable',
            'url': os.getenv('NOCODB_URL', 'http://localhost:8080'),
        }

        # Overall status
        check_statuses = [check['status'] for check in health['checks'].values()]
        if 'unhealthy' in check_statuses:
            health['status'] = 'unhealthy'
        elif 'degraded' in check_statuses:
            health['status'] = 'degraded'

        return health


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