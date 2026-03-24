"""Configuration settings for Team Records Bot."""
import os
import logging
from typing import Dict, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TelegramConfig:
    """Telegram API configuration."""
    api_id: int = None
    api_hash: str = None
    phone: str = None
    session_file: str = "team_records_bot.session"

    # SOCKS5 proxy for Tor
    proxy_host: str = "127.0.0.1"
    proxy_port: int = 9050
    proxy_type: str = "socks5"

    def validate(self):
        """Validate telegram configuration."""
        if not self.api_id:
            raise ValueError("Telegram API ID is required (set TG_API_ID environment variable)")
        if not self.api_hash:
            raise ValueError("Telegram API hash is required (set TG_API_HASH environment variable)")
        if not self.phone:
            raise ValueError("Telegram phone number is required (set TG_PHONE environment variable)")

        # Validate phone format
        import re
        if not re.match(r'^\+\d{10,15}$', self.phone):
            raise ValueError("Telegram phone must be in format +1234567890")


@dataclass
class GoogleSheetsConfig:
    """Google Sheets configuration."""
    spreadsheet_url: str = None
    spreadsheet_id: str = None
    title: str = None

    # Schema type 1: Client Records GIDs (11 sheets)
    client_records_gids: List[int] = None

    # Schema type 2: Performance Tracking (MAO UK)
    performance_gid: int = 794990782

    # Schema type 3: Financial Records
    financial_gid: int = 1395471353

    # Schema type 4: Daily Summary Report
    daily_summary_gid: int = 975912225

    # Schema type 5: Team Weekly Assessment
    weekly_assessment_gid: int = 265525062

    def __post_init__(self):
        if self.client_records_gids is None:
            self.client_records_gids = [
                550866614, 1230058767, 729968113, 1920827915, 776863779,
                1279281320, 1592176479, 2126441720, 217401166, 91396268, 1698881195
            ]


@dataclass
class DatabaseConfig:
    """Database configuration."""
    db_path: str = "team_records.db"
    backup_interval: int = 3600  # seconds
    backup_dir: str = "backups"


@dataclass
class BotConfig:
    """General bot configuration."""
    # Reminder settings
    day1_reminder_hours: int = 24
    day2_reminder_hours: int = 48

    # Report scheduling
    daily_report_time: str = "18:00"  # 6 PM
    weekly_report_day: int = 5  # Friday (0=Monday, 6=Sunday)

    # Loop settings
    loop_interval: float = 5.0  # seconds

    # Admin settings
    admin_chat_ids: List[int] = None
    manager_chat_ids: List[int] = None

    # Sync settings
    sync_interval: int = 3600  # seconds (1 hour)

    # Maintenance intervals
    reminder_check_interval: int = 300  # 5 minutes
    health_check_interval: int = 1800  # 30 minutes
    conversation_cleanup_hours: int = 24  # 24 hours

    # Rate limiting
    telegram_max_messages_per_minute: int = 30
    telegram_min_delay_between_messages: float = 0.05

    # Database settings
    max_db_connections: int = 20
    query_timeout: int = 30

    # Google Sheets settings
    sheets_rate_limit_delay: float = 0.5
    sheets_batch_size: int = 3
    sheets_batch_delay: float = 2.0

    # Language settings
    default_language: str = "zh"  # Chinese
    supported_languages: List[str] = None

    def __post_init__(self):
        if self.admin_chat_ids is None:
            self.admin_chat_ids = []
        if self.manager_chat_ids is None:
            self.manager_chat_ids = []
        if self.supported_languages is None:
            self.supported_languages = ["zh", "en"]


class Config:
    """Main configuration class."""

    def __init__(self):
        self.telegram = TelegramConfig()
        self.google_sheets = GoogleSheetsConfig()
        self.database = DatabaseConfig()
        self.bot = BotConfig()

        # Load environment variables
        self._load_env_vars()

        # Validate only if running as main bot (not during import/testing)
        # self._validate_config()

    def _load_env_vars(self):
        """Load configuration from environment variables and .env file."""
        # Try loading .env file
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

        # Telegram config
        self.telegram.api_id = int(os.getenv("TG_API_ID") or os.getenv("API_ID") or "0")
        self.telegram.api_hash = os.getenv("TG_API_HASH") or os.getenv("API_HASH") or ""
        self.telegram.phone = os.getenv("TG_PHONE") or os.getenv("PHONE") or ""

        if os.getenv("TG_SESSION_FILE"):
            self.telegram.session_file = os.getenv("TG_SESSION_FILE")

        # Proxy config
        if os.getenv("PROXY_HOST"):
            self.telegram.proxy_host = os.getenv("PROXY_HOST")
        if os.getenv("PROXY_PORT"):
            self.telegram.proxy_port = int(os.getenv("PROXY_PORT"))

        # Google Sheets config - REQUIRED
        self.google_sheets.spreadsheet_id = os.getenv("SHEETS_ID") or os.getenv("SPREADSHEET_ID") or "1rkgRG95lxUgeplceekMY3Z_NZIBKxjTKNwLSpw04xgQ"
        self.google_sheets.spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{self.google_sheets.spreadsheet_id}/"
        self.google_sheets.title = os.getenv("SHEETS_TITLE", "Team Records")

        # Database config
        if os.getenv("DB_PATH"):
            self.database.db_path = os.getenv("DB_PATH")

        # Bot config
        if os.getenv("ADMIN_CHAT_IDS"):
            try:
                self.bot.admin_chat_ids = [int(x.strip()) for x in os.getenv("ADMIN_CHAT_IDS").split(",") if x.strip()]
            except ValueError as e:
                raise ValueError(f"Invalid ADMIN_CHAT_IDS format: {e}")
        if os.getenv("MANAGER_CHAT_IDS"):
            try:
                self.bot.manager_chat_ids = [int(x.strip()) for x in os.getenv("MANAGER_CHAT_IDS").split(",") if x.strip()]
            except ValueError as e:
                raise ValueError(f"Invalid MANAGER_CHAT_IDS format: {e}")

    def _get_required_env(self, key: str, default: str = None) -> str:
        """Get required environment variable."""
        value = os.getenv(key)
        if not value:
            raise ValueError(f"Required environment variable {key} is not set")
        return value

    def _get_required_int_env(self, key: str, default: int = None) -> int:
        """Get required integer environment variable."""
        value = self._get_required_env(key)
        try:
            return int(value)
        except ValueError:
            raise ValueError(f"Environment variable {key} must be a valid integer")

    def _validate_config(self):
        """Validate all configuration sections."""
        # Validate telegram config
        self.telegram.validate()

        # Validate Google Sheets config
        if not self.google_sheets.spreadsheet_id:
            raise ValueError("Google Sheets spreadsheet ID is required (set SHEETS_ID environment variable)")

        # Validate numeric ranges
        if self.bot.loop_interval <= 0:
            raise ValueError("Bot loop interval must be positive")

        if self.bot.sync_interval <= 0:
            raise ValueError("Sync interval must be positive")

        # Validate admin/manager chat IDs are actually integers
        for chat_id in self.bot.admin_chat_ids:
            if not isinstance(chat_id, int):
                raise ValueError(f"Admin chat ID must be integer: {chat_id}")

        for chat_id in self.bot.manager_chat_ids:
            if not isinstance(chat_id, int):
                raise ValueError(f"Manager chat ID must be integer: {chat_id}")


# Global config instance - initialized safely
config = None

def initialize_config():
    """Initialize the global configuration."""
    global config
    try:
        config = Config()
        return config
    except Exception as e:
        logger.error(f"Failed to initialize configuration: {e}")
        raise

def get_config():
    """Get the configuration, initializing if needed."""
    global config
    if config is None:
        config = initialize_config()
    return config

# Initialize config on import, but allow graceful handling of failures
try:
    config = Config()
except Exception as e:
    import logging
    logging.getLogger(__name__).error(f"Configuration initialization failed: {e}")
    # Don't raise here - let the application handle it gracefully


# Frontdesk staff mapping (for schema type 1)
FRONTDESK_STAFF = {
    "阿YIM": "Amy",
    "阿俊": "Jun",
    # Add more staff mappings as needed
}


# Category mappings
CATEGORY_TYPES = {
    "飞机筛选": "plane_filter",
    "RCS筛选": "rcs_filter",
    # Add more category mappings as needed
}


# Status mappings
STATUS_TYPES = {
    "注册": "registered",
    "不注册": "not_registered",
}