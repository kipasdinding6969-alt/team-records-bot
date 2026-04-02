import { useEffect, useState } from 'react'
import { api } from '../api'
import { getLang, t } from '../i18n'
import { useTheme } from '../ThemeContext'

interface GranularRow {
  staff_id: number
  display_name: string
  team: string | null
  category: string
  powder: number
  no_reply: number
  reply_rate: number
  stuck: number
  blocked: number
  scammed: number
  link_no_reply: number
  registered: number
  audit_rate: number
  training: number
  scheduled: number
  withdrawal: number
  new_order: number
  conversion: number
  new_kill: number
  dead: number
}

interface BlownAccount {
  id?: number
  staff_name: string
  team: string
  account_name: string
  date: string
  note: string
}

const COLUMNS: { key: keyof GranularRow; i18nKey: string; color?: string; pct?: boolean }[] = [
  { key: 'powder', i18nKey: 'perf_detail.powder' },
  { key: 'no_reply', i18nKey: 'perf_detail.no_reply' },
  { key: 'reply_rate', i18nKey: 'perf_detail.reply_rate', pct: true },
  { key: 'stuck', i18nKey: 'perf_detail.stuck' },
  { key: 'blocked', i18nKey: 'perf_detail.blocked' },
  { key: 'scammed', i18nKey: 'perf_detail.scammed' },
  { key: 'link_no_reply', i18nKey: 'perf_detail.link_no_reply' },
  { key: 'registered', i18nKey: 'perf_detail.registered' },
  { key: 'audit_rate', i18nKey: 'perf_detail.audit_rate', pct: true },
  { key: 'training', i18nKey: 'perf_detail.training' },
  { key: 'scheduled', i18nKey: 'perf_detail.scheduled' },
  { key: 'withdrawal', i18nKey: 'perf_detail.withdrawal' },
  { key: 'new_order', i18nKey: 'perf_detail.new_order' },
  { key: 'conversion', i18nKey: 'perf_detail.conversion', pct: true },
  { key: 'new_kill', i18nKey: 'perf_detail.new_kill' },
  { key: 'dead', i18nKey: 'perf_detail.dead' },
]

export default function PerformanceDetail() {
  const { theme } = useTheme()
  const lang = getLang()
  const accent = theme.accent

  const [selectedDate, setSelectedDate] = useState(() => new Date().toISOString().split('T')[0])
  const [team, setTeam] = useState('all')
  const [rows, setRows] = useState<GranularRow[]>([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [teams, setTeams] = useState<{ key: string; label: string }[]>([])

  useEffect(() => {
    api.allStaff().then(staff => {
      const uniqueTeams = [...new Set(staff.map((s: any) => s.team).filter(Boolean))]
      setTeams(uniqueTeams.map(t => ({ key: t, label: t })))
    }).catch(() => {})
  }, [])

  const [drawerOpen, setDrawerOpen] = useState(false)
  const [blownList, setBlownList] = useState<BlownAccount[]>([])
  const [blownLoading, setBlownLoading] = useState(false)
  const [blownForm, setBlownForm] = useState<BlownAccount>({ staff_name: '', team: '', account_name: '', date: selectedDate, note: '' })

  useEffect(() => {
    setLoading(true)
    api.performanceGranular(selectedDate, team === 'all' ? undefined : team)
      .then(res => setRows(res.rows || []))
      .catch(() => setRows([]))
      .finally(() => setLoading(false))
  }, [selectedDate, team])

  useEffect(() => {
    if (drawerOpen) {
      setBlownLoading(true)
      api.blownAccounts(selectedDate, team === 'all' ? undefined : team)
        .then(setBlownList)
        .catch(() => setBlownList([]))
        .finally(() => setBlownLoading(false))
    }
  }, [drawerOpen, selectedDate, team])

  const grouped: Record<string, { name: string; team: string | null; categories: GranularRow[] }> = {}
  rows.forEach(r => {
    const key = `${r.staff_id}`
    if (!grouped[key]) grouped[key] = { name: r.display_name, team: r.team, categories: [] }
    grouped[key].categories.push(r)
  })

  function sumRow(cats: GranularRow[]): Record<string, number> {
    const totals: Record<string, number> = {}
    COLUMNS.forEach(c => {
      if (c.pct) {
        const vals = cats.map(r => r[c.key] as number).filter(v => v > 0)
        totals[c.key] = vals.length > 0 ? Math.round(vals.reduce((a, b) => a + b, 0) / vals.length) : 0
      } else {
        totals[c.key] = cats.reduce((sum, r) => sum + (r[c.key] as number || 0), 0)
      }
    })
    return totals
  }

  const allCats = Object.values(grouped).flatMap(g => g.categories)
  const grandTotal = sumRow(allCats)

  function toggleExpand(key: string) {
    setExpanded(prev => ({ ...prev, [key]: !prev[key] }))
  }

  function handleAddBlown() {
    api.addBlownAccount({ ...blownForm, date: selectedDate })
      .then(() => {
        setBlownForm({ staff_name: '', team: '', account_name: '', date: selectedDate, note: '' })
        api.blownAccounts(selectedDate, team === 'all' ? undefined : team)
          .then(setBlownList)
          .catch(() => {})
      })
      .catch(() => {})
  }

  return (
    <div className="page-container" style={{ maxWidth: 1600 }}>
      <h1 className="page-title" style={{ marginBottom: 8 }}>
        {t('perf_detail.title', lang)}
      </h1>
      <p className="page-subtitle" style={{ marginBottom: 20 }}>
        {t('perf_detail.subtitle', lang)}
      </p>

      {/* Controls row */}
      <div className="toolbar" style={{ overflowX: 'auto', paddingBottom: 4 }}>
        <input type="date" className="input" style={{ width: 'auto' }} value={selectedDate} onChange={e => setSelectedDate(e.target.value)} />
        <div className="tab-bar" style={{ marginBottom: 0 }}>
          <button
            key="all"
            className={`tab-btn ${team === 'all' ? 'active' : ''}`}
            onClick={() => setTeam('all')}
          >
            {t('perf_detail.all_teams', lang)}
          </button>
          {teams.map(tm => (
            <button
              key={tm.key}
              className={`tab-btn ${team === tm.key ? 'active' : ''}`}
              onClick={() => setTeam(tm.key)}
            >
              {tm.label}
            </button>
          ))}
        </div>
        <div className="toolbar-spacer" />
        <button
          className="btn-primary btn-sm"
          onClick={() => setDrawerOpen(true)}
        >
          {t('perf_detail.blown', lang)}
        </button>
      </div>

      {loading ? (
        <div className="empty-state">{t('common.loading', lang)}...</div>
      ) : rows.length === 0 ? (
        <div className="empty-state">
          <div className="empty-text" style={{ fontSize: 14, color: theme.textPrimary, marginBottom: 4 }}>--</div>
          <div className="empty-text">{t('perf.no_data', lang)}</div>
        </div>
      ) : (
        <div className="card" style={{ overflowX: 'auto', padding: 0 }}>
          <style>{`
            .pd-parent-row { cursor: pointer; }
            .pd-parent-row:hover { background: ${accent}08 !important; }
            .pd-child-row td { color: ${theme.textSecondary} !important; font-size: 11px; }
            .pd-child-row td:first-child { border-left: 3px solid ${accent}30; padding-left: 24px !important; }
            .pd-total-row td { border-top: 2px solid ${accent}40 !important; font-weight: 700 !important; }
          `}</style>
          <table className="data-grid-table" style={{ minWidth: 1400 }}>
            <thead>
              <tr>
                <th style={{ textAlign: 'left', position: 'sticky', left: 0, zIndex: 3, minWidth: 140 }}>{t('perf.name', lang)}</th>
                <th style={{ textAlign: 'left' }}>{t('perf.team', lang)}</th>
                <th style={{ textAlign: 'left' }}>{t('frontdesk.category', lang)}</th>
                {COLUMNS.map(c => <th key={c.key} style={{ textAlign: 'right' }}>{t(c.i18nKey, lang)}</th>)}
              </tr>
            </thead>
            <tbody>
              {Object.entries(grouped).map(([key, g]) => {
                const isOpen = expanded[key]
                const personTotal = sumRow(g.categories)
                return (
                  <>{/* Fragment key on tr below */}
                    <tr key={`p-${key}`} className="pd-parent-row" onClick={() => toggleExpand(key)}>
                      <td style={{ fontWeight: 600, textAlign: 'left', position: 'sticky', left: 0, zIndex: 1, minWidth: 140, background: theme.cardBg }}>
                        <span style={{ marginRight: 8, fontSize: 12, color: accent, display: 'inline-block', transition: 'transform 0.2s', transform: isOpen ? 'rotate(90deg)' : 'rotate(0deg)' }}>&#9654;</span>
                        {g.name}
                      </td>
                      <td style={{ textAlign: 'left' }}>
                        <span className="pill-badge badge-info">{g.team || '-'}</span>
                      </td>
                      <td style={{ color: theme.textSecondary, fontSize: 12, textAlign: 'left' }}>({g.categories.length})</td>
                      {COLUMNS.map(c => (
                        <td key={c.key} style={{ textAlign: 'right', fontFamily: 'monospace', color: c.key === 'dead' ? theme.danger : c.pct ? accent : theme.textPrimary }}>
                          {c.pct ? `${personTotal[c.key] || 0}%` : personTotal[c.key] || 0}
                        </td>
                      ))}
                    </tr>
                    {isOpen && g.categories.map((cat, ci) => (
                      <tr key={`c-${key}-${ci}`} className="pd-child-row">
                        <td style={{ position: 'sticky', left: 0, zIndex: 1, background: theme.bg }}></td>
                        <td></td>
                        <td style={{ fontSize: 12, fontWeight: 600, textAlign: 'left' }}>{cat.category}</td>
                        {COLUMNS.map(c => (
                          <td key={c.key} style={{ textAlign: 'right', fontFamily: 'monospace' }}>
                            {c.pct ? `${(cat[c.key] as number) || 0}%` : (cat[c.key] as number) || 0}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </>
                )
              })}
              <tr className="pd-total-row">
                <td style={{ fontWeight: 700, textAlign: 'left', position: 'sticky', left: 0, zIndex: 1, background: `${accent}0A` }}>
                  {t('perf_detail.grand_total', lang)}
                </td>
                <td></td>
                <td></td>
                {COLUMNS.map(c => (
                  <td key={c.key} style={{ textAlign: 'right', fontFamily: 'monospace', color: c.key === 'dead' ? theme.danger : accent }}>
                    {c.pct ? `${grandTotal[c.key] || 0}%` : grandTotal[c.key] || 0}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      )}

      {/* Blown Accounts Drawer */}
      {drawerOpen && (
        <>
          <div
            className="modal-overlay"
            style={{ alignItems: 'stretch', justifyContent: 'flex-end' }}
            onClick={() => setDrawerOpen(false)}
          />
          <div style={{
            position: 'fixed', top: 0, right: 0, bottom: 0, width: 400, maxWidth: '90vw',
            background: theme.cardBg, borderLeft: `1px solid ${theme.cardBorder}`,
            zIndex: 101, display: 'flex', flexDirection: 'column', boxShadow: '-4px 0 24px rgba(0,0,0,0.2)',
          }}>
            {/* Drawer header */}
            <div style={{ padding: 20, borderBottom: `1px solid ${theme.cardBorder}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: theme.textPrimary }}>{t('perf_detail.blown', lang)}</h2>
              <button
                className="btn-secondary"
                style={{ height: 32, padding: '0 12px', fontSize: 14 }}
                onClick={() => setDrawerOpen(false)}
              >
                X
              </button>
            </div>

            {/* Blown list */}
            <div style={{ flex: 1, overflowY: 'auto', padding: 20 }}>
              {blownLoading ? (
                <div className="empty-state">{t('common.loading', lang)}...</div>
              ) : blownList.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-text">--</div>
                </div>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                  {blownList.map((b, i) => (
                    <div key={b.id || i} className="card" style={{ padding: 12 }}>
                      <div style={{ fontWeight: 700, color: theme.textPrimary, marginBottom: 4, fontSize: 14 }}>{b.account_name}</div>
                      <div style={{ color: theme.textSecondary, fontSize: 12 }}>{b.staff_name} / {b.team}</div>
                      <div style={{ color: theme.textSecondary, fontSize: 12, marginTop: 4 }}>{b.date}</div>
                      {b.note && <div style={{ color: theme.textSecondary, fontSize: 12, marginTop: 4, fontStyle: 'italic' }}>{b.note}</div>}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Add blown form */}
            <div style={{ padding: 20, borderTop: `1px solid ${theme.cardBorder}` }}>
              <h3 className="section-title" style={{ margin: '0 0 12px' }}>{t('perf_detail.add_blown', lang)}</h3>
              <div className="form-grid-2col" style={{ gap: 8 }}>
                <input className="input" placeholder={t('perf.name', lang)} value={blownForm.staff_name} onChange={e => setBlownForm(p => ({ ...p, staff_name: e.target.value }))} />
                <input className="input" placeholder={t('perf.team', lang)} value={blownForm.team} onChange={e => setBlownForm(p => ({ ...p, team: e.target.value }))} />
                <input className="input" placeholder={t('perf_detail.account_name', lang)} value={blownForm.account_name} onChange={e => setBlownForm(p => ({ ...p, account_name: e.target.value }))} />
                <input className="input" placeholder={t('detail.link_note', lang)} value={blownForm.note} onChange={e => setBlownForm(p => ({ ...p, note: e.target.value }))} />
              </div>
              <button
                className="btn-primary"
                style={{ marginTop: 8, width: '100%', height: 40 }}
                onClick={handleAddBlown}
              >
                {t('perf_detail.add_blown', lang)}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
