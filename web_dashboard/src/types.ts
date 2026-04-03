export interface Staff {
  id: number
  display_name: string
  role: string
  team: string | null
  is_active: number
  daily_target: number
  xp_total: number
  current_streak: number
  total_clients: number
  total_orders: number
  today_leads: number
  today_orders: number
  today_deposit: number
}

export interface Client {
  id: number
  phone: string
  status: string
  source: string | null
  total_deposited: number
  created_at: string
  contacted_at: string | null
  replied_at: string | null
  registered_at: string | null
  training_at: string | null
  first_order_at: string | null
  next_followup: string | null
  first_day_status: string | null
  second_day_status: string | null
  frontdesk_name: string | null
  team: string | null
}

export interface ClientNote {
  id: number
  note_type: string
  old_status: string | null
  new_status: string | null
  content: string | null
  created_at: string
  staff_name: string | null
}

export interface Deposit {
  id: number
  amount: number
  currency: string
  platform: string | null
  deposit_date: string
}

export interface ClientDetail extends Client {
  notes: ClientNote[]
  deposits: Deposit[]
}

export interface DashboardStats {
  total_clients: number
  total_active: number
  total_staff: number
  total_deposits: number
  today_new: number
  today_contacts: number
  today_orders: number
  today_deposits: number
  overdue_followups: number
  conversion_rate: number
  by_status: Record<string, number>
}

export interface FunnelStage {
  stage: string
  count: number
  pct: number
}

export interface Activity {
  id: number
  note_type: string
  old_status: string | null
  new_status: string | null
  content: string | null
  created_at: string
  staff_name: string | null
  client_phone: string | null
  client_id: number | null
}

export interface Trends {
  daily_new: { day: string; new_clients: number }[]
  daily_orders: { day: string; orders: number }[]
  daily_deposits: { day: string; total: number }[]
}

export interface ClientList {
  total: number
  page: number
  per_page: number
  clients: Client[]
}

export interface DashboardUser {
  id: number
  username: string
  display_name: string
  role: 'owner' | 'admin' | 'member'
  staff_id: number | null
  team_scope: string | null
  is_active: number
  last_login: string | null
  created_at: string
}

export interface AuthState {
  token: string
  username: string
  role: 'owner' | 'admin' | 'member'
  team_scope: string | null
  display_name: string
  staff_id: number | null
  staff_role: string | null
  user_id: number | null
}

export const STATUS_COLORS: Record<string, string> = {
  new: '#94a3b8',
  contacted: '#60a5fa',
  replied: '#fbbf24',
  registered: '#34d399',
  training: '#2dd4bf',
  withdrew: '#fb923c',
  ordered: '#22d3ee',
  ghosted: '#64748b',
  blocked: '#fb7185',
  scammed: '#f87171',
  scheduled: '#a78bfa',
  dead: '#475569',
}

// Status/role keys for i18n lookup — use getStatusLabel()/getRoleLabel() for translated text
export const STATUS_KEYS = ['new', 'contacted', 'replied', 'registered', 'training', 'withdrew', 'ordered', 'ghosted', 'blocked', 'scammed', 'scheduled', 'dead'] as const

export const ROLE_KEYS = ['owner', 'admin', 'member'] as const

// Legacy compat: static labels used as fallback when i18n is unavailable
export const STATUS_LABELS: Record<string, string> = {
  new: 'New', contacted: 'Contacted', replied: 'Replied', registered: 'Registered',
  training: 'Training', withdrew: 'Withdrew', ordered: 'Ordered', ghosted: 'Ghosted',
  blocked: 'Blocked', scammed: 'Scammed', scheduled: 'Scheduled', dead: 'Dead',
}

export const ROLE_LABELS: Record<string, string> = {
  owner: 'Owner', admin: 'Admin', member: 'Member',
}

export const ROLE_COLORS: Record<string, string> = {
  owner: '#00b894',
  admin: '#fdcb6e',
  member: '#7f848e',
}

// Phase 22: Lead categories
export type LeadCategory = 'UK表单粉' | 'CA表单粉' | 'AU表单粉' | 'EU表单粉' | '飞机筛选' | 'RCS筛选'
export type DayStatus = 'register' | 'no_register' | 'pending'

export const LEAD_CATEGORIES: LeadCategory[] = ['UK表单粉', 'CA表单粉', 'AU表单粉', 'EU表单粉', '飞机筛选', 'RCS筛选']

// Phase 22: Frontdesk history entry
export interface FrontdeskHistoryEntry {
  id: number
  phone: string
  category: LeadCategory | null
  first_day_status: DayStatus | null
  second_day_status: DayStatus | null
  client_condition: string | null
  recruiter: string | null
  status: string
  created_at: string
}

// Phase 22: Granular performance row
export interface GranularPerfRow {
  staff_id: number
  display_name: string
  team: string
  category: string
  powder_count: number
  no_reply_start: number
  reply_rate: number
  stuck_explanation: number
  blocked_playing: number
  been_scammed: number
  sent_link_no_reply: number
  completed_registration: number
  audit_rate: number
  completed_training: number
  scheduled_time: number
  withdrawal: number
  new_order: number
  conversion_rate: number
  new_kill: number
  dead_client: number
}

// Phase 22: Blown account
export interface BlownAccount {
  id: number
  staff_id: number
  display_name: string
  team: string
  blown_date: string
  account_type: string
  phone_number: string | null
  account_identifier: string | null
  reason: string | null
  category: string | null
}

// Phase 22: Exam
export interface Exam {
  id: number
  exam_name: string
  team: string | null
  start_date: string
  end_date: string
  status: 'active' | 'completed' | 'cancelled'
  created_at: string
}

export interface ExamResultRow {
  staff_id: number
  display_name: string
  team: string
  role: string
  total_powder: number
  avg_reply_rate: number
  total_registrations: number
  total_training: number
  total_withdrawals: number
  total_new_orders: number
  conversion_rate: number
  total_new_kills: number
}

// Phase 22: Maintainer deposits
export type MaintainerRole = 'frontdesk' | 'opener_legacy' | 'newbie' | 'group_hype' | 'customer_service' | 'maintenance'

export interface MaintainerDeposit {
  id: number
  client_id: number
  phone: string
  amount: number
  pressure_amount: number
  total_in: number
  deposit_group_id: number | null
  platform: string | null
  deposit_date: string
  group_number: string | null
  total_pressure: number | null
  total_collected: number | null
  cut_count: number | null
  frontdesk_name: string | null
}

// Phase 22: Crypto transactions
export interface CryptoTransaction {
  id: number
  txn_type: 'in' | 'out'
  client_name: string
  client_number: string | null
  maintenance_id: number | null
  maintenance_name: string | null
  country: string | null
  amount_usdt: number
  situation: string | null
  group_name: string | null
  txn_date: string
  created_at: string
}

// Phase 22: Country financial summary
export interface CountryFinancialSummary {
  summary_date: string
  country: string
  new_orders: number
  deposit_count: number
  total_deposits: number
  avg_per_client: number
  second_filter_in?: number
  second_filter_out?: number
  rcs_in?: number
  rcs_out?: number
}

// Phase 24: Client comments
export interface ClientComment {
  id: number
  client_id: number
  staff_id: number
  staff_name: string
  content: string
  parent_comment_id: number | null
  is_system: boolean
  is_deleted: boolean
  created_at: string
  updated_at: string | null
}

// Phase 24: Audit log
export interface AuditLogEntry {
  id: number
  user_id: number
  username: string
  action: string
  entity_type: string
  entity_id: number | null
  old_values: string | null
  new_values: string | null
  ip_address: string | null
  created_at: string
}

// Phase 22: Group comparison
export interface GroupCompareRow {
  staff_id: number
  display_name: string
  powder_count: number
  reply_rate: number
  completed_registration: number
  completed_training: number
  withdrawal: number
  new_order: number
  conversion_rate: number
}

export interface GroupCompareData {
  team: string
  leader: string | null
  today: GroupCompareRow[]
  cumulative: GroupCompareRow[]
  totals: {
    total_clients: number
    new_leads: number
    registered: number
    training: number
    withdrew: number
    orders: number
    killed: number
  }
}

export interface GroupCompareResult {
  date: string
  groups: GroupCompareData[]
}

// ─── Phase 26: Domain Model ────────────────────────────────────────────────

export interface ClientPipelineStatus {
  client_id: number
  contacted_at: string | null
  replied_at: string | null
  registered_at: string | null
  training_completed_at: string | null
  bonus_withdrew_at: string | null
  day1_complete: number
  day2_training_at: string | null
  own_tasks_started_at: string | null
  insufficient_funds_at: string | null
  new_order_amount: number | null
  new_order_at: string | null
  pressure_amount: number | null
  pressure_at: string | null
  kill_type: 'register_kill' | 'new_order_kill' | 'pressure_kill' | 'salary_kill' | null
  kill_knife: number | null
  kill_at: string | null
  is_unkilled: number
  unkill_reason: string | null
  total_deposited: number
  updated_at: string
}

export interface ClientRoleAssignment {
  id: number
  client_id: number
  staff_id: number
  role_type: 'frontdesk' | 'maintenance' | 'group_hype' | 'newbie' | 'customer_service' | 'opener_legacy' | 'full_line'
  assigned_at: string
  ended_at: string | null
  handoff_reason: string | null
  is_active: number
  staff_name?: string
}

export interface KnifeDeposit {
  id: number
  client_id: number
  knife_number: number
  amount: number
  deposit_day: number | null
  platform: string | null
  maintenance_id: number | null
  notes: string | null
  created_at: string
}

export interface GroupInteraction {
  id: number
  client_id: number
  group_id: string | null
  actor_staff_id: number | null
  actor_role: 'newbie' | 'group_hype' | 'passerby'
  day_number: number | null
  script_completed: number
  client_read_messages: number
  client_replied: number
  client_pm_character: number
  client_left_group: number
  notes: string | null
  created_at: string
  client_phone: string | null
  client_account_id: string | null
  client_platform: string | null
  first_day_status: string | null
  second_day_status: string | null
  actor_name?: string | null
  frontdesk_name?: string | null
}

export const KILL_LABELS: Record<string, Record<string, string>> = {
  register_kill: { zh: '注册杀', en: 'Register Kill' },
  new_order_kill: { zh: '新单杀', en: 'New Order Kill' },
  pressure_kill: { zh: '承压杀', en: 'Pressure Kill' },
  salary_kill: { zh: '工资杀', en: 'Salary Kill' },
}

export const ROLE_TYPE_LABELS: Record<string, Record<string, string>> = {
  frontdesk: { zh: '前台', en: 'Frontdesk' },
  maintenance: { zh: '维护', en: 'Maintenance' },
  group_hype: { zh: '炒群', en: 'Group Hype' },
  newbie: { zh: '小白', en: 'Newbie' },
  customer_service: { zh: '客服', en: 'Customer Service' },
  opener_legacy: { zh: '开单', en: 'Opener (Legacy)' },
  full_line: { zh: '全线', en: 'Full Line' },
}

// ─── API Response Types ────────────────────────────────────────────────────

// Auth
export interface LoginResponse {
  access_token: string
  token_type: string
  username: string
  display_name: string
  role: AuthState['role']
  team_scope: string | null
  staff_id: number | null
  staff_role: string | null
  user_id: number
}

export interface VerifyResponse {
  ok: boolean
  username: string
  role: AuthState['role']
  team_scope: string | null
  display_name: string
  staff_id: number | null
  staff_role: string | null
  user_id: number
}

// Phone Registry
export interface PhoneRegistryEntry {
  found: true
  id?: number
  phone: string
  phone_normalized: string
  submitter_name: string
  submitter_staff_id: number | null
  source: string
  submitted_at: string | null
  created_at?: string
  linked_clients: { id: number; phone: string; status: string; frontdesk_id: number | null; frontdesk_name: string | null }[]
  log: PhoneRegistryLogEntry[]
  history?: PhoneRegistryLogEntry[]
  duplicate_flagged?: boolean
  message_count?: number
}

export interface PhoneRegistryNotFound {
  found: false
  phone: string
}

export type PhoneRegistryLookupResult = PhoneRegistryEntry | PhoneRegistryNotFound

export interface PhoneRegistryLogEntry {
  id: number
  action: string
  actor_name: string
  details: string | null
  created_at: string
}

export interface PhoneRegistryStatsResult {
  total: number
  total_registered: number
  duplicates_blocked: number
  by_source: Record<string, number>
  chat_export_phones: number
  chat_export_duplicates: number
}

export interface PhoneCheckResult {
  phone: string
  normalized: string
  status: 'available' | 'own' | 'taken'
  owner?: string
  submitted_at?: string
  category?: string
  team_name?: string
  editable?: boolean
  client_id?: number
  client_status?: string
  client_owner?: string
  is_own_client?: boolean
  source?: string
  duplicate_flagged?: boolean
}

export interface PhoneRegistrySearchResult {
  total: number
  page: number
  per_page: number
  results: {
    id: number
    phone: string
    phone_normalized: string
    submitter_name: string
    submitter_staff_id: number | null
    source: string
    submitted_at: string
  }[]
}

export interface PhoneRegistryDuplicatesResult {
  total: number
  page: number
  per_page: number
  results: {
    phone_normalized: string
    phone: string
    submitter_count: number
    submitters: string
    earliest: string
    latest: string
  }[]
}

export interface PhoneRegistryHistoryResult {
  phone: string
  normalized: string
  entries: Record<string, unknown>[]
}

export interface BulkCheckResponse {
  total: number
  found: number
  results: {
    phone: string
    phone_input: string
    normalized: string
    found: boolean
    submitter_name?: string
    submitted_at?: string
    source_table?: string
  }[]
}

export interface PhoneRegistryByStaffResult {
  total: number
  page: number
  per_page: number
  results: {
    id: number
    phone: string
    phone_normalized: string
    submitter_name: string
    source: string
    submitted_at: string
    created_at: string
  }[]
}

// Client Links
export interface ClientLink {
  id: number
  client_id_a: number
  client_id_b: number
  link_type: string
  note: string | null
  created_at: string
  phone_a: string
  phone_b: string
  status_a: string
  status_b: string
  name_a: string | null
  name_b: string | null
}

// Permissions
export interface StaffPermissionOverride {
  id: number
  command: string
  allowed: number
  reason: string | null
  created_at?: string
  updated_at?: string
  granted_by_name?: string | null
}

export interface StaffPermissionsResult {
  staff: { id: number; display_name: string; role: string; team: string | null }
  overrides: StaffPermissionOverride[]
}

export interface AllPermissionsStaffEntry {
  id: number
  display_name: string
  role: string
  team: string | null
  overrides: { id: number; command: string; allowed: number; reason: string | null }[]
}

// Client Notes (enhanced from backend)
export interface ClientNoteEntry {
  id: number
  note_type: string
  old_status: string | null
  new_status: string | null
  content: string | null
  author_name: string | null
  phone_normalized: string | null
  created_at: string
  staff_name: string | null
}

// Timeline
export interface TimelineItem {
  id: number
  client_id?: number
  timeline_type: 'note' | 'deposit' | 'link'
  note_type?: string
  content: string | null
  created_at: string
  author_name?: string | null
  staff_name?: string | null
  client_phone?: string | null
  old_status?: string | null
  new_status?: string | null
  phone_a?: string
  phone_b?: string
  amount?: number
  currency?: string
  platform?: string
}

// Performance
export interface PerformanceDailyStaffRow {
  staff_id: number
  display_name: string
  team: string | null
  new_leads: number
  contacted: number
  replied: number
  registered: number
  training: number
  withdrew: number
  new_orders: number
  ghosted: number
  dead: number
  total_deposit: number
  reply_rate: number
  registration_rate: number
  training_rate: number
  conversion_rate: number
}

export interface PerformanceDailyResult {
  date: string
  team: string
  staff: PerformanceDailyStaffRow[]
  totals: Record<string, number>
}

export interface PerformanceSummaryResult {
  from: string
  to: string
  team: string
  staff: PerformanceDailyStaffRow[]
  totals: Record<string, number>
}

export interface PerformanceTrendPoint {
  stat_date: string
  new_leads: number
  contacted: number
  replied: number
  registered: number
  training: number
  withdrew: number
  new_orders: number
  ghosted: number
  dead: number
  total_deposit: number
  reply_rate: number
  conversion_rate: number
}

// Team Performance
export interface TeamPerformanceMember {
  id: number
  display_name: string
  role: string
  today_leads: number
  today_orders: number
  today_deposit: number
}

export interface TeamPerformanceResult {
  team: string
  members: TeamPerformanceMember[]
  totals: { today_leads: number; today_orders: number; today_deposit: number }
}

// Org Chart
export interface OrgChartStaff {
  id: number
  display_name: string
  role: string
  team: string | null
  maintenance_id: number | null
  tg_username: string | null
  daily_target: number | null
  last_active_at: string | null
  active_clients: number
  override_count: number
}

export interface OrgChartTeam {
  team: string
  leader: OrgChartStaff | null
  members: OrgChartStaff[]
  member_count: number
  total_clients: number
  total_deposit?: number
}

export interface OrgChartResult {
  teams: OrgChartTeam[]
  unassigned: OrgChartStaff[]
}

// Linked Timeline
export interface LinkedTimelineResult {
  client_id: number
  linked_client_ids: number[]
  timeline: TimelineItem[]
}

// All Staff (management view)
export interface AllStaffMember {
  id: number
  display_name: string
  role: string
  team: string | null
  tg_username: string | null
  daily_target: number | null
  is_active: number
  phone: string | null
  language: string | null
  client_count: number
}

// Targets
export interface TeamTarget {
  id: number
  team: string
  period_type: string
  period_start: string
  period_end: string
  target_leads: number | null
  target_registers: number | null
  target_orders: number | null
  target_deposit: number | null
  created_by_name: string | null
  created_at: string
}

// Commissions
export interface CommissionEntry {
  id: number
  staff_id: number
  trigger_type: string
  amount: number
  status: string
  period: string
  created_at: string
  staff_name: string
  team: string | null
}

export interface CommissionSummaryEntry {
  staff_id: number
  display_name: string
  team: string | null
  approved_total: number
  pending_total: number
  total_entries: number
}

// Templates
export interface MessageTemplate {
  id: number
  name: string
  content: string
  category: string
  is_default: number
  created_at: string
  created_by_name: string | null
}

// Contests
export interface ContestEntry {
  id: number
  title: string
  metric: string
  target: number
  team: string | null
  start_date: string
  end_date: string
  status: string
  created_at: string
  winner_name: string | null
  created_by_name: string | null
}

export interface ContestScore {
  staff_id: number
  score: number
  updated_at: string
  display_name: string
  team: string | null
}

// Gamification
export interface StaffGamificationResult {
  staff_id: number
  total_xp: number
  streak: { current_streak: number; longest_streak: number; last_action_date?: string }
  badges: { name: string; emoji: string; description: string; earned_at: string }[]
  recent_xp: { action: string; xp_amount: number; created_at: string }[]
}

// Audit Log
export interface AuditLogResult {
  total: number
  page: number
  per_page: number
  entries: AuditLogEntry[]
}

// Org Units
export interface OrgUnit {
  id: number
  name: string
  unit_type: string
  parent_id: number | null
  leader_staff_id: number | null
  is_active: number
  leader_name: string | null
  children: OrgUnit[]
}

export interface CrossRoleNote {
  id: number;
  client_id: number;
  from_role: string;
  from_staff_id: number | null;
  content: string | null;
  created_at: string;
  staff_name: string | null;
}
export interface ExamResultsResponse {
  exam: Exam
  results: ExamResultRow[]
}