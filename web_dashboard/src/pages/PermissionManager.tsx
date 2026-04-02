import { useEffect, useState } from 'react'
import { api, getAuthState } from '../api'
import { getLang, t } from '../i18n'
import { useTheme } from '../ThemeContext'
import { PageHeader, Spinner, Empty } from '../components/SharedUI'

const PERM_SECTIONS = [
  {
    key: 'clients_access',
    labelKey: 'perm.group.clients_access',
    permissions: [
      { cmd: 'clients.view', labelKey: 'perm.section.clients_view' },
      { cmd: 'clients.create', labelKey: 'perm.section.clients_create' },
      { cmd: 'clients.edit', labelKey: 'perm.section.clients_edit' },
      { cmd: 'clients.delete', labelKey: 'perm.section.clients_delete' },
    ],
  },
  {
    key: 'phone',
    labelKey: 'perm.group.phone',
    permissions: [
      { cmd: 'phone.lookup', labelKey: 'perm.section.phone_lookup' },
      { cmd: 'phone.override', labelKey: 'perm.section.phone_override' },
    ],
  },
  {
    key: 'performance',
    labelKey: 'perm.group.performance',
    permissions: [
      { cmd: 'performance.view', labelKey: 'perm.section.performance_view' },
      { cmd: 'performance.recalculate', labelKey: 'perm.section.performance_recalculate' },
    ],
  },
  {
    key: 'deposits',
    labelKey: 'perm.group.deposits',
    permissions: [
      { cmd: 'deposits.view', labelKey: 'perm.section.deposits_view' },
      { cmd: 'deposits.create', labelKey: 'perm.section.deposits_create' },
    ],
  },
  {
    key: 'reports',
    labelKey: 'perm.group.reports',
    permissions: [
      { cmd: 'reports.export', labelKey: 'perm.section.reports_export' },
    ],
  },
  {
    key: 'users',
    labelKey: 'perm.group.users',
    permissions: [
      { cmd: 'users.manage', labelKey: 'perm.section.users_manage' },
    ],
  },
  {
    key: 'comments',
    labelKey: 'perm.group.comments',
    permissions: [
      { cmd: 'comments.create', labelKey: 'perm.section.comments_create' },
      { cmd: 'comments.moderate', labelKey: 'perm.section.comments_moderate' },
    ],
  },
]

export default function PermissionManager() {
  const { theme } = useTheme()
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const lang = getLang()
  const auth = getAuthState()

  const [staffList, setStaffList] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedStaff, setSelectedStaff] = useState<any>(null)
  const [saving, setSaving] = useState(false)

  const [localPerms, setLocalPerms] = useState<Record<string, boolean>>({})

  const loadAll = () => {
    setLoading(true)
    api.allPermissions().then(data => {
      setStaffList(data)
    }).catch(e => {
      console.error(e)
      setError(t('common.update_failed', lang as any))
    }).finally(() => setLoading(false))
  }

  useEffect(() => { loadAll() }, [])

  useEffect(() => {
    if (!selectedStaff) {
      setLocalPerms({})
      return
    }
    const perms: Record<string, boolean> = {}
    for (const section of PERM_SECTIONS) {
      for (const p of section.permissions) {
        const ov = selectedStaff.overrides?.find((o: any) => o.command === p.cmd)
        perms[p.cmd] = ov ? ov.allowed : true
      }
    }
    setLocalPerms(perms)
  }, [selectedStaff])

  const handleToggle = (cmd: string) => {
    setLocalPerms(prev => ({ ...prev, [cmd]: !prev[cmd] }))
  }

  const handleSave = async () => {
    if (!selectedStaff) return
    setSaving(true)
    setError('')
    setSuccess('')
    try {
      await api.bulkPermissions({
        staff_id: selectedStaff.id,
        permissions: localPerms,
      })
      setSuccess(t('perm.save_success', lang))
      loadAll()
      setTimeout(() => setSuccess(''), 3000)
    } catch (e) {
      console.error(e)
      setError(t('perm.save_failed', lang))
    }
    setSaving(false)
  }

  const applyTemplate = (templateName: string) => {
    const templateMap: Record<string, Record<string, boolean>> = {
      frontdesk: {
        'clients.view': true, 'clients.create': true, 'clients.edit': true, 'clients.delete': false,
        'phone.lookup': true, 'phone.override': false,
        'performance.view': true, 'performance.recalculate': false,
        'deposits.view': true, 'deposits.create': false,
        'reports.export': false,
        'users.manage': false,
        'comments.create': true, 'comments.moderate': false,
      },
      leader: {
        'clients.view': true, 'clients.create': true, 'clients.edit': true, 'clients.delete': true,
        'phone.lookup': true, 'phone.override': true,
        'performance.view': true, 'performance.recalculate': true,
        'deposits.view': true, 'deposits.create': true,
        'reports.export': true,
        'users.manage': false,
        'comments.create': true, 'comments.moderate': true,
      },
      cs: {
        'clients.view': true, 'clients.create': false, 'clients.edit': false, 'clients.delete': false,
        'phone.lookup': true, 'phone.override': false,
        'performance.view': false, 'performance.recalculate': false,
        'deposits.view': false, 'deposits.create': false,
        'reports.export': false,
        'users.manage': false,
        'comments.create': true, 'comments.moderate': false,
      },
    }
    const perms = templateMap[templateName]
    if (perms) setLocalPerms(perms)
  }

  if (loading) return <Spinner />

  const getLevel = (role: string) => role === 'owner' ? 4 : role === 'admin' ? 3 : role === 'leader' ? 2 : 1
  const myLevel = getLevel(auth?.role || 'member')

  return (
    <div className="page-container">
      <PageHeader title={t('perm.title', lang)} />

      {error && (
        <div className="alert alert-error">{error}</div>
      )}
      {success && (
        <div className="alert alert-success">{success}</div>
      )}

      <div style={{ display: 'flex', gap: 20, alignItems: 'flex-start' }}>
        {/* Staff selector sidebar */}
        <div className="card" style={{ width: 280, minWidth: 280 }}>
          <h3 className="section-title">
            {t('perm.hierarchy', lang)}
          </h3>
          {['owner', 'admin', 'leader', 'frontdesk', 'customer_service'].map(roleLevel => {
            const roleStaff = staffList.filter(s =>
              s.role === roleLevel || (roleLevel === 'frontdesk' && s.role === 'member')
            )
            if (roleStaff.length === 0) return null
            return (
              <div key={roleLevel} style={{ marginBottom: 12 }}>
                <div className="field-label" style={{ marginBottom: 8 }}>
                  {roleLevel}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {roleStaff.map(s => {
                    const sLevel = getLevel(s.role)
                    const canEdit = myLevel > sLevel || auth?.role === 'owner'
                    return (
                      <div
                        key={s.id}
                        onClick={() => canEdit && setSelectedStaff(s)}
                        style={{
                          padding: '8px 12px', borderRadius: 8,
                          cursor: canEdit ? 'pointer' : 'not-allowed',
                          background: selectedStaff?.id === s.id ? theme.accentLight : 'transparent',
                          opacity: canEdit ? 1 : 0.5,
                          border: `1px solid ${selectedStaff?.id === s.id ? theme.accent : 'transparent'}`,
                          transition: 'all 0.2s',
                        }}
                      >
                        <div style={{ fontWeight: 600, color: theme.textPrimary, fontSize: 14 }}>
                          {s.display_name}
                        </div>
                        <div style={{ fontSize: 12, color: theme.textSecondary }}>
                          {s.team || t('perm.unassigned', lang)}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </div>

        {/* Permission grid */}
        <div className="card" style={{ flex: 1, minWidth: 0 }}>
          {selectedStaff ? (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20, flexWrap: 'wrap', gap: 12 }}>
                <div>
                  <h2 style={{ margin: '0 0 4px', fontSize: 20, color: theme.textPrimary, fontWeight: 700 }}>
                    {selectedStaff.display_name}
                  </h2>
                  <div style={{ fontSize: 13, color: theme.textSecondary }}>
                    {selectedStaff.role} {selectedStaff.team ? `\u2022 ${selectedStaff.team}` : `\u2022 ${t('perm.unassigned', lang)}`}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {['frontdesk', 'leader', 'cs'].map(tmpl => (
                    <button key={tmpl} className="btn-secondary" style={{ height: 32, padding: '0 12px', fontSize: 12, borderRadius: 20 }} onClick={() => applyTemplate(tmpl)}>
                      {t(`perm.template.${tmpl}`, lang)}
                    </button>
                  ))}
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {PERM_SECTIONS.map(section => (
                  <div key={section.key} style={{ background: theme.bgElevated, borderRadius: 8, padding: 20, border: `1px solid ${theme.cardBorder}` }}>
                    <h3 className="section-title" style={{ margin: '0 0 12px' }}>
                      {t(section.labelKey, lang)}
                    </h3>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 12 }}>
                      {section.permissions.map(perm => {
                        const isAllowed = localPerms[perm.cmd] ?? true
                        return (
                          <div
                            key={perm.cmd}
                            onClick={() => handleToggle(perm.cmd)}
                            style={{
                              display: 'flex', alignItems: 'center', gap: 12,
                              padding: '8px 12px', borderRadius: 8,
                              cursor: 'pointer', transition: 'all 0.2s',
                              border: `1px solid ${isAllowed ? theme.success : theme.danger}40`,
                              background: isAllowed ? `${theme.success}10` : `${theme.danger}10`,
                            }}
                          >
                            <div style={{
                              width: 36, height: 20, borderRadius: 10,
                              background: isAllowed ? theme.success : theme.cardBorder,
                              position: 'relative', transition: 'all 0.2s', flexShrink: 0,
                            }}>
                              <div style={{
                                width: 16, height: 16, borderRadius: '50%', background: '#fff',
                                position: 'absolute', top: 2,
                                left: isAllowed ? 18 : 2, transition: 'all 0.2s',
                              }} />
                            </div>
                            <span style={{ fontSize: 13, fontWeight: 600, color: theme.textPrimary }}>
                              {t(perm.labelKey, lang)}
                            </span>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                ))}
              </div>

              <div style={{ marginTop: 20, display: 'flex', justifyContent: 'flex-end' }}>
                <button className="btn-primary" onClick={handleSave} disabled={saving}>
                  {saving ? t('common.saving', lang) : t('common.save', lang)}
                </button>
              </div>
            </div>
          ) : (
            <Empty label={t('perm.select_staff', lang)} />
          )}
        </div>
      </div>
    </div>
  )
}
