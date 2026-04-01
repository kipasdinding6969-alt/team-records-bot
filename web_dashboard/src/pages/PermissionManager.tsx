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
      fontSize: 24,
      fontWeight: 700,
      color: theme.textPrimary,
      margin: '0 0 8px',
      letterSpacing: '-0.02em',
    } as React.CSSProperties,
    subtitle: {
      fontSize: 15,
      color: theme.textSecondary,
      marginBottom: 32,
    } as React.CSSProperties,
    layout: {
      display: 'flex',
      gap: 24,
      minHeight: 500,
      alignItems: 'flex-start',
    } as React.CSSProperties,
    leftPanel: {
      width: 280,
      flexShrink: 0,
      background: theme.cardBg,
      border: `1px solid ${theme.cardBorder}`,
      borderRadius: 12,
      overflow: 'hidden',
      boxShadow: theme.shadow,
    } as React.CSSProperties,
    leftHeader: {
      padding: '16px 20px',
      borderBottom: `1px solid ${theme.cardBorder}`,
      fontSize: 13,
      fontWeight: 700,
      color: theme.textPrimary,
      textTransform: 'uppercase' as const,
      letterSpacing: 0.5,
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
    },
    staffItem: (selected: boolean): React.CSSProperties => ({
      padding: '12px 20px',
      cursor: 'pointer',
      background: selected ? theme.accentLight : 'transparent',
      borderLeft: `3px solid ${selected ? theme.accent : 'transparent'}`,
      borderBottom: `1px solid ${theme.cardBorder}`,
      transition: 'all 0.15s ease',
    }),
    staffName: {
      fontSize: 14,
      fontWeight: 600,
      color: theme.textPrimary,
      display: 'flex',
      alignItems: 'center',
    },
    staffMeta: {
      fontSize: 12,
      color: theme.textSecondary,
      marginTop: 4,
    },
    roleBadge: (role: string): React.CSSProperties => {
      const colors: Record<string, string> = {
        owner: theme.chartLine,
        admin: '#3b82f6',
        member: theme.textSecondary,
      }
      const c = colors[role] || theme.textSecondary
      return {
        display: 'inline-block',
        fontSize: 10,
        fontWeight: 700,
        color: c,
        background: `${c}20`,
        border: `1px solid ${c}40`,
        borderRadius: 4,
        padding: '2px 6px',
        letterSpacing: 0.5,
        textTransform: 'uppercase',
        marginLeft: 8,
      }
    },
    rightPanel: {
      flex: 1,
      background: theme.cardBg,
      border: `1px solid ${theme.cardBorder}`,
      borderRadius: 12,
      padding: 32,
      boxShadow: theme.shadow,
    } as React.CSSProperties,
    sectionTitle: {
      fontSize: 13,
      fontWeight: 700,
      color: theme.textSecondary,
      textTransform: 'uppercase' as const,
      letterSpacing: 0.5,
      marginBottom: 16,
      display: 'flex',
      alignItems: 'center',
      gap: 8,
    },
    overrideRow: {
      display: 'flex',
      alignItems: 'center',
      gap: 16,
      padding: '12px 16px',
      border: `1px solid ${theme.cardBorder}`,
      borderRadius: 8,
      marginBottom: 8,
      background: theme.bg,
      fontSize: 14,
      transition: 'all 0.2s',
    } as React.CSSProperties,
    allowedBadge: {
      fontSize: 11,
      fontWeight: 700,
      padding: '4px 10px',
      borderRadius: 20,
      letterSpacing: 0.5,
      textTransform: 'uppercase' as const,
      flexShrink: 0,
    },
    cmdText: {
      fontFamily: 'monospace',
      color: theme.accent,
      fontWeight: 600,
      flex: 1,
      minWidth: 100,
    },
    reasonText: {
      color: theme.textSecondary,
      fontSize: 13,
      flex: 2,
    },
    deleteBtn: {
      background: theme.dangerBg,
      border: `1px solid ${theme.danger}40`,
      color: theme.danger,
      borderRadius: 6,
      padding: '6px 12px',
      fontSize: 12,
      fontWeight: 600,
      cursor: 'pointer',
      flexShrink: 0,
      transition: 'all 0.2s',
    } as React.CSSProperties,
    addForm: {
      marginTop: 32,
      background: theme.bg,
      border: `1px solid ${theme.cardBorder}`,
      borderRadius: 12,
      padding: 24,
    } as React.CSSProperties,
    addTitle: {
      fontSize: 14,
      fontWeight: 700,
      color: theme.textPrimary,
      textTransform: 'uppercase' as const,
      letterSpacing: 0.5,
      marginBottom: 16,
      display: 'flex',
      alignItems: 'center',
      gap: 8,
    },
    formRow: {
      display: 'flex',
      gap: 12,
      flexWrap: 'wrap' as const,
      alignItems: 'stretch',
    } as React.CSSProperties,
    input: {
      padding: '10px 14px',
      background: theme.inputBg,
      border: `1px solid ${theme.inputBorder}`,
      color: theme.textPrimary,
      borderRadius: 8,
      fontSize: 14,
      outline: 'none',
      boxShadow: theme.shadow,
    } as React.CSSProperties,
    toggleBtn: (allowed: boolean): React.CSSProperties => ({
      padding: '10px 20px',
      background: allowed ? theme.successBg : theme.dangerBg,
      border: `1px solid ${allowed ? theme.success : theme.danger}40`,
      color: allowed ? theme.success : theme.danger,
      borderRadius: 8,
      fontSize: 13,
      fontWeight: 700,
      cursor: 'pointer',
      flexShrink: 0,
      boxShadow: theme.shadow,
      textTransform: 'uppercase',
      letterSpacing: 0.5,
    }),
    saveBtn: {
      padding: '10px 24px',
      background: theme.accent,
      border: 'none',
      color: '#fff',
      borderRadius: 8,
      fontSize: 14,
      fontWeight: 600,
      cursor: 'pointer',
      flexShrink: 0,
      boxShadow: theme.shadow,
    } as React.CSSProperties,
    emptyMsg: {
      color: theme.textSecondary,
      fontSize: 15,
      padding: '24px 0',
      textAlign: 'center' as const,
    },
    infoRow: {
      display: 'flex',
      gap: 32,
      marginBottom: 32,
      flexWrap: 'wrap' as const,
      padding: '20px',
      background: theme.bg,
      borderRadius: 12,
      border: `1px solid ${theme.cardBorder}`,
    } as React.CSSProperties,
    infoField: {
      display: 'flex',
      flexDirection: 'column' as const,
      gap: 6,
    } as React.CSSProperties,
    infoLabel: {
      fontSize: 12,
      color: theme.textSecondary,
      textTransform: 'uppercase' as const,
      letterSpacing: 0.5,
      fontWeight: 600,
    } as React.CSSProperties,
    infoValue: {
      fontSize: 16,
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
      setSaveMsg('Saved successfully.')
      await loadAll()
    } catch (e: any) {
      setSaveMsg(e.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div style={S.page}>
      <h1 style={S.title}>🔐 {t('perm.title', lang)}</h1>
      <p style={S.subtitle}>Manage granular access controls for team members.</p>

      {loading ? (
        <div style={{ color: theme.textSecondary, fontSize: 15, fontWeight: 500 }}>{t('perm.loading', lang)}...</div>
      ) : (
        <div style={S.layout}>
          <div style={S.leftPanel}>
            <div style={S.leftHeader}>
              <span>{t('perm.staff', lang)}</span>
              <span className="pill-badge" style={{ background: theme.cardBorder, padding: '4px 12px',  }}>{staffList.length}</span>
            </div>
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
                    {s.team && <span style={{ fontWeight: 500 }}>{s.team}</span>}
                    {s.overrides.length > 0 && (
                      <span style={{ marginLeft: s.team ? 8 : 0, color: theme.accent }}>
                        • {s.overrides.length} override{s.overrides.length !== 1 ? 's' : ''}
                      </span>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>

          <div style={S.rightPanel}>
            {!selected ? (
              <div style={S.emptyMsg}>👈 Select a staff member from the left to manage their permissions.</div>
            ) : (
              <>
                <div style={S.infoRow}>
                  <div style={S.infoField}>
                    <span style={S.infoLabel}>{t('perm.role', lang)}</span>
                    <span style={S.infoValue}>
                      {selected.role.charAt(0).toUpperCase() + selected.role.slice(1)}
                      {selected.team && (
                        <span style={{ color: theme.textSecondary, fontWeight: 500, marginLeft: 8, fontSize: 14 }}>
                          ({selected.team})
                        </span>
                      )}
                    </span>
                  </div>
                  <div style={S.infoField}>
                    <span style={S.infoLabel}>Staff ID</span>
                    <span style={{ ...S.infoValue, fontFamily: 'monospace' }}>#{selected.staff_id}</span>
                  </div>
                  <div style={S.infoField}>
                    <span style={S.infoLabel}>Total Overrides</span>
                    <span style={S.infoValue}>{selected.overrides.length}</span>
                  </div>
                </div>

                {/* Section-level permission toggles */}
                <div style={{ ...S.sectionTitle, marginTop: 8 }}>
                  🎛️ {t('perm.section_permissions', lang)}
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 12, marginBottom: 32 }}>
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
                          display: 'flex', alignItems: 'center', gap: 12,
                          padding: '12px 16px', borderRadius: 8, cursor: 'pointer',
                          background: theme.bg,
                          border: `1px solid ${isAllowed ? theme.success : theme.danger}40`,
                          boxShadow: isAllowed ? `0 2px 8px ${theme.success}10` : 'none',
                          transition: 'all 0.2s',
                        }}
                      >
                        <div style={{
                          width: 40, height: 24, borderRadius: 12,
                          background: isAllowed ? theme.success : theme.cardBorder,
                          position: 'relative', transition: 'background 0.2s',
                          flexShrink: 0,
                        }}>
                          <div style={{
                            width: 20, height: 20, borderRadius: '50%', background: '#fff',
                            position: 'absolute', top: 2,
                            left: isAllowed ? 18 : 2,
                            transition: 'left 0.2s',
                            boxShadow: '0 1px 3px rgba(0,0,0,0.2)'
                          }} />
                        </div>
                        <span style={{ fontSize: 13, color: theme.textPrimary, fontWeight: 600 }}>
                          {t(`perm.${section}`, lang)}
                        </span>
                      </div>
                    )
                  })}
                </div>

                <div style={{...S.sectionTitle, borderTop: `1px solid ${theme.cardBorder}`, paddingTop: 32}}>
                  🛠️ {t('perm.overrides', lang)} <span style={{ color: theme.textMuted, fontWeight: 500 }}>({selected.overrides.length})</span>
                </div>

                {selected.overrides.length === 0 ? (
                  <div style={{ color: theme.textSecondary, fontSize: 14, fontStyle: 'italic', padding: '16px 0' }}>{t('perm.no_overrides', lang)}</div>
                ) : (
                  selected.overrides.map(ov => (
                    <div key={ov.command} style={S.overrideRow}>
                      <span style={S.cmdText}>/{ov.command}</span>
                      <span style={{
                        ...S.allowedBadge,
                        background: ov.allowed ? theme.successBg : theme.dangerBg,
                        color: ov.allowed ? theme.success : theme.danger,
                        border: `1px solid ${ov.allowed ? theme.success : theme.danger}40`,
                      }}>
                        {ov.allowed ? t('perm.allowed', lang) : t('perm.denied', lang)}
                      </span>
                      <span style={S.reasonText}>{ov.reason || '—'}</span>
                      <button className="glass-btn"
                        style={S.deleteBtn}
                        onClick={() => handleDelete(selected.staff_id, ov.command)}
                      >
                        {t('common.delete', lang)}
                      </button>
                    </div>
                  ))
                )}

                <div style={S.addForm}>
                  <div style={S.addTitle}>➕ {t('perm.add_override', lang)}</div>
                  <div style={S.formRow}>
                    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minWidth: 180 }}>
                      <label style={{ fontSize: 12, fontWeight: 600, color: theme.textSecondary, marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>Command</label>
                      <input
                        style={S.input}
                        placeholder="e.g. view_clients"
                        value={newCmd}
                        onChange={e => setNewCmd(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && handleSave()}
                      />
                    </div>
                    
                    <div style={{ display: 'flex', flexDirection: 'column', width: 120 }}>
                      <label style={{ fontSize: 12, fontWeight: 600, color: theme.textSecondary, marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>Action</label>
                      <button className="glass-btn"
                        style={S.toggleBtn(newAllowed)}
                        onClick={() => setNewAllowed(a => !a)}
                      >
                        {newAllowed ? '✅ Allow' : '❌ Deny'}
                      </button>
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', flex: 2, minWidth: 200 }}>
                      <label style={{ fontSize: 12, fontWeight: 600, color: theme.textSecondary, marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>Reason (Optional)</label>
                      <input
                        style={S.input}
                        placeholder={t('perm.reason', lang)}
                        value={newReason}
                        onChange={e => setNewReason(e.target.value)}
                      />
                    </div>
                  </div>
                  <div style={{ marginTop: 16, display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 16 }}>
                    {saveMsg && (
                      <div style={{
                        fontSize: 13,
                        fontWeight: 600,
                        color: saveMsg.includes('fail') || saveMsg.includes('error') ? theme.danger : theme.success,
                      }}>
                        {saveMsg}
                      </div>
                    )}
                    <button className="glass-btn" style={S.saveBtn} onClick={handleSave} disabled={saving || !newCmd.trim()}>
                      {saving ? 'Saving...' : t('perm.save', lang)}
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
