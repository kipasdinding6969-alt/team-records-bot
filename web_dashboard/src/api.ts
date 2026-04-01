import type {
  Activity,
  AuthState,
  Client,
  ClientDetail,
  ClientList,
  DashboardStats,
  DashboardUser,
  FunnelStage,
  Staff,
  Trends,
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
    throw new Error(err.detail || 'Request failed')
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
    req<{
      access_token: string
      token_type: string
      username: string
      display_name: string
      role: AuthState['role']
      team_scope: string | null
      staff_id: number | null
      user_id: number
    }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password, remember_me }),
    }),

  verify: () =>
    req<{
      ok: boolean
      username: string
      role: AuthState['role']
      team_scope: string | null
      display_name: string
      staff_id: number | null
      user_id: number
    }>('/api/auth/verify'),

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
    req<any>(`/api/phone-registry/lookup?phone=${encodeURIComponent(phone)}`),

  phoneRegistrySearch: (q: string, page = 1) =>
    req<{ total: number; page: number; per_page: number; results: any[] }>(
      `/api/phone-registry/search?q=${encodeURIComponent(q)}&page=${page}`
    ),

  phoneRegistryStats: () => req<any>('/api/phone-registry/stats'),

  phoneRegistryOverride: (phone: string, new_submitter: string, new_staff_id?: number) =>
    req<{ ok: boolean }>(`/api/phone-registry/override?phone=${encodeURIComponent(phone)}`, {
      method: 'POST',
      body: JSON.stringify({ new_submitter, new_staff_id }),
    }),

  // Phase 16: Client Links
  clientLinks: (clientId: number) => req<any[]>(`/api/clients/${clientId}/links`),

  createClientLink: (data: { client_id_a: number; client_id_b: number; link_type?: string; note?: string }) =>
    req<{ ok: boolean }>('/api/client-links', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  deleteClientLink: (linkId: number) =>
    req<{ ok: boolean }>(`/api/client-links/${linkId}`, { method: 'DELETE' }),

  // Phase 16: Permissions
  staffPermissions: (staffId: number) => req<any>(`/api/permissions/${staffId}`),

  allPermissions: () => req<any[]>('/api/permissions'),

  setPermissionOverride: (data: { staff_id: number; command: string; allowed: boolean; reason?: string }) =>
    req<{ ok: boolean }>('/api/permissions', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  deletePermissionOverride: (staffId: number, command: string) =>
    req<{ ok: boolean }>(`/api/permissions/${staffId}/${command}`, { method: 'DELETE' }),

  // Phase 16.5: Client Notes
  clientNotes: (clientId: number) => req<any[]>(`/api/clients/${clientId}/notes`),

  addClientNote: (clientId: number, data: { content: string; note_type?: string; phone_normalized?: string }) =>
    req<{ ok: boolean }>(`/api/clients/${clientId}/notes`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  clientTimeline: (clientId: number) => req<any[]>(`/api/clients/${clientId}/timeline`),

  // Phase 16.5: Performance Dashboard
  performanceDaily: (date?: string, team?: string) => {
    const p = new URLSearchParams()
    if (date) p.set('date', date)
    if (team) p.set('team', team)
    return req<any>(`/api/performance/daily${p.toString() ? `?${p}` : ''}`)
  },

  performanceSummary: (from: string, to: string, team?: string) => {
    const p = new URLSearchParams({ from, to })
    if (team) p.set('team', team)
    return req<any>(`/api/performance/summary?${p}`)
  },

  // Phase 17: Org Chart
  orgChart: () => req<any>('/api/org-chart'),

  // Phase 17: Linked Timeline (cross-client)
  linkedTimeline: (clientId: number) => req<any>(`/api/clients/${clientId}/linked-timeline`),

  // Phase 17: Create client via dashboard
  createClient: (data: { phone: string; source: string; account_id?: string; nickname?: string; platform?: string }) =>
    req<{ ok: boolean; client_id: number }>('/api/clients', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Phase 17: Phone duplicate pre-check
  phoneCheck: (phone: string) =>
    req<any>(`/api/phone-registry/check?phone=${encodeURIComponent(phone)}`),

  // Phase 17: Bulk permissions
  bulkPermissions: (data: { staff_id: number; permissions: Record<string, boolean>; reason?: string }) =>
    req<{ ok: boolean; updated: number }>('/api/permissions/bulk', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Phase 17: Team performance
  teamPerformance: (team: string) => req<any>(`/api/team/${encodeURIComponent(team)}/performance`),
}
