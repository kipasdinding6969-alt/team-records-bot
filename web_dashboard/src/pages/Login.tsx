import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, isAuthenticated, setAuthState } from '../api'
import { t, getLang } from '../i18n'
import { Spinner } from '../components/SharedUI'

export default function Login() {
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
    return <div className="d-flex align-center justify-center min-h-200"><Spinner label="Redirecting..." /></div>
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
          <div className="subtitle login-subtitle">{t('login.subtitle', getLang())}</div>
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
            className="btn-primary btn-login"
            type="submit"
            disabled={loading}
          >
            {loading ? t('login.logging_in', getLang()) : t('login.submit', getLang())}
          </button>
        </form>
      </div>
      <div className="login-version">
        v2.11 — Phase 34
      </div>
    </div>
  )
}
