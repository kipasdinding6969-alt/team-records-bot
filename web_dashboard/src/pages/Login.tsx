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
    <div className="login-page">
      <div className="card login-card">
        <div className="login-brand">
          <div className="login-brand-icon">
            T
          </div>
          <div className="heading-lg">{t('login.title', getLang())}</div>
          <div className="subtitle" style={{ letterSpacing: 2 }}>{t('login.subtitle', getLang())}</div>
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
          <label className="remember-label">
            <input
              type="checkbox"
              checked={rememberMe}
              onChange={e => setRememberMe(e.target.checked)}
            />
            <span>{t('login.remember', getLang())}</span>
          </label>
          {error && (
            <div className="alert alert-error">
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
      <div className="login-version">
        v2.9 — Phase 29
      </div>
    </div>
  )
}
