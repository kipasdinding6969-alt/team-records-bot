"""V2 data models — pipeline-centric dataclasses."""
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Any, Dict, Optional, List
from enum import Enum


class StaffRole(str, Enum):
    FRONTDESK = 'frontdesk'
    MAINTENANCE = 'maintenance'
    MANAGER = 'manager'
    ADMIN = 'admin'
    LEADER = 'leader'
    CUSTOMER_SERVICE = 'customer_service'
    NEWBIE = 'newbie'
    VIEWER = 'viewer'


# ── Permission constants ──────────────────────────────────────────────────────

VIEWER_COMMANDS = {'/me', '/dashboard', '/pipeline', '/search', '/rag', '/export', '/help', '/today'}
NEWBIE_COMMANDS = {'/add', '/me', '/note', '/help'}
CS_COMMANDS = {'/search', '/note', '/pipeline', '/dashboard', '/rag', '/export', '/me', '/help', '/today'}
LEADER_COMMANDS = 'all'  # scoped to their team

# Internal command names (without leading slash) for policy_engine compatibility
_VIEWER_CMDS = {'me', 'dashboard', 'pipeline', 'search', 'rag', 'export', 'help', 'today', 'leaderboard'}
_NEWBIE_CMDS = {'add', 'me', 'note', 'help'}
_CS_CMDS = {'search', 'note', 'pipeline', 'dashboard', 'rag', 'export', 'me', 'help', 'today', 'leaderboard', 'hot', 'summary', 'template'}


def check_permission(staff: 'Staff', command: str) -> bool:
    """Check if staff member is allowed to execute command.

    command may include a leading slash (e.g. '/add') or not ('add').
    """
    cmd = command.lstrip('/')
    role = staff.role

    if role == StaffRole.ADMIN:
        return True
    if role == StaffRole.MANAGER:
        return True
    if role == StaffRole.LEADER:
        return True  # all commands, team-scoped at handler level
    if role in (StaffRole.FRONTDESK, StaffRole.MAINTENANCE):
        return True  # policy_engine handles fine-grained checks for these
    if role == StaffRole.CUSTOMER_SERVICE:
        return cmd in _CS_CMDS
    if role == StaffRole.NEWBIE:
        return cmd in _NEWBIE_CMDS
    if role == StaffRole.VIEWER:
        return cmd in _VIEWER_CMDS
    return False


class ClientStatus(str, Enum):
    NEW = 'new'
    CONTACTED = 'contacted'
    REPLIED = 'replied'
    REGISTERED = 'registered'
    TRAINING = 'training'
    WITHDREW = 'withdrew'
    ORDERED = 'ordered'
    GHOSTED = 'ghosted'
    BLOCKED = 'blocked'
    SCAMMED = 'scammed'
    SCHEDULED = 'scheduled'
    DEAD = 'dead'

    @classmethod
    def active_statuses(cls) -> List['ClientStatus']:
        """Statuses that need follow-up."""
        return [cls.NEW, cls.CONTACTED, cls.REPLIED, cls.REGISTERED, cls.TRAINING, cls.SCHEDULED]

    @classmethod
    def terminal_statuses(cls) -> List['ClientStatus']:
        """Truly terminal — no further action, ever."""
        return [cls.BLOCKED, cls.SCAMMED, cls.DEAD]

    @classmethod
    def completed_statuses(cls) -> List['ClientStatus']:
        """Done for now but may reactivate (ordered again, ghosted revival, etc.)."""
        return [cls.WITHDREW, cls.ORDERED, cls.GHOSTED]

    @classmethod
    def pipeline_order(cls) -> List['ClientStatus']:
        """Main pipeline stages in order."""
        return [cls.NEW, cls.CONTACTED, cls.REPLIED, cls.REGISTERED, cls.TRAINING, cls.WITHDREW, cls.ORDERED]

    @classmethod
    def valid_transitions(cls, from_status: 'ClientStatus') -> List['ClientStatus']:
        """Valid next statuses from a given status."""
        # Can always move to terminal statuses from any active status
        terminal = [cls.GHOSTED, cls.BLOCKED, cls.SCAMMED, cls.DEAD]
        transitions = {
            cls.NEW: [cls.CONTACTED, cls.SCHEDULED] + terminal,
            cls.CONTACTED: [cls.REPLIED, cls.SCHEDULED] + terminal,
            cls.REPLIED: [cls.REGISTERED, cls.SCHEDULED] + terminal,
            cls.REGISTERED: [cls.TRAINING, cls.SCHEDULED] + terminal,
            cls.TRAINING: [cls.WITHDREW, cls.ORDERED, cls.SCHEDULED] + terminal,
            cls.WITHDREW: [cls.ORDERED, cls.CONTACTED] + terminal,
            cls.ORDERED: [cls.CONTACTED, cls.REPLIED, cls.REGISTERED, cls.TRAINING] + terminal,
            cls.SCHEDULED: [cls.CONTACTED, cls.REPLIED, cls.REGISTERED] + terminal,
            cls.GHOSTED: [cls.CONTACTED, cls.REPLIED] + terminal,
            cls.BLOCKED: terminal,
            cls.SCAMMED: terminal,
            cls.DEAD: terminal,
        }
        return transitions.get(from_status, [])


class NoteType(str, Enum):
    STATUS_CHANGE = 'status_change'
    FOLLOWUP = 'followup'
    NOTE = 'note'
    CALL = 'call'
    MESSAGE = 'message'


class PeriodType(str, Enum):
    WEEKLY = 'weekly'
    MONTHLY = 'monthly'


@dataclass
class Staff:
    tg_user_id: int
    tg_chat_id: int
    display_name: str
    id: Optional[int] = None
    tg_username: Optional[str] = None
    role: StaffRole = StaffRole.FRONTDESK
    team: Optional[str] = None
    phone: Optional[str] = None
    language: str = 'zh'
    is_active: bool = True
    daily_target: int = 40
    created_at: Optional[datetime] = None
    last_active_at: Optional[datetime] = None

    maintenance_id: Optional[int] = None  # NULL if they ARE maintenance

    def is_manager_or_above(self) -> bool:
        return self.role in (StaffRole.MAINTENANCE, StaffRole.MANAGER, StaffRole.ADMIN, StaffRole.LEADER)

    def is_admin(self) -> bool:
        return self.role == StaffRole.ADMIN

    def is_leader(self) -> bool:
        return self.role == StaffRole.LEADER

    def is_read_only(self) -> bool:
        return self.role == StaffRole.VIEWER

    def can_modify_pipeline(self) -> bool:
        return self.role not in (StaffRole.VIEWER, StaffRole.NEWBIE, StaffRole.CUSTOMER_SERVICE)


@dataclass
class Client:
    frontdesk_id: int
    phone: str
    source: str
    id: Optional[int] = None
    account_id: Optional[str] = None
    phone_remark: Optional[str] = None
    nickname: Optional[str] = None
    recruiter: Optional[str] = None
    status: ClientStatus = ClientStatus.NEW
    status_note: Optional[str] = None
    contacted_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None
    registered_at: Optional[datetime] = None
    training_at: Optional[datetime] = None
    withdrew_at: Optional[datetime] = None
    first_order_at: Optional[datetime] = None
    next_followup: Optional[datetime] = None
    followup_count: int = 0
    platform: Optional[str] = None
    total_deposited: float = 0.0
    maintenance_id: Optional[int] = None   # auto-set from frontdesk's team
    handoff_at: Optional[datetime] = None  # when client was handed to maintenance
    handoff_note: Optional[str] = None     # notes during handoff
    sheet_gid: Optional[int] = None
    sheet_row: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def is_stale(self, hours: int = 72) -> bool:
        """True if no update in given hours and in an active (needs-followup) status."""
        if self.status not in ClientStatus.active_statuses():
            return False
        if not self.updated_at:
            return True
        delta = datetime.now() - self.updated_at
        return delta.total_seconds() > hours * 3600

    def status_emoji(self) -> str:
        emojis = {
            ClientStatus.NEW: '🆕',
            ClientStatus.CONTACTED: '📱',
            ClientStatus.REPLIED: '💬',
            ClientStatus.REGISTERED: '✅',
            ClientStatus.TRAINING: '📚',
            ClientStatus.WITHDREW: '💰',
            ClientStatus.ORDERED: '🎯',
            ClientStatus.GHOSTED: '👻',
            ClientStatus.BLOCKED: '🚫',
            ClientStatus.SCAMMED: '⚠️',
            ClientStatus.SCHEDULED: '📅',
            ClientStatus.DEAD: '💀',
        }
        return emojis.get(self.status, '❓')


@dataclass
class ClientNote:
    client_id: int
    staff_id: int
    note_type: NoteType
    id: Optional[int] = None
    old_status: Optional[str] = None
    new_status: Optional[str] = None
    content: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass
class DailyStat:
    staff_id: int
    stat_date: date
    id: Optional[int] = None
    new_leads: int = 0
    contacted: int = 0
    replied: int = 0
    registered: int = 0
    training: int = 0
    withdrew: int = 0
    new_orders: int = 0
    ghosted: int = 0
    blocked: int = 0
    dead: int = 0
    reply_rate: float = 0.0
    conversion_rate: float = 0.0
    total_deposit: float = 0.0
    created_at: Optional[datetime] = None

    def calculate_rates(self):
        """Recalculate reply_rate and conversion_rate from raw counts.

        reply_rate     = replied / contacted  (how many contacted actually replied)
        conversion_rate = new_orders / registered  (how many registered ultimately ordered)
        """
        if self.contacted > 0:
            self.reply_rate = round(self.replied / self.contacted * 100, 2)
        if self.registered > 0:
            self.conversion_rate = round(self.new_orders / self.registered * 100, 2)


@dataclass
class Deposit:
    client_id: int
    frontdesk_id: int
    amount: float
    deposit_date: date
    id: Optional[int] = None
    currency: str = 'USD'
    platform: Optional[str] = None
    knife_number: Optional[int] = None
    role_type: Optional[str] = None
    note: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass
class Reminder:
    staff_id: int
    remind_at: datetime
    message: str
    id: Optional[int] = None
    client_id: Optional[int] = None
    is_sent: bool = False
    sent_at: Optional[datetime] = None
    source: str = 'manual'
    created_at: Optional[datetime] = None

    def is_due(self) -> bool:
        return not self.is_sent and datetime.now() >= self.remind_at


@dataclass
class TeamTarget:
    team: str
    period_type: PeriodType
    period_start: date
    period_end: date
    id: Optional[int] = None
    target_leads: Optional[int] = None
    target_registers: Optional[int] = None
    target_orders: Optional[int] = None
    target_deposit: Optional[float] = None
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None


@dataclass
class BotTask:
    """Task for Ralph Loop processing."""
    id: Optional[int] = None
    task_type: str = None  # "message", "reminder", "report", "sync"
    priority: int = 1  # 1 = highest, 5 = lowest
    data: Optional[Dict[str, Any]] = field(default_factory=dict)
    status: str = 'pending'  # pending, processing, completed, failed
    scheduled_time: Optional[datetime] = None
    attempts: int = 0
    max_attempts: int = 3
    error_message: Optional[str] = None
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
