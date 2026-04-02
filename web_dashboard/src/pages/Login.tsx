import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, isAuthenticated, setAuthState } from '../api'
import { useTheme } from '../ThemeContext'
import { t, getLang } from '../i18n'

export default function Login() {
  const { theme } = useTheme()
  const nav = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [rememberMe, setRememberMe] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const alreadyAuthed = isAuthenticated()
  useEffect(() => {
    if (alreadyAuthed) {
      nav('/', { replace: true })
    }
  }, [alreadyAuthed, nav])

  if (alreadyAuthed) {
    return null
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await api.login(username, password, rememberMe)
      setAuthState(
        {
          token: res.access_token,
          username: res.username,
          display_name: res.display_name,
          role: res.role,
          team_scope: res.team_scope,
          staff_id: res.staff_id,
          user_id: res.user_id,
        },
        rememberMe
      )
      nav('/', { replace: true })
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t('login.failed', getLang()))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        background: theme.bg,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexDirection: 'column',
      }}
    >
      <div className="card" style={{ width: '100%', maxWidth: 400, padding: 24, background: theme.bgElevated }}>
        <div style={{ marginBottom: 20, textAlign: 'center' }}>
          <div style={{
            width: 56, height: 56, borderRadius: 12, background: theme.accent,
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            color: '#fff', fontWeight: 'bold', fontSize: 28, marginBottom: 20,
            boxShadow: `0 8px 24px ${theme.accentLight}`
          }}>
            T
          </div>
          <div style={{ fontSize: 28, fontWeight: 800, color: theme.textPrimary, letterSpacing: '-0.02em' }}>{t('login.title', getLang())}</div>
          <div style={{ fontSize: 14, color: theme.textSecondary, marginTop: 8, fontWeight: 500, letterSpacing: 2 }}>{t('login.subtitle', getLang())}</div>
        </div>
        <form onSubmit={submit} className="form-grid">
          <label>
            <span>{t('login.username', getLang())}</span>
            <input
              className="input"
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              autoFocus
              required
            />
          </label>
          <label>
            <span>{t('login.password', getLang())}</span>
            <input
              className="input"
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
            />
          </label>
          <label
            style={{
              display: 'flex',
              flexDirection: 'row',
              alignItems: 'center',
              gap: 8,
              cursor: 'pointer',
            }}
          >
            <input
              type="checkbox"
              checked={rememberMe}
              onChange={e => setRememberMe(e.target.checked)}
              style={{ accentColor: theme.accent, width: 16, height: 16 }}
            />
            <span style={{ fontSize: 13, color: theme.textSecondary, fontWeight: 500 }}>{t('login.remember', getLang())}</span>
          </label>
          {error && (
            <div className="badge-danger" style={{ padding: 12, fontSize: 14, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8 }}>
              {error}
            </div>
          )}
          <button
            className="btn-primary"
            type="submit"
            disabled={loading}
            style={{ width: '100%', height: 48, fontSize: 16, fontWeight: 700, marginTop: 8 }}
          >
            {loading ? t('login.logging_in', getLang()) : t('login.submit', getLang())}
          </button>
        </form>
      </div>
      <div style={{ marginTop: 20, fontSize: 13, color: theme.textMuted, fontWeight: 500, letterSpacing: 0.5 }}>
        v2.0 — Phase 23
      </div>
    </div>
  )
}
