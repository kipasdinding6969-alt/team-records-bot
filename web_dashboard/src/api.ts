export const debug = import.meta.env?.DEV ? console.error.bind(console) : () => {};

import type {
  Activity,
  AllPermissionsStaffEntry,
  AllStaffMember,
  AuditLogResult,
  AuthState,
  BlownAccount,
  BulkCheckResponse,
  Client,
  ClientComment,
  ClientDetail,
  ClientLink,
  ClientList,
  ClientNoteEntry,
  CrossRoleNote,
  ClientPipelineStatus,
  ClientRoleAssignment,
  CommissionEntry,
  CommissionSummaryEntry,
  ContestEntry,
  ContestScore,
  CountryFinancialSummary,
  CryptoTransaction,
  DashboardStats,
  DashboardUser,
  Exam,
  ExamResultsResponse,
  FrontdeskHistoryEntry,
  FunnelStage,
  GranularPerfRow,
  GroupCompareResult,
  GroupInteraction,
  KnifeDeposit,
  LinkedTimelineResult,
  LoginResponse,
  MaintainerDeposit,
  MessageTemplate,
  OrgChartResult,
  OrgUnit,
  PerformanceDailyResult,
  PerformanceSummaryResult,
  PerformanceTrendPoint,
  PhoneCheckResult,
  PhoneRegistryByStaffResult,
  PhoneRegistryDuplicatesResult,
  PhoneRegistryHistoryResult,
  PhoneRegistryLookupResult,
  PhoneRegistrySearchResult,
  PhoneRegistryStatsResult,
  Staff,
  StaffGamificationResult,
  StaffPermissionsResult,
  TeamPerformanceResult,
  TeamTarget,
  TimelineItem,
  Trends,
  VerifyResponse,
} from './types'

const BASE = ''
const AUTH_STATE_KEY = 'dashboard_auth_state'

// ─── Auth state storage ────────────────────────────────────────────────────────

export function getAuthState(): AuthState | null {
  const raw = localStorage.getItem(AUTH_STATE_KEY) || sessionStorage.getItem(AUTH_STATE_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as AuthState
  } catch {
    return null
  }
}

export function setAuthState(state: AuthState, persistent = true) {
  const raw = JSON.stringify(state)
  if (persistent) {
    localStorage.setItem(AUTH_STATE_KEY, raw)
  } else {
    sessionStorage.setItem(AUTH_STATE_KEY, raw)
  }
}

export function clearAuthState() {
  localStorage.removeItem(AUTH_STATE_KEY)
  sessionStorage.removeItem(AUTH_STATE_KEY)
  localStorage.removeItem('dashboard_token')
}

export function getToken(): string {
  return getAuthState()?.token || localStorage.getItem('dashboard_token') || ''
}

export function setToken(token: string) {
  localStorage.setItem('dashboard_token', token)
}

export function isAuthenticated(): boolean {
  return !!getToken()
}

export function getRole(): AuthState['role'] | null {
  return getAuthState()?.role ?? null
}

export function getTeamScope(): string | null {
  return getAuthState()?.team_scope ?? null
}

function authHeaders(): Record<string, string> {
  const t = getToken()
  return t ? { Authorization: `Bearer ${t}` } : {}
}

async function req<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
      ...(options.headers as Record<string, string> || {}),
    },
  })
  if (res.status === 401) {
    clearAuthState()
    window.location.href = '/login'
    throw new Error('Unauthorized')
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    const detail = err.detail
    // Preserve structured error objects (e.g. 409 duplicate response with type/owner/message)
    if (typeof detail === 'object' && detail !== null) {
      const e = new Error(detail.message || JSON.stringify(detail)) as Error & { detail: unknown }
      e.detail = detail
      throw e
    }
    throw new Error(detail || 'Request failed')
  }
  return res.json() as Promise<T>
}

async function downloadCsv(path: string, filename: string) {
  const res = await fetch(`${BASE}${path}`, { headers: authHeaders() })
  if (!res.ok) throw new Error('Export failed')
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export const api = {
  setup: (username: string, password: string, display_name: string) =>
    req<{ ok: boolean; message: string }>('/api/auth/setup', {
      method: 'POST',
      body: JSON.stringify({ username, password, display_name }),
    }),

  login: (username: string, password: string, remember_me = false) =>
    req<LoginResponse>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password, remember_me }),
    }),

  verify: () => req<VerifyResponse>('/api/auth/verify'),

  changePassword: (current_password: string, new_password: string) =>
    req<{ ok: boolean }>('/api/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({ current_password, new_password }),
    }),

  dashboard: () => req<DashboardStats>('/api/dashboard'),

  funnel: () => req<FunnelStage[]>('/api/funnel'),

  activity: () => req<Activity[]>('/api/activity'),

  staff: () => req<Staff[]>('/api/staff'),

  trends: () => req<Trends>('/api/trends'),

  clients: (params: Record<string, string | number | undefined>) => {
    const entries = Object.entries(params)
      .filter(([, v]) => v !== undefined && v !== '')
      .map(([k, v]) => [k, String(v)] as [string, string])
    const qs = new URLSearchParams(entries).toString()
    return req<ClientList>(`/api/clients${qs ? `?${qs}` : ''}`)
  },

  clientDetail: (id: number) => req<ClientDetail>(`/api/clients/${id}`),

  pipeline: () => req<Record<string, Client[]>>('/api/pipeline'),

  exportClients: (status?: string, team?: string) => {
    const p = new URLSearchParams()
    if (status) p.set('status', status)
    if (team) p.set('team', team)
    const today = new Date().toISOString().split('T')[0]
    return downloadCsv(`/api/export/clients${p.toString() ? `?${p}` : ''}`, `clients_${today}.csv`)
  },

  exportReport: (period: string) => {
    const today = new Date().toISOString().split('T')[0]
    return downloadCsv(`/api/export/report?period=${period}`, `report_${period}_${today}.csv`)
  },

  // User management
  listUsers: () => req<DashboardUser[]>('/api/users'),

  createUser: (data: {
    username: string
    password: string
    display_name: string
    role: string
    team_scope?: string | null
    staff_id?: number | null
  }) =>
    req<{ ok: boolean; id: number }>('/api/users', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateUser: (
    id: number,
    data: {
      display_name?: string
      role?: string
      team_scope?: string | null
      staff_id?: number | null
      is_active?: boolean
    }
  ) =>
    req<{ ok: boolean }>(`/api/users/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deactivateUser: (id: number) =>
    req<{ ok: boolean }>(`/api/users/${id}`, { method: 'DELETE' }),

  resetPassword: (id: number, new_password: string) =>
    req<{ ok: boolean }>(`/api/users/${id}/reset-password`, {
      method: 'POST',
      body: JSON.stringify({ new_password }),
    }),

  // Phase 16: Phone Registry
  phoneRegistryLookup: (phone: string) =>
    req<PhoneRegistryLookupResult>(`/api/phone-registry/lookup?phone=${encodeURIComponent(phone)}`),

  phoneRegistrySearch: (q: string, page = 1) =>
    req<PhoneRegistrySearchResult>(
      `/api/phone-registry/search?q=${encodeURIComponent(q)}&page=${page}`
    ),

  phoneRegistryStats: () => req<PhoneRegistryStatsResult>('/api/phone-registry/stats'),

  phoneRegistryOverride: (phone: string, new_submitter: string, new_staff_id?: number) =>
    req<{ ok: boolean }>(`/api/phone-registry/override?phone=${encodeURIComponent(phone)}`, {
      method: 'POST',
      body: JSON.stringify({ new_submitter, new_staff_id }),
    }),

  // Phase 16: Client Links
  clientLinks: (clientId: number) => req<ClientLink[]>(`/api/clients/${clientId}/links`),

  createClientLink: (data: { client_id_a: number; client_id_b: number; link_type?: string; note?: string }) =>
    req<{ ok: boolean }>(`/api/clients/${data.client_id_a}/links`, {
      method: 'POST',
      body: JSON.stringify({ linked_client_id: data.client_id_b, link_type: data.link_type || 'related', note: data.note }),
    }),

  deleteClientLink: (linkId: number) =>
    req<{ ok: boolean }>(`/api/client-links/${linkId}`, { method: 'DELETE' }),

  // Phase 16: Permissions
  staffPermissions: (staffId: number) => req<StaffPermissionsResult>(`/api/permissions/${staffId}`),

  allPermissions: () => req<AllPermissionsStaffEntry[]>('/api/permissions'),

  setPermissionOverride: (data: { staff_id: number; command: string; allowed: boolean; reason?: string }) =>
    req<{ ok: boolean }>('/api/permissions', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  deletePermissionOverride: (staffId: number, command: string) =>
    req<{ ok: boolean }>(`/api/permissions/${staffId}/${command}`, { method: 'DELETE' }),

  // Phase 16.5: Client Notes
  clientNotes: (clientId: number) => req<ClientNoteEntry[]>(`/api/clients/${clientId}/notes`),

  addClientNote: (clientId: number, data: { content: string; note_type?: string; phone_normalized?: string }) =>
    req<{ ok: boolean }>(`/api/clients/${clientId}/notes`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  clientTimeline: (clientId: number) => req<TimelineItem[]>(`/api/clients/${clientId}/timeline`),

  // Phase 16.5: Performance Dashboard
  performanceDaily: (date?: string, team?: string) => {
    const p = new URLSearchParams()
    if (date) p.set('date', date)
    if (team) p.set('team', team)
    return req<PerformanceDailyResult>(`/api/performance/daily${p.toString() ? `?${p}` : ''}`)
  },

  performanceSummary: (from: string, to: string, team?: string) => {
    const p = new URLSearchParams({ from, to })
    if (team) p.set('team', team)
    return req<PerformanceSummaryResult>(`/api/performance/summary?${p}`)
  },

  // Phase 17: Org Chart
  orgChart: () => req<OrgChartResult>('/api/org-chart'),

  // Phase 17: Linked Timeline (cross-client)
  linkedTimeline: (clientId: number) => req<LinkedTimelineResult>(`/api/clients/${clientId}/linked-timeline`),

  // Phase 17: Create client via dashboard
  createClient: (data: {
    phone: string; source: string; account_id?: string; nickname?: string;
    platform?: string; phone_remark?: string; recruiter?: string; category?: string;
    first_day_status?: string; second_day_status?: string; client_condition?: string;
  }) =>
    req<{ ok: boolean; client_id: number }>('/api/clients', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Phase 17: Recalculate daily stats
  recalculateStats: () =>
    req<{ ok: boolean; date: string; staff_updated: number }>('/api/performance/recalculate', { method: 'POST' }),

  // Phase 17: Staff management
  allStaff: () => req<AllStaffMember[]>('/api/staff/all'),

  updateStaff: (staffId: number, data: { team?: string; role?: string; display_name?: string; daily_target?: number; is_active?: boolean }) =>
    req<{ ok: boolean }>(`/api/staff/${staffId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  // Phase 17: Phone duplicate pre-check
  phoneCheck: (phone: string) =>
    req<PhoneCheckResult>(`/api/phone-registry/check?phone=${encodeURIComponent(phone)}`),

  // Phase 17: Bulk permissions
  bulkPermissions: (data: { staff_id: number; permissions: Record<string, boolean>; reason?: string }) =>
    req<{ ok: boolean; updated: number }>('/api/permissions/bulk', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Phase 17: Team performance
  teamPerformance: (team: string) => req<TeamPerformanceResult>(`/api/team/${encodeURIComponent(team)}/performance`),

  // Phase 19: Targets
  getTargets: (team?: string) => req<TeamTarget[]>(`/api/targets${team ? `?team=${encodeURIComponent(team)}` : ''}`),
  setTarget: (data: { team: string; period_type: string; period_start: string; period_end: string; target_leads?: number; target_registers?: number; target_orders?: number; target_deposit?: number }) =>
    req<{ ok: boolean }>('/api/targets', { method: 'POST', body: JSON.stringify(data) }),

  // Phase 19: Real trends
  performanceTrend: (staffId: number, days?: number) =>
    req<PerformanceTrendPoint[]>(`/api/performance/trend?staff_id=${staffId}${days ? `&days=${days}` : ''}`),
  trendsBatch: (team?: string, days?: number) => {
    const p = new URLSearchParams()
    if (team) p.set('team', team)
    if (days) p.set('days', String(days))
    return req<Record<number, number[]>>(`/api/performance/trends-batch${p.toString() ? `?${p}` : ''}`)
  },

  // Phase 19: Commissions
  getCommissions: (period?: string, team?: string) => {
    const p = new URLSearchParams()
    if (period) p.set('period', period)
    if (team) p.set('team', team)
    return req<CommissionEntry[]>(`/api/commissions${p.toString() ? `?${p}` : ''}`)
  },
  commissionSummary: (period?: string) =>
    req<CommissionSummaryEntry[]>(`/api/commissions/summary${period ? `?period=${period}` : ''}`),

  // Phase 19: Templates
  getTemplates: () => req<MessageTemplate[]>('/api/templates'),
  createTemplate: (data: { name: string; content: string; category?: string }) =>
    req<{ ok: boolean; id: number }>('/api/templates', { method: 'POST', body: JSON.stringify(data) }),
  updateTemplate: (id: number, data: { name: string; content: string; category?: string }) =>
    req<{ ok: boolean }>(`/api/templates/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteTemplate: (id: number) =>
    req<{ ok: boolean }>(`/api/templates/${id}`, { method: 'DELETE' }),

  // Phase 19: Contests
  getContests: () => req<ContestEntry[]>('/api/contests'),
  createContest: (data: { title: string; metric: string; target: number; team?: string; start_date: string; end_date: string }) =>
    req<{ ok: boolean; id: number }>('/api/contests', { method: 'POST', body: JSON.stringify(data) }),
  contestLeaderboard: (contestId: number) => req<ContestScore[]>(`/api/contests/${contestId}/leaderboard`),

  // Phase 19: Gamification
  staffGamification: (staffId: number) => req<StaffGamificationResult>(`/api/gamification/${staffId}`),

  // Phase 22: Frontdesk
  frontdeskHistory: (staffId?: number, page = 1) =>
    req<{ total: number; entries: FrontdeskHistoryEntry[] }>(`/api/frontdesk/history${staffId ? `?staff_id=${staffId}&page=${page}` : `?page=${page}`}`),
  updateDayStatus: (clientId: number, day: 1 | 2, status: string) =>
    req<{ ok: boolean }>(`/api/clients/${clientId}/day-status`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ day, status }) }),

  // Phase 22: Granular Performance
  performanceGranular: (date?: string, team?: string) => {
    const p = new URLSearchParams()
    if (date) p.set('date', date)
    if (team) p.set('team', team)
    return req<{ date: string; rows: GranularPerfRow[] }>(`/api/performance/granular?${p}`)
  },
  upsertGranularPerf: (data: {
    staff_id: number; stat_date: string; category: string;
    powder_count?: number; no_reply_start?: number; reply_rate?: number;
    stuck_explanation?: number; blocked_playing?: number; been_scammed?: number;
    sent_link_no_reply?: number; completed_registration?: number; audit_rate?: number;
    completed_training?: number; scheduled_time?: number; withdrawal?: number;
    new_order?: number; conversion_rate?: number; new_kill?: number; dead_client?: number;
    note?: string;
  }) =>
    req<{ ok: boolean }>('/api/performance/granular', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),
  blownAccounts: (date?: string, team?: string) => {
    const p = new URLSearchParams()
    if (date) p.set('date', date)
    if (team) p.set('team', team)
    return req<BlownAccount[]>(`/api/performance/blown-accounts?${p}`)
  },
  addBlownAccount: (data: {
    staff_id: number; blown_date?: string; account_type?: string;
    phone_number?: string; account_identifier?: string; reason?: string; category?: string;
  }) =>
    req<{ ok: boolean }>('/api/performance/blown-accounts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),

  // Phase 22: Group Compare
  groupCompare: (date?: string) => {
    const p = new URLSearchParams()
    if (date) p.set('date', date)
    return req<GroupCompareResult>(`/api/groups/compare?${p}`)
  },

  // Phase 22: Exams
  getExams: () => req<Exam[]>('/api/exams'),
  createExam: (data: { exam_name: string; start_date: string; end_date: string; team?: string }) =>
    req<{ ok: boolean; id: number }>('/api/exams', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),
  examResults: (examId: number) => req<ExamResultsResponse>(`/api/exams/${examId}/results`),
  closeExam: (examId: number) => req<{ ok: boolean }>(`/api/exams/${examId}/close`, { method: 'PUT' }),

  // Phase 22: Maintainer Deposits
  maintainerDeposits: (groupNumber?: string, team?: string) => {
    const p = new URLSearchParams()
    if (groupNumber) p.set('group_number', groupNumber)
    if (team) p.set('team', team)
    return req<MaintainerDeposit[]>(`/api/maintainer/deposits?${p}`)
  },
  createMaintainerDeposit: (data: {
    client_id: number; amount?: number; currency?: string; platform?: string;
    pressure_amount?: number; total_in?: number; deposit_group_id?: number;
    group_number?: string; deposit_date?: string;
  }) =>
    req<{ ok: boolean; id: number }>('/api/maintainer/deposits', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),
  maintainerReassign: (fromStaffId: number, toStaffId: number) =>
    req<{ ok: boolean }>('/api/maintainer/reassign', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ from_staff_id: fromStaffId, to_staff_id: toStaffId }) }),

  // Phase 22: Crypto & Financial
  cryptoLedger: (from?: string, to?: string) => {
    const p = new URLSearchParams()
    if (from) p.set('from_date', from)
    if (to) p.set('to_date', to)
    return req<CryptoTransaction[]>(`/api/cs/crypto-ledger?${p}`)
  },
  addCryptoTransaction: (data: {
    txn_type: string; client_name: string; amount_usdt: number;
    client_number?: string; maintenance_id?: number; country?: string;
    situation?: string; group_name?: string; txn_date?: string;
  }) =>
    req<{ ok: boolean; id: number }>('/api/cs/crypto-ledger', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),
  dailyFinancial: (date?: string) =>
    req<{ date: string; countries: CountryFinancialSummary[] }>(`/api/cs/daily-financial${date ? `?date=${date}` : ''}`),
  upsertDailyFinancial: (data: {
    summary_date: string; country: string; new_orders?: number; deposit_count?: number;
    total_deposits?: number; avg_per_client?: number; second_filter_in?: number;
    second_filter_out?: number; rcs_in?: number; rcs_out?: number;
  }) =>
    req<{ ok: boolean }>('/api/cs/daily-financial', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),

  // Phase 24: Client Comments
  clientComments: (clientId: number) =>
    req<ClientComment[]>(`/api/clients/${clientId}/comments`),

  addClientComment: (clientId: number, data: { content: string; parent_comment_id?: number }) =>
    req<{ ok: boolean; comment_id: number }>(`/api/clients/${clientId}/comments`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateComment: (commentId: number, content: string) =>
    req<{ ok: boolean }>(`/api/comments/${commentId}`, {
      method: 'PUT',
      body: JSON.stringify({ content }),
    }),

  deleteComment: (commentId: number) =>
    req<{ ok: boolean }>(`/api/comments/${commentId}`, { method: 'DELETE' }),

  // Phase 24: Audit Log
  auditLog: (params: { entity_type?: string; entity_id?: number; user_id?: number; from?: string; to?: string; page?: number; per_page?: number }) => {
    const p = new URLSearchParams()
    if (params.entity_type) p.set('entity_type', params.entity_type)
    if (params.entity_id) p.set('entity_id', String(params.entity_id))
    if (params.user_id) p.set('user_id', String(params.user_id))
    if (params.from) p.set('from', params.from)
    if (params.to) p.set('to', params.to)
    if (params.page) p.set('page', String(params.page))
    if (params.per_page) p.set('per_page', String(params.per_page))
    return req<AuditLogResult>(`/api/audit-log${p.toString() ? `?${p}` : ''}`)
  },

  // Phase 24: Phone Registry Enhanced
  phoneRegistryDuplicates: (page = 1, per_page = 50) =>
    req<PhoneRegistryDuplicatesResult>(`/api/phone-registry/duplicates?page=${page}&per_page=${per_page}`),

  phoneRegistryHistory: (phone: string) =>
    req<PhoneRegistryHistoryResult>(`/api/phone-registry/history/${encodeURIComponent(phone)}`),

  phoneRegistryBulkCheck: (phones: string[]) =>
    req<BulkCheckResponse>('/api/phone-registry/bulk-check', {
      method: 'POST',
      body: JSON.stringify({ phones }),
    }),

  phoneRegistryByStaff: (staffId: number, page = 1, per_page = 50) =>
    req<PhoneRegistryByStaffResult>(`/api/phone-registry/by-staff/${staffId}?page=${page}&per_page=${per_page}`),

  // ─── Phase 26: Domain Model ────────────────────────────────────────────

  // Pipeline
  clientPipeline: (clientId: number) =>
    req<ClientPipelineStatus>(`/api/clients/${clientId}/pipeline`),

  updatePipeline: (clientId: number, step: string, value?: string) =>
    req<{ ok: boolean }>(`/api/clients/${clientId}/pipeline`, {
      method: 'PUT',
      body: JSON.stringify({ step, value }),
    }),

  // Role Assignments
  clientRoles: (clientId: number) =>
    req<ClientRoleAssignment[]>(`/api/clients/${clientId}/roles`),

  assignRole: (clientId: number, data: { staff_id: number; role_type: string }) =>
    req<{ ok: boolean }>(`/api/clients/${clientId}/roles`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  recordHandoff: (clientId: number, maintainerStaffId: number) =>
    req<{ ok: boolean }>(`/api/clients/${clientId}/handoff`, {
      method: 'POST',
      body: JSON.stringify({ maintainer_staff_id: maintainerStaffId }),
    }),

  // Knife Deposits
  clientKnives: (clientId: number) =>
    req<KnifeDeposit[]>(`/api/clients/${clientId}/knives`),

  addKnife: (clientId: number, data: { knife_number: number; amount: number; deposit_day?: number; platform?: string; notes?: string }) =>
    req<{ ok: boolean }>(`/api/clients/${clientId}/knives`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  recordKill: (clientId: number, data: { kill_type: string; kill_knife?: number }) =>
    req<{ ok: boolean }>(`/api/clients/${clientId}/kill`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  unkillClient: (clientId: number, reason: string) =>
    req<{ ok: boolean }>(`/api/clients/${clientId}/unkill`, {
      method: 'PUT',
      body: JSON.stringify({ reason }),
    }),

  // Cross-Role Notes
  clientRoleNotes: (clientId: number, role?: string) =>
    req<CrossRoleNote[]>(`/api/clients/${clientId}/role-notes${role ? `?role=${role}` : ''}`),

  addRoleNote: (clientId: number, data: { from_role: string; content: string }) =>
    req<{ ok: boolean }>(`/api/clients/${clientId}/role-notes`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Group Interactions
  clientGroupInteractions: (clientId: number) =>
    req<GroupInteraction[]>(`/api/clients/${clientId}/group-interactions`),

  addGroupInteraction: (clientId: number, data: {
    group_id?: string; actor_role: string; day_number?: number;
    script_completed?: boolean; client_read_messages?: boolean;
    client_replied?: boolean; client_pm_character?: boolean;
    client_left_group?: boolean; notes?: string
  }) =>
    req<{ ok: boolean }>(`/api/clients/${clientId}/group-interactions`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Group Interactions (list)
  listGroupInteractions: (params: { from_date?: string; to_date?: string; group_id?: string; page?: number; per_page?: number }) => {
    const p = new URLSearchParams()
    if (params.from_date) p.set('from_date', params.from_date)
    if (params.to_date) p.set('to_date', params.to_date)
    if (params.group_id) p.set('group_id', params.group_id)
    if (params.page) p.set('page', String(params.page))
    if (params.per_page) p.set('per_page', String(params.per_page))
    return req<{ total: number; page: number; per_page: number; items: GroupInteraction[] }>(`/api/group-interactions${p.toString() ? `?${p}` : ''}`)
  },

  // Organization
  orgTree: () => req<OrgUnit[]>('/api/org/tree'),

  createOrgUnit: (data: { name: string; unit_type: string; parent_id?: number; leader_staff_id?: number }) =>
    req<{ ok: boolean; id: number }>('/api/org/units', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
}
