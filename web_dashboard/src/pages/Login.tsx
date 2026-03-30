import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, isAuthenticated, setToken } from '../api'

export default function Login() {
  const nav = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
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
      const res = await api.login(username, password)
      setToken(res.access_token)
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
        background: '#1a1a2e',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <div
        style={{
          background: '#16213e',
          border: '1px solid #0f3460',
          borderRadius: 8,
          padding: 40,
          width: 360,
        }}
      >
        <div style={{ marginBottom: 32, textAlign: 'center' }}>
          <div style={{ fontSize: 24, fontWeight: 700, color: '#e0e0e0' }}>团队记录</div>
          <div style={{ fontSize: 13, color: '#7f848e', marginTop: 6 }}>Manager Dashboard</div>
        </div>
        <form onSubmit={submit}>
          <label style={{ display: 'block', marginBottom: 16 }}>
            <span style={{ fontSize: 12, color: '#7f848e', display: 'block', marginBottom: 6 }}>
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
          <label style={{ display: 'block', marginBottom: 24 }}>
            <span style={{ fontSize: 12, color: '#7f848e', display: 'block', marginBottom: 6 }}>
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
          {error && (
            <div
              style={{
                background: '#2d1515',
                border: '1px solid #ff7675',
                color: '#ff7675',
                padding: '8px 12px',
                borderRadius: 4,
                fontSize: 13,
                marginBottom: 16,
              }}
            >
              {error}
            </div>
          )}
          <button
            type="submit"
            disabled={loading}
            style={{
              width: '100%',
              padding: '11px',
              background: loading ? '#0f3460' : '#00b894',
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

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '10px 12px',
  background: '#1a1a2e',
  border: '1px solid #0f3460',
  borderRadius: 4,
  color: '#e0e0e0',
  fontSize: 14,
  outline: 'none',
}
