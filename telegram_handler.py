"""Telegram handler using Telethon client."""
import asyncio
import logging
import time
from typing import Dict, Callable, Any, Optional, List
import re
import socks
from collections import deque

from telethon import TelegramClient, events, Button
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
from telethon.tl.types import User, Chat, Channel

from config import config
from database import database
from models import TeamMember, BotTask

logger = logging.getLogger(__name__)


class TelegramHandler:
    """Handles Telegram client operations and message routing."""

    def __init__(self):
        self.client: Optional[TelegramClient] = None
        self.handlers: Dict[str, Callable] = {}
        # Removed: using database-only conversation states
        self.is_authenticated = False

        # Rate limiting
        self.message_timestamps = deque()
        self.max_messages_per_minute = config.bot.telegram_max_messages_per_minute
        self.min_delay_between_messages = config.bot.telegram_min_delay_between_messages

    async def initialize(self):
        """Initialize Telegram client with proxy and authentication."""
        # Setup SOCKS5 proxy for Tor
        proxy = None
        if config.telegram.proxy_host and config.telegram.proxy_port:
            proxy = (socks.SOCKS5, config.telegram.proxy_host, config.telegram.proxy_port)

        # Create Telegram client
        self.client = TelegramClient(
            config.telegram.session_file,
            config.telegram.api_id,
            config.telegram.api_hash,
            proxy=proxy
        )

        try:
            await self.client.start(phone=config.telegram.phone)
            self.is_authenticated = True
            logger.info("Telegram client initialized successfully")

            # Set up event handlers
            self._setup_event_handlers()

        except Exception as e:
            logger.error(f"Failed to initialize Telegram client: {e}")
            raise

    async def disconnect(self):
        """Disconnect Telegram client."""
        if self.client and self.client.is_connected():
            await self.client.disconnect()
            logger.info("Telegram client disconnected")

    def _setup_event_handlers(self):
        """Set up Telethon event handlers."""

        @self.client.on(events.NewMessage(pattern=r'^/\w+'))
        async def command_handler(event):
            """Handle bot commands."""
            try:
                await self._handle_command(event)
            except Exception as e:
                logger.error(f"Error handling command: {e}")
                await self._send_error_message(event.chat_id, "Sorry, something went wrong.")

        @self.client.on(events.NewMessage(func=lambda e: not e.text.startswith('/')))
        async def message_handler(event):
            """Handle non-command messages (for conversations)."""
            try:
                await self._handle_conversation(event)
            except Exception as e:
                logger.error(f"Error handling conversation: {e}")

        @self.client.on(events.CallbackQuery)
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
        command = parts[0][1:]  # Remove '/' prefix
        args = parts[1:] if len(parts) > 1 else []

        # Update user activity
        await self._update_user_activity(user, chat_id)

        # Create task for Ralph Loop processing
        task_data = {
            'event_type': 'command',
            'command': command,
            'args': args,
            'user_id': user.id,
            'chat_id': chat_id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name
        }

        task = BotTask(
            task_type='message',
            priority=1,
            data=task_data
        )

        await database.create_task(task)
        logger.info(f"Created task for command /{command} from user {user.id}")

    async def _handle_conversation(self, event):
        """Handle conversation states for multi-step commands."""
        user = await event.get_sender()
        chat_id = event.chat_id
        message = event.message.text

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

            await database.create_task(task)
            logger.info(f"Created conversation task for user {user.id}")

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

        await database.create_task(task)
        await event.answer()  # Answer callback to remove loading state

    async def _update_user_activity(self, user: User, chat_id: int):
        """Update or create team member record."""
        member = await database.get_team_member_by_user_id(user.id)

        if member:
            await database.update_team_member_activity(user.id)
        else:
            # New user - create basic record (role will be assigned later)
            new_member = TeamMember(
                user_id=user.id,
                chat_id=chat_id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                role='unregistered'
            )
            await database.create_team_member(new_member)

    async def _rate_limit_check(self):
        """Check and enforce rate limiting with thread safety."""
        # Use a lock to prevent race conditions in rate limiting
        import threading
        if not hasattr(self, '_rate_limit_lock'):
            self._rate_limit_lock = threading.Lock()

        with self._rate_limit_lock:
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

        # Sleep outside the lock to avoid blocking other threads
        if should_sleep > 0:
            if should_sleep > self.min_delay_between_messages:
                logger.warning(f"Rate limit reached, sleeping for {should_sleep:.2f} seconds")
            await asyncio.sleep(max(should_sleep, 0))

    # Message sending methods
    async def send_message(self, chat_id: int, text: str, parse_mode: str = None,
                          reply_markup: Any = None, disable_web_page_preview: bool = True):
        """Send a text message with rate limiting."""
        await self._rate_limit_check()

        try:
            await self.client.send_message(
                chat_id,
                text,
                parse_mode=parse_mode,
                buttons=reply_markup,
                link_preview=not disable_web_page_preview
            )
        except Exception as e:
            logger.error(f"Failed to send message to {chat_id}: {e}")
            raise

    async def send_photo(self, chat_id: int, photo, caption: str = None,
                        reply_markup: Any = None):
        """Send a photo message."""
        try:
            await self.client.send_file(
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
            await self.client.send_file(
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
            await self.client.edit_message(
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
            await self.client.delete_messages(chat_id, [message_id])
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

    # Conversation state management - now database-backed
    async def set_conversation_state(self, user_id: int, state: Dict[str, Any]):
        """Set conversation state for a user."""
        await database.set_conversation_state(user_id, state)

    async def get_conversation_state(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get conversation state for a user."""
        return await database.get_conversation_state(user_id)

    async def clear_conversation_state(self, user_id: int):
        """Clear conversation state for a user."""
        await database.clear_conversation_state(user_id)

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
        """Send message to team members with optional role filter."""
        async with database.get_connection() as db:
            query = "SELECT chat_id FROM team_members WHERE is_active = TRUE"
            params = []

            if role:
                query += " AND role = ?"
                params.append(role)

            cursor = await db.execute(query, params)
            chat_ids = [row[0] for row in await cursor.fetchall()]

        for chat_id in chat_ids:
            try:
                await self.send_message(chat_id, message)
            except Exception as e:
                logger.error(f"Failed to send team broadcast to {chat_id}: {e}")

    # Health check
    async def health_check(self) -> bool:
        """Check if client is connected and authenticated."""
        try:
            if not self.client or not self.client.is_connected():
                return False

            # Try to get self info
            me = await self.client.get_me()
            return me is not None

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    # Session management
    async def logout(self):
        """Log out from Telegram."""
        try:
            if self.client:
                await self.client.log_out()
                self.is_authenticated = False
                logger.info("Logged out from Telegram")
        except Exception as e:
            logger.error(f"Failed to log out: {e}")


# Global telegram handler instance
telegram_handler = TelegramHandler()