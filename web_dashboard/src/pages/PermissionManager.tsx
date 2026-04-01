import { useEffect, useState } from 'react'
import { api } from '../api'
import { getLang, t } from '../i18n'
import { useTheme } from '../ThemeContext'

interface PermOverride {
  command: string
  allowed: boolean
  reason: string | null
}

interface StaffPerms {
  staff_id: number
  display_name: string
  role: string
  team: string | null
  overrides: PermOverride[]
}



export default function PermissionManager() {
  const { theme } = useTheme()
  const lang = getLang()

  const S = {
  page: {
    color: theme.textPrimary,
    minHeight: '100%',
  } as React.CSSProperties,
  title: {
    fontSize: 22,
    fontWeight: 700,
    color: theme.textPrimary,
    margin: '0 0 24px',
  } as React.CSSProperties,
  layout: {
    display: 'flex',
    gap: 20,
    minHeight: 500,
  } as React.CSSProperties,
  leftPanel: {
    width: 240,
    flexShrink: 0,
    background: theme.cardBg,
    border: `1px solid ${theme.cardBorder}`,
    borderRadius: 8,
    overflow: 'hidden',
    alignSelf: 'flex-start',
  } as React.CSSProperties,
  leftHeader: {
    padding: '12px 16px',
    borderBottom: `1px solid ${theme.cardBorder}`,
    fontSize: 12,
    fontWeight: 700,
    color: theme.textSecondary,
    textTransform: 'uppercase' as const,
    letterSpacing: 0.5,
  },
  staffItem: (selected: boolean): React.CSSProperties => ({
    padding: '11px 16px',
    cursor: 'pointer',
    background: selected ? '${theme.cardBorder}' : 'transparent',
    borderLeft: `3px solid ${selected ? '#00b894' : 'transparent'}`,
    borderBottom: `1px solid ${theme.cardBorder}`,
    transition: 'all 0.12s',
  }),
  staffName: {
    fontSize: 13,
    fontWeight: 600,
    color: theme.textPrimary,
  },
  staffMeta: {
    fontSize: 11,
    color: theme.textSecondary,
    marginTop: 2,
  },
  roleBadge: (role: string): React.CSSProperties => {
    const colors: Record<string, string> = {
      owner: theme.chartLine,
      admin: '#74b9ff',
      member: theme.textSecondary,
    }
    const c = colors[role] || '${theme.textSecondary}'
    return {
      display: 'inline-block',
      fontSize: 9,
      fontWeight: 700,
      color: c,
      background: `${c}22`,
      border: `1px solid ${c}`,
      borderRadius: 3,
      padding: '1px 5px',
      letterSpacing: 0.5,
      textTransform: 'uppercase',
      marginLeft: 6,
    }
  },
  rightPanel: {
    flex: 1,
    background: theme.cardBg,
    border: `1px solid ${theme.cardBorder}`,
    borderRadius: 8,
    padding: 20,
  } as React.CSSProperties,
  sectionTitle: {
    fontSize: 12,
    fontWeight: 700,
    color: theme.textSecondary,
    textTransform: 'uppercase' as const,
    letterSpacing: 0.5,
    marginBottom: 12,
  },
  overrideRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '9px 0',
    borderBottom: `1px solid ${theme.cardBorder}`,
    fontSize: 13,
  } as React.CSSProperties,
  allowedBadge: {
    fontSize: 10,
    fontWeight: 700,
    padding: '2px 8px',
    borderRadius: 3,
    letterSpacing: 0.5,
    textTransform: 'uppercase' as const,
    flexShrink: 0,
  },
  cmdText: {
    fontFamily: 'monospace',
    color: theme.textPrimary,
    flex: 1,
    minWidth: 80,
  },
  reasonText: {
    color: theme.textSecondary,
    fontSize: 12,
    flex: 2,
  },
  deleteBtn: {
    background: 'transparent',
    border: '1px solid #d6303166',
    color: '#d63031',
    borderRadius: 4,
    padding: '3px 10px',
    fontSize: 11,
    cursor: 'pointer',
    flexShrink: 0,
  } as React.CSSProperties,
  addForm: {
    marginTop: 20,
    background: theme.cardBorder,
    borderRadius: 6,
    padding: 16,
  } as React.CSSProperties,
  addTitle: {
    fontSize: 12,
    fontWeight: 700,
    color: theme.textSecondary,
    textTransform: 'uppercase' as const,
    letterSpacing: 0.5,
    marginBottom: 12,
  },
  formRow: {
    display: 'flex',
    gap: 10,
    flexWrap: 'wrap' as const,
    alignItems: 'center',
  } as React.CSSProperties,
  input: {
    padding: '8px 12px',
    background: theme.cardBg,
    border: `1px solid ${theme.cardBorder}`,
    color: theme.textPrimary,
    borderRadius: 5,
    fontSize: 13,
    outline: 'none',
  } as React.CSSProperties,
  toggleBtn: (allowed: boolean): React.CSSProperties => ({
    padding: '8px 14px',
    background: allowed ? '${theme.accent}33' : theme.badgeRed,
    border: `1px solid ${allowed ? '#00b894' : '#d63031'}`,
    color: allowed ? '${theme.accent}' : '#d63031',
    borderRadius: 5,
    fontSize: 12,
    fontWeight: 700,
    cursor: 'pointer',
    flexShrink: 0,
  }),
  saveBtn: {
    padding: '8px 18px',
    background: theme.accent,
    border: 'none',
    color: '#fff',
    borderRadius: 5,
    fontSize: 13,
    fontWeight: 600,
    cursor: 'pointer',
    flexShrink: 0,
  } as React.CSSProperties,
  emptyMsg: {
    color: theme.textSecondary,
    fontSize: 13,
    padding: '12px 0',
  },
  infoRow: {
    display: 'flex',
    gap: 24,
    marginBottom: 20,
    flexWrap: 'wrap' as const,
  } as React.CSSProperties,
  infoField: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: 3,
  } as React.CSSProperties,
  infoLabel: {
    fontSize: 11,
    color: theme.textSecondary,
    textTransform: 'uppercase' as const,
    letterSpacing: 0.5,
  } as React.CSSProperties,
  infoValue: {
    fontSize: 14,
    color: theme.textPrimary,
    fontWeight: 600,
  },
  }

  const [staffList, setStaffList] = useState<StaffPerms[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<StaffPerms | null>(null)
  const [newCmd, setNewCmd] = useState('')
  const [newAllowed, setNewAllowed] = useState(true)
  const [newReason, setNewReason] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState('')

  async function loadAll() {
    setLoading(true)
    try {
      const data = await api.allPermissions()
      setStaffList(data)
      if (selected) {
        const refreshed = data.find((s: StaffPerms) => s.staff_id === selected.staff_id)
        if (refreshed) setSelected(refreshed)
      }
    } catch {
      // silent
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAll()
  }, [])

  async function handleDelete(staffId: number, command: string) {
    try {
      await api.deletePermissionOverride(staffId, command)
      await loadAll()
    } catch {
      // silent
    }
  }

  async function handleSave() {
    if (!selected || !newCmd.trim()) return
    setSaving(true)
    setSaveMsg('')
    try {
      await api.setPermissionOverride({
        staff_id: selected.staff_id,
        command: newCmd.trim(),
        allowed: newAllowed,
        reason: newReason.trim() || undefined,
      })
      setNewCmd('')
      setNewReason('')
      setNewAllowed(true)
      setSaveMsg('Saved.')
      await loadAll()
    } catch (e: any) {
      setSaveMsg(e.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div style={S.page}>
      <h1 style={S.title}>{t('perm.title', lang)}</h1>

      {loading ? (
        <div style={{ color: theme.textSecondary, fontSize: 14 }}>{t('perm.loading', lang)}</div>
      ) : (
        <div style={S.layout}>
          <div style={S.leftPanel}>
            <div style={S.leftHeader}>{t('perm.staff', lang)} ({staffList.length})</div>
            {staffList.map(s => (
              <div
                key={s.staff_id}
                style={S.staffItem(selected?.staff_id === s.staff_id)}
                onClick={() => { setSelected(s); setSaveMsg('') }}
              >
                <div style={S.staffName}>
                  {s.display_name}
                  <span style={S.roleBadge(s.role)}>{s.role}</span>
                </div>
                {(s.team || s.overrides.length > 0) && (
                  <div style={S.staffMeta}>
                    {s.team && <span>{s.team}</span>}
                    {s.overrides.length > 0 && (
                      <span style={{ marginLeft: s.team ? 8 : 0 }}>
                        {s.overrides.length} override{s.overrides.length !== 1 ? 's' : ''}
                      </span>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>

          <div style={S.rightPanel}>
            {!selected ? (
              <div style={S.emptyMsg}>Select a staff member to manage permissions.</div>
            ) : (
              <>
                <div style={S.infoRow}>
                  <div style={S.infoField}>
                    <span style={S.infoLabel}>{t('perm.role', lang)}</span>
                    <span style={S.infoValue}>
                      {selected.role}
                      {selected.team && (
                        <span style={{ color: theme.textSecondary, fontWeight: 400, marginLeft: 8 }}>
                          {selected.team}
                        </span>
                      )}
                    </span>
                  </div>
                  <div style={S.infoField}>
                    <span style={S.infoLabel}>Staff ID</span>
                    <span style={S.infoValue}>#{selected.staff_id}</span>
                  </div>
                </div>

                {/* Section-level permission toggles */}
                <div style={{ ...S.sectionTitle, marginTop: 4 }}>
                  {t('perm.section_permissions', lang)}
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginBottom: 20 }}>
                  {['view_clients', 'edit_clients', 'add_clients', 'view_performance', 'export_data', 'manage_team'].map(section => {
                    const ov = selected.overrides.find((o: PermOverride) => o.command === section)
                    const isAllowed = ov ? ov.allowed : true
                    return (
                      <div
                        key={section}
                        onClick={async () => {
                          try {
                            await api.setPermissionOverride({
                              staff_id: selected.staff_id,
                              command: section,
                              allowed: !isAllowed,
                              reason: `Toggle from dashboard`,
                            })
                            await loadAll()
                          } catch { /* silent */ }
                        }}
                        style={{
                          display: 'flex', alignItems: 'center', gap: 8,
                          padding: '10px 12px', borderRadius: 6, cursor: 'pointer',
                          background: isAllowed ? '${theme.accent}15' : '#d6303115',
                          border: `1px solid ${isAllowed ? '#00b89444' : '#d6303144'}`,
                          transition: 'all 0.15s',
                        }}
                      >
                        <div style={{
                          width: 36, height: 20, borderRadius: 10,
                          background: isAllowed ? '${theme.accent}' : '#636e72',
                          position: 'relative', transition: 'background 0.15s',
                        }}>
                          <div style={{
                            width: 16, height: 16, borderRadius: '50%', background: '#fff',
                            position: 'absolute', top: 2,
                            left: isAllowed ? 18 : 2,
                            transition: 'left 0.15s',
                          }} />
                        </div>
                        <span style={{ fontSize: 12, color: theme.textPrimary, fontWeight: 500 }}>
                          {t(`perm.${section}`, lang)}
                        </span>
                      </div>
                    )
                  })}
                </div>

                <div style={S.sectionTitle}>
                  {t('perm.overrides', lang)} ({selected.overrides.length})
                </div>

                {selected.overrides.length === 0 ? (
                  <div style={S.emptyMsg}>{t('perm.no_overrides', lang)}</div>
                ) : (
                  selected.overrides.map(ov => (
                    <div key={ov.command} style={S.overrideRow}>
                      <span style={S.cmdText}>/{ov.command}</span>
                      <span style={{
                        ...S.allowedBadge,
                        background: ov.allowed ? '${theme.accent}33' : theme.badgeRed,
                        color: ov.allowed ? '${theme.accent}' : '#d63031',
                        border: `1px solid ${ov.allowed ? '#00b894' : '#d63031'}`,
                      }}>
                        {ov.allowed ? t('perm.allowed', lang) : t('perm.denied', lang)}
                      </span>
                      <span style={S.reasonText}>{ov.reason || '—'}</span>
                      <button
                        style={S.deleteBtn}
                        onClick={() => handleDelete(selected.staff_id, ov.command)}
                      >
                        {t('common.delete', lang)}
                      </button>
                    </div>
                  ))
                )}

                <div style={S.addForm}>
                  <div style={S.addTitle}>{t('perm.add_override', lang)}</div>
                  <div style={S.formRow}>
                    <input
                      style={{ ...S.input, width: 140 }}
                      placeholder={t('perm.command', lang)}
                      value={newCmd}
                      onChange={e => setNewCmd(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && handleSave()}
                    />
                    <button
                      style={S.toggleBtn(newAllowed)}
                      onClick={() => setNewAllowed(a => !a)}
                    >
                      {newAllowed ? t('perm.allowed', lang) : t('perm.denied', lang)}
                    </button>
                    <input
                      style={{ ...S.input, flex: 1, minWidth: 140 }}
                      placeholder={t('perm.reason', lang)}
                      value={newReason}
                      onChange={e => setNewReason(e.target.value)}
                    />
                    <button style={S.saveBtn} onClick={handleSave} disabled={saving || !newCmd.trim()}>
                      {saving ? '...' : t('perm.save', lang)}
                    </button>
                  </div>
                  {saveMsg && (
                    <div style={{
                      marginTop: 8,
                      fontSize: 12,
                      color: saveMsg.includes('fail') || saveMsg.includes('error') ? '#e88' : theme.accent,
                    }}>
                      {saveMsg}
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
