import { useEffect, useState } from 'react'
import { api, getAuthState, debug } from '../api'
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
      debug(e)
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
      debug(e)
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

      <div className="content-split">
        {/* Staff selector sidebar */}
        <div className="card content-split-sidebar">
          <h3 className="section-title">
            {t('perm.hierarchy', lang)}
          </h3>
          {['owner', 'admin', 'leader', 'frontdesk', 'customer_service'].map(roleLevel => {
            const roleStaff = staffList.filter(s =>
              s.role === roleLevel || (roleLevel === 'frontdesk' && s.role === 'member')
            )
            if (roleStaff.length === 0) return <div key={roleLevel} className="empty-text subtitle mb-12">No staff in this role</div>
            return (
              <div key={roleLevel} className="mb-12">
                <div className="field-label mb-8">
                  {roleLevel}
                </div>
                <div className="d-flex flex-col gap-4">
                  {roleStaff.map(s => {
                    const sLevel = getLevel(s.role)
                    const canEdit = myLevel > sLevel || auth?.role === 'owner'
                    return (
                      <div
                        key={s.id}
                        onClick={() => canEdit && setSelectedStaff(s)}
                        className={`search-result-item ${selectedStaff?.id === s.id ? 'active' : ''} ${!canEdit ? 'disabled' : ''}`}
                      >
                        <div>
                          <div className="label-sm">{s.display_name}</div>
                          <div className="caption">{s.team || t('perm.unassigned', lang)}</div>
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
        <div className="card content-split-main">
          {selectedStaff ? (
            <div>
              <div className="d-flex justify-between align-center mb-20 flex-wrap gap-12">
                <div>
                  <h2 className="heading-md mb-4">{selectedStaff.display_name}</h2>
                  <div className="caption">
                    {selectedStaff.role} {selectedStaff.team ? `\u2022 ${selectedStaff.team}` : `\u2022 ${t('perm.unassigned', lang)}`}
                  </div>
                </div>
                <div className="d-flex gap-8 flex-wrap">
                  {['frontdesk', 'leader', 'cs'].map(tmpl => (
                    <button key={tmpl} className="btn-secondary btn-sm btn-pill" onClick={() => applyTemplate(tmpl)}>
                      {t(`perm.template.${tmpl}`, lang)}
                    </button>
                  ))}
                </div>
              </div>

              <div className="d-flex flex-col gap-12">
                {PERM_SECTIONS.map(section => (
                  <div key={section.key} className="form-section">
                    <h3 className="section-title mb-12">
                      {t(section.labelKey, lang)}
                    </h3>
                    <div className="perm-grid">
                      {section.permissions.map(perm => {
                        const isAllowed = localPerms[perm.cmd] ?? true
                        return (
                          <div
                            key={perm.cmd}
                            onClick={() => handleToggle(perm.cmd)}
                            className={`perm-toggle ${isAllowed ? 'allowed' : 'denied'}`}
                          >
                            <div className={`toggle-track ${isAllowed ? 'on' : 'off'}`}>
                              <div className={`toggle-knob ${isAllowed ? 'on' : 'off'}`} />
                            </div>
                            <span className="label-sm">
                              {t(perm.labelKey, lang)}
                            </span>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                ))}
              </div>

              <div className="modal-actions mt-20">
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
