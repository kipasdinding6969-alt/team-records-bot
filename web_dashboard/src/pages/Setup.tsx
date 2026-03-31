import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '10px 12px',
  background: '#1a1a2e',
  border: '1px solid #0f3460',
  borderRadius: 4,
  color: '#e0e0e0',
  fontSize: 14,
  outline: 'none',
  boxSizing: 'border-box',
}

export default function Setup() {
  const nav = useNavigate()
  const [form, setForm] = useState({
    display_name: '',
    username: '',
    password: '',
    confirm_password: '',
  })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  function set(field: string, value: string) {
    setForm(prev => ({ ...prev, [field]: value }))
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    if (form.password !== form.confirm_password) {
      setError('两次密码不一致')
      return
    }
    if (form.password.length < 6) {
      setError('密码至少 6 个字符')
      return
    }
    setLoading(true)
    try {
      await api.setup(form.username, form.password, form.display_name)
      nav('/login', { replace: true })
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '设置失败')
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
          width: 400,
        }}
      >
        <div style={{ marginBottom: 28, textAlign: 'center' }}>
          <div style={{ fontSize: 22, fontWeight: 700, color: '#e0e0e0' }}>首次设置</div>
          <div style={{ fontSize: 13, color: '#7f848e', marginTop: 6 }}>
            创建初始管理员账户
          </div>
        </div>

        <form onSubmit={submit}>
          {['display_name', 'username', 'password', 'confirm_password'].map(field => (
            <label key={field} style={{ display: 'block', marginBottom: 16 }}>
              <span style={{ fontSize: 12, color: '#7f848e', display: 'block', marginBottom: 6 }}>
                {
                  {
                    display_name: '显示名称',
                    username: '用户名',
                    password: '密码',
                    confirm_password: '确认密码',
                  }[field]
                }
              </span>
              <input
                type={field.includes('password') ? 'password' : 'text'}
                value={form[field as keyof typeof form]}
                onChange={e => set(field, e.target.value)}
                required
                autoFocus={field === 'display_name'}
                style={inputStyle}
              />
            </label>
          ))}

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
            }}
          >
            {loading ? '创建中...' : '创建账户'}
          </button>
        </form>
      </div>
    </div>
  )
}
