"""Configuration settings for Team Records Bot."""
import os
from typing import Dict, List
from dataclasses import dataclass


@dataclass
class TelegramConfig:
    """Telegram API configuration."""
    api_id: int = 32326218
    api_hash: str = "2f44dfd151f291c8a4ec5c405eb51e94"
    phone: str = "+31651036582"
    session_file: str = "team_records_bot.session"

    # SOCKS5 proxy for Tor
    proxy_host: str = "127.0.0.1"
    proxy_port: int = 9050
    proxy_type: str = "socks5"


@dataclass
class GoogleSheetsConfig:
    """Google Sheets configuration."""
    spreadsheet_url: str = "https://docs.google.com/spreadsheets/d/1rkgRG95lxUgeplceekMY3Z_NZIBKxjTKNwLSpw04xgQ/"
    spreadsheet_id: str = "1rkgRG95lxUgeplceekMY3Z_NZIBKxjTKNwLSpw04xgQ"
    title: str = "欧洲前台客户"

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

    def _load_env_vars(self):
        """Load configuration from environment variables."""
        # Telegram config
        if os.getenv("TG_API_ID"):
            self.telegram.api_id = int(os.getenv("TG_API_ID"))
        if os.getenv("TG_API_HASH"):
            self.telegram.api_hash = os.getenv("TG_API_HASH")
        if os.getenv("TG_PHONE"):
            self.telegram.phone = os.getenv("TG_PHONE")
        if os.getenv("TG_SESSION_FILE"):
            self.telegram.session_file = os.getenv("TG_SESSION_FILE")

        # Proxy config
        if os.getenv("PROXY_HOST"):
            self.telegram.proxy_host = os.getenv("PROXY_HOST")
        if os.getenv("PROXY_PORT"):
            self.telegram.proxy_port = int(os.getenv("PROXY_PORT"))

        # Google Sheets config
        if os.getenv("SHEETS_ID"):
            self.google_sheets.spreadsheet_id = os.getenv("SHEETS_ID")

        # Database config
        if os.getenv("DB_PATH"):
            self.database.db_path = os.getenv("DB_PATH")

        # Bot config
        if os.getenv("ADMIN_CHAT_IDS"):
            self.bot.admin_chat_ids = [int(x.strip()) for x in os.getenv("ADMIN_CHAT_IDS").split(",")]
        if os.getenv("MANAGER_CHAT_IDS"):
            self.bot.manager_chat_ids = [int(x.strip()) for x in os.getenv("MANAGER_CHAT_IDS").split(",")]


# Global config instance
config = Config()


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