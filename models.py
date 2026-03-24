"""Data models for Team Records Bot."""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from enum import Enum


class StatusType(Enum):
    """Registration status types."""
    REGISTERED = "注册"
    NOT_REGISTERED = "不注册"


@dataclass
class ClientRecord:
    """Schema Type 1: Client Records (11 sheets)."""
    row_num: int
    date: str  # Format: "X月X日"
    phone_remark: str  # e.g., "65 IPHONE SE"
    frontdesk: str  # e.g., "阿YIM", "阿俊"
    category: str  # e.g., "飞机筛选", "RCS筛选"
    recruiter: str
    frontdesk_number: str
    frontdesk_username: str  # e.g., "@ammeeeelia3589"
    client_number: str
    account_id: str
    first_day: str  # "注册" or "不注册"
    second_day: str  # "注册" or "不注册"
    client_condition: Optional[str] = None

    # Metadata
    sheet_gid: Optional[int] = None
    block_number: int = 1  # 1 or 2 (for side-by-side blocks)
    created_at: Optional[datetime] = field(default_factory=datetime.now)
    updated_at: Optional[datetime] = field(default_factory=datetime.now)


@dataclass
class PerformanceRecord:
    """Schema Type 2: Performance Tracking (MAO UK)."""
    name: str  # Frontdesk person name
    category: str  # Powder source type
    powder_count: int  # Total leads
    no_initial_reply: int  # Leads that didn't reply initially
    reply_rate: float  # Percentage
    stuck_explanation: int
    blocked_or_play: int
    been_scammed: int
    sent_link_no_reply: int
    completed_register: int
    review_rate: float  # Percentage
    completed_training: int
    scheduled_time: int
    withdrawal: int
    new_order: int
    conversion_rate: float  # Percentage
    new_kill: int
    dead_client: int

    # Metadata
    is_sum_row: bool = False
    created_at: Optional[datetime] = field(default_factory=datetime.now)
    updated_at: Optional[datetime] = field(default_factory=datetime.now)


@dataclass
class FinancialRecord:
    """Schema Type 3: Financial Records (杀猪盘)."""
    date: str
    account_id: str  # Format: "123456 / 123456"
    group_id: str  # Format: "1234 / 12345678910"
    frontdesk: str
    maintenance: str
    frontdesk_number: str
    platform: str  # e.g., "Iconnect"
    new_order_amount: Optional[float] = None  # Dollar amount
    pressure_amount: Optional[float] = None  # Dollar amount
    note: Optional[str] = None  # e.g., "工资杀6刀", "未回"

    # Progressive knife amounts (1-8)
    knife_1: Optional[float] = None
    knife_2: Optional[float] = None
    knife_3: Optional[float] = None
    knife_4: Optional[float] = None
    knife_5: Optional[float] = None
    knife_6: Optional[float] = None
    knife_7: Optional[float] = None
    knife_8: Optional[float] = None

    total_in: Optional[float] = None  # Total income

    # Role columns
    role_frontdesk: Optional[str] = None
    role_order_opener: Optional[str] = None
    role_newbie: Optional[str] = None
    role_group_chat: Optional[str] = None
    role_customer_service: Optional[str] = None
    role_maintenance: Optional[str] = None

    # Metadata
    created_at: Optional[datetime] = field(default_factory=datetime.now)
    updated_at: Optional[datetime] = field(default_factory=datetime.now)


@dataclass
class DailySummaryRecord:
    """Schema Type 4: Daily Summary Report."""
    frontdesk: str
    section: str  # "today", "cumulative", "today_training", "total_training"

    # Today's stats (section A)
    new_powder: Optional[int] = None
    today_reply: Optional[int] = None
    today_register: Optional[int] = None
    today_completed_training: Optional[int] = None
    today_withdraw: Optional[int] = None
    today_new_order: Optional[int] = None

    # Cumulative totals (section B)
    total_powder: Optional[int] = None
    total_reply: Optional[int] = None
    total_register: Optional[int] = None
    total_completed_training: Optional[int] = None
    total_withdraw: Optional[int] = None
    total_new_order: Optional[int] = None

    # Training details (sections C & D)
    today_training: Optional[int] = None
    today_not_withdraw: Optional[int] = None
    today_training_and_withdraw: Optional[int] = None
    today_conversion: Optional[int] = None

    # Metadata
    report_date: Optional[date] = field(default_factory=date.today)
    created_at: Optional[datetime] = field(default_factory=datetime.now)
    updated_at: Optional[datetime] = field(default_factory=datetime.now)


@dataclass
class TeamWeeklyRecord:
    """Schema Type 5: Team Weekly Assessment (5天考核)."""
    team_name: str  # e.g., "发财小组", "金鑫小组", "夏天小组"
    date_range: str  # Format: "1/6/2025 - 5/6/2025"
    frontdesk: str
    section: str  # "daily_activity" or "training_conversion"
    day_number: int  # 1-5

    # Daily Activity (section A)
    new_powder: Optional[int] = None
    today_reply: Optional[int] = None
    today_register: Optional[int] = None
    today_completed_training: Optional[int] = None
    today_withdraw: Optional[int] = None
    today_new_order: Optional[int] = None

    # Training Conversion (section B)
    today_training: Optional[int] = None
    today_not_withdraw: Optional[int] = None
    today_training_and_withdraw: Optional[int] = None

    # Summary row marker
    is_sum_row: bool = False

    # Metadata
    created_at: Optional[datetime] = field(default_factory=datetime.now)
    updated_at: Optional[datetime] = field(default_factory=datetime.now)


@dataclass
class TeamMember:
    """Team member registration."""
    user_id: int
    chat_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None
    frontdesk_name: Optional[str] = None  # Chinese name like "阿YIM"
    role: str = "frontdesk"  # frontdesk, admin, manager
    is_active: bool = True

    # Metadata
    registered_at: Optional[datetime] = field(default_factory=datetime.now)
    last_active: Optional[datetime] = field(default_factory=datetime.now)


@dataclass
class Reminder:
    """Scheduled reminder."""
    id: Optional[int] = None
    client_record_id: int = None
    frontdesk_user_id: int = None
    reminder_type: str = None  # "day1" or "day2"
    scheduled_time: Optional[datetime] = None
    message: Optional[str] = None
    is_sent: bool = False
    sent_at: Optional[datetime] = None

    # Metadata
    created_at: Optional[datetime] = field(default_factory=datetime.now)


@dataclass
class BotTask:
    """Task for Ralph Loop processing."""
    id: Optional[int] = None
    task_type: str = None  # "message", "reminder", "report", "sync"
    priority: int = 1  # 1 = highest, 5 = lowest
    data: Optional[Dict[str, Any]] = field(default_factory=dict)
    status: str = "pending"  # pending, processing, completed, failed
    scheduled_time: Optional[datetime] = None
    attempts: int = 0
    max_attempts: int = 3
    error_message: Optional[str] = None

    # Metadata
    created_at: Optional[datetime] = field(default_factory=datetime.now)
    updated_at: Optional[datetime] = field(default_factory=datetime.now)


@dataclass
class ReportTemplate:
    """Report generation template."""
    template_type: str  # "daily_summary", "weekly_assessment", "performance", "financial"
    frontdesk: Optional[str] = None
    team_name: Optional[str] = None
    date_range: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)


# Helper functions for model validation and conversion
def validate_status(status: str) -> bool:
    """Validate registration status."""
    return status in ["注册", "不注册"]


def validate_date_format(date_str: str) -> bool:
    """Validate Chinese date format (X月X日)."""
    import re
    pattern = r'^\d{1,2}月\d{1,2}日$'
    return bool(re.match(pattern, date_str))


def convert_percentage_string(pct_str: str) -> float:
    """Convert percentage string to float."""
    if not pct_str or pct_str == "-":
        return 0.0
    try:
        # Remove % sign if present
        clean_str = pct_str.replace("%", "").strip()
        return float(clean_str)
    except ValueError:
        return 0.0


def convert_amount_string(amount_str: str) -> Optional[float]:
    """Convert amount string to float."""
    if not amount_str or amount_str in ["-", "未回"]:
        return None
    try:
        # Remove currency symbols and extract number
        clean_str = amount_str.replace("$", "").replace("刀", "").strip()
        return float(clean_str)
    except ValueError:
        return None