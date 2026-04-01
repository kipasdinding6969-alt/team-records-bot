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
}

const getStyles = (theme: any) => ({
  page: { padding: 0, color: '#2d2a26', minHeight: '100%' } as React.CSSProperties,
  title: { fontSize: 22, fontWeight: 700, color: '#2d2a26', margin: '0 0 20px' } as React.CSSProperties,
  controls: { display: 'flex', gap: 12, marginBottom: 24, flexWrap: 'wrap' as const, alignItems: 'center' } as React.CSSProperties,
  input: {
    padding: '8px 14px', background: '#ffffff', border: '1px solid #e2e8f0',
    color: '#2d2a26', borderRadius: 6, fontSize: 14, outline: 'none',
  } as React.CSSProperties,
  teamTab: (active: boolean): React.CSSProperties => ({
    padding: '8px 16px', borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: 'pointer',
    border: active ? '1px solid #3b82f6' : '1px solid #e2e8f0',
    background: active ? '#3b82f6' : '#ffffff',
    color: active ? '#ffffff' : theme.textSecondary,
    transition: 'all 0.15s',
  }),
  card: {
    background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 10,
    padding: 18, marginBottom: 14, boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
  } as React.CSSProperties,
  cardName: { fontSize: 15, fontWeight: 700, color: '#2d2a26', marginBottom: 2 },
  cardTeam: { fontSize: 12, color: theme.textSecondary, marginBottom: 12 },
  metricsGrid: {
    display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(100px, 1fr))', gap: 10,
  } as React.CSSProperties,
  metricBox: {
    background: '#f8fafc', borderRadius: 6, padding: '10px 12px', textAlign: 'center' as const,
  } as React.CSSProperties,
  metricValue: (color: string) => ({
    fontSize: 20, fontWeight: 700, color, lineHeight: 1.2,
  }),
  metricLabel: { fontSize: 10, color: theme.textSecondary, marginTop: 2, letterSpacing: 0.3 },
  summaryCard: {
    background: '#f0f9ff', border: '1px solid #bae6fd', borderRadius: 10,
    padding: 20, marginTop: 8,
  } as React.CSSProperties,
  summaryTitle: { fontSize: 13, fontWeight: 700, color: '#3b82f6', marginBottom: 14 },
  empty: { color: theme.textSecondary, fontSize: 14, padding: 20, textAlign: 'center' as const } as React.CSSProperties,
})

export default function Performance() {
  const { theme } = useTheme()
  const S = getStyles(theme)
  const lang = getLang()
  const auth = getAuthState()

  const [selectedDate, setSelectedDate] = useState(() => new Date().toISOString().split('T')[0])
  const [team, setTeam] = useState('all')
  const [data, setData] = useState<{ staff: StaffPerf[]; totals: Record<string, number> } | null>(null)
  const [loading, setLoading] = useState(true)

  // Summary range
  const [showSummary, setShowSummary] = useState(false)
  const [summaryFrom, setSummaryFrom] = useState(() => {
    const d = new Date(); d.setDate(d.getDate() - 7); return d.toISOString().split('T')[0]
  })
  const [summaryTo, setSummaryTo] = useState(() => new Date().toISOString().split('T')[0])
  const [summaryData, setSummaryData] = useState<any>(null)
  const [summaryLoading, setSummaryLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    api.performanceDaily(selectedDate, team)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [selectedDate, team])

  function metric(label: string, value: number | string, color = '#2d2a26') {
    return (
      <div style={S.metricBox}>
        <div style={S.metricValue(color)}>{value}</div>
        <div style={S.metricLabel}>{label}</div>
      </div>
    )
  }

  return (
    <div style={S.page}>
      <h1 style={S.title}>{t('perf.title', lang)}</h1>

      <div style={S.controls}>
        <input
          type="date"
          style={S.input}
          value={selectedDate}
          onChange={e => setSelectedDate(e.target.value)}
        />
        {TEAMS.map(tm => (
          <button
            key={tm.key}
            style={S.teamTab(team === tm.key)}
            onClick={() => setTeam(tm.key)}
          >
            {lang === 'zh' ? tm.zh : tm.en}
          </button>
        ))}
      </div>

      {loading ? (
        <div style={S.empty}>{t('common.loading', lang)}</div>
      ) : !data || data.staff.length === 0 ? (
        <div style={S.empty}>{t('perf.no_data', lang)}</div>
      ) : (
        <>
          {data.staff.map(s => (
            <div key={s.staff_id} style={S.card}>
              <div style={S.cardName}>{s.display_name}</div>
              <div style={S.cardTeam}>{s.team || '—'}</div>
              <div style={S.metricsGrid}>
                {metric(t('perf.new_powder', lang), s.new_leads, '#3b82f6')}
                {metric(t('perf.reply_rate', lang), `${s.reply_rate}%`, '#22c55e')}
                {metric(t('perf.register', lang), s.registered, '#3b82f6')}
                {metric(t('perf.training', lang), s.training, '#f59e0b')}
                {metric(t('perf.withdraw', lang), s.withdrew, '#22c55e')}
                {metric(t('perf.new_order', lang), s.new_orders, '#22c55e')}
                {metric(t('perf.conversion', lang), `${s.conversion_rate}%`, '#3b82f6')}
                {metric(t('perf.deposit', lang), `$${(s.total_deposit || 0).toFixed(0)}`, '#22c55e')}
                {metric(t('perf.dead', lang), s.dead, '${theme.textSecondary}')}
              </div>
            </div>
          ))}

          <div style={S.summaryCard}>
            <div style={S.summaryTitle}>{t('perf.team_total', lang)}</div>
            <div style={S.metricsGrid}>
              {metric(t('perf.new_powder', lang), data.totals.new_leads || 0, '#3b82f6')}
              {metric(t('perf.reply_rate', lang), `${data.totals.reply_rate || 0}%`, '#22c55e')}
              {metric(t('perf.register', lang), data.totals.registered || 0, '#3b82f6')}
              {metric(t('perf.training', lang), data.totals.training || 0, '#f59e0b')}
              {metric(t('perf.withdraw', lang), data.totals.withdrew || 0, '#22c55e')}
              {metric(t('perf.new_order', lang), data.totals.new_orders || 0, '#22c55e')}
              {metric(t('perf.conversion', lang), `${data.totals.conversion_rate || 0}%`, '#3b82f6')}
              {metric(t('perf.deposit', lang), `$${(data.totals.total_deposit || 0).toFixed(0)}`, '#22c55e')}
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
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, color: '#2d2a26' }}>
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
                      {metric(t('perf.new_powder', lang), s.new_leads || 0, '#3b82f6')}
                      {metric(t('perf.reply_rate', lang), `${s.reply_rate || 0}%`, '#22c55e')}
                      {metric(t('perf.register', lang), s.registered || 0, '#3b82f6')}
                      {metric(t('perf.new_order', lang), s.new_orders || 0, '#22c55e')}
                      {metric(t('perf.deposit', lang), `$${(s.total_deposit || 0).toFixed(0)}`, '#22c55e')}
                    </div>
                  </div>
                ))}
                {summaryData.totals && (
                  <div style={S.summaryCard}>
                    <div style={S.summaryTitle}>{t('perf.team_total', lang)} ({summaryFrom} ~ {summaryTo})</div>
                    <div style={S.metricsGrid}>
                      {metric(t('perf.new_powder', lang), summaryData.totals.new_leads || 0, '#3b82f6')}
                      {metric(t('perf.new_order', lang), summaryData.totals.new_orders || 0, '#22c55e')}
                      {metric(t('perf.deposit', lang), `$${(summaryData.totals.total_deposit || 0).toFixed(0)}`, '#22c55e')}
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
