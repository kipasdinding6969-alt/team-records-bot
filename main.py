"""Team Records Bot - Main Ralph Loop Implementation."""
import asyncio
import logging
import signal
import sys
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timedelta
import traceback
import os

from config import config
from database_v2 import database_v2
from telegram_handler import telegram_handler
from models_v2 import BotTask, ReportTemplate

# Import V2 handlers
from handlers_v2.quick_actions import QUICK_ACTIONS_COMMANDS, QUICK_ACTIONS_CALLBACKS, QUICK_ACTIONS_CONVERSATIONS
from handlers_v2.pipeline import PIPELINE_COMMANDS, PIPELINE_CALLBACKS, PIPELINE_CONVERSATIONS
from handlers_v2.management import MANAGEMENT_COMMANDS, MANAGEMENT_CALLBACKS, MANAGEMENT_CONVERSATIONS
from handlers_v2.registration_v2 import REGISTRATION_V2_COMMANDS, REGISTRATION_V2_CALLBACKS, REGISTRATION_V2_CONVERSATIONS
from handlers_v2.group_chat import GROUP_COMMANDS, GROUP_CALLBACKS, GROUP_CONVERSATIONS
from handlers_v2.gamification import GAMIFICATION_COMMANDS, GAMIFICATION_CALLBACKS, GAMIFICATION_CONVERSATIONS
from handlers_v2.voice import VOICE_COMMANDS, VOICE_CALLBACKS, VOICE_CONVERSATIONS
from handlers_v2.menu import MENU_COMMANDS, MENU_CALLBACKS, MENU_CONVERSATIONS
from handlers_v2.gamification_v2 import GAMIFICATION_V2_COMMANDS, GAMIFICATION_V2_CALLBACKS, GAMIFICATION_V2_CONVERSATIONS
from handlers_v2.followup_handler import FOLLOWUP_HANDLER_COMMANDS, FOLLOWUP_HANDLER_CALLBACKS, FOLLOWUP_HANDLER_CONVERSATIONS
from handlers_v2.mini_app import MINI_APP_COMMANDS, MINI_APP_CALLBACKS, MINI_APP_CONVERSATIONS
from handlers_v2.nl_handler import NL_HANDLER_COMMANDS, NL_HANDLER_CALLBACKS, NL_HANDLER_CONVERSATIONS
from handlers_v2.inline_flows import INLINE_FLOWS_COMMANDS, INLINE_FLOWS_CALLBACKS, INLINE_FLOWS_CONVERSATIONS
from handlers_v2.broadcast_handler import BROADCAST_COMMANDS, BROADCAST_CALLBACKS, BROADCAST_CONVERSATIONS
from handlers_v2.export_handler import EXPORT_HANDLER_COMMANDS, EXPORT_HANDLER_CALLBACKS, EXPORT_HANDLER_CONVERSATIONS
from handlers_v2.tags import TAGS_COMMANDS, TAGS_CALLBACKS, TAGS_CONVERSATIONS
from handlers_v2.timeline import TIMELINE_COMMANDS, TIMELINE_CALLBACKS, TIMELINE_CONVERSATIONS
from handlers_v2.sla import SLA_COMMANDS, SLA_CALLBACKS, SLA_CONVERSATIONS
from handlers_v2.coaching import COACHING_COMMANDS, COACHING_CALLBACKS, COACHING_CONVERSATIONS
from handlers_v2.persistent_keyboard import (
    KEYBOARD_COMMANDS, KEYBOARD_CALLBACKS, KEYBOARD_CONVERSATIONS, KEYBOARD_ROUTES,
)
from handlers_v2.commission_handler import (
    COMMISSION_COMMANDS, COMMISSION_CALLBACKS, COMMISSION_CONVERSATIONS,
    auto_calculate_deposit_commission, auto_calculate_registration_commission,
)
from handlers_v2.report_handler import REPORT_COMMANDS, REPORT_CALLBACKS, REPORT_CONVERSATIONS
from handlers_v2.handoff_handler import HANDOFF_COMMANDS, HANDOFF_CALLBACKS, HANDOFF_CONVERSATIONS
from handlers_v2.phase16_commands import PHASE16_COMMANDS, PHASE16_CALLBACKS, PHASE16_CONVERSATIONS
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
        self.last_task_cleanup = None
        self.last_contest_maintenance = None
        self.last_streak_maintenance = None
        self.last_followup_processing = None
        self.last_morning_digest = None
        self.last_evening_digest = None
        self.last_sla_check = None

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

            # Initialize V2 database with persistent connection
            await database_v2.initialize()
            await database_v2.connect()
            logger.info("DatabaseV2 initialized (persistent connection)")

            # Initialize Telegram handler
            await telegram_handler.initialize()
            logger.info("Telegram handler initialized")

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

            # Seed default message templates — idempotent
            try:
                await database_v2.seed_default_templates()
            except Exception as e:
                logger.warning(f"seed_default_templates failed: {e}")

            # Seed gamification v2 badges — idempotent
            try:
                await database_v2.seed_badges()
            except Exception as e:
                logger.warning(f"seed_badges failed: {e}")

            # Seed organization units from staff teams — idempotent
            try:
                await database_v2.seed_organization_units()
            except Exception as e:
                logger.warning(f"seed_organization_units failed: {e}")

            # Seed default follow-up sequences + register status-change hook
            try:
                from engines.followup_engine import seed_default_sequences, register_hooks
                await seed_default_sequences()
                register_hooks()
            except Exception as e:
                logger.warning(f"followup seed/hooks failed: {e}")

            # Seed commission rules + register commission hooks
            try:
                await database_v2.seed_commission_rules()
                from database_v2 import _status_change_hooks
                _status_change_hooks.append(auto_calculate_registration_commission)
                logger.info("Commission rules seeded, hooks registered")
            except Exception as e:
                logger.warning(f"Commission setup failed: {e}")

            # Register V2 bot commands with Telegram (visible in command menu)
            await self._register_bot_commands()

            # Set Menu Button → Mini App for all users
            await self._set_menu_button()

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
            async with database_v2.get_connection() as db:
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
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(
                sig,
                lambda s=sig: (
                    logger.info(f"Received signal {s}, initiating graceful shutdown..."),
                    setattr(self, 'running', False),
                ),
            )

    async def _register_handlers(self):
        """Register all V2 command, callback, and conversation handlers."""
        all_commands = {}
        all_commands.update(QUICK_ACTIONS_COMMANDS)
        all_commands.update(PIPELINE_COMMANDS)
        all_commands.update(MANAGEMENT_COMMANDS)
        all_commands.update(REGISTRATION_V2_COMMANDS)
        all_commands.update(GROUP_COMMANDS)
        all_commands.update(GAMIFICATION_COMMANDS)
        all_commands.update(VOICE_COMMANDS)
        all_commands.update(MENU_COMMANDS)
        all_commands.update(GAMIFICATION_V2_COMMANDS)
        all_commands.update(FOLLOWUP_HANDLER_COMMANDS)
        all_commands.update(MINI_APP_COMMANDS)
        all_commands.update(NL_HANDLER_COMMANDS)
        all_commands.update(INLINE_FLOWS_COMMANDS)
        all_commands.update(BROADCAST_COMMANDS)
        all_commands.update(EXPORT_HANDLER_COMMANDS)  # overrides management.py CSV export
        all_commands.update(TAGS_COMMANDS)
        all_commands.update(TIMELINE_COMMANDS)
        all_commands.update(SLA_COMMANDS)
        all_commands.update(COACHING_COMMANDS)
        all_commands.update(KEYBOARD_COMMANDS)
        all_commands.update(COMMISSION_COMMANDS)
        all_commands.update(REPORT_COMMANDS)
        all_commands.update(HANDOFF_COMMANDS)
        all_commands.update(PHASE16_COMMANDS)

        all_callbacks = {}
        all_callbacks.update(QUICK_ACTIONS_CALLBACKS)
        all_callbacks.update(PIPELINE_CALLBACKS)
        all_callbacks.update(MANAGEMENT_CALLBACKS)
        all_callbacks.update(REGISTRATION_V2_CALLBACKS)
        all_callbacks.update(GROUP_CALLBACKS)
        all_callbacks.update(GAMIFICATION_CALLBACKS)
        all_callbacks.update(VOICE_CALLBACKS)
        all_callbacks.update(MENU_CALLBACKS)
        all_callbacks.update(GAMIFICATION_V2_CALLBACKS)
        all_callbacks.update(FOLLOWUP_HANDLER_CALLBACKS)
        all_callbacks.update(MINI_APP_CALLBACKS)
        all_callbacks.update(NL_HANDLER_CALLBACKS)
        all_callbacks.update(INLINE_FLOWS_CALLBACKS)
        all_callbacks.update(BROADCAST_CALLBACKS)
        all_callbacks.update(EXPORT_HANDLER_CALLBACKS)
        all_callbacks.update(TAGS_CALLBACKS)
        all_callbacks.update(TIMELINE_CALLBACKS)
        all_callbacks.update(SLA_CALLBACKS)
        all_callbacks.update(COACHING_CALLBACKS)
        all_callbacks.update(KEYBOARD_CALLBACKS)
        all_callbacks.update(COMMISSION_CALLBACKS)
        all_callbacks.update(REPORT_CALLBACKS)
        all_callbacks.update(HANDOFF_CALLBACKS)
        all_callbacks.update(PHASE16_CALLBACKS)

        all_conversations = {}
        all_conversations.update(QUICK_ACTIONS_CONVERSATIONS)
        all_conversations.update(PIPELINE_CONVERSATIONS)
        all_conversations.update(MANAGEMENT_CONVERSATIONS)
        all_conversations.update(REGISTRATION_V2_CONVERSATIONS)
        all_conversations.update(GROUP_CONVERSATIONS)
        all_conversations.update(GAMIFICATION_CONVERSATIONS)
        all_conversations.update(VOICE_CONVERSATIONS)
        all_conversations.update(MENU_CONVERSATIONS)
        all_conversations.update(GAMIFICATION_V2_CONVERSATIONS)
        all_conversations.update(FOLLOWUP_HANDLER_CONVERSATIONS)
        all_conversations.update(MINI_APP_CONVERSATIONS)
        all_conversations.update(NL_HANDLER_CONVERSATIONS)
        all_conversations.update(INLINE_FLOWS_CONVERSATIONS)
        all_conversations.update(BROADCAST_CONVERSATIONS)
        all_conversations.update(EXPORT_HANDLER_CONVERSATIONS)
        all_conversations.update(TAGS_CONVERSATIONS)
        all_conversations.update(TIMELINE_CONVERSATIONS)
        all_conversations.update(SLA_CONVERSATIONS)
        all_conversations.update(COACHING_CONVERSATIONS)
        all_conversations.update(KEYBOARD_CONVERSATIONS)
        all_conversations.update(COMMISSION_CONVERSATIONS)
        all_conversations.update(REPORT_CONVERSATIONS)
        all_conversations.update(HANDOFF_CONVERSATIONS)
        all_conversations.update(PHASE16_CONVERSATIONS)

        self.command_handlers = all_commands
        self.callback_handlers = all_callbacks
        self.conversation_handlers = all_conversations

        logger.info(f"Registered {len(all_commands)} commands, {len(all_callbacks)} callbacks, {len(all_conversations)} conversation handlers")

    async def _perform_health_checks(self):
        """Perform initial health checks."""
        try:
            # Check database connection
            stats = await database_v2.get_stats()
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
                BotCommand('start',  '🚀 开始'),
                BotCommand('me',     '📊 我的仪表板'),
                BotCommand('add',    '➕ 添加客户'),
                BotCommand('app',    '📊 打开看板'),
                BotCommand('search', '🔍 搜索客户'),
                BotCommand('help',   '❓ 帮助'),
            ]
            await bot_client(SetBotCommandsRequest(
                scope=BotCommandScopeDefault(),
                lang_code='',
                commands=commands,
            ))
            logger.info(f"Registered {len(commands)} bot commands with Telegram")
        except Exception as e:
            logger.warning(f"_register_bot_commands failed: {e}")

    async def _set_menu_button(self):
        """Set the Telegram Menu Button to open the Mini App for all users."""
        try:
            import aiohttp
            from handlers_v2.mini_app import MINI_APP_URL
            bot_token = os.getenv('BOT_TOKEN', '')
            if not bot_token:
                logger.warning("_set_menu_button: no BOT_TOKEN, skipping")
                return
            url = f"https://api.telegram.org/bot{bot_token}/setChatMenuButton"
            payload = {
                "menu_button": {
                    "type": "web_app",
                    "text": "📊 CRM看板",
                    "web_app": {"url": MINI_APP_URL},
                }
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    data = await resp.json()
                    if data.get('ok'):
                        logger.info("Menu Button set to Mini App via Bot API")
                    else:
                        logger.warning(f"_set_menu_button API error: {data}")
        except Exception as e:
            logger.warning(f"_set_menu_button failed: {e}")

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
            task = await database_v2.get_next_task()

            if task:
                # Mark task as processing
                await database_v2.update_task_status(task.id, 'processing')
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
                await database_v2.update_task_status(task.id, 'completed')
                self.metrics['tasks_processed'] += 1
                logger.info(f"Task {task.id} completed successfully")
            else:
                # Check if we should retry
                if task.attempts < task.max_attempts:
                    await database_v2.update_task_status(task.id, 'pending')
                    logger.info(f"Task {task.id} failed, will retry (attempt {task.attempts + 1})")
                else:
                    await database_v2.update_task_status(task.id, 'failed', 'Max attempts exceeded')
                    logger.error(f"Task {task.id} failed permanently after {task.attempts} attempts")

        except Exception as e:
            logger.error(f"Error executing task {task.id}: {e}")
            await database_v2.update_task_status(task.id, 'failed', str(e))
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
            elif event_type == 'voice':
                return await self._handle_voice_task(data)
            elif event_type == 'nl_message':
                return await self._handle_nl_message_task(data)
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
                    user_language = await database_v2.get_user_language(user_id) if user_id else None
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

    async def _handle_voice_task(self, data: Dict[str, Any]) -> bool:
        """Handle voice message task — delegate to voice handler."""
        try:
            from handlers_v2.voice import handle_voice_message
            await asyncio.wait_for(handle_voice_message(data), timeout=60.0)
            return True
        except asyncio.TimeoutError:
            logger.error("Voice handler timed out")
            return False
        except Exception as e:
            logger.error(f"Error handling voice task: {e}")
            return False

    async def _handle_nl_message_task(self, data: Dict[str, Any]) -> bool:
        """Handle plain-text NL message — check keyboard routes first, then NL handler."""
        try:
            # Check persistent keyboard button texts BEFORE NL handler
            text = (data.get('text') or '').strip()
            if text in KEYBOARD_ROUTES:
                handler = KEYBOARD_ROUTES[text]
                await asyncio.wait_for(handler(data), timeout=30.0)
                return True

            from handlers_v2.nl_handler import handle_nl_message
            await asyncio.wait_for(handle_nl_message(data), timeout=35.0)
            return True
        except asyncio.TimeoutError:
            logger.error("NL message handler timed out")
            return False
        except Exception as e:
            logger.error(f"Error handling nl_message task: {e}")
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
        """Handle reminder-related tasks (V2 — processes via maintenance loop)."""
        # V2 reminders are processed directly in _maint_v2_reminders / _maint_v2_stale_check.
        # Legacy reminder tasks are acknowledged and completed silently.
        logger.debug(f"Legacy reminder task acknowledged: {task.data.get('action', 'unknown')}")
        return True

    async def _handle_report_task(self, task: BotTask) -> bool:
        """Handle report generation tasks (V2 — uses channel summaries)."""
        try:
            # V2 reports go through post_channel_summary / dashboard_sheets.
            # For legacy report tasks, attempt to send a channel summary.
            results = await telegram_handler.post_channel_summary()
            self.metrics['reports_generated'] += 1
            return results.get('success', False)
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
                await database_v2.cleanup_old_tasks()
            elif action == 'cleanup_old_reminders':
                # V2 reminders auto-clean via mark_reminder_sent
                pass
            elif action == 'backup_database':
                await database_v2.backup_database()
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
        await self._maint_health_check(current_time)
        await self._maint_schedule_daily_report(current_time)
        await self._maint_schedule_channel_post(current_time)
        await self._maint_v2_reminders(current_time)
        await self._maint_v2_stale_check(current_time)
        await self._maint_v2_daily_stats(current_time)
        await self._maint_rag_reindex(current_time)
        await self._maint_policy_dead_check(current_time)
        await self._maint_policy_target_check(current_time)
        await self._maint_obsidian_report(current_time)
        await self._maint_v2_sheet_sync(current_time)
        await self._maint_task_cleanup(current_time)
        await self._maint_contest_maintenance(current_time)
        await self._maint_streak_maintenance(current_time)
        await self._maint_followup_processing(current_time)
        await self._maint_morning_digest(current_time)
        await self._maint_evening_digest(current_time)
        await self._maint_sla_check(current_time)

    async def _maint_health_check(self, current_time: datetime):
        """Schedule periodic health check task."""
        if not self.last_health_check or (current_time - self.last_health_check).total_seconds() > config.bot.health_check_interval:
            health_task = BotTask(
                task_type='maintenance',
                priority=4,
                data={'action': 'health_check'}
            )
            await database_v2.create_task(health_task)
            self.last_health_check = current_time

    async def _maint_schedule_daily_report(self, current_time: datetime):
        """Schedule daily report if time has come."""
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
            await database_v2.create_task(daily_report_task)
            self.last_report_generation = current_time.date()

    async def _maint_schedule_channel_post(self, current_time: datetime):
        """Schedule channel summary post during working hours."""
        _post_channel_id = config.bot.broadcast_channel_id or config.bot.report_channel_id
        if _post_channel_id and self._should_post_channel_summary():
            channel_post_task = BotTask(
                task_type='channel_post',
                priority=3,
                data={'action': 'post_summary'}
            )
            await database_v2.create_task(channel_post_task)
            self.last_channel_post = current_time

    async def _maint_v2_reminders(self, current_time: datetime):
        """Process V2 pending reminders."""
        try:
            pending_v2 = await database_v2.get_pending_reminders_v2(before=current_time)
            for reminder in pending_v2:
                staff = await database_v2.get_staff_by_id(reminder.staff_id)
                if staff:
                    try:
                        await telegram_handler.send_message(staff.tg_chat_id, reminder.message)
                        await database_v2.mark_reminder_sent(reminder.id)
                        self.metrics['reminders_sent'] += 1
                    except Exception as send_err:
                        logger.warning(f'Reminder {reminder.id} send failed (staff_id={reminder.staff_id}, '
                                       f'chat_id={staff.tg_chat_id}): {send_err}')
                        # Mark as sent to prevent infinite retry loop on unresolvable entities
                        await database_v2.mark_reminder_sent(reminder.id)
                else:
                    logger.warning(f'Reminder {reminder.id}: staff_id={reminder.staff_id} not found, marking sent')
                    await database_v2.mark_reminder_sent(reminder.id)
        except Exception as e:
            logger.error(f'V2 reminder processing error: {e}')

    async def _maint_v2_stale_check(self, current_time: datetime):
        """V2 stale client detection every 5 minutes."""
        if not self.last_v2_stale_check or (current_time - self.last_v2_stale_check).total_seconds() > 300:
            try:
                from working_hours import is_working_hours
                if is_working_hours():
                    stale = await database_v2.get_all_stale_clients(hours=72)
                    if stale:
                        logger.info(f'V2: {len(stale)} stale clients detected')
                        from models_v2 import Reminder as ReminderV2
                        # Fetch all pending reminders once to avoid N+1 queries in the loop.
                        existing = await database_v2.get_pending_reminders_v2()
                        for client in stale:
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

    async def _maint_v2_daily_stats(self, current_time: datetime):
        """Recalculate V2 daily stats at end of day (~21:00)."""
        if not self.last_v2_stats_calc or self.last_v2_stats_calc.date() < current_time.date():
            if current_time.hour >= 21:
                try:
                    await database_v2.recalculate_all_today_stats()
                    logger.info('V2: Daily stats recalculated')
                    self.last_v2_stats_calc = current_time
                except Exception as e:
                    logger.error(f'V2 daily stats error: {e}')

    async def _maint_rag_reindex(self, current_time: datetime):
        """Rebuild RAG index hourly."""
        if not self.last_rag_reindex or (current_time - self.last_rag_reindex).total_seconds() > 3600:
            try:
                from engines.rag_engine import rebuild_index
                await rebuild_index()
                logger.info('V2: RAG index refreshed')
            except Exception as e:
                logger.debug(f'V2 RAG reindex skipped (Ollama may be down): {e}')
            self.last_rag_reindex = current_time

    async def _maint_policy_dead_check(self, current_time: datetime):
        """Auto-mark dead clients every 6 hours."""
        if not self.last_policy_dead_check or (current_time - self.last_policy_dead_check).total_seconds() > 21600:
            try:
                from engines.policy_engine import auto_mark_dead_clients
                count = await auto_mark_dead_clients()
                if count > 0:
                    logger.info(f'Policy: auto-marked {count} clients as dead (14d inactive)')
            except Exception as e:
                logger.error(f'Policy auto_mark_dead_clients error: {e}')
            self.last_policy_dead_check = current_time

    async def _maint_policy_target_check(self, current_time: datetime):
        """Check daily targets missed at end of day (~21:00)."""
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

    async def _maint_obsidian_report(self, current_time: datetime):
        """Save Obsidian daily report at end of day (~21:30)."""
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

    async def _maint_v2_sheet_sync(self, current_time: datetime):
        """V2 bidirectional Sheets sync on sync_interval (default 3600s)."""
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

            if _dashboard_mod.dashboard_sheets is not None:
                try:
                    await _dashboard_mod.dashboard_sheets.refresh_all_tabs()
                    logger.info('V2: Dashboard tabs refreshed')
                except Exception as e:
                    logger.error(f'V2 dashboard refresh error: {e}')

            if _nocodb_writer is not None:
                try:
                    noco_stats = await _nocodb_writer.sync_all_from_sqlite()
                    logger.info(f'NocoDB sync: {noco_stats}')
                except Exception as e:
                    logger.error(f'NocoDB sync error: {e}')

            self.last_v2_sheet_sync = current_time

    async def _maint_contest_maintenance(self, current_time: datetime):
        """Auto-end expired contests and refresh scores every 15 minutes."""
        if not self.last_contest_maintenance or (current_time - self.last_contest_maintenance).total_seconds() > 900:
            try:
                ended = await database_v2.auto_end_expired_contests()
                if ended > 0:
                    logger.info(f'Contest: auto-ended {ended} expired contest(s)')
                contest = await database_v2.get_active_contest()
                if contest:
                    await database_v2.refresh_contest_scores(contest['id'])
            except Exception as e:
                logger.error(f'Contest maintenance error: {e}')
            self.last_contest_maintenance = current_time

    async def _maint_task_cleanup(self, current_time: datetime):
        """Cleanup completed/failed tasks older than 24 hours."""
        if not self.last_task_cleanup or (current_time - self.last_task_cleanup).total_seconds() > 86400:
            try:
                await database_v2.cleanup_old_tasks(days_old=1)
                logger.debug('Task queue: cleaned up completed tasks older than 24h')
            except Exception as e:
                logger.error(f'Task cleanup error: {e}')
            self.last_task_cleanup = current_time

    async def _maint_streak_maintenance(self, current_time: datetime):
        """Reset weekly streak freezes on Monday and check daily streaks."""
        if not self.last_streak_maintenance or (current_time - self.last_streak_maintenance).total_seconds() > 3600:
            try:
                if current_time.weekday() == 0 and current_time.hour < 6:
                    await database_v2.reset_weekly_streak_freezes()
                    logger.info('Streaks: weekly freeze reset (Monday)')
            except Exception as e:
                logger.error(f'Streak maintenance error: {e}')
            self.last_streak_maintenance = current_time

    async def _maint_followup_processing(self, current_time: datetime):
        """Process due follow-up queue items every 30 minutes."""
        if not self.last_followup_processing or (current_time - self.last_followup_processing).total_seconds() > 1800:
            try:
                from engines.followup_engine import process_due_followups
                await process_due_followups()
            except Exception as e:
                logger.error(f'Follow-up processing error: {e}')
            self.last_followup_processing = current_time

    async def _maint_morning_digest(self, current_time: datetime):
        """Send morning digest at 8:00 AM local time (once per day)."""
        if (
            not self.last_morning_digest
            or self.last_morning_digest.date() < current_time.date()
        ) and current_time.hour == 8:
            try:
                from engines.digest_engine import send_morning_digests
                await send_morning_digests()
                self.last_morning_digest = current_time
            except Exception as e:
                logger.error(f'Morning digest error: {e}')

    async def _maint_evening_digest(self, current_time: datetime):
        """Send evening digest at 6:00 PM local time (once per day)."""
        if (
            not self.last_evening_digest
            or self.last_evening_digest.date() < current_time.date()
        ) and current_time.hour == 18:
            try:
                from engines.digest_engine import send_evening_digests
                await send_evening_digests()
                self.last_evening_digest = current_time
            except Exception as e:
                logger.error(f'Evening digest error: {e}')

    async def _maint_sla_check(self, current_time: datetime):
        """Check open SLA events every 5 minutes for warnings and escalations."""
        if not self.last_sla_check or (current_time - self.last_sla_check).total_seconds() > 300:
            try:
                from engines.sla_engine import check_sla_breaches
                team_leader_chat = None
                if config.bot.manager_chat_ids:
                    team_leader_chat = config.bot.manager_chat_ids[0] if isinstance(
                        config.bot.manager_chat_ids, list) else config.bot.manager_chat_ids
                await check_sla_breaches(telegram_handler, team_leader_chat)
            except Exception as e:
                logger.error(f'SLA check error: {e}')
            self.last_sla_check = current_time

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
                async with database_v2.get_connection() as db:
                    cursor = await db.execute(
                        "SELECT COUNT(*) FROM bot_tasks WHERE status = 'processing'")
                    count = (await cursor.fetchone())[0]

                    if count > 0:
                        await db.execute(
                            "UPDATE bot_tasks SET status = 'pending', updated_at = CURRENT_TIMESTAMP"
                            " WHERE status = 'processing'")
                        await db.commit()
                        logger.info(f"Reset {count} processing tasks to pending")

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
                await database_v2.cleanup_old_conversation_states(hours_old=1)
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
            'database_stats': await database_v2.get_stats(),
            'task_queue_size': (await database_v2.get_stats()).get('bot_tasks', 0)
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
            stats = await database_v2.get_stats()
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