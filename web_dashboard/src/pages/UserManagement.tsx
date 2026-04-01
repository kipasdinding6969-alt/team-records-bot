import { useEffect, useState } from 'react'
import { api, getAuthState } from '../api'
import type { DashboardUser } from '../types'
import { ROLE_COLORS, ROLE_LABELS } from '../types'
import { useTheme } from '../ThemeContext'

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

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '9px 11px',
    background: theme.bg,
    border: `1px solid ${theme.cardBorder}`,
    borderRadius: 4,
    color: theme.textPrimary,
    fontSize: 13,
    outline: 'none',
    boxSizing: 'border-box',
  }

  const selectStyle: React.CSSProperties = {
    ...inputStyle,
    cursor: 'pointer',
  }

  const auth = getAuthState()
  const isOwner = auth?.role === 'owner'

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
      setError(e instanceof Error ? e.message : '加载失败')
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
          setFormError('请填写所有必填字段')
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
          setFormError('密码至少 6 个字符')
          return
        }
        await api.resetPassword(editTarget.id, resetPwd)
      }
      closeModal()
      await load()
    } catch (e: unknown) {
      setFormError(e instanceof Error ? e.message : '操作失败')
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
      setError(e instanceof Error ? e.message : '停用失败')
    }
  }

  async function reactivate(u: DashboardUser) {
    try {
      await api.updateUser(u.id, { is_active: true })
      await load()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '启用失败')
    }
  }

  const canEdit = (u: DashboardUser) => {
    if (!auth) return false
    if (auth.role === 'owner') return true
    return u.role === 'member' && u.team_scope === auth.team_scope
  }

  const th: React.CSSProperties = {
    padding: '10px 12px',
    textAlign: 'left',
    fontSize: 11,
    color: theme.textSecondary,
    fontWeight: 600,
    letterSpacing: 0.5,
    borderBottom: `1px solid ${theme.cardBorder}`,
  }

  const td: React.CSSProperties = {
    padding: '10px 12px',
    fontSize: 13,
    color: theme.textPrimary,
    borderBottom: `1px solid ${theme.cardBorder}`,
    verticalAlign: 'middle',
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: theme.textPrimary }}>用户管理</h2>
        <button
          onClick={openAdd}
          style={{
            padding: '8px 16px',
            background: theme.accent,
            border: 'none',
            borderRadius: 4,
            color: '#fff',
            fontSize: 13,
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          ＋ 添加用户
        </button>
      </div>

      {error && (
        <div style={{ background: theme.badgeRed, border: `1px solid ${theme.badgeRed}`, color: theme.badgeRed, padding: '8px 12px', borderRadius: 4, marginBottom: 16, fontSize: 13 }}>
          {error}
        </div>
      )}

      {loading ? (
        <div style={{ color: theme.textSecondary, padding: 20, textAlign: 'center' }}>加载中...</div>
      ) : (
        <div style={{ background: theme.cardBg, border: `1px solid ${theme.cardBorder}`, borderRadius: 6, overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                {['显示名称', '用户名', '角色', '团队', '状态', '最后登录', '操作'].map(h => (
                  <th key={h} style={th}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {users.map(u => (
                <tr key={u.id} style={{ opacity: u.is_active ? 1 : 0.5 }}>
                  <td style={td}>{u.display_name}</td>
                  <td style={{ ...td, color: theme.textSecondary }}>{u.username}</td>
                  <td style={td}>
                    <span style={{
                      fontSize: 10, fontWeight: 700,
                      color: ROLE_COLORS[u.role],
                      background: `${ROLE_COLORS[u.role]}22`,
                      border: `1px solid ${ROLE_COLORS[u.role]}`,
                      borderRadius: 3, padding: '2px 7px',
                      letterSpacing: 0.5, textTransform: 'uppercase',
                    }}>
                      {ROLE_LABELS[u.role] || u.role}
                    </span>
                  </td>
                  <td style={{ ...td, color: theme.textSecondary }}>{u.team_scope ?? '全部'}</td>
                  <td style={td}>
                    <span style={{ color: u.is_active ? '${theme.accent}' : theme.badgeRed, fontSize: 12 }}>
                      {u.is_active ? '活跃' : '已停用'}
                    </span>
                  </td>
                  <td style={{ ...td, color: theme.textSecondary, fontSize: 12 }}>
                    {u.last_login ? new Date(u.last_login).toLocaleDateString('zh-CN') : '—'}
                  </td>
                  <td style={td}>
                    <div style={{ display: 'flex', gap: 6 }}>
                      {canEdit(u) && (
                        <>
                          <button onClick={() => openEdit(u)} style={actionBtn('${theme.cardBorder}', '${theme.textSecondary}')}>编辑</button>
                          <button onClick={() => openReset(u)} style={actionBtn('${theme.cardBorder}', '${theme.chartLine}')}>重置密码</button>
                        </>
                      )}
                      {canEdit(u) && u.is_active && auth?.user_id !== u.id && (
                        confirmDeactivate === u.id ? (
                          <>
                            <button onClick={() => deactivate(u.id)} style={actionBtn('${theme.badgeRed}', '${theme.badgeRed}')}>确认停用</button>
                            <button onClick={() => setConfirmDeactivate(null)} style={actionBtn('${theme.cardBorder}', '${theme.textSecondary}')}>取消</button>
                          </>
                        ) : (
                          <button onClick={() => setConfirmDeactivate(u.id)} style={actionBtn('${theme.cardBorder}', '${theme.badgeRed}')}>停用</button>
                        )
                      )}
                      {canEdit(u) && !u.is_active && isOwner && (
                        <button onClick={() => reactivate(u)} style={actionBtn('${theme.cardBorder}', '${theme.accent}')}>启用</button>
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
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
        }}>
          <div style={{
            background: theme.cardBg, border: `1px solid ${theme.cardBorder}`, borderRadius: 8,
            padding: 32, width: 400, maxWidth: '90vw',
          }}>
            <h3 style={{ margin: '0 0 20px', fontSize: 16, color: theme.textPrimary }}>
              {modal === 'add' ? '添加用户' : modal === 'edit' ? '编辑用户' : '重置密码'}
            </h3>

            {modal === 'reset' ? (
              <>
                <p style={{ color: theme.textSecondary, fontSize: 13, marginTop: 0 }}>
                  为 <strong style={{ color: theme.textPrimary }}>{editTarget?.display_name}</strong> 设置新密码
                </p>
                <label style={{ display: 'block', marginBottom: 16 }}>
                  <span style={{ fontSize: 12, color: theme.textSecondary, display: 'block', marginBottom: 6 }}>新密码</span>
                  <input type="password" value={resetPwd} onChange={e => setResetPwd(e.target.value)} style={inputStyle} autoFocus />
                </label>
              </>
            ) : (
              <>
                <label style={{ display: 'block', marginBottom: 14 }}>
                  <span style={{ fontSize: 12, color: theme.textSecondary, display: 'block', marginBottom: 5 }}>显示名称 *</span>
                  <input value={form.display_name} onChange={e => setF('display_name', e.target.value)} style={inputStyle} autoFocus={modal === 'add'} />
                </label>

                {modal === 'add' && (
                  <>
                    <label style={{ display: 'block', marginBottom: 14 }}>
                      <span style={{ fontSize: 12, color: theme.textSecondary, display: 'block', marginBottom: 5 }}>用户名 *</span>
                      <input value={form.username} onChange={e => setF('username', e.target.value)} style={inputStyle} />
                    </label>
                    <label style={{ display: 'block', marginBottom: 14 }}>
                      <span style={{ fontSize: 12, color: theme.textSecondary, display: 'block', marginBottom: 5 }}>密码 *</span>
                      <input type="password" value={form.password} onChange={e => setF('password', e.target.value)} style={inputStyle} />
                    </label>
                  </>
                )}

                <label style={{ display: 'block', marginBottom: 14 }}>
                  <span style={{ fontSize: 12, color: theme.textSecondary, display: 'block', marginBottom: 5 }}>角色</span>
                  <select
                    value={form.role}
                    onChange={e => setF('role', e.target.value)}
                    style={selectStyle}
                    disabled={!isOwner}
                  >
                    {isOwner && <option value="owner">拥有者</option>}
                    {isOwner && <option value="admin">管理员</option>}
                    <option value="member">成员</option>
                  </select>
                </label>

                <label style={{ display: 'block', marginBottom: 14 }}>
                  <span style={{ fontSize: 12, color: theme.textSecondary, display: 'block', marginBottom: 5 }}>团队</span>
                  <input
                    value={form.team_scope}
                    onChange={e => setF('team_scope', e.target.value)}
                    placeholder="留空表示全部"
                    style={inputStyle}
                    disabled={!isOwner}
                  />
                </label>

                <label style={{ display: 'block', marginBottom: 14 }}>
                  <span style={{ fontSize: 12, color: theme.textSecondary, display: 'block', marginBottom: 5 }}>关联员工 ID</span>
                  <input
                    type="number"
                    value={form.staff_id}
                    onChange={e => setF('staff_id', e.target.value)}
                    placeholder="可选"
                    style={inputStyle}
                  />
                </label>
              </>
            )}

            {formError && (
              <div style={{ color: theme.badgeRed, fontSize: 12, marginBottom: 14, background: theme.badgeRed, padding: '6px 10px', borderRadius: 4 }}>
                {formError}
              </div>
            )}

            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button onClick={closeModal} style={actionBtn('${theme.cardBorder}', '${theme.textSecondary}')}>取消</button>
              <button
                onClick={saveUser}
                disabled={saving}
                style={{
                  padding: '8px 16px', background: saving ? '${theme.cardBorder}' : theme.accent,
                  border: 'none', borderRadius: 4, color: '#fff', fontSize: 13,
                  fontWeight: 600, cursor: saving ? 'not-allowed' : 'pointer',
                }}
              >
                {saving ? '保存中...' : '保存'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function actionBtn(bg: string, color: string): React.CSSProperties {
  return {
    padding: '5px 10px',
    background: bg,
    border: `1px solid ${color}`,
    borderRadius: 3,
    color,
    fontSize: 11,
    cursor: 'pointer',
    whiteSpace: 'nowrap',
  }
}
