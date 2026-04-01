import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, isAuthenticated, setAuthState } from '../api'
import { useTheme } from '../ThemeContext'

export default function Login() {
  const { theme } = useTheme()

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '10px 12px',
    background: theme.bg,
    border: `1px solid ${theme.cardBorder}`,
    borderRadius: 4,
    color: theme.textPrimary,
    fontSize: 14,
    outline: 'none',
    boxSizing: 'border-box',
  }

  const nav = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [rememberMe, setRememberMe] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  if (isAuthenticated()) {
    nav('/', { replace: true })
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
      setError(err instanceof Error ? err.message : '登录失败')
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
      }}
    >
      <div
        style={{
          background: theme.cardBg,
          border: `1px solid ${theme.cardBorder}`,
          borderRadius: 8,
          padding: 40,
          width: 360,
        }}
      >
        <div style={{ marginBottom: 32, textAlign: 'center' }}>
          <div style={{ fontSize: 24, fontWeight: 700, color: theme.textPrimary }}>团队记录</div>
          <div style={{ fontSize: 13, color: theme.textSecondary, marginTop: 6 }}>Manager Dashboard</div>
        </div>
        <form onSubmit={submit}>
          <label style={{ display: 'block', marginBottom: 16 }}>
            <span style={{ fontSize: 12, color: theme.textSecondary, display: 'block', marginBottom: 6 }}>
              用户名
            </span>
            <input
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              autoFocus
              required
              style={inputStyle}
            />
          </label>
          <label style={{ display: 'block', marginBottom: 16 }}>
            <span style={{ fontSize: 12, color: theme.textSecondary, display: 'block', marginBottom: 6 }}>
              密码
            </span>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
              style={inputStyle}
            />
          </label>
          <label
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              marginBottom: 24,
              cursor: 'pointer',
            }}
          >
            <input
              type="checkbox"
              checked={rememberMe}
              onChange={e => setRememberMe(e.target.checked)}
              style={{ accentColor: theme.accent, width: 14, height: 14 }}
            />
            <span style={{ fontSize: 12, color: theme.textSecondary }}>记住我 (30 天)</span>
          </label>
          {error && (
            <div
              style={{
                background: theme.badgeRed,
                border: `1px solid ${theme.badgeRed}`,
                color: theme.badgeRed,
                padding: '8px 12px',
                borderRadius: 4,
                fontSize: 13,
                marginBottom: 16,
              }}
            >
              {error}
            </div>
          )}
          <button className="glass-btn"
            type="submit"
            disabled={loading}
            style={{
              width: '100%',
              padding: '11px',
              background: loading ? '${theme.cardBorder}' : theme.accent,
              border: 'none',
              borderRadius: 4,
              color: '#fff',
              fontSize: 14,
              fontWeight: 600,
              cursor: loading ? 'not-allowed' : 'pointer',
              transition: 'background 0.15s',
            }}
          >
            {loading ? '登录中...' : '登录'}
          </button>
        </form>
      </div>
    </div>
  )
}


