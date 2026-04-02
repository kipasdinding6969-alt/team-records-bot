import { Fragment, useEffect, useState } from 'react'
import { api } from '../api'
import { getLang, t } from '../i18n'
import { useTheme } from '../ThemeContext'
import type { GranularPerfRow, BlownAccount } from '../types'

const COLUMNS: { key: keyof GranularPerfRow; i18nKey: string; color?: string; pct?: boolean }[] = [
  { key: 'powder_count', i18nKey: 'perf_detail.powder' },
  { key: 'no_reply_start', i18nKey: 'perf_detail.no_reply' },
  { key: 'reply_rate', i18nKey: 'perf_detail.reply_rate', pct: true },
  { key: 'stuck_explanation', i18nKey: 'perf_detail.stuck' },
  { key: 'blocked_playing', i18nKey: 'perf_detail.blocked' },
  { key: 'been_scammed', i18nKey: 'perf_detail.scammed' },
  { key: 'sent_link_no_reply', i18nKey: 'perf_detail.link_no_reply' },
  { key: 'completed_registration', i18nKey: 'perf_detail.registered' },
  { key: 'audit_rate', i18nKey: 'perf_detail.audit_rate', pct: true },
  { key: 'completed_training', i18nKey: 'perf_detail.training' },
  { key: 'scheduled_time', i18nKey: 'perf_detail.scheduled' },
  { key: 'withdrawal', i18nKey: 'perf_detail.withdrawal' },
  { key: 'new_order', i18nKey: 'perf_detail.new_order' },
  { key: 'conversion_rate', i18nKey: 'perf_detail.conversion', pct: true },
  { key: 'new_kill', i18nKey: 'perf_detail.new_kill' },
  { key: 'dead_client', i18nKey: 'perf_detail.dead' },
]

export default function PerformanceDetail() {
  const { theme } = useTheme()
  const lang = getLang()
  const [selectedDate, setSelectedDate] = useState(() => new Date().toISOString().split('T')[0])
  const [team, setTeam] = useState('all')
  const [rows, setRows] = useState<GranularPerfRow[]>([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [teams, setTeams] = useState<{ key: string; label: string }[]>([])

  useEffect(() => {
    api.allStaff().then(staff => {
      const uniqueTeams = [...new Set(staff.map((s: any) => s.team).filter(Boolean))]
      setTeams(uniqueTeams.map(t => ({ key: t, label: t })))
    }).catch((e) => { if (import.meta.env?.DEV) console.warn('api call failed:', e) })
  }, [])

  const [drawerOpen, setDrawerOpen] = useState(false)
  const [blownList, setBlownList] = useState<BlownAccount[]>([])
  const [blownLoading, setBlownLoading] = useState(false)
  const [blownForm, setBlownForm] = useState<Partial<BlownAccount>>({ display_name: '', team: '', account_identifier: '', blown_date: selectedDate, reason: '' })

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

  const grouped: Record<string, { name: string; team: string; categories: GranularPerfRow[] }> = {}
  rows.forEach(r => {
    const key = `${r.staff_id}`
    if (!grouped[key]) grouped[key] = { name: r.display_name, team: r.team, categories: [] }
    grouped[key].categories.push(r)
  })

  function sumRow(cats: GranularPerfRow[]): Record<string, number> {
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
    api.addBlownAccount({ ...blownForm, blown_date: selectedDate })
      .then(() => {
        setBlownForm({ display_name: '', team: '', account_identifier: '', blown_date: selectedDate, reason: '' })
        api.blownAccounts(selectedDate, team === 'all' ? undefined : team)
          .then(setBlownList)
          .catch((e) => { if (import.meta.env?.DEV) console.warn('api call failed:', e) })
      })
      .catch((e) => { if (import.meta.env?.DEV) console.warn('api call failed:', e) })
  }

  return (
    <div className="page-container max-w-1600">
      <h1 className="page-title mb-8">
        {t('perf_detail.title', lang)}
      </h1>
      <p className="page-subtitle mb-20">
        {t('perf_detail.subtitle', lang)}
      </p>

      {/* Controls row */}
      <div className="toolbar overflow-x-auto pb-4">
        <input type="date" className="input width-auto" value={selectedDate} onChange={e => setSelectedDate(e.target.value)} />
        <div className="tab-bar mb-0">
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
          <div className="empty-text mb-4">{t('perf.no_data', lang)}</div>
        </div>
      ) : (
        <div className="card overflow-x-auto p-0">
          <table className="data-grid-table min-w-1400">
            <thead>
              <tr>
                <th className="text-left sticky-left z-2 min-w-140">{t('perf.name', lang)}</th>
                <th className="text-left">{t('perf.team', lang)}</th>
                <th className="text-left">{t('frontdesk.category', lang)}</th>
                {COLUMNS.map(c => <th key={c.key} className="text-right">{t(c.i18nKey, lang)}</th>)}
              </tr>
            </thead>
            <tbody>
              {Object.entries(grouped).map(([key, g]) => {
                const isOpen = expanded[key]
                const personTotal = sumRow(g.categories)
                return (
                  <Fragment key={key}>
                    <tr key={`p-${key}`} className="pd-parent-row" onClick={() => toggleExpand(key)}>
                      <td className="text-bold text-left sticky-left z-1 min-w-140 bg-card">
                        <span className={`expand-arrow ${isOpen ? 'open' : ''}`}>&#9654;</span>
                        {g.name}
                      </td>
                      <td className="text-left">
                        <span className="pill-badge badge-info">{g.team || '-'}</span>
                      </td>
                      <td className="caption text-left">({g.categories.length})</td>
                      {COLUMNS.map(c => (
                        <td key={c.key} className={`text-right cell-mono ${c.key === 'dead_client' ? 'text-danger' : c.pct ? 'text-accent' : ''}`}>
                          {c.pct ? `${personTotal[c.key] || 0}%` : personTotal[c.key] || 0}
                        </td>
                      ))}
                    </tr>
                    {isOpen && g.categories.map((cat, ci) => (
                      <tr key={`c-${key}-${ci}`} className="pd-child-row">
                        <td className="sticky-left z-1 bg-page"></td>
                        <td></td>
                        <td className="caption text-bold text-left">{cat.category}</td>
                        {COLUMNS.map(c => (
                          <td key={c.key} className="text-right cell-mono">
                            {c.pct ? `${(cat[c.key] as number) || 0}%` : (cat[c.key] as number) || 0}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </Fragment>
                )
              })}
              <tr className="pd-total-row">
                <td className="text-bold text-left sticky-left z-1 bg-accent-subtle">
                  {t('perf_detail.grand_total', lang)}
                </td>
                <td></td>
                <td></td>
                {COLUMNS.map(c => (
                  <td key={c.key} className={`text-right cell-mono ${c.key === 'dead_client' ? 'text-danger' : 'text-accent'}`}>
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
            className="modal-overlay drawer-overlay"
            onClick={() => setDrawerOpen(false)}
          />
          <div className="drawer-right">
            {/* Drawer header */}
            <div className="drawer-header">
              <h2 className="heading-md">{t('perf_detail.blown', lang)}</h2>
              <button
                className="btn-secondary btn-sm"
                onClick={() => setDrawerOpen(false)}
              >
                X
              </button>
            </div>

            {/* Blown list */}
            <div className="drawer-body">
              {blownLoading ? (
                <div className="empty-state">{t('common.loading', lang)}...</div>
              ) : blownList.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-text">--</div>
                </div>
              ) : (
                <div className="grid-2col gap-8">
                  {blownList.map((b, i) => (
                    <div key={b.id || i} className="card p-12">
                      <div className="text-bold subtitle mb-4">{b.account_identifier}</div>
                      <div className="caption">{b.display_name} / {b.team}</div>
                      <div className="caption mt-4">{b.blown_date}</div>
                      {b.reason && <div className="caption mt-4 text-italic">{b.reason}</div>}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Add blown form */}
            <div className="drawer-footer">
              <h3 className="section-title mb-12">{t('perf_detail.add_blown', lang)}</h3>
              <div className="form-grid-2col gap-8">
                <input className="input" placeholder={t('perf.name', lang)} value={blownForm.display_name || ''} onChange={e => setBlownForm(p => ({ ...p, display_name: e.target.value }))} />
                <input className="input" placeholder={t('perf.team', lang)} value={blownForm.team || ''} onChange={e => setBlownForm(p => ({ ...p, team: e.target.value }))} />
                <input className="input" placeholder={t('perf_detail.account_name', lang)} value={blownForm.account_identifier || ''} onChange={e => setBlownForm(p => ({ ...p, account_identifier: e.target.value }))} />
                <input className="input" placeholder={t('detail.link_note', lang)} value={blownForm.reason || ''} onChange={e => setBlownForm(p => ({ ...p, reason: e.target.value }))} />
              </div>
              <button
                className="btn-primary mt-8 w-full btn-md"
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
