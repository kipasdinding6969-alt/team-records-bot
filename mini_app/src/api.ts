import type { Client, ClientDetail, PipelineData, Stats, LeaderboardEntry, StaffMe } from './types'

const BASE = '/api'

function getInitData(): string {
  if (typeof window !== 'undefined' && window.Telegram?.WebApp?.initData) {
    return window.Telegram.WebApp.initData
  }
  return ''
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-Telegram-Init-Data': getInitData(),
      ...options?.headers,
    },
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`HTTP ${res.status}: ${text}`)
  }
  return res.json()
}

export const api = {
  getPipeline(): Promise<PipelineData> {
    return request('/pipeline')
  },

  getClient(id: number): Promise<ClientDetail> {
    return request(`/client/${id}`)
  },

  updateStatus(id: number, status: string): Promise<{ ok: boolean }> {
    return request(`/client/${id}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    })
  },

  addNote(id: number, content: string): Promise<{ ok: boolean }> {
    return request(`/client/${id}/note`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    })
  },

  getStats(): Promise<Stats> {
    return request('/stats')
  },

  getLeaderboard(): Promise<LeaderboardEntry[]> {
    return request('/leaderboard')
  },

  getMe(): Promise<StaffMe> {
    return request('/staff/me')
  },
}

// Extend window type for Telegram WebApp
declare global {
  interface Window {
    Telegram?: {
      WebApp?: {
        initData: string
        initDataUnsafe: Record<string, unknown>
        colorScheme: 'light' | 'dark'
        themeParams: Record<string, string>
        expand(): void
        close(): void
        ready(): void
        HapticFeedback?: {
          impactOccurred(style: string): void
          notificationOccurred(type: string): void
        }
      }
    }
  }
}
