import { useEffect, useState } from 'react'
import { api, getAuthState } from '../api'
import { getLang, t } from '../i18n'
import { useTheme } from '../ThemeContext'
import type { OrgChartTeam, PerformanceDailyStaffRow, TeamTarget, PerformanceSummaryResult } from '../types'

interface StaffPerf {
  staff_id: number
  display_name: string
  team: string | null
  new_leads: number
  replied: number
  registered: number
  training: number
  withdrew: number
  new_orders: number
  dead: number
  total_deposit: number
  reply_rate: number
  registration_rate: number
  training_rate: number
  conversion_rate: number
  trend?: number[]
}

function Sparkline({ data, color }: { data: number[], color: string }) {
  if (!data || data.length === 0) return <span className="text-muted">{'\u2014'}</span>
  const max = Math.max(...data, 1)
  const width = 60
  const height = 24
  const dx = width / (data.length - 1 || 1)

  const points = data.map((d, i) => {
    const x = i * dx
    const y = height - (d / max) * height
    return `${x},${y}`
  }).join(' ')

  return (
    <svg width={width} height={height} className="sparkline-svg">
      <polyline fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" points={points} />
      {data.map((d, i) => (
        <circle key={`${i}-${d}`} cx={i * dx} cy={height - (d / max) * height} r="2" fill={color} />
      ))}
    </svg>
  )
}

function MetricBox({ label, value, colorClass }: { label: string; value: number | string; colorClass: string }) {
  return (
    <div className="metric-card">
      <div className={`metric-value ${colorClass}`}>{value}</div>
      <div className="metric-label">{label}</div>
    </div>
  )
}

export default function Performance() {
  const { theme } = useTheme()
  const lang = getLang()
  const auth = getAuthState()

  const [selectedDate, setSelectedDate] = useState(() => new Date().toISOString().split('T')[0])
  const [team, setTeam] = useState('all')
  const [data, setData] = useState<{ staff: StaffPerf[]; totals: Record<string, number> } | null>(null)
  const [targets, setTargets] = useState<TeamTarget[]>([])
  const [loading, setLoading] = useState(true)
  const [toast, setToast] = useState<{ msg: string, type: 'success' | 'error' | 'info' } | null>(null)
  const [recalculating, setRecalculating] = useState(false)

  const [showSummary, setShowSummary] = useState(false)
  const [summaryFrom, setSummaryFrom] = useState(() => {
    const d = new Date(); d.setDate(d.getDate() - 7); return d.toISOString().split('T')[0]
  })
  const [summaryTo, setSummaryTo] = useState(() => new Date().toISOString().split('T')[0])
  const [summaryData, setSummaryData] = useState<PerformanceSummaryResult | null>(null)
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [teamsList, setTeamsList] = useState<{ key: string, label: string }[]>([])

  let summaryTotals = null;
  if (summaryData && summaryData.staff) {
    summaryTotals = {
      new_leads: summaryData.staff.reduce((acc, s) => acc + (s.new_leads || 0), 0),
      new_orders: summaryData.staff.reduce((acc, s) => acc + (s.new_orders || 0), 0),
      total_deposit: summaryData.staff.reduce((acc, s) => acc + (s.total_deposit || 0), 0),
    };
  }

  useEffect(() => {
    api.orgChart()
      .then(orgData => {
        const dynamicTeams = [{ key: 'all', label: lang === 'zh' ? '全线' : 'All Teams' }]
        if (orgData && orgData.teams) {
          orgData.teams.forEach((entry: OrgChartTeam) => {
            dynamicTeams.push({ key: entry.team, label: entry.team })
          })
        }
        setTeamsList(dynamicTeams)
      })
      .catch(() => setTeamsList([{ key: 'all', label: lang === 'zh' ? '全线' : 'All Teams' }]))
  }, [lang])

  const showToast = (msg: string, type: 'success' | 'error' | 'info') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3000)
  }

  useEffect(() => {
    setLoading(true)
    Promise.all([
      api.performanceDaily(selectedDate, team),
      api.trendsBatch(team, 7),
      api.getTargets(team)
    ])
      .then(([res, trendsData, targetsData]) => {
        if (res && res.staff) {
          res.staff = res.staff.map((s: PerformanceDailyStaffRow) => ({
            ...s,
            trend: trendsData[s.staff_id] || []
          }))
        }
        setData(res)
        setTargets(targetsData)
      })
      .catch(() => { setData(null); showToast(t('common.error', lang), 'error') })
      .finally(() => setLoading(false))
  }, [selectedDate, team])

  return (
    <div className="page-container">
      <h1 className="heading-lg mb-8">
        {t('perf.title', lang)}
      </h1>
      <p className="subtitle mb-20">
        {t('perf.subtitle', lang)}
      </p>

      {toast && (
        <div className={`toast ${toast.type === 'error' ? 'toast-error' : toast.type === 'success' ? 'toast-success' : 'toast-info'}`}>
          {toast.msg}
        </div>
      )}

      {/* Controls: date picker + team pills */}
      <div className="toolbar">
        <input type="date" className="input w-auto" value={selectedDate} onChange={e => setSelectedDate(e.target.value)} />
        <div className="d-flex gap-8 items-center nowrap">
          {teamsList.map(tm => (
            <button
              key={tm.key}
              className={team === tm.key ? 'btn-primary btn-pill btn-sm' : 'btn-secondary btn-pill btn-sm'}
              onClick={() => setTeam(tm.key)}
            >
              {tm.label}
            </button>
          ))}
        </div>
        <button
          className={`btn-primary ml-auto${recalculating ? ' opacity-70' : ''}`}
          disabled={recalculating}
          onClick={() => {
            setRecalculating(true)
            showToast(t('perf.recalculating', lang), 'info')
            api.recalculateStats()
              .then(r => {
                showToast(t('perf.recalculated', lang).replace('{count}', String(r.staff_updated)), 'success')
                setLoading(true)
                api.performanceDaily(selectedDate, team).then(async res => {
                  const trendsData = await api.trendsBatch(team, 7)
                  if (res && res.staff) {
                    res.staff = res.staff.map((s: PerformanceDailyStaffRow) => ({ ...s, trend: trendsData[s.staff_id] || [] }))
                  }
                  setData(res)
                }).finally(() => setLoading(false))
              })
              .catch(e => showToast(e.message, 'error'))
              .finally(() => setRecalculating(false))
          }}
        >
          {recalculating ? t('perf.recalculating', lang) : t('perf.recalculate', lang)}
        </button>
      </div>

      {loading ? (
        <div className="empty-state">{t('common.loading', lang)}...</div>
      ) : !data || data.staff.length === 0 ? (
        <div className="empty-state">
          <div className="empty-text fs-16 text-primary mb-4">{t('perf.no_data_title', lang)}</div>
          <div className="empty-text">{t('perf.no_data', lang)}</div>
        </div>
      ) : (
        <>
          {/* Target bars */}
          {targets && targets.length > 0 && (
            <div className="flex-col gap-12 mb-20">
              <h2 className="heading-md">
                {t('targets.title', lang)} ({targets[0].period_type})
              </h2>
              {targets.map(tData => {
                const leadsPct = Math.min(100, ((data.totals.new_leads || 0) / (tData.target_leads || 1)) * 100) || 0
                const ordersPct = Math.min(100, ((data.totals.new_orders || 0) / (tData.target_orders || 1)) * 100) || 0
                const depositPct = Math.min(100, ((data.totals.total_deposit || 0) / (tData.target_deposit || 1)) * 100) || 0

                const getBarColor = (pct: number) => pct >= 80 ? theme.success : pct >= 50 ? theme.warning : theme.danger

                const bar = (label: string, actual: number, target: number | null, pct: number, prefix = '') => {
                  if (!target) return <span className="subtitle">{'\u2014'}</span>
                  return (
                    <div key={label} className="card p-20 target-bar-card">
                      <div className="d-flex justify-between fs-12 fw-600 mb-8 text-secondary">
                        <span>{label}</span>
                        <span className="text-primary">{prefix}{actual.toLocaleString()} / {prefix}{target.toLocaleString()} ({pct.toFixed(0)}%)</span>
                      </div>
                      <div className="progress-bar">
                        <div className="progress-fill" style={{ width: `${pct}%`, background: getBarColor(pct) }} />
                      </div>
                    </div>
                  )
                }

                return (
                  <div key={tData.id} className="d-flex gap-12 flex-wrap">
                    {bar(t('targets.leads', lang), data.totals.new_leads || 0, tData.target_leads, leadsPct)}
                    {bar(t('targets.orders', lang), data.totals.new_orders || 0, tData.target_orders, ordersPct)}
                    {bar(t('targets.deposit', lang), data.totals.total_deposit || 0, tData.target_deposit, depositPct, '$')}
                  </div>
                )
              })}
            </div>
          )}

          {/* Data table */}
          <div className="card p-0 overflow-x mb-20">
            <table className="data-grid-table">
              <thead>
                <tr>
                  <th className="text-left">{t('perf.name', lang)}</th>
                  <th className="text-left">{t('perf.team', lang)}</th>
                  <th className="text-center">{t('perf.trend', lang)}</th>
                  <th className="cell-right">{t('perf.new_powder', lang)}</th>
                  <th className="cell-right">{t('perf.reply_rate', lang)}</th>
                  <th className="cell-right">{t('perf.register', lang)}</th>
                  <th className="cell-right">{t('perf.training', lang)}</th>
                  <th className="cell-right">{t('perf.withdraw', lang)}</th>
                  <th className="cell-right">{t('perf.new_order', lang)}</th>
                  <th className="cell-right">{t('perf.conversion', lang)}</th>
                  <th className="cell-right">{t('perf.deposit', lang)}</th>
                  <th className="cell-right">{t('perf.dead', lang)}</th>
                </tr>
              </thead>
              <tbody>
                {data.staff.map(s => (
                  <tr key={s.staff_id}>
                    <td className="fw-600 text-left">{s.display_name}</td>
                    <td className="text-left">
                      <span className="pill-badge badge-info">{s.team || '-'}</span>
                    </td>
                    <td className="cell-center cell-trend">
                      {s.trend && <Sparkline data={s.trend} color={theme.accent} />}
                    </td>
                    <td className="cell-mono-right text-accent">{s.new_leads}</td>
                    <td className="cell-mono-right text-success">{Number(s.reply_rate || 0).toFixed(1)}%</td>
                    <td className="cell-mono-right text-accent">{s.registered}</td>
                    <td className="cell-mono-right text-warning">{s.training}</td>
                    <td className="cell-mono-right text-success">{s.withdrew}</td>
                    <td className="cell-mono-right text-success fw-700">{s.new_orders}</td>
                    <td className="cell-mono-right text-accent">{Number(s.conversion_rate || 0).toFixed(1)}%</td>
                    <td className="cell-mono-right text-success fw-700">${(s.total_deposit || 0).toLocaleString()}</td>
                    <td className="cell-mono-right text-danger">{s.dead}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Summary totals card */}
          <div className="card border-accent mt-20">
            <div className="label-section text-accent mb-20">
              {t('perf.team_total', lang)}
            </div>
            <div className="grid-4">
              <MetricBox label={t('perf.new_powder', lang)} value={data.totals.new_leads || 0} colorClass="text-accent" />
              <MetricBox label={t('perf.reply_rate', lang)} value={`${Number(data.totals.reply_rate || 0).toFixed(1)}%`} colorClass="text-success" />
              <MetricBox label={t('perf.register', lang)} value={data.totals.registered || 0} colorClass="text-accent" />
              <MetricBox label={t('perf.training', lang)} value={data.totals.training || 0} colorClass="text-warning" />
              <MetricBox label={t('perf.withdraw', lang)} value={data.totals.withdrew || 0} colorClass="text-success" />
              <MetricBox label={t('perf.new_order', lang)} value={data.totals.new_orders || 0} colorClass="text-success" />
              <MetricBox label={t('perf.conversion', lang)} value={`${Number(data.totals.conversion_rate || 0).toFixed(1)}%`} colorClass="text-accent" />
              <MetricBox label={t('perf.deposit', lang)} value={`$${(data.totals.total_deposit || 0).toLocaleString()}`} colorClass="text-success" />
            </div>
          </div>
        </>
      )}

      {/* Summary Report Section */}
      <div className="mt-20 border-top pt-20">
        <div
          className={`accordion-header${showSummary ? ' mb-20' : ''}`}
          onClick={() => setShowSummary(!showSummary)}
        >
          <h2 className="heading-md">{t('perf.summary', lang)}</h2>
          <span className={`accordion-chevron${showSummary ? ' open' : ''}`}>&#9660;</span>
        </div>

        {showSummary && (
          <div>
            <div className="form-row-center flex-wrap mb-20">
              <label className="field-label">{t('perf.date_from', lang)}:</label>
              <input type="date" className="input w-auto" value={summaryFrom} onChange={e => setSummaryFrom(e.target.value)} />
              <label className="field-label">{t('perf.date_to', lang)}:</label>
              <input type="date" className="input w-auto" value={summaryTo} onChange={e => setSummaryTo(e.target.value)} />
              <button
                className="btn-primary px-20"
                onClick={() => {
                  setSummaryLoading(true)
                  api.performanceSummary(summaryFrom, summaryTo, team !== 'all' ? team : undefined)
                    .then(setSummaryData)
                    .catch(() => setSummaryData(null))
                    .finally(() => setSummaryLoading(false))
                }}
              >
                {t('common.search', lang)}
              </button>
            </div>

            {summaryLoading && <div className="empty-state">{t('common.loading', lang)}</div>}
            {summaryData && !summaryLoading && (
              <div className="flex-col gap-12">
                {(summaryData.staff || []).map((s: PerformanceDailyStaffRow) => (
                  <div key={s.staff_id || s.display_name} className="card">
                    <div className="heading-md mb-4">{s.display_name}</div>
                    <div className="label-section text-secondary mb-20">
                      {s.team || '-'} / {summaryFrom} ~ {summaryTo}
                    </div>
                    <div className="grid-4">
                      <MetricBox label={t('perf.new_powder', lang)} value={s.new_leads || 0} colorClass="text-accent" />
                      <MetricBox label={t('perf.reply_rate', lang)} value={`${Number(s.reply_rate || 0).toFixed(1)}%`} colorClass="text-success" />
                      <MetricBox label={t('perf.register', lang)} value={s.registered || 0} colorClass="text-accent" />
                      <MetricBox label={t('perf.new_order', lang)} value={s.new_orders || 0} colorClass="text-success" />
                      <MetricBox label={t('perf.deposit', lang)} value={`$${(s.total_deposit || 0).toLocaleString()}`} colorClass="text-success" />
                    </div>
                  </div>
                ))}
                {summaryTotals && (
                  <div className="card border-accent">
                    <div className="label-section text-accent mb-20">
                      {t('perf.team_total', lang)} ({summaryFrom} ~ {summaryTo})
                    </div>
                    <div className="grid-4">
                      <MetricBox label={t('perf.new_powder', lang)} value={summaryTotals.new_leads || 0} colorClass="text-accent" />
                      <MetricBox label={t('perf.new_order', lang)} value={summaryTotals.new_orders || 0} colorClass="text-success" />
                      <MetricBox label={t('perf.deposit', lang)} value={`${(summaryTotals.total_deposit || 0).toLocaleString()}`} colorClass="text-success" />
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
