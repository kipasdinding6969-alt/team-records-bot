import type {
  Activity,
  Client,
  ClientDetail,
  ClientList,
  DashboardStats,
  FunnelStage,
  Staff,
  Trends,
} from './types'

const BASE = ''

export function getToken(): string {
  return localStorage.getItem('dashboard_token') || ''
}

export function setToken(token: string) {
  localStorage.setItem('dashboard_token', token)
}

export function clearToken() {
  localStorage.removeItem('dashboard_token')
}

export function isAuthenticated(): boolean {
  return !!getToken()
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
    clearToken()
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
  login: (username: string, password: string) =>
    req<{ access_token: string; token_type: string }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),

  verify: () => req<{ ok: boolean; username: string }>('/api/auth/verify'),

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

  // pipeline endpoint reused from mini app (same DB)
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
}
