import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { t, getLang } from '../i18n'

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
    <div className="login-page">
      <div className="card login-card">
        <div className="setup-header">
          <div className="heading-lg">{t('setup.title', getLang())}</div>
          <div className="subtitle mt-8">
            {t('setup.subtitle', getLang())}
          </div>
        </div>

        <form onSubmit={submit} className="form-grid">
          {['display_name', 'username', 'password', 'confirm_password'].map(field => (
            <label key={field}>
              <span className="field-label">
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
            <div className="alert alert-error">
              {error}
            </div>
          )}

          <button className="btn-primary w-full" type="submit" disabled={loading}>
            {loading ? t('setup.creating', getLang()) : t('setup.create', getLang())}
          </button>
        </form>
      </div>
    </div>
  )
}
