import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useTheme } from '../ThemeContext'
import { t, getLang } from '../i18n'

export default function Setup() {
  const { theme } = useTheme()
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
      setError(t('setup.pwd_mismatch', getLang()))
      return
    }
    if (form.password.length < 6) {
      setError(t('setup.pwd_min', getLang()))
      return
    }
    setLoading(true)
    try {
      await api.setup(form.username, form.password, form.display_name)
      nav('/login', { replace: true })
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t('setup.failed', getLang()))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: theme.bg, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div className="card" style={{ width: 400, background: theme.bgElevated }}>
        <div style={{ marginBottom: 24, textAlign: 'center' }}>
          <div style={{ fontSize: 24, fontWeight: 700, color: theme.textPrimary }}>{t('setup.title', getLang())}</div>
          <div style={{ fontSize: 13, color: theme.textSecondary, marginTop: 8 }}>
            {t('setup.subtitle', getLang())}
          </div>
        </div>

        <form onSubmit={submit} className="form-grid">
          {['display_name', 'username', 'password', 'confirm_password'].map(field => (
            <label key={field}>
              <span style={{ fontSize: 12, color: theme.textSecondary, marginBottom: 4, display: 'block' }}>
                {
                  {
                    display_name: t('setup.display_name', getLang()),
                    username: t('setup.username', getLang()),
                    password: t('setup.password', getLang()),
                    confirm_password: t('setup.confirm_password', getLang()),
                  }[field]
                }
              </span>
              <input
                className="input"
                type={field.includes('password') ? 'password' : 'text'}
                value={form[field as keyof typeof form]}
                onChange={e => set(field, e.target.value)}
                required
                autoFocus={field === 'display_name'}
              />
            </label>
          ))}

          {error && (
            <div className="badge-danger" style={{ padding: 12, fontSize: 14, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8 }}>
              {error}
            </div>
          )}

          <button className="btn-primary" type="submit" disabled={loading} style={{ width: '100%' }}>
            {loading ? t('setup.creating', getLang()) : t('setup.create', getLang())}
          </button>
        </form>
      </div>
    </div>
  )
}
