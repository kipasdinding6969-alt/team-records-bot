import { useState, useEffect, useCallback, useRef } from 'react'
import { api } from './api'
import { PipelineData, Stats, LeaderboardEntry, TabId } from './types'
import { t } from './i18n'
import KanbanBoard from './components/KanbanBoard'
import Dashboard from './components/Dashboard'
import Leaderboard from './components/Leaderboard'
import './styles/app.css'

const LANG = 'zh'

// SVG icons
const IconKanban = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <rect x="3" y="3" width="5" height="18" rx="1"/>
    <rect x="10" y="3" width="5" height="12" rx="1"/>
    <rect x="17" y="3" width="4" height="16" rx="1"/>
  </svg>
)

const IconToday = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <rect x="3" y="4" width="18" height="18" rx="2"/>
    <line x1="16" y1="2" x2="16" y2="6"/>
    <line x1="8" y1="2" x2="8" y2="6"/>
    <line x1="3" y1="10" x2="21" y2="10"/>
    <line x1="8" y1="14" x2="8" y2="14" strokeWidth="3" strokeLinecap="round"/>
    <line x1="12" y1="14" x2="12" y2="14" strokeWidth="3" strokeLinecap="round"/>
    <line x1="16" y1="14" x2="16" y2="14" strokeWidth="3" strokeLinecap="round"/>
  </svg>
)

const IconLeaderboard = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/>
    <polyline points="17 6 23 6 23 12"/>
  </svg>
)

export default function App() {
  const [tab, setTab] = useState<TabId>('kanban')
  const [pipeline, setPipeline] = useState<PipelineData | null>(null)
  const [stats, setStats] = useState<Stats | null>(null)
  const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [toast, setToast] = useState('')
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Check if running inside Telegram
  const isTelegram = !!(window.Telegram?.WebApp?.initData)

  // Initialize Telegram Mini App
  useEffect(() => {
    const tg = window.Telegram?.WebApp
    if (tg) {
      tg.ready()
      tg.expand()
    }
  }, [])

  const loadAll = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const [p, s, lb] = await Promise.all([
        api.getPipeline(),
        api.getStats(),
        api.getLeaderboard(),
      ])
      setPipeline(p)
      setStats(s)
      setLeaderboard(lb)
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadAll() }, [loadAll])

  function showToast(msg: string) {
    setToast(msg)
    if (toastTimer.current) clearTimeout(toastTimer.current)
    toastTimer.current = setTimeout(() => setToast(''), 2000)
  }

  function handleTabChange(newTab: TabId) {
    setTab(newTab)
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred('light')
  }

  if (loading) {
    return (
      <div className="app">
        <div className="app-content">
          <div className="loading-container">
            <div className="spinner" />
            <span>{t('loading', LANG)}</span>
          </div>
        </div>
      </div>
    )
  }

  if (!isTelegram && error) {
    return (
      <div className="app">
        <div className="app-content">
          <div className="loading-container" style={{ textAlign: 'center', padding: '2rem' }}>
            <span style={{ fontSize: '3rem', display: 'block', marginBottom: '1rem' }}>📱</span>
            <span style={{ fontSize: '1.1rem', fontWeight: 600 }}>请在 Telegram 中打开</span>
            <span style={{ color: '#888', marginTop: '0.5rem', display: 'block' }}>
              此应用需要通过 Telegram Bot 菜单打开
            </span>
            <span style={{ color: '#666', marginTop: '1rem', display: 'block', fontSize: '0.85rem' }}>
              Please open this app via the Telegram Bot menu
            </span>
          </div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="app">
        <div className="app-content">
          <div className="loading-container">
            <span>{t('error_load', LANG)}</span>
            <button className="btn-primary" style={{ width: 120 }} onClick={loadAll}>
              {t('retry', LANG)}
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="app">
      <div className="app-content">
        {tab === 'kanban' && pipeline && (
          <KanbanBoard
            data={pipeline}
            lang={LANG}
            onRefresh={loadAll}
            showToast={showToast}
          />
        )}
        {tab === 'today' && stats && (
          <Dashboard stats={stats} lang={LANG} />
        )}
        {tab === 'leaderboard' && leaderboard && (
          <Leaderboard entries={leaderboard} lang={LANG} />
        )}
      </div>

      <nav className="bottom-nav">
        <button
          className={`nav-tab ${tab === 'kanban' ? 'active' : ''}`}
          onClick={() => handleTabChange('kanban')}
        >
          <IconKanban />
          {t('tab_kanban', LANG)}
        </button>
        <button
          className={`nav-tab ${tab === 'today' ? 'active' : ''}`}
          onClick={() => handleTabChange('today')}
        >
          <IconToday />
          {t('tab_today', LANG)}
        </button>
        <button
          className={`nav-tab ${tab === 'leaderboard' ? 'active' : ''}`}
          onClick={() => handleTabChange('leaderboard')}
        >
          <IconLeaderboard />
          {t('tab_leaderboard', LANG)}
        </button>
      </nav>

      {/* Toast notification */}
      <div className={`toast ${toast ? 'show' : ''}`}>{toast}</div>
    </div>
  )
}
