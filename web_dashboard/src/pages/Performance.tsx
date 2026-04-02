import { useEffect, useState } from 'react'
import { api, getAuthState } from '../api'
import { getLang, t } from '../i18n'
import { useTheme } from '../ThemeContext'

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
  if (!data || data.length === 0) return <div style={{ width: 60, height: 24, margin: '0 auto' }} />
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
    <svg width={width} height={height} style={{ overflow: 'visible', display: 'block', margin: '0 auto' }}>
      <polyline fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" points={points} />
      {data.map((d, i) => (
        <circle key={i} cx={i * dx} cy={height - (d / max) * height} r="2" fill={color} />
      ))}
    </svg>
  )
}

function MetricBox({ label, value, color }: { label: string; value: number | string; color: string }) {
  return (
    <div className="metric-card">
      <div className="metric-value" style={{ color }}>{value}</div>
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
  const [targets, setTargets] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [toast, setToast] = useState<{ msg: string, type: 'success' | 'error' | 'info' } | null>(null)
  const [recalculating, setRecalculating] = useState(false)

  const [showSummary, setShowSummary] = useState(false)
  const [summaryFrom, setSummaryFrom] = useState(() => {
    const d = new Date(); d.setDate(d.getDate() - 7); return d.toISOString().split('T')[0]
  })
  const [summaryTo, setSummaryTo] = useState(() => new Date().toISOString().split('T')[0])
  const [summaryData, setSummaryData] = useState<any>(null)
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [teamsList, setTeamsList] = useState<{ key: string, label: string }[]>([])

  useEffect(() => {
    api.orgChart()
      .then(orgData => {
        const dynamicTeams = [{ key: 'all', label: lang === 'zh' ? '全线' : 'All Teams' }]
        if (orgData && orgData.teams) {
          orgData.teams.forEach((t: any) => {
            dynamicTeams.push({ key: t.team, label: t.team })
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
          res.staff = res.staff.map((s: any) => ({
            ...s,
            trend: trendsData[s.staff_id] || []
          }))
        }
        setData(res)
        setTargets(targetsData)
      })
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [selectedDate, team])

  return (
    <div className="page-container">
      <h1 style={{ fontSize: 24, fontWeight: 700, color: theme.textPrimary, margin: '0 0 8px', letterSpacing: '-0.02em' }}>
        {t('perf.title', lang)}
      </h1>
      <p style={{ fontSize: 14, color: theme.textSecondary, marginBottom: 20, fontWeight: 500 }}>
        {t('perf.subtitle', lang)}
      </p>

      {toast && (
        <div className={`toast ${toast.type === 'error' ? 'toast-error' : toast.type === 'success' ? 'toast-success' : 'toast-info'}`}>
          {toast.msg}
        </div>
      )}

      {/* Controls: date picker + team pills */}
      <div className="toolbar">
        <input type="date" className="input" style={{ width: 'auto' }} value={selectedDate} onChange={e => setSelectedDate(e.target.value)} />
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'nowrap' }}>
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
          className="btn-primary"
          style={{ marginLeft: 'auto', height: 32, fontSize: 12, padding: '0 20px', opacity: recalculating ? 0.7 : 1 }}
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
                    res.staff = res.staff.map((s: any) => ({ ...s, trend: trendsData[s.staff_id] || [] }))
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
          <div className="empty-text" style={{ fontSize: 16, color: theme.textPrimary, marginBottom: 4 }}>{t('perf.no_data_title', lang)}</div>
          <div className="empty-text">{t('perf.no_data', lang)}</div>
        </div>
      ) : (
        <>
          {/* Target bars */}
          {targets && targets.length > 0 && (
            <div style={{ marginBottom: 20, display: 'flex', flexDirection: 'column', gap: 12 }}>
              <h2 style={{ fontSize: 18, fontWeight: 700, margin: 0, color: theme.textPrimary }}>
                {t('targets.title', lang)} ({targets[0].period_type})
              </h2>
              {targets.map(tData => {
                const leadsPct = Math.min(100, ((data.totals.new_leads || 0) / (tData.target_leads || 1)) * 100) || 0
                const ordersPct = Math.min(100, ((data.totals.new_orders || 0) / (tData.target_orders || 1)) * 100) || 0
                const depositPct = Math.min(100, ((data.totals.total_deposit || 0) / (tData.target_deposit || 1)) * 100) || 0

                const getBarColor = (pct: number) => pct >= 80 ? theme.success : pct >= 50 ? theme.warning : theme.danger

                const bar = (label: string, actual: number, target: number | null, pct: number, prefix = '') => {
                  if (!target) return null
                  return (
                    <div key={label} className="card" style={{ flex: 1, minWidth: 200, padding: 20 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, fontWeight: 600, marginBottom: 8, color: theme.textSecondary }}>
                        <span>{label}</span>
                        <span style={{ color: theme.textPrimary }}>{prefix}{actual.toLocaleString()} / {prefix}{target.toLocaleString()} ({pct.toFixed(0)}%)</span>
                      </div>
                      <div className="progress-bar">
                        <div className="progress-fill" style={{ width: `${pct}%`, background: getBarColor(pct) }} />
                      </div>
                    </div>
                  )
                }

                return (
                  <div key={tData.id} style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                    {bar(t('targets.leads', lang), data.totals.new_leads || 0, tData.target_leads, leadsPct)}
                    {bar(t('targets.orders', lang), data.totals.new_orders || 0, tData.target_orders, ordersPct)}
                    {bar(t('targets.deposit', lang), data.totals.total_deposit || 0, tData.target_deposit, depositPct, '$')}
                  </div>
                )
              })}
            </div>
          )}

          {/* Data table */}
          <div className="card" style={{ overflowX: 'auto', marginBottom: 20, padding: 0 }}>
            <table className="data-grid-table">
              <thead>
                <tr>
                  <th style={{ textAlign: 'left' }}>{t('perf.name', lang)}</th>
                  <th style={{ textAlign: 'left' }}>{t('perf.team', lang)}</th>
                  <th style={{ textAlign: 'center' }}>{t('perf.trend', lang)}</th>
                  <th style={{ textAlign: 'right' }}>{t('perf.new_powder', lang)}</th>
                  <th style={{ textAlign: 'right' }}>{t('perf.reply_rate', lang)}</th>
                  <th style={{ textAlign: 'right' }}>{t('perf.register', lang)}</th>
                  <th style={{ textAlign: 'right' }}>{t('perf.training', lang)}</th>
                  <th style={{ textAlign: 'right' }}>{t('perf.withdraw', lang)}</th>
                  <th style={{ textAlign: 'right' }}>{t('perf.new_order', lang)}</th>
                  <th style={{ textAlign: 'right' }}>{t('perf.conversion', lang)}</th>
                  <th style={{ textAlign: 'right' }}>{t('perf.deposit', lang)}</th>
                  <th style={{ textAlign: 'right' }}>{t('perf.dead', lang)}</th>
                </tr>
              </thead>
              <tbody>
                {data.staff.map(s => (
                  <tr key={s.staff_id}>
                    <td style={{ fontWeight: 600, textAlign: 'left' }}>{s.display_name}</td>
                    <td style={{ textAlign: 'left' }}>
                      <span className="pill-badge badge-info">{s.team || '-'}</span>
                    </td>
                    <td style={{ textAlign: 'center', width: 60 }}>
                      {s.trend && <Sparkline data={s.trend} color={theme.accent} />}
                    </td>
                    <td style={{ textAlign: 'right', fontFamily: 'monospace', color: theme.accent }}>{s.new_leads}</td>
                    <td style={{ textAlign: 'right', fontFamily: 'monospace', color: theme.success }}>{s.reply_rate}%</td>
                    <td style={{ textAlign: 'right', fontFamily: 'monospace', color: theme.accent }}>{s.registered}</td>
                    <td style={{ textAlign: 'right', fontFamily: 'monospace', color: theme.warning }}>{s.training}</td>
                    <td style={{ textAlign: 'right', fontFamily: 'monospace', color: theme.success }}>{s.withdrew}</td>
                    <td style={{ textAlign: 'right', fontFamily: 'monospace', fontWeight: 700, color: theme.success }}>{s.new_orders}</td>
                    <td style={{ textAlign: 'right', fontFamily: 'monospace', color: theme.accent }}>{s.conversion_rate}%</td>
                    <td style={{ textAlign: 'right', fontFamily: 'monospace', fontWeight: 700, color: theme.success }}>${(s.total_deposit || 0).toLocaleString()}</td>
                    <td style={{ textAlign: 'right', fontFamily: 'monospace', color: theme.danger }}>{s.dead}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Summary totals card */}
          <div className="card" style={{ border: `2px solid ${theme.accent}`, marginTop: 20 }}>
            <div style={{ fontSize: 16, fontWeight: 700, color: theme.accent, marginBottom: 20, textTransform: 'uppercase', letterSpacing: 0.5 }}>
              {t('perf.team_total', lang)}
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
              <MetricBox label={t('perf.new_powder', lang)} value={data.totals.new_leads || 0} color={theme.accent} />
              <MetricBox label={t('perf.reply_rate', lang)} value={`${data.totals.reply_rate || 0}%`} color={theme.success} />
              <MetricBox label={t('perf.register', lang)} value={data.totals.registered || 0} color={theme.accent} />
              <MetricBox label={t('perf.training', lang)} value={data.totals.training || 0} color={theme.warning} />
              <MetricBox label={t('perf.withdraw', lang)} value={data.totals.withdrew || 0} color={theme.success} />
              <MetricBox label={t('perf.new_order', lang)} value={data.totals.new_orders || 0} color={theme.success} />
              <MetricBox label={t('perf.conversion', lang)} value={`${data.totals.conversion_rate || 0}%`} color={theme.accent} />
              <MetricBox label={t('perf.deposit', lang)} value={`$${(data.totals.total_deposit || 0).toLocaleString()}`} color={theme.success} />
            </div>
          </div>
        </>
      )}

      {/* Summary Report Section */}
      <div style={{ marginTop: 20, borderTop: `1px solid ${theme.cardBorder}`, paddingTop: 20 }}>
        <div
          style={{ display: 'flex', alignItems: 'center', gap: 12, cursor: 'pointer', marginBottom: showSummary ? 20 : 0 }}
          onClick={() => setShowSummary(!showSummary)}
        >
          <h2 style={{ fontSize: 18, fontWeight: 700, margin: 0, color: theme.textPrimary }}>{t('perf.summary', lang)}</h2>
          <span style={{ fontSize: 12, color: theme.accent, transition: 'transform 0.2s', display: 'inline-block', transform: showSummary ? 'rotate(180deg)' : 'rotate(0deg)' }}>V</span>
        </div>

        {showSummary && (
          <div>
            <div style={{ display: 'flex', gap: 12, marginBottom: 20, alignItems: 'center', flexWrap: 'wrap' }}>
              <label style={{ fontSize: 12, color: theme.textSecondary, fontWeight: 600 }}>{t('perf.date_from', lang)}:</label>
              <input type="date" className="input" style={{ width: 'auto' }} value={summaryFrom} onChange={e => setSummaryFrom(e.target.value)} />
              <label style={{ fontSize: 12, color: theme.textSecondary, fontWeight: 600 }}>{t('perf.date_to', lang)}:</label>
              <input type="date" className="input" style={{ width: 'auto' }} value={summaryTo} onChange={e => setSummaryTo(e.target.value)} />
              <button
                className="btn-primary"
                style={{ padding: '0 24px' }}
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
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {(summaryData.staff || []).map((s: any) => (
                  <div key={s.staff_id || s.display_name} className="card">
                    <div style={{ fontSize: 18, fontWeight: 700, color: theme.textPrimary, marginBottom: 4 }}>{s.display_name}</div>
                    <div style={{ fontSize: 12, color: theme.textSecondary, marginBottom: 20, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                      {s.team || '-'} / {summaryFrom} ~ {summaryTo}
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: 12 }}>
                      <MetricBox label={t('perf.new_powder', lang)} value={s.new_leads || 0} color={theme.accent} />
                      <MetricBox label={t('perf.reply_rate', lang)} value={`${s.reply_rate || 0}%`} color={theme.success} />
                      <MetricBox label={t('perf.register', lang)} value={s.registered || 0} color={theme.accent} />
                      <MetricBox label={t('perf.new_order', lang)} value={s.new_orders || 0} color={theme.success} />
                      <MetricBox label={t('perf.deposit', lang)} value={`$${(s.total_deposit || 0).toFixed(0)}`} color={theme.success} />
                    </div>
                  </div>
                ))}
                {summaryData.totals && (
                  <div className="card" style={{ border: `2px solid ${theme.accent}` }}>
                    <div style={{ fontSize: 16, fontWeight: 700, color: theme.accent, marginBottom: 20, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                      {t('perf.team_total', lang)} ({summaryFrom} ~ {summaryTo})
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: 12 }}>
                      <MetricBox label={t('perf.new_powder', lang)} value={summaryData.totals.new_leads || 0} color={theme.accent} />
                      <MetricBox label={t('perf.new_order', lang)} value={summaryData.totals.new_orders || 0} color={theme.success} />
                      <MetricBox label={t('perf.deposit', lang)} value={`$${(summaryData.totals.total_deposit || 0).toFixed(0)}`} color={theme.success} />
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
