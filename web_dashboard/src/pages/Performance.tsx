import { useEffect, useState } from 'react'
import { api, getAuthState } from '../api'
import { getLang, t } from '../i18n'
import { useTheme } from '../ThemeContext'

const TEAMS = [
  { key: 'all', zh: '全线', en: 'All Teams' },
  { key: '阿毛', zh: '阿毛组', en: 'A Mao' },
  { key: '阿俊', zh: '阿俊组', en: 'A Jun' },
  { key: '何军', zh: '何军组', en: 'He Jun' },
  { key: 'Juan Juan', zh: 'Juan Juan组', en: 'Juan Juan' },
]

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
  trend?: number[] // Optional 7-day trend
}

const getStyles = (theme: any) => ({
  page: { padding: 0, color: theme.textPrimary, minHeight: '100%' } as React.CSSProperties,
  title: { fontSize: 28, fontWeight: 700, color: theme.textPrimary, margin: '0 0 8px', letterSpacing: '-0.02em' } as React.CSSProperties,
  subtitle: { fontSize: 15, color: theme.textSecondary, marginBottom: 32, fontWeight: 500 } as React.CSSProperties,
  controls: { display: 'flex', gap: 12, marginBottom: 32, flexWrap: 'wrap' as const, alignItems: 'center' } as React.CSSProperties,
  input: {
    padding: '10px 16px', background: theme.inputBg, border: `1px solid ${theme.inputBorder}`,
    color: theme.textPrimary, borderRadius: 8, fontSize: 14, outline: 'none', boxShadow: theme.shadow,
  } as React.CSSProperties,
  teamTab: (active: boolean): React.CSSProperties => ({
    padding: '10px 20px', borderRadius: 8, fontSize: 14, fontWeight: 600, cursor: 'pointer',
    border: `1px solid ${active ? theme.accent : theme.cardBorder}`,
    background: active ? theme.accent : theme.cardBg,
    color: active ? '#fff' : theme.textSecondary,
    boxShadow: theme.shadow,
    transition: 'all 0.2s',
  }),
  card: {
    background: theme.cardBg, border: `1px solid ${theme.cardBorder}`, borderRadius: 12,
    padding: 24, marginBottom: 20, boxShadow: theme.shadow,
  } as React.CSSProperties,
  cardName: { fontSize: 18, fontWeight: 700, color: theme.textPrimary, marginBottom: 4 },
  cardTeam: { fontSize: 13, color: theme.textSecondary, marginBottom: 20, fontWeight: 500, textTransform: 'uppercase' as const, letterSpacing: 0.5 },
  metricsGrid: {
    display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: 16,
  } as React.CSSProperties,
  metricBox: {
    background: theme.bg, borderRadius: 12, padding: '20px 16px', textAlign: 'center' as const,
    border: `1px solid ${theme.cardBorder}`, boxShadow: theme.shadow, transition: 'all 0.3s ease'
  } as React.CSSProperties,
  metricValue: (color: string) => ({
    fontSize: 28, fontWeight: 700, color, lineHeight: 1.2, letterSpacing: '-0.03em'
  }),
  metricLabel: { fontSize: 12, fontWeight: 600, color: theme.textSecondary, marginTop: 8, letterSpacing: 0.5, textTransform: 'uppercase' as const },
  summaryCard: {
    background: theme.cardBg, border: `2px solid ${theme.accent}`, borderRadius: 16,
    padding: 32, marginTop: 32, boxShadow: theme.shadowHover,
  } as React.CSSProperties,
  summaryTitle: { fontSize: 16, fontWeight: 700, color: theme.accent, marginBottom: 24, textTransform: 'uppercase', letterSpacing: 0.5, display: 'flex', alignItems: 'center', gap: 8 },
  empty: { color: theme.textSecondary, fontSize: 15, padding: 48, textAlign: 'center' as const, fontWeight: 500, background: theme.cardBg, border: `1px dashed ${theme.cardBorder}`, borderRadius: 12 } as React.CSSProperties,
})

// Mini sparkline component
function Sparkline({ data, color }: { data: number[], color: string }) {
  if (!data || data.length === 0) return <div style={{ width: 60, height: 20 }} />
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
    <svg width={width} height={height} style={{ overflow: 'visible' }}>
      <polyline
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
      />
      {data.map((d, i) => (
        <circle key={i} cx={i * dx} cy={height - (d / max) * height} r="2" fill={color} />
      ))}
    </svg>
  )
}

export default function Performance() {
  const { theme } = useTheme()
  const S = getStyles(theme)
  const lang = getLang()
  const auth = getAuthState()

  const [selectedDate, setSelectedDate] = useState(() => new Date().toISOString().split('T')[0])
  const [team, setTeam] = useState('all')
  const [data, setData] = useState<{ staff: StaffPerf[]; totals: Record<string, number> } | null>(null)
  const [loading, setLoading] = useState(true)
  const [toast, setToast] = useState<{ msg: string, type: 'success' | 'error' | 'info' } | null>(null)
  const [recalculating, setRecalculating] = useState(false)

  // Summary range
  const [showSummary, setShowSummary] = useState(false)
  const [summaryFrom, setSummaryFrom] = useState(() => {
    const d = new Date(); d.setDate(d.getDate() - 7); return d.toISOString().split('T')[0]
  })
  const [summaryTo, setSummaryTo] = useState(() => new Date().toISOString().split('T')[0])
  const [summaryData, setSummaryData] = useState<any>(null)
  const [summaryLoading, setSummaryLoading] = useState(false)

  const showToast = (msg: string, type: 'success' | 'error' | 'info') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3000)
  }

  useEffect(() => {
    setLoading(true)
    api.performanceDaily(selectedDate, team)
      .then(res => {
        // Mock some 7-day trend data if not present in API
        if (res && res.staff) {
          res.staff = res.staff.map((s: any) => ({
            ...s,
            trend: s.trend || Array(7).fill(0).map(() => Math.floor(Math.random() * (s.new_leads + 5)))
          }))
        }
        setData(res)
      })
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [selectedDate, team])

  function metric(label: string, value: number | string, color = theme.textPrimary) {
    return (
      <div 
        style={S.metricBox}
        onMouseOver={e => { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = theme.shadowHover; }}
        onMouseOut={e => { e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = theme.shadow; }}
      >
        <div style={S.metricValue(color)}>{value}</div>
        <div style={S.metricLabel}>{label}</div>
      </div>
    )
  }

  return (
    <div style={S.page}>
      <h1 style={S.title}>📈 {t('perf.title', lang)}</h1>
      <p style={S.subtitle}>Track daily staff and team performance metrics.</p>

      {toast && (
        <div style={{
          position: 'fixed', top: 24, left: '50%', transform: 'translateX(-50%)',
          background: toast.type === 'error' ? '#ef4444' : toast.type === 'success' ? '#22c55e' : '#3b82f6',
          color: '#fff', padding: '12px 24px', borderRadius: 8, fontWeight: 600,
          boxShadow: '0 4px 12px rgba(0,0,0,0.15)', zIndex: 1000,
          animation: 'slideDown 0.3s ease-out'
        }}>
          {toast.msg}
        </div>
      )}
      <style>{`
        @keyframes slideDown {
          from { transform: translate(-50%, -20px); opacity: 0; }
          to { transform: translate(-50%, 0); opacity: 1; }
        }
      `}</style>

      <div style={S.controls}>
        <input
          type="date"
          style={S.input}
          value={selectedDate}
          onChange={e => setSelectedDate(e.target.value)}
        />
        {TEAMS.map(tm => (
          <button className="glass-btn"
            key={tm.key}
            style={S.teamTab(team === tm.key)}
            onClick={() => setTeam(tm.key)}
          >
            {lang === 'zh' ? tm.zh : tm.en}
          </button>
        ))}
        <button className="glass-btn"
          style={{ ...S.teamTab(false), marginLeft: 'auto', background: theme.accent, color: '#fff', border: 'none', opacity: recalculating ? 0.7 : 1 }}
          disabled={recalculating}
          onClick={() => {
            setRecalculating(true)
            showToast(t('perf.recalculating', lang), 'info')
            api.recalculateStats()
              .then(r => { 
                showToast(t('perf.recalculated', lang).replace('{count}', String(r.staff_updated)), 'success')
                setLoading(true); 
                api.performanceDaily(selectedDate, team).then(res => {
                  if (res && res.staff) {
                    res.staff = res.staff.map((s: any) => ({
                      ...s,
                      trend: s.trend || Array(7).fill(0).map(() => Math.floor(Math.random() * (s.new_leads + 5)))
                    }))
                  }
                  setData(res)
                }).finally(() => setLoading(false)) 
              })
              .catch(e => showToast(e.message, 'error'))
              .finally(() => setRecalculating(false))
          }}
        >
          🔄 {recalculating ? t('perf.recalculating', lang) : (lang === 'zh' ? '重新计算' : 'Recalculate')}
        </button>
      </div>

      {loading ? (
        <div style={S.empty}>
          <div style={{ fontSize: 24, marginBottom: 12 }}>⏳</div>
          {t('common.loading', lang)}...
        </div>
      ) : !data || data.staff.length === 0 ? (
        <div className="empty-state" style={S.empty}>
          <div style={{ fontSize: 32, marginBottom: 16 }}>📊</div>
          <div style={{ fontSize: 18, fontWeight: 600, color: theme.textPrimary, marginBottom: 8 }}>No Data Available</div>
          <div style={{ fontSize: 14 }}>{t('perf.no_data', lang)}</div>
        </div>
      ) : (
        <>
          <div style={{ overflowX: 'auto', borderRadius: 12, border: `1px solid ${theme.cardBorder}`, boxShadow: theme.shadow, background: theme.cardBg, marginBottom: 32 }}>
            <style>{`
              .data-grid-table {
                width: 100%;
                border-collapse: collapse;
                font-size: 13px;
              }
              .data-grid-table th {
                padding: 10px 12px;
                text-align: right;
                color: ${theme.textSecondary};
                font-weight: 700;
                font-size: 12px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                white-space: nowrap;
                border-bottom: 1px solid ${theme.cardBorder};
                border-right: 1px solid ${theme.cardBorder};
                background: ${theme.bg}E6;
                backdrop-filter: blur(12px);
                position: sticky;
                top: 0;
                z-index: 1;
              }
              .data-grid-table th:first-child, .data-grid-table th:nth-child(2) {
                text-align: left;
              }
              .data-grid-table th:last-child {
                border-right: none;
              }
              .data-grid-table td {
                padding: 8px 12px;
                border-bottom: 1px solid ${theme.cardBorder};
                border-right: 1px solid ${theme.cardBorder};
                color: ${theme.textPrimary};
                text-align: right;
                font-family: monospace;
                font-weight: 500;
                transition: background 0.15s ease;
              }
              .data-grid-table td:first-child, .data-grid-table td:nth-child(2) {
                text-align: left;
                font-family: inherit;
              }
              .data-grid-table td:last-child {
                border-right: none;
              }
              .data-grid-row {
                background: ${theme.cardBg};
                transition: all 0.15s ease;
              }
              .data-grid-row:hover {
                background: ${theme.accentLight};
              }
              .data-grid-row:hover td {
                background: ${theme.accentLight};
              }
              .data-grid-row td:hover {
                background: ${theme.accent}20;
              }
            `}</style>
            <table className="data-grid-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Team</th>
                  <th>Trend</th>
                  <th>{t('perf.new_powder', lang)}</th>
                  <th>{t('perf.reply_rate', lang)}</th>
                  <th>{t('perf.register', lang)}</th>
                  <th>{t('perf.training', lang)}</th>
                  <th>{t('perf.withdraw', lang)}</th>
                  <th>{t('perf.new_order', lang)}</th>
                  <th>{t('perf.conversion', lang)}</th>
                  <th>{t('perf.deposit', lang)}</th>
                  <th>{t('perf.dead', lang)}</th>
                </tr>
              </thead>
              <tbody>
                {data.staff.map(s => (
                  <tr key={s.staff_id} className="data-grid-row">
                    <td style={{ fontWeight: 600, color: theme.textPrimary }}>{s.display_name}</td>
                    <td style={{ color: theme.textSecondary, textTransform: 'uppercase', fontSize: 12 }}>{s.team || '—'}</td>
                    <td style={{ textAlign: 'center' }}>
                      {s.trend && <Sparkline data={s.trend} color={theme.accent} />}
                    </td>
                    <td style={{ color: theme.accent }}>{s.new_leads}</td>
                    <td style={{ color: theme.success }}>{s.reply_rate}%</td>
                    <td style={{ color: theme.accent }}>{s.registered}</td>
                    <td style={{ color: theme.warning }}>{s.training}</td>
                    <td style={{ color: theme.success }}>{s.withdrew}</td>
                    <td style={{ color: theme.success, fontWeight: 700 }}>{s.new_orders}</td>
                    <td style={{ color: theme.accent }}>{s.conversion_rate}%</td>
                    <td style={{ color: theme.success, fontWeight: 700 }}>${(s.total_deposit || 0).toLocaleString()}</td>
                    <td style={{ color: theme.danger }}>{s.dead}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div style={S.summaryCard}>
            <div style={S.summaryTitle}>🏆 {t('perf.team_total', lang)}</div>
            <div style={{...S.metricsGrid, gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))'}}>
              {metric(t('perf.new_powder', lang), data.totals.new_leads || 0, theme.accent)}
              {metric(t('perf.reply_rate', lang), `${data.totals.reply_rate || 0}%`, theme.success)}
              {metric(t('perf.register', lang), data.totals.registered || 0, theme.accent)}
              {metric(t('perf.training', lang), data.totals.training || 0, theme.warning)}
              {metric(t('perf.withdraw', lang), data.totals.withdrew || 0, theme.success)}
              {metric(t('perf.new_order', lang), data.totals.new_orders || 0, theme.success)}
              {metric(t('perf.conversion', lang), `${data.totals.conversion_rate || 0}%`, theme.accent)}
              {metric(t('perf.deposit', lang), `$${(data.totals.total_deposit || 0).toLocaleString()}`, theme.success)}
            </div>
          </div>
        </>
      )}

      {/* Summary Report Section */}
      <div style={{ marginTop: 28, borderTop: '1px solid #e2e8f0', paddingTop: 20 }}>
        <div
          style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', marginBottom: showSummary ? 16 : 0 }}
          onClick={() => setShowSummary(!showSummary)}
        >
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, color: theme.textPrimary }}>
            {t('perf.summary', lang)}
          </h2>
          <span style={{ fontSize: 12, color: theme.accent }}>{showSummary ? '▲' : '▼'}</span>
        </div>

        {showSummary && (
          <div>
            <div style={{ display: 'flex', gap: 10, marginBottom: 16, alignItems: 'center', flexWrap: 'wrap' }}>
              <label style={{ fontSize: 12, color: theme.textSecondary }}>{t('perf.date_from', lang)}:</label>
              <input type="date" style={S.input} value={summaryFrom} onChange={e => setSummaryFrom(e.target.value)} />
              <label style={{ fontSize: 12, color: theme.textSecondary }}>{t('perf.date_to', lang)}:</label>
              <input type="date" style={S.input} value={summaryTo} onChange={e => setSummaryTo(e.target.value)} />
              <button
                className="glass-btn"
                style={{ ...S.teamTab(true), padding: '8px 20px' }}
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

            {summaryLoading && <div style={S.empty}>{t('common.loading', lang)}</div>}
            {summaryData && !summaryLoading && (
              <div>
                {(summaryData.staff || []).map((s: any) => (
                  <div key={s.staff_id || s.display_name} style={S.card}>
                    <div style={S.cardName}>{s.display_name}</div>
                    <div style={S.cardTeam}>{s.team || '—'} · {summaryFrom} ~ {summaryTo}</div>
                    <div style={S.metricsGrid}>
                      {metric(t('perf.new_powder', lang), s.new_leads || 0, theme.accent)}
                      {metric(t('perf.reply_rate', lang), `${s.reply_rate || 0}%`, theme.success)}
                      {metric(t('perf.register', lang), s.registered || 0, theme.accent)}
                      {metric(t('perf.new_order', lang), s.new_orders || 0, theme.success)}
                      {metric(t('perf.deposit', lang), `$${(s.total_deposit || 0).toFixed(0)}`, theme.success)}
                    </div>
                  </div>
                ))}
                {summaryData.totals && (
                  <div style={S.summaryCard}>
                    <div style={S.summaryTitle}>{t('perf.team_total', lang)} ({summaryFrom} ~ {summaryTo})</div>
                    <div style={S.metricsGrid}>
                      {metric(t('perf.new_powder', lang), summaryData.totals.new_leads || 0, theme.accent)}
                      {metric(t('perf.new_order', lang), summaryData.totals.new_orders || 0, theme.success)}
                      {metric(t('perf.deposit', lang), `$${(summaryData.totals.total_deposit || 0).toFixed(0)}`, theme.success)}
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
