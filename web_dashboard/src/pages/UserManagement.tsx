import { useEffect, useState } from 'react'
import { api, getAuthState } from '../api'
import type { DashboardUser } from '../types'
import { ROLE_COLORS, ROLE_LABELS } from '../types'
import { useTheme } from '../ThemeContext'
import { t, getLang } from '../i18n'

type ModalMode = 'add' | 'edit' | 'reset' | null

interface FormState {
  username: string
  display_name: string
  password: string
  role: string
  team_scope: string
  staff_id: string
}

const defaultForm: FormState = {
  username: '',
  display_name: '',
  password: '',
  role: 'member',
  team_scope: '',
  staff_id: '',
}

export default function UserManagement() {
  const { theme } = useTheme()

  const auth = getAuthState()
  const isOwner = auth?.role === 'owner'
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') closeModal() }
    window.addEventListener('keydown', handleEsc)
    return () => window.removeEventListener('keydown', handleEsc)
  }, [])

  const [users, setUsers] = useState<DashboardUser[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [modal, setModal] = useState<ModalMode>(null)
  const [editTarget, setEditTarget] = useState<DashboardUser | null>(null)
  const [form, setForm] = useState<FormState>(defaultForm)
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState('')
  const [resetPwd, setResetPwd] = useState('')
  const [confirmDeactivate, setConfirmDeactivate] = useState<number | null>(null)

  async function load() {
    setLoading(true)
    try {
      setUsers(await api.listUsers())
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t('common.error', getLang()))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  function openAdd() {
    setForm({ ...defaultForm, role: isOwner ? 'member' : 'member', team_scope: auth?.team_scope ?? '' })
    setFormError('')
    setEditTarget(null)
    setModal('add')
  }

  function openEdit(u: DashboardUser) {
    setForm({
      username: u.username,
      display_name: u.display_name,
      password: '',
      role: u.role,
      team_scope: u.team_scope ?? '',
      staff_id: u.staff_id?.toString() ?? '',
    })
    setFormError('')
    setEditTarget(u)
    setModal('edit')
  }

  function openReset(u: DashboardUser) {
    setResetPwd('')
    setFormError('')
    setEditTarget(u)
    setModal('reset')
  }

  function closeModal() {
    setModal(null)
    setEditTarget(null)
    setFormError('')
  }

  function setF(field: keyof FormState, value: string) {
    setForm(prev => ({ ...prev, [field]: value }))
  }

  async function saveUser() {
    setFormError('')
    setSaving(true)
    try {
      if (modal === 'add') {
        if (!form.username || !form.display_name || !form.password) {
          setFormError(t('users.all_required', getLang()))
          return
        }
        await api.createUser({
          username: form.username,
          display_name: form.display_name,
          password: form.password,
          role: form.role,
          team_scope: form.team_scope || null,
          staff_id: form.staff_id ? parseInt(form.staff_id) : null,
        })
      } else if (modal === 'edit' && editTarget) {
        const updates: Record<string, unknown> = {}
        if (form.display_name !== editTarget.display_name) updates.display_name = form.display_name
        if (isOwner && form.role !== editTarget.role) updates.role = form.role
        if (isOwner && (form.team_scope || null) !== editTarget.team_scope) updates.team_scope = form.team_scope || null
        if ((form.staff_id ? parseInt(form.staff_id) : null) !== editTarget.staff_id) {
          updates.staff_id = form.staff_id ? parseInt(form.staff_id) : null
        }
        if (Object.keys(updates).length > 0) {
          await api.updateUser(editTarget.id, updates)
        }
      } else if (modal === 'reset' && editTarget) {
        if (!resetPwd || resetPwd.length < 6) {
          setFormError(t('users.pwd_min_6', getLang()))
          return
        }
        await api.resetPassword(editTarget.id, resetPwd)
      }
      closeModal()
      await load()
    } catch (e: unknown) {
      setFormError(e instanceof Error ? e.message : t('common.error', getLang()))
    } finally {
      setSaving(false)
    }
  }

  async function deactivate(id: number) {
    try {
      await api.deactivateUser(id)
      setConfirmDeactivate(null)
      await load()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t('common.error', getLang()))
    }
  }

  async function reactivate(u: DashboardUser) {
    try {
      await api.updateUser(u.id, { is_active: true })
      await load()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t('common.error', getLang()))
    }
  }

  const canEdit = (u: DashboardUser) => {
    if (!auth) return false
    if (auth.role === 'owner') return true
    return u.role === 'member' && u.team_scope === auth.team_scope
  }

  return (
    <div className="page-container">
      <div className="toolbar">
        <h1 className="page-title">{t('users.title', getLang())}</h1>
        <div className="toolbar-spacer" />
        <button className="btn-primary" onClick={openAdd}>
          + {t('users.add', getLang())}
        </button>
      </div>

      {error && (
        <div className="alert alert-error">{error}</div>
      )}

      {loading ? (
        <div className="loading-state">{t('common.loading', getLang())}</div>
      ) : (
        <div className="card overflow-hidden">
          <table className="data-grid-table">
            <thead>
              <tr>
                <th>{t('users.display_name', getLang())}</th>
                <th>{t('users.username', getLang())}</th>
                <th>{t('users.role', getLang())}</th>
                <th>{t('users.team', getLang())}</th>
                <th>{t('users.status', getLang())}</th>
                <th>{t('users.last_login', getLang())}</th>
                <th>{t('users.actions', getLang())}</th>
              </tr>
            </thead>
            <tbody>
              {users.map(u => (
                <tr key={u.id} className={u.is_active ? '' : 'row-inactive'}>
                  <td>{u.display_name}</td>
                  <td className="text-secondary">{u.username}</td>
                  <td>
                    <span className="role-badge-dynamic" style={{
                      '--role-color': ROLE_COLORS[u.role],
                      '--role-bg': `${ROLE_COLORS[u.role]}22`,
                    } as React.CSSProperties}>
                      {ROLE_LABELS[u.role] || u.role}
                    </span>
                  </td>
                  <td className="text-secondary">{u.team_scope ?? t('users.all_teams', getLang())}</td>
                  <td>
                    <span className={`${u.is_active ? 'badge-success' : 'badge-danger'} fs-12`}>
                      {u.is_active ? t('users.active', getLang()) : t('users.deactivated', getLang())}
                    </span>
                  </td>
                  <td className="text-secondary fs-12">
                    {u.last_login ? new Date(u.last_login).toLocaleDateString(getLang() === 'zh' ? 'zh-CN' : 'en-US') : '\u2014'}
                  </td>
                  <td>
                    <div className="d-flex gap-8">
                      {canEdit(u) && (
                        <>
                          <button className="btn-secondary btn-sm" onClick={() => openEdit(u)}>{t('common.edit', getLang())}</button>
                          <button className="btn-secondary btn-sm" onClick={() => openReset(u)}>{t('users.reset_password', getLang())}</button>
                        </>
                      )}
                      {canEdit(u) && u.is_active && auth?.user_id !== u.id && (
                        confirmDeactivate === u.id ? (
                          <>
                            <button className="btn-danger btn-sm" onClick={() => deactivate(u.id)}>{t('users.confirm_deactivate', getLang())}</button>
                            <button className="btn-secondary btn-sm" onClick={() => setConfirmDeactivate(null)}>{t('common.cancel', getLang())}</button>
                          </>
                        ) : (
                          <button className="btn-danger btn-sm" onClick={() => setConfirmDeactivate(u.id)}>{t('users.deactivate', getLang())}</button>
                        )
                      )}
                      {canEdit(u) && !u.is_active && isOwner && (
                        <button className="btn-secondary btn-sm text-accent" onClick={() => reactivate(u)}>{t('users.reactivate', getLang())}</button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Modal */}
      {modal && (
        <div className="modal-overlay">
          <div className="modal-content w-480">
            <h3 className="modal-title">
              {modal === 'add' ? t('users.add', getLang()) : modal === 'edit' ? t('users.edit', getLang()) : t('users.reset_password', getLang())}
            </h3>

            {modal === 'reset' ? (
              <div className="form-grid">
                <p className="text-secondary fs-13 m-0">
                  {t('users.set_pwd_for', getLang())} <strong className="text-primary">{editTarget?.display_name}</strong>
                </p>
                <label>
                  <span className="field-label">{t('users.new_password', getLang())}</span>
                  <input className="input" type="password" value={resetPwd} onChange={e => setResetPwd(e.target.value)} autoFocus />
                </label>
              </div>
            ) : (
              <div className="form-grid">
                <label>
                  <span className="field-label">{t('users.display_name', getLang())} *</span>
                  <input className="input" value={form.display_name} onChange={e => setF('display_name', e.target.value)} autoFocus={modal === 'add'} />
                </label>

                {modal === 'add' && (
                  <>
                    <label>
                      <span className="field-label">{t('users.username', getLang())} *</span>
                      <input className="input" value={form.username} onChange={e => setF('username', e.target.value)} />
                    </label>
                    <label>
                      <span className="field-label">{t('users.password', getLang())} *</span>
                      <input className="input" type="password" value={form.password} onChange={e => setF('password', e.target.value)} />
                    </label>
                  </>
                )}

                <label>
                  <span className="field-label">{t('users.role', getLang())}</span>
                  <select className="input" value={form.role} onChange={e => setF('role', e.target.value)} disabled={!isOwner}>
                    {isOwner && <option value="owner">{t('role.owner', getLang())}</option>}
                    {isOwner && <option value="admin">{t('role.admin', getLang())}</option>}
                    <option value="member">{t('role.member', getLang())}</option>
                  </select>
                </label>

                <label>
                  <span className="field-label">{t('users.team', getLang())}</span>
                  <input className="input" value={form.team_scope} onChange={e => setF('team_scope', e.target.value)} placeholder={t('users.all_teams', getLang())} disabled={!isOwner} />
                </label>

                <label>
                  <span className="field-label">{t('users.linked_staff', getLang())}</span>
                  <input className="input" type="number" value={form.staff_id} onChange={e => setF('staff_id', e.target.value)} placeholder={t('users.optional', getLang())} />
                </label>
              </div>
            )}

            {formError && (
              <div className="alert alert-error alert-compact">
                {formError}
              </div>
            )}

            <div className="modal-actions">
              <button className="btn-secondary" onClick={closeModal}>{t('common.cancel', getLang())}</button>
              <button className="btn-primary" onClick={saveUser} disabled={saving}>
                {saving ? t('users.saving', getLang()) : t('common.save', getLang())}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
