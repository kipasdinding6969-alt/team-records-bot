import { useEffect, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api } from '../api'
import type { Activity, DashboardStats, FunnelStage, Trends } from '../types'
import { getLang, t } from '../i18n'
import { getTheme, resolveTheme } from '../theme'

function useThemeLang() {
  const theme = resolveTheme(getTheme())
  const lang = getLang()
  return { theme, lang }
}

function StatCard({
  label,
  value,
  sub,
  accent,
  cardBg,
  cardBorder,
  textSecondary,
  textPrimary,
  shadow,
}: {
  label: string
  value: string | number
  sub?: string
  accent?: string
  cardBg: string
  cardBorder: string
  textSecondary: string
  textPrimary: string
  shadow: string
}) {
  return (
    <div style={{
      background: cardBg, border: `1px solid ${cardBorder}`,
      borderRadius: 12, padding: '20px 24px', boxShadow: shadow,
    }}>
      <div style={{ fontSize: 12, color: textSecondary, marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.8 }}>
        {label}
      </div>
      <div style={{ fontSize: 28, fontWeight: 700, color: accent || textPrimary }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: textSecondary, marginTop: 4 }}>{sub}</div>}
    </div>
  )
}

export default function Dashboard() {
  const { theme, lang } = useThemeLang()
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [funnel, setFunnel] = useState<FunnelStage[]>([])
  const [trends, setTrends] = useState<Trends | null>(null)
  const [activity, setActivity] = useState<Activity[]>([])
  const [loading, setLoading] = useState(true)
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date())

  async function load() {
    try {
      const [s, f, tr, a] = await Promise.all([
        api.dashboard(),
        api.funnel(),
        api.trends(),
        api.activity(),
      ])
      setStats(s)
      setFunnel(f)
      setTrends(tr)
      setActivity(a.slice(0, 12))
      setLastRefresh(new Date())
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    const id = setInterval(load, 30_000)
    return () => clearInterval(id)
  }, [])

  const cardProps = {
    cardBg: theme.cardBg,
    cardBorder: theme.cardBorder,
    textSecondary: theme.textSecondary,
    textPrimary: theme.textPrimary,
    shadow: theme.shadow,
  }

  const CARD_STYLE: React.CSSProperties = {
    background: theme.cardBg,
    border: `1px solid ${theme.cardBorder}`,
    borderRadius: 12,
    padding: '20px 24px',
    boxShadow: theme.shadow,
  }

  if (loading) return <Spinner color={theme.textSecondary} label={t('dash.loading', lang)} />

  const statusLabel = (v: string) => t(`status.${v}`, lang) || v

  return (
    <div>
      <PageHeader title={t('nav.dashboard', lang)} sub={`${lastRefresh.toLocaleTimeString()}`} theme={theme} />

      {stats && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
          gap: 16,
          marginBottom: 24,
        }}>
          <StatCard label={t('dash.total_clients', lang)} value={stats.total_clients} {...cardProps} />
          <StatCard label={t('dash.active_clients', lang)} value={stats.total_active} accent={theme.accent} {...cardProps} />
          <StatCard label={t('dash.today_new', lang)} value={stats.today_new} accent="#fdcb6e" {...cardProps} />
          <StatCard label={t('dash.today_orders', lang)} value={stats.today_orders} accent={theme.accent} {...cardProps} />
          <StatCard label={t('dash.today_deposits', lang)} value={`$${stats.today_deposits.toFixed(0)}`} accent="#00cec9" {...cardProps} />
          <StatCard label={t('dash.conversion', lang)} value={`${stats.conversion_rate}%`} {...cardProps} />
          <StatCard label={t('dash.overdue', lang)} value={stats.overdue_followups} accent={stats.overdue_followups > 0 ? '#ff7675' : theme.textSecondary} {...cardProps} />
          <StatCard label={t('dash.total_staff', lang)} value={stats.total_staff} {...cardProps} />
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, marginBottom: 24 }}>
        <div style={CARD_STYLE}>
          <SectionTitle theme={theme}>{t('dash.funnel', lang)}</SectionTitle>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={funnel} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={theme.cardBorder} />
              <XAxis dataKey="stage" tick={{ fill: theme.textSecondary, fontSize: 11 }} tickFormatter={statusLabel} />
              <YAxis tick={{ fill: theme.textSecondary, fontSize: 11 }} />
              <Tooltip contentStyle={{ background: theme.cardBg, border: `1px solid ${theme.cardBorder}`, borderRadius: 4, color: theme.textPrimary }} labelFormatter={statusLabel} />
              <Bar dataKey="count" fill={theme.chartBar} radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div style={CARD_STYLE}>
          <SectionTitle theme={theme}>{t('dash.new_clients_trend', lang)}</SectionTitle>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={trends?.daily_new || []} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={theme.cardBorder} />
              <XAxis dataKey="day" tick={{ fill: theme.textSecondary, fontSize: 10 }} tickFormatter={(v: string) => v.slice(5)} interval="preserveStartEnd" />
              <YAxis tick={{ fill: theme.textSecondary, fontSize: 11 }} />
              <Tooltip contentStyle={{ background: theme.cardBg, border: `1px solid ${theme.cardBorder}`, borderRadius: 4, color: theme.textPrimary }} />
              <Line type="monotone" dataKey="new_clients" stroke={theme.chartLine} dot={false} strokeWidth={2} name={t('dash.new_clients_trend', lang)} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div style={CARD_STYLE}>
        <SectionTitle theme={theme}>{t('dash.recent_activity', lang)}</SectionTitle>
        {activity.length === 0 ? (
          <Empty color={theme.textSecondary} />
        ) : (
          <div>
            {activity.map(a => (
              <div key={a.id} style={{
                display: 'flex', alignItems: 'flex-start', gap: 12,
                padding: '10px 0', borderBottom: `1px solid ${theme.cardBorder}40`,
              }}>
                <div style={{
                  width: 8, height: 8, borderRadius: '50%',
                  background: theme.accent, marginTop: 5, flexShrink: 0,
                }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, color: theme.textPrimary, lineHeight: 1.4 }}>
                    <span style={{ color: theme.textSecondary }}>{a.staff_name || '-'}</span>
                    {' — '}
                    <span style={{ color: '#74b9ff', fontFamily: 'monospace', fontSize: 12 }}>{a.client_phone || '-'}</span>
                    {a.content && (
                      <span style={{
                        marginLeft: 8, color: theme.textSecondary, fontSize: 12,
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                        maxWidth: 300, display: 'inline-block', verticalAlign: 'middle',
                      }}>{a.content}</span>
                    )}
                  </div>
                  <div style={{ fontSize: 11, color: theme.textSecondary, marginTop: 2 }}>
                    {a.created_at ? new Date(a.created_at).toLocaleString() : ''}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export function PageHeader({ title, sub, theme }: { title: string; sub?: string; theme?: any }) {
  const th = theme || resolveTheme(getTheme())
  return (
    <div style={{ marginBottom: 24 }}>
      <h1 style={{ fontSize: 22, fontWeight: 700, color: th.textPrimary }}>{title}</h1>
      {sub && <div style={{ fontSize: 12, color: th.textSecondary, marginTop: 4 }}>{sub}</div>}
    </div>
  )
}

export function SectionTitle({ children, theme }: { children: React.ReactNode; theme?: any }) {
  const th = theme || resolveTheme(getTheme())
  return (
    <div style={{ fontSize: 13, fontWeight: 600, color: th.textSecondary, marginBottom: 16, letterSpacing: 0.5, textTransform: 'uppercase' }}>
      {children}
    </div>
  )
}

export function Spinner({ color, label }: { color?: string; label?: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200, color: color || '#7f848e' }}>
      {label || '加载中...'}
    </div>
  )
}

export function Empty({ color }: { color?: string }) {
  return <div style={{ color: color || '#7f848e', fontSize: 13, padding: '16px 0' }}>—</div>
}
