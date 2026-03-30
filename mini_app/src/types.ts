export interface Client {
  id: number
  phone: string
  status: string
  source?: string
  frontdesk_name?: string
  total_deposited: number
  created_at: string
  contacted_at?: string
  replied_at?: string
  registered_at?: string
  training_at?: string
  first_order_at?: string
  next_followup?: string
}

export interface Note {
  id: number
  content: string
  note_type: string
  old_status?: string
  new_status?: string
  staff_name?: string
  created_at: string
}

export interface Deposit {
  id: number
  amount: number
  currency: string
  platform?: string
  deposit_date: string
}

export interface ClientDetail extends Client {
  notes: Note[]
  deposits: Deposit[]
}

export interface PipelineData {
  [status: string]: Client[]
}

export interface Stats {
  by_status: Record<string, number>
  today_new: number
  today_contacts: number
  today_orders: number
  overdue_followups: number
  total_active: number
  total_clients: number
}

export interface Badge {
  name: string
  emoji: string
  description?: string
}

export interface LeaderboardEntry {
  id: number
  display_name: string
  team?: string
  xp_total: number
  current_streak: number
  longest_streak: number
  badges: Badge[]
  today_leads: number
  today_orders: number
  today_deposits: number
}

export interface StaffMe {
  id: number
  display_name: string
  role: string
  team?: string
  tg_user_id: number
  xp_total: number
  current_streak: number
  daily_target: number
}

export type TabId = 'kanban' | 'today' | 'leaderboard'
