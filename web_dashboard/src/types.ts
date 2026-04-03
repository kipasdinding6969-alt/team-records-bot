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
  is_active: boolean
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
export type DayStatus = '注册' | '不注册' | 'pending'

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
export type MaintainerRole = 'frontdesk' | 'opener' | 'newbie' | 'group_chat' | 'cs' | 'maintenance'

export interface MaintainerDeposit {
  id: number
  client_id: number
  phone: string
  amount: number
  knife_number: number | null
  role_type: string | null
  pressure_amount: number
  total_in: number
  deposit_group_id: number | null
  platform: string | null
  deposit_date: string
  note: string | null
  frontdesk_name: string
  team: string
  group_number: string | null
  total_pressure: number | null
  total_collected: number | null
  cut_count: number | null
}

// Phase 22: Crypto transactions
export interface CryptoTransaction {
  id: number
  txn_type: 'in' | 'out'
  client_name: string
  client_number: string | null
  maintainer_id: number | null
  maintainer_name: string | null
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
export interface GroupCompareData {
  team: string
  leader: string | null
  today: GranularPerfRow[]
  cumulative: Record<string, number>[]
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
  role_type: 'frontdesk' | 'maintainer' | 'group_hype' | 'newbie_actor' | 'customer_service' | 'opener_legacy' | 'full_line'
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
  maintainer_id: number | null
  notes: string | null
  created_at: string
}

export interface CrossRoleNote {
  id: number
  client_id: number
  from_role: string
  from_staff_id: number | null
  content: string
  created_at: string
}

export interface GroupInteraction {
  id: number
  client_id: number
  group_id: string | null
  actor_staff_id: number | null
  actor_role: 'newbie_actor' | 'group_hype' | 'passerby'
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

export interface OrgUnit {
  id: number
  name: string
  unit_type: 'organization' | 'branch' | 'group' | 'subgroup'
  parent_id: number | null
  leader_staff_id: number | null
  leader_name?: string
  is_active: number
  children?: OrgUnit[]
}

export type KillType = 'register_kill' | 'new_order_kill' | 'pressure_kill' | 'salary_kill'

export const KILL_LABELS: Record<string, Record<string, string>> = {
  register_kill: { zh: '注册杀', en: 'Register Kill' },
  new_order_kill: { zh: '新单杀', en: 'New Order Kill' },
  pressure_kill: { zh: '承压杀', en: 'Pressure Kill' },
  salary_kill: { zh: '工资杀', en: 'Salary Kill' },
}

export const ROLE_TYPE_LABELS: Record<string, Record<string, string>> = {
  frontdesk: { zh: '前台', en: 'Frontdesk' },
  maintainer: { zh: '维护', en: 'Maintainer' },
  group_hype: { zh: '炒群', en: 'Group Hype' },
  newbie_actor: { zh: '小白', en: 'Newbie Actor' },
  customer_service: { zh: '客服', en: 'Customer Service' },
  opener_legacy: { zh: '开单', en: 'Opener (Legacy)' },
  full_line: { zh: '全线', en: 'Full Line' },
}
