import { useEffect, useState } from 'react'
import { api, getAuthState } from '../api'
import { getLang, t } from '../i18n'

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

const S = {
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
    color: active ? '#ffffff' : '#7f848e',
    transition: 'all 0.15s',
  }),
  card: {
    background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 10,
    padding: 18, marginBottom: 14, boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
  } as React.CSSProperties,
  cardName: { fontSize: 15, fontWeight: 700, color: '#2d2a26', marginBottom: 2 },
  cardTeam: { fontSize: 12, color: '#7f848e', marginBottom: 12 },
  metricsGrid: {
    display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(100px, 1fr))', gap: 10,
  } as React.CSSProperties,
  metricBox: {
    background: '#f8fafc', borderRadius: 6, padding: '10px 12px', textAlign: 'center' as const,
  } as React.CSSProperties,
  metricValue: (color: string) => ({
    fontSize: 20, fontWeight: 700, color, lineHeight: 1.2,
  }),
  metricLabel: { fontSize: 10, color: '#7f848e', marginTop: 2, letterSpacing: 0.3 },
  summaryCard: {
    background: '#f0f9ff', border: '1px solid #bae6fd', borderRadius: 10,
    padding: 20, marginTop: 8,
  } as React.CSSProperties,
  summaryTitle: { fontSize: 13, fontWeight: 700, color: '#3b82f6', marginBottom: 14 },
  empty: { color: '#7f848e', fontSize: 14, padding: 20, textAlign: 'center' as const } as React.CSSProperties,
}

export default function Performance() {
  const lang = getLang()
  const auth = getAuthState()

  const [selectedDate, setSelectedDate] = useState(() => new Date().toISOString().split('T')[0])
  const [team, setTeam] = useState('all')
  const [data, setData] = useState<{ staff: StaffPerf[]; totals: Record<string, number> } | null>(null)
  const [loading, setLoading] = useState(true)

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
                {metric(t('perf.dead', lang), s.dead, '#7f848e')}
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
    </div>
  )
}
