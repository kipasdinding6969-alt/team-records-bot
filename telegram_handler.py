"""Telegram handler using Telethon client."""
import asyncio
import logging
import time
from typing import Dict, Callable, Any, Optional, List
import re
import socks
from collections import deque
from datetime import datetime, timedelta

from telethon import TelegramClient, events, Button
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
from telethon.tl.types import User, Chat, Channel

from config import config
from database_v2 import database_v2
from models_v2 import BotTask

logger = logging.getLogger(__name__)


class TelegramHandler:
    """Handles Telegram client operations and message routing."""

    def __init__(self):
        self.client: Optional[TelegramClient] = None  # User client (existing session)
        self.bot_client: Optional[TelegramClient] = None  # Bot client (NEW for interactive messages)
        self.handlers: Dict[str, Callable] = {}
        # Removed: using database-only conversation states
        self.is_authenticated = False

        # Rate limiting
        self.message_timestamps = deque()
        self.max_messages_per_minute = config.bot.telegram_max_messages_per_minute
        self.min_delay_between_messages = config.bot.telegram_min_delay_between_messages
        self._rate_limit_lock = asyncio.Lock()

    async def initialize(self):
        """Initialize Telegram clients with proxy and authentication."""
        # Setup SOCKS5 proxy for Tor
        proxy = None
        if config.telegram.proxy_host and config.telegram.proxy_port:
            proxy = (socks.SOCKS5, config.telegram.proxy_host, config.telegram.proxy_port)

        # Create user client (existing session)
        self.client = TelegramClient(
            config.telegram.session_file,
            config.telegram.api_id,
            config.telegram.api_hash,
            proxy=proxy
        )

        try:
            await self.client.start(phone=config.telegram.phone)
            logger.info("Telegram user client initialized successfully")

            # Create bot client if bot token is available
            if config.telegram.bot_token:
                bot_session_file = config.telegram.session_file.replace('.session', '_api.session')
                self.bot_client = TelegramClient(
                    bot_session_file,
                    config.telegram.api_id,
                    config.telegram.api_hash,
                    proxy=proxy
                )

                await self.bot_client.start(bot_token=config.telegram.bot_token)
                logger.info("Telegram bot client initialized successfully")

                # Set up event handlers on bot client (for interactive messages)
                self._setup_event_handlers()
            else:
                logger.warning("No bot token provided - running in user-only mode")
                # Fallback to user client for events
                self._setup_event_handlers()

            self.is_authenticated = True

        except Exception as e:
            logger.error(f"Failed to initialize Telegram client(s): {e}")
            raise

    async def disconnect(self):
        """Disconnect Telegram clients."""
        if self.client and self.client.is_connected():
            await self.client.disconnect()
            logger.info("Telegram user client disconnected")

        if self.bot_client and self.bot_client.is_connected():
            await self.bot_client.disconnect()
            logger.info("Telegram bot client disconnected")

    def _setup_event_handlers(self):
        """Set up Telethon event handlers on the appropriate client."""
        # Use bot client for interactive messages if available, otherwise fallback to user client
        event_client = self.bot_client if self.bot_client else self.client

        @event_client.on(events.NewMessage(pattern=r'^/\w+'))
        async def command_handler(event):
            """Handle bot commands."""
            try:
                await self._handle_command(event)
            except Exception as e:
                logger.error(f"Error handling command: {e}")
                await self._send_error_message(event.chat_id, "Sorry, something went wrong.")

        @event_client.on(events.NewMessage(func=lambda e: bool(e.voice)))
        async def voice_handler(event):
            """Handle voice note messages."""
            try:
                await self._handle_voice(event)
            except Exception as e:
                logger.error(f"Error handling voice: {e}")

        @event_client.on(events.NewMessage(func=lambda e: not e.text.startswith('/')))
        async def message_handler(event):
            """Handle non-command messages (for conversations)."""
            try:
                await self._handle_conversation(event)
            except Exception as e:
                logger.error(f"Error handling conversation: {e}")

        @event_client.on(events.CallbackQuery)
        async def callback_handler(event):
            """Handle inline keyboard callbacks."""
            try:
                await self._handle_callback(event)
            except Exception as e:
                logger.error(f"Error handling callback: {e}")

    async def _handle_command(self, event):
        """Parse and route command to appropriate handler."""
        user = await event.get_sender()
        chat_id = event.chat_id
        message = event.message.text

        # Parse command and arguments
        parts = message.split()
        command = parts[0][1:].split('@')[0].lower()  # Remove '/' prefix and @botname suffix
        args = parts[1:] if len(parts) > 1 else []

        # Update user activity
        await self._update_user_activity(user, chat_id)

        # Detect chat type (private, group, supergroup, channel)
        chat = await event.get_chat()
        if hasattr(chat, 'megagroup') and chat.megagroup:
            chat_type = 'supergroup'
        elif hasattr(chat, 'broadcast') and chat.broadcast:
            chat_type = 'channel'
        elif hasattr(chat, 'gigagroup') and chat.gigagroup:
            chat_type = 'supergroup'
        elif hasattr(chat, 'title'):
            chat_type = 'group'
        else:
            chat_type = 'private'

        # Get forum topic (message_thread_id) if present
        reply_to_msg_id = None
        if hasattr(event.message, 'reply_to') and event.message.reply_to:
            reply_to_msg_id = getattr(event.message.reply_to, 'reply_to_top_id', None) or \
                              getattr(event.message.reply_to, 'reply_to_msg_id', None)

        # Create task for Ralph Loop processing
        task_data = {
            'event_type': 'command',
            'command': command,
            'args': ' '.join(args),  # Join args into string (handlers expect string)
            'user_id': user.id,
            'chat_id': chat_id,
            'chat_type': chat_type,
            'chat_title': getattr(chat, 'title', None),
            'message_thread_id': reply_to_msg_id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
        }

        # Group middleware: detect team from linked group or team_config
        if chat_type in ('group', 'supergroup'):
            try:
                from handlers_v2.group_chat import group_middleware
                should_process = await group_middleware(task_data)
                if not should_process:
                    return  # Drop non-command messages in groups
            except Exception as e:
                logger.debug(f"Group middleware error: {e}")

            # Also try auto-detecting team from team_config (by chat_id)
            if 'group_team' not in task_data:
                try:
                    from team_config import team_config
                    for tid in team_config.get_all_team_ids():
                        if team_config.get_team_chat_id(tid) == chat_id:
                            task_data['group_team'] = tid
                            break
                except Exception:
                    pass

        task = BotTask(
            task_type='message',
            priority=1,
            data=task_data
        )

        await database_v2.create_task(task)
        logger.info(f"Created task for command /{command} from user {user.id} (chat_type={chat_type})")

    async def _handle_voice(self, event):
        """Download voice OGG and queue a voice task for the Ralph Loop."""
        import tempfile
        user = await event.get_sender()
        chat_id = event.chat_id

        # Download to /tmp/ immediately — Telegram file refs are short-lived
        try:
            client_to_use = self.bot_client if self.bot_client else self.client
            suffix = '.ogg'
            tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False, dir='/tmp')
            tmp.close()
            await client_to_use.download_media(event.message, file=tmp.name)
            voice_path = tmp.name
        except Exception as e:
            logger.error(f"Failed to download voice from {user.id}: {e}")
            return

        await self._update_user_activity(user, chat_id)

        task_data = {
            'event_type': 'voice',
            'user_id': user.id,
            'chat_id': chat_id,
            'voice_path': voice_path,
        }
        task = BotTask(task_type='message', priority=1, data=task_data)
        await database_v2.create_task(task)
        logger.info(f"Queued voice task for user {user.id} → {voice_path}")

    async def _handle_conversation(self, event):
        """Handle conversation states or route plain text to NL handler."""
        user = await event.get_sender()
        chat_id = event.chat_id
        message = event.message.text

        # Only process private chats for NL handler
        chat = await event.get_chat()
        is_private = not hasattr(chat, 'title')

        # Check if user has an active conversation state in database
        conversation_state = await self.get_conversation_state(user.id)
        if conversation_state:
            # Create task for conversation handling
            task_data = {
                'event_type': 'conversation',
                'message': message,
                'user_id': user.id,
                'chat_id': chat_id,
                'state': conversation_state
            }

            task = BotTask(
                task_type='message',
                priority=1,
                data=task_data
            )

            await database_v2.create_task(task)
            logger.info(f"Created conversation task for user {user.id}")

        elif is_private and message:
            # No active conversation state — route to NL handler (lowest priority)
            task_data = {
                'event_type': 'nl_message',
                'text': message,
                'user_id': user.id,
                'chat_id': chat_id,
            }
            task = BotTask(
                task_type='message',
                priority=2,  # lower priority than commands (1)
                data=task_data
            )
            await database_v2.create_task(task)
            logger.info(f"Created nl_message task for user {user.id}: {message[:40]!r}")

    async def _handle_callback(self, event):
        """Handle inline keyboard button callbacks."""
        user = await event.get_sender()
        chat_id = event.chat_id
        callback_data = event.data.decode()

        # Create task for callback handling
        task_data = {
            'event_type': 'callback',
            'callback_data': callback_data,
            'user_id': user.id,
            'chat_id': chat_id,
            'message_id': event.message_id
        }

        task = BotTask(
            task_type='message',
            priority=1,
            data=task_data
        )

        await database_v2.create_task(task)
        await event.answer()  # Answer callback to remove loading state

    async def _update_user_activity(self, user: User, chat_id: int):
        """Update or create staff record in V2 database."""
        await database_v2.register_or_update_activity(
            user.id, chat_id, user.username, user.first_name, user.last_name
        )

    async def _rate_limit_check(self):
        """Check and enforce rate limiting for async safety."""
        async with self._rate_limit_lock:
            current_time = time.time()

            # Remove timestamps older than 1 minute to prevent memory leak
            while self.message_timestamps and current_time - self.message_timestamps[0] > 60:
                self.message_timestamps.popleft()

            # Enforce minimum delay first (always applies)
            if self.message_timestamps and current_time - self.message_timestamps[-1] < self.min_delay_between_messages:
                sleep_time = self.min_delay_between_messages - (current_time - self.message_timestamps[-1])
                should_sleep = sleep_time
            else:
                should_sleep = 0

            # Check if we're hitting rate limit
            if len(self.message_timestamps) >= self.max_messages_per_minute:
                if self.message_timestamps:
                    rate_limit_sleep = 60 - (current_time - self.message_timestamps[0]) + 1
                    should_sleep = max(should_sleep, rate_limit_sleep)

            # Record this message timestamp before sleeping
            self.message_timestamps.append(current_time)

        # Sleep outside the lock to avoid blocking other coroutines
        if should_sleep > 0:
            if should_sleep > self.min_delay_between_messages:
                logger.warning(f"Rate limit reached, sleeping for {should_sleep:.2f} seconds")
            await asyncio.sleep(max(should_sleep, 0))

    # Message sending methods
    async def send_message(self, chat_id: int, text: str, parse_mode: str = None,
                          reply_markup: Any = None, disable_web_page_preview: bool = True,
                          reply_to: int = None):
        """Send a text message with rate limiting.

        reply_to: forum topic message-thread-id (Telethon reply_to param).
        """
        await self._rate_limit_check()

        try:
            # Use bot client for interactive messages if available, otherwise fallback to user client
            client_to_use = self.bot_client if self.bot_client else self.client
            await client_to_use.send_message(
                chat_id,
                text,
                parse_mode=parse_mode,
                buttons=reply_markup,
                link_preview=not disable_web_page_preview,
                reply_to=reply_to,
            )
        except Exception as e:
            logger.error(f"Failed to send message to {chat_id}: {e}")
            raise

    async def send_to_team(self, team_id: str, message: str, topic: str = 'daily',
                           parse_mode: str = 'html'):
        """Send a message to a team's forum topic.

        topic: partial name used to look up the topic id (e.g. '日报').
        """
        try:
            from team_config import team_config
            chat_id = team_config.get_team_chat_id(team_id)
            if not chat_id:
                logger.warning(f"send_to_team: no chat_id for team '{team_id}'")
                return
            topic_id = team_config.get_team_topic_id(team_id, topic)
            await self.send_message(chat_id, message, parse_mode=parse_mode, reply_to=topic_id)
            logger.info(f"Sent message to team '{team_id}' topic '{topic}' (topic_id={topic_id})")
        except Exception as e:
            logger.error(f"send_to_team({team_id}) failed: {e}")

    async def send_to_broadcast(self, message: str, parse_mode: str = 'html'):
        """Send a message to the broadcast channel."""
        try:
            from team_config import team_config
            channel_id = team_config.get_broadcast_id() or config.bot.broadcast_channel_id
            if not channel_id:
                logger.warning("send_to_broadcast: no broadcast channel configured")
                return
            await self.send_message(channel_id, message, parse_mode=parse_mode)
            logger.info(f"Sent message to broadcast channel {channel_id}")
        except Exception as e:
            logger.error(f"send_to_broadcast failed: {e}")

    async def send_to_management(self, message: str, topic: str = 'summary',
                                  parse_mode: str = 'html'):
        """Send a message to the management group forum topic.

        topic: partial name (e.g. '总报表' or 'summary').
        """
        try:
            from team_config import team_config
            chat_id = team_config.get_management_id()
            if not chat_id:
                logger.warning("send_to_management: no management chat configured")
                return
            topic_id = team_config.get_management_topic_id(topic)
            await self.send_message(chat_id, message, parse_mode=parse_mode, reply_to=topic_id)
            logger.info(f"Sent message to management topic '{topic}' (topic_id={topic_id})")
        except Exception as e:
            logger.error(f"send_to_management failed: {e}")

    async def send_photo(self, chat_id: int, photo, caption: str = None,
                        reply_markup: Any = None):
        """Send a photo message."""
        try:
            # Use bot client for interactive messages if available, otherwise fallback to user client
            client_to_use = self.bot_client if self.bot_client else self.client
            await client_to_use.send_file(
                chat_id,
                photo,
                caption=caption,
                buttons=reply_markup
            )
        except Exception as e:
            logger.error(f"Failed to send photo to {chat_id}: {e}")

    async def send_document(self, chat_id: int, document, caption: str = None):
        """Send a document."""
        try:
            # Use bot client for interactive messages if available, otherwise fallback to user client
            client_to_use = self.bot_client if self.bot_client else self.client
            await client_to_use.send_file(
                chat_id,
                document,
                caption=caption
            )
        except Exception as e:
            logger.error(f"Failed to send document to {chat_id}: {e}")

    async def edit_message(self, chat_id: int, message_id: int, text: str,
                          reply_markup: Any = None):
        """Edit an existing message."""
        try:
            # Use bot client for interactive messages if available, otherwise fallback to user client
            client_to_use = self.bot_client if self.bot_client else self.client
            await client_to_use.edit_message(
                chat_id,
                message_id,
                text,
                buttons=reply_markup
            )
        except Exception as e:
            logger.error(f"Failed to edit message {message_id} in {chat_id}: {e}")

    async def delete_message(self, chat_id: int, message_id: int):
        """Delete a message."""
        try:
            # Use bot client for interactive messages if available, otherwise fallback to user client
            client_to_use = self.bot_client if self.bot_client else self.client
            await client_to_use.delete_messages(chat_id, [message_id])
        except Exception as e:
            logger.error(f"Failed to delete message {message_id} in {chat_id}: {e}")

    # Utility methods
    async def get_user_info(self, user_id: int) -> Optional[User]:
        """Get user information."""
        try:
            return await self.client.get_entity(user_id)
        except Exception as e:
            logger.error(f"Failed to get user info for {user_id}: {e}")
            return None

    async def get_chat_info(self, chat_id: int):
        """Get chat information."""
        try:
            return await self.client.get_entity(chat_id)
        except Exception as e:
            logger.error(f"Failed to get chat info for {chat_id}: {e}")
            return None

    async def check_user_permissions(self, chat_id: int, user_id: int) -> Dict[str, bool]:
        """Check user permissions in a chat."""
        try:
            permissions = await self.client.get_permissions(chat_id, user_id)
            return {
                'can_send_messages': permissions.send_messages,
                'can_edit_messages': permissions.edit_messages,
                'can_delete_messages': permissions.delete_messages,
                'is_admin': permissions.is_admin
            }
        except Exception as e:
            logger.error(f"Failed to check permissions for {user_id} in {chat_id}: {e}")
            return {}

    # Conversation state management - database_v2 backed
    async def set_conversation_state(self, user_id: int, state: Dict[str, Any]):
        """Set conversation state for a user."""
        await database_v2.set_conversation_state(user_id, state)

    async def get_conversation_state(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get conversation state for a user."""
        return await database_v2.get_conversation_state(user_id)

    async def clear_conversation_state(self, user_id: int):
        """Clear conversation state for a user."""
        await database_v2.clear_conversation_state(user_id)

    # Keyboard helpers
    @staticmethod
    def create_inline_keyboard(buttons: List[List[Dict[str, str]]]) -> List[List[Button]]:
        """Create inline keyboard markup."""
        keyboard = []
        for row in buttons:
            button_row = []
            for btn in row:
                if 'callback_data' in btn:
                    button_row.append(Button.inline(btn['text'], btn['callback_data']))
                elif 'url' in btn:
                    button_row.append(Button.url(btn['text'], btn['url']))
            keyboard.append(button_row)
        return keyboard

    @staticmethod
    def create_reply_keyboard(buttons: List[List[str]], resize: bool = True,
                            one_time: bool = False) -> List[List[Button]]:
        """Create reply keyboard markup."""
        keyboard = []
        for row in buttons:
            button_row = [Button.text(text) for text in row]
            keyboard.append(button_row)
        return keyboard

    # Error handling
    async def _send_error_message(self, chat_id: int, error_text: str):
        """Send error message to user."""
        await self.send_message(chat_id, f"❌ {error_text}")

    # Broadcast methods
    async def broadcast_to_admins(self, message: str):
        """Send message to all admin users."""
        for admin_id in config.bot.admin_chat_ids:
            try:
                await self.send_message(admin_id, message)
            except Exception as e:
                logger.error(f"Failed to send admin broadcast to {admin_id}: {e}")

    async def broadcast_to_managers(self, message: str):
        """Send message to all manager users."""
        for manager_id in config.bot.manager_chat_ids:
            try:
                await self.send_message(manager_id, message)
            except Exception as e:
                logger.error(f"Failed to send manager broadcast to {manager_id}: {e}")

    async def broadcast_to_team(self, message: str, role: str = None):
        """Send message to staff members with optional role filter."""
        async with database_v2.get_connection() as db:
            if role:
                cursor = await db.execute(
                    'SELECT tg_chat_id FROM staff WHERE is_active=1 AND role=?', (role,))
            else:
                cursor = await db.execute('SELECT tg_chat_id FROM staff WHERE is_active=1')
            chat_ids = [row[0] for row in await cursor.fetchall()]

        for chat_id in chat_ids:
            try:
                await self.send_message(chat_id, message)
            except Exception as e:
                logger.error(f"Failed to send team broadcast to {chat_id}: {e}")

    # Channel auto-posting
    async def post_channel_summary(self, channel_id: int = None) -> Dict[str, Any]:
        """Post summary to broadcast channel and per-team 日报 topics + management 总报表."""
        try:
            from working_hours import is_working_hours

            # Only post during working hours
            if not is_working_hours():
                return {'success': False, 'message': 'Outside working hours, skipping channel post'}

            # Resolve broadcast channel: prefer team_config, then explicit arg, then fallback
            try:
                from team_config import team_config as _tc
                broadcast_id = _tc.get_broadcast_id()
            except Exception:
                broadcast_id = None
            if not broadcast_id:
                broadcast_id = config.bot.broadcast_channel_id or channel_id or config.bot.report_channel_id

            if not broadcast_id:
                logger.warning("No broadcast channel ID configured")
                return {'success': False, 'message': 'No channel ID configured'}

            # Generate full summary message
            summary_message = await self._generate_channel_summary()

            # 1. Post to broadcast channel
            client = self.bot_client if self.bot_client else self.client
            await client.send_message(broadcast_id, summary_message, parse_mode='html')
            logger.info(f"Posted broadcast summary to {broadcast_id}")

            # 2. Post per-team stats to each team's 日报 topic
            try:
                from team_config import team_config as _tc
                for team_id in _tc.get_all_team_ids():
                    team_summary = await self._generate_team_summary(team_id)
                    await self.send_to_team(team_id, team_summary, topic='日报', parse_mode='html')
            except Exception as e:
                logger.error(f"Failed to post per-team summaries: {e}")

            # 3. Post management summary to 总报表 topic
            try:
                mgmt_summary = await self._generate_management_summary()
                await self.send_to_management(mgmt_summary, topic='总报表', parse_mode='html')
            except Exception as e:
                logger.error(f"Failed to post management summary: {e}")

            return {
                'success': True,
                'channel_id': broadcast_id,
                'message_length': len(summary_message),
            }

        except Exception as e:
            logger.error(f"Failed to post channel summary: {e}")
            return {'success': False, 'error': str(e)}

    async def _generate_channel_summary(self) -> str:
        """Generate channel summary with today's stats and team performance."""
        try:
            from datetime import date
            today = date.today()
            today_str = today.strftime('%Y-%m-%d')

            # Get today's statistics
            stats = await self._get_daily_stats(today_str)

            # Generate summary message
            summary = f"""📊 <b>团队日报</b>
🗓 {today.strftime('%Y年%m月%d日')}

<b>📈 今日数据:</b>
• 新增客户: {stats.get('new_clients', 0)}
• 完成注册: {stats.get('registrations', 0)}
• 待处理客户: {stats.get('pending_clients', 0)}
• 完成培训: {stats.get('training_complete', 0)}

<b>👥 团队排名:</b>"""

            # Add top performers
            top_performers = await self._get_top_performers(today_str)
            if top_performers:
                for i, performer in enumerate(top_performers[:5], 1):
                    medal = ['🥇', '🥈', '🥉', '4️⃣', '5️⃣'][i-1]
                    summary += f"\n{medal} {performer['name']} — {performer['registrations']}单"
            else:
                summary += "\n暂无数据"

            # Add pending alerts if any
            pending_count = stats.get('pending_clients', 0)
            stale_count = stats.get('stale_clients', 0)
            if pending_count > 0:
                summary += f"\n\n⚠️ <b>待跟进:</b> {pending_count} 个客户待处理"
            if stale_count > 0:
                summary += f"\n🔴 <b>超时警告:</b> {stale_count} 个客户超3天未更新"

            summary += f"\n\n🔄 下次更新: {(datetime.now() + timedelta(hours=config.bot.report_interval_hours)).strftime('%H:%M')}"

            return summary

        except Exception as e:
            logger.error(f"Failed to generate channel summary: {e}")
            return f"📊 <b>团队日报 / Daily Report</b>\n\n❌ 数据生成失败 / Failed to generate stats\n错误: {str(e)}"

    async def _generate_team_summary(self, team_id: str) -> str:
        """Generate per-team daily summary for posting to the team's 日报 topic."""
        try:
            from datetime import date
            from team_config import team_config as _tc
            today = date.today()
            today_str = today.strftime('%Y-%m-%d')
            team_info = _tc.get_team_info(team_id) or {}
            title = team_info.get('title', team_id)
            leader = team_info.get('leader', '')
            members = team_info.get('members', [])

            stats = await self._get_daily_stats(today_str)
            top = await self._get_top_performers(today_str)

            # Filter top performers to this team's members
            team_names = set(m.lower() for m in members)
            team_top = [p for p in top if p['name'].lower() in team_names]

            summary = f"""📊 <b>{title} — 日报</b>
🗓 {today.strftime('%Y年%m月%d日')}

<b>📈 今日数据:</b>
• 新增客户: {stats.get('new_clients', 0)}
• 完成注册: {stats.get('registrations', 0)}
• 待处理: {stats.get('pending_clients', 0)}

<b>👥 本组排名:</b>"""

            if team_top:
                medals = ['🥇', '🥈', '🥉', '4️⃣', '5️⃣']
                for i, p in enumerate(team_top[:5]):
                    summary += f"\n{medals[i]} {p['name']} — {p['registrations']}单"
            else:
                summary += "\n暂无数据"

            return summary

        except Exception as e:
            logger.error(f"Failed to generate team summary for {team_id}: {e}")
            return f"📊 <b>{team_id} 日报</b>\n\n❌ 数据生成失败: {e}"

    async def _generate_management_summary(self) -> str:
        """Generate management-level summary for the 总报表 topic."""
        try:
            from datetime import date
            from team_config import team_config as _tc
            today = date.today()
            today_str = today.strftime('%Y-%m-%d')

            stats = await self._get_daily_stats(today_str)
            top = await self._get_top_performers(today_str)

            summary = f"""📊 <b>管理层总报表</b>
🗓 {today.strftime('%Y年%m月%d日')}

<b>📈 全线数据:</b>
• 新增客户: {stats.get('new_clients', 0)}
• 完成注册: {stats.get('registrations', 0)}
• 待处理客户: {stats.get('pending_clients', 0)}
• 完成培训: {stats.get('training_complete', 0)}
• 超时警告: {stats.get('stale_clients', 0)}

<b>🏆 全线排名 TOP 5:</b>"""

            if top:
                medals = ['🥇', '🥈', '🥉', '4️⃣', '5️⃣']
                for i, p in enumerate(top[:5]):
                    summary += f"\n{medals[i]} {p['name']} — {p['registrations']}单 / {p['total_clients']}客"
            else:
                summary += "\n暂无数据"

            # Per-team breakdown
            summary += "\n\n<b>📋 各组概览:</b>"
            for team_id in _tc.get_all_team_ids():
                info = _tc.get_team_info(team_id) or {}
                title = info.get('title', team_id)
                members = info.get('members', [])
                team_names = set(m.lower() for m in members)
                team_regs = sum(p['registrations'] for p in top if p['name'].lower() in team_names)
                summary += f"\n• {title}: {team_regs}单"

            return summary

        except Exception as e:
            logger.error(f"Failed to generate management summary: {e}")
            return f"📊 <b>管理层总报表</b>\n\n❌ 数据生成失败: {e}"

    async def _get_daily_stats(self, date_str: str) -> Dict[str, int]:
        """Get daily statistics for channel summary (V2 schema)."""
        try:
            stats = {}
            async with database_v2.get_connection() as db:
                cursor = await db.execute(
                    'SELECT COUNT(*) FROM clients WHERE DATE(created_at) = ?', (date_str,))
                stats['new_clients'] = (await cursor.fetchone())[0]

                cursor = await db.execute(
                    """SELECT COUNT(*) FROM clients
                       WHERE status IN ('registered','training','ordered')
                       AND DATE(registered_at) = ?""", (date_str,))
                stats['registrations'] = (await cursor.fetchone())[0]

                cursor = await db.execute(
                    """SELECT COUNT(*) FROM clients
                       WHERE status IN ('new','contacted','replied')
                       AND DATE(created_at) >= DATE('now', '-7 days')""")
                stats['pending_clients'] = (await cursor.fetchone())[0]

                cursor = await db.execute(
                    """SELECT COUNT(*) FROM clients
                       WHERE status='training'
                       AND DATE(training_at) = ?""", (date_str,))
                stats['training_complete'] = (await cursor.fetchone())[0]

                stale_days = config.bot.stale_client_days if hasattr(config.bot, 'stale_client_days') else 3
                cursor = await db.execute(
                    f"""SELECT COUNT(*) FROM clients
                        WHERE status IN ('new','contacted','replied')
                        AND updated_at <= datetime('now', '-{stale_days} days')
                        AND updated_at >= datetime('now', '-30 days')""")
                stats['stale_clients'] = (await cursor.fetchone())[0]

            return stats

        except Exception as e:
            logger.error(f"Failed to get daily stats: {e}")
            return {}

    async def _get_top_performers(self, date_str: str) -> List[Dict[str, Any]]:
        """Get top performing frontdesk staff for today (V2 schema)."""
        try:
            async with database_v2.get_connection() as db:
                cursor = await db.execute(
                    """SELECT s.display_name,
                              COUNT(CASE WHEN c.registered_at IS NOT NULL
                                         AND DATE(c.registered_at) = ? THEN 1 END) AS registrations,
                              COUNT(c.id) AS total_clients
                       FROM staff s
                       LEFT JOIN clients c ON c.frontdesk_id = s.id
                       WHERE s.role NOT IN ('maintenance','manager','admin','leader')
                       GROUP BY s.id, s.display_name
                       ORDER BY registrations DESC, total_clients DESC
                       LIMIT 5""",
                    (date_str,))

                performers = []
                for row in await cursor.fetchall():
                    performers.append({
                        'name': row[0],
                        'registrations': row[1],
                        'total_clients': row[2],
                    })
                return performers

        except Exception as e:
            logger.error(f"Failed to get top performers: {e}")
            return []

    # Health check
    async def health_check(self) -> bool:
        """Check if clients are connected and authenticated."""
        try:
            # Check user client
            if not self.client or not self.client.is_connected():
                return False

            # Try to get self info from user client
            me = await self.client.get_me()
            if me is None:
                return False

            # Check bot client if available
            if self.bot_client:
                if not self.bot_client.is_connected():
                    return False

                # Try to get self info from bot client
                bot_me = await self.bot_client.get_me()
                if bot_me is None:
                    return False

            return True

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    # Session management
    async def logout(self):
        """Log out from Telegram clients."""
        try:
            if self.client:
                await self.client.log_out()
                logger.info("Logged out from Telegram user client")

            if self.bot_client:
                await self.bot_client.log_out()
                logger.info("Logged out from Telegram bot client")

            self.is_authenticated = False
        except Exception as e:
            logger.error(f"Failed to log out: {e}")


# Global telegram handler instance
telegram_handler = TelegramHandler()