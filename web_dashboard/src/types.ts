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
  user_id: number | null
}

export const STATUS_COLORS: Record<string, string> = {
  new: '#7f848e',
  contacted: '#0f3460',
  replied: '#fdcb6e',
  registered: '#00b894',
  training: '#00cec9',
  withdrew: '#ff7675',
  ordered: '#00b894',
  ghosted: '#636e72',
  blocked: '#d63031',
  scammed: '#e17055',
  scheduled: '#74b9ff',
  dead: '#636e72',
}

export const STATUS_LABELS: Record<string, string> = {
  new: '新客户',
  contacted: '已联系',
  replied: '已回复',
  registered: '已注册',
  training: '培训中',
  withdrew: '已撤回',
  ordered: '已下单',
  ghosted: '已消失',
  blocked: '已封锁',
  scammed: '已诈骗',
  scheduled: '已预约',
  dead: '已终止',
}

export const ROLE_LABELS: Record<string, string> = {
  owner: '拥有者',
  admin: '管理员',
  member: '成员',
}

export const ROLE_COLORS: Record<string, string> = {
  owner: '#00b894',
  admin: '#fdcb6e',
  member: '#7f848e',
}
