import { useEffect, useState } from 'react'
import { PageHeader, SectionTitle, Spinner, Empty } from '../components/SharedUI'
export { PageHeader, SectionTitle, Spinner, Empty, MessageBanner } from '../components/SharedUI'
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
import { useTheme } from '../ThemeContext'

function useThemeLang() {
  const { theme } = useTheme()
  const lang = getLang()
  return { theme, lang }
}

function StatCard({
  label,
  value,
  sub,
  accent,
}: {
  label: string
  value: string | number
  sub?: string
  accent?: string
}) {
  const { theme } = useTheme()
  return (
    <div className="stat-card" style={{ cursor: 'default' }}>
      <div className="stat-label" style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 0 }}>
        {accent && <div style={{ width: 8, height: 8, borderRadius: '50%', background: accent, flexShrink: 0 }} />}
        {label}
      </div>
      <div className="stat-value">{value}</div>
      {sub && <div style={{ fontSize: 12, color: theme.textSecondary, fontWeight: 500 }}>{sub}</div>}
    </div>
  )
}

export default function Dashboard() {
  const { theme, lang } = useThemeLang()
  const [error, setError] = useState('')
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

  const tooltipStyle = {
    background: theme.cardBg,
    border: `1px solid ${theme.cardBorder}`,
    borderRadius: 8,
    color: theme.textPrimary,
    boxShadow: theme.shadowHover,
    fontWeight: 600,
    padding: '12px',
  }

  if (loading) return <Spinner color={theme.textSecondary} label={t('dash.loading', lang)} />

  const statusLabel = (v: string) => t(`status.${v}`, lang) || v

  return (
    <div className="page-container fade-in">
      <PageHeader title={t('nav.dashboard', lang)} sub={`${t('dash.last_updated', lang)}: ${lastRefresh.toLocaleTimeString()}`} theme={theme} />

      {/* Stat cards */}
      {stats && (
        <div className="grid-4 section-gap">
          <StatCard label={t('dash.total_clients', lang)} value={stats.total_clients.toLocaleString()} />
          <StatCard label={t('dash.active_clients', lang)} value={stats.total_active.toLocaleString()} accent={theme.accent} />
          <StatCard label={t('dash.today_new', lang)} value={stats.today_new.toLocaleString()} accent={theme.chartLine} />
          <StatCard label={t('dash.today_orders', lang)} value={stats.today_orders.toLocaleString()} accent={theme.success} />
          <StatCard label={t('dash.today_deposits', lang)} value={`$${stats.today_deposits.toLocaleString()}`} accent={theme.success} />
          <StatCard label={t('dash.conversion', lang)} value={`${stats.conversion_rate}%`} />
          <StatCard label={t('dash.overdue', lang)} value={stats.overdue_followups.toLocaleString()} accent={stats.overdue_followups > 0 ? theme.danger : theme.textSecondary} />
          <StatCard label={t('dash.total_staff', lang)} value={stats.total_staff.toLocaleString()} />
        </div>
      )}

      {/* Charts */}
      <div className="grid-2 section-gap">
        <div className="card">
          <SectionTitle theme={theme}>{t('dash.funnel', lang)}</SectionTitle>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={funnel} margin={{ top: 20, right: 20, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={theme.cardBorder} vertical={false} />
              <XAxis dataKey="stage" tick={{ fill: theme.textSecondary, fontSize: 12, fontWeight: 500 }} tickFormatter={statusLabel} axisLine={false} tickLine={false} dy={12} />
              <YAxis tick={{ fill: theme.textSecondary, fontSize: 12, fontWeight: 500 }} axisLine={false} tickLine={false} />
              <Tooltip cursor={{ fill: theme.accentLight, opacity: 0.4 }} contentStyle={tooltipStyle} itemStyle={{ color: theme.textPrimary, fontSize: 14 }} labelStyle={{ color: theme.textSecondary, marginBottom: 8, fontSize: 13, textTransform: 'uppercase' }} labelFormatter={statusLabel} />
              <Bar dataKey="count" fill={theme.chartBar} radius={[8, 8, 0, 0]} maxBarSize={60} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <SectionTitle theme={theme}>{t('dash.new_clients_trend', lang)}</SectionTitle>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={trends?.daily_new || []} margin={{ top: 20, right: 20, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={theme.cardBorder} vertical={false} />
              <XAxis dataKey="day" tick={{ fill: theme.textSecondary, fontSize: 12, fontWeight: 500 }} tickFormatter={(v: string) => v.slice(5)} interval="preserveStartEnd" axisLine={false} tickLine={false} dy={12} />
              <YAxis tick={{ fill: theme.textSecondary, fontSize: 12, fontWeight: 500 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={tooltipStyle} itemStyle={{ color: theme.textPrimary, fontSize: 14 }} labelStyle={{ color: theme.textSecondary, marginBottom: 8, fontSize: 13 }} />
              <Line type="monotone" dataKey="new_clients" stroke={theme.chartLine} dot={{ fill: theme.chartLine, strokeWidth: 2, r: 4 }} activeDot={{ r: 8, strokeWidth: 0 }} strokeWidth={3} name={t('dash.new_clients_trend', lang)} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Activity feed */}
      <div className="card">
        <SectionTitle theme={theme}>{t('dash.recent_activity', lang)}</SectionTitle>
        {error && <div className="badge-danger" style={{ padding: 12, marginBottom: 20, fontSize: 13, display: 'block' }}>{error}</div>}
        {activity.length === 0 ? (
          <Empty color={theme.textSecondary} />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {activity.map(a => (
              <div key={a.id} style={{
                display: 'flex', alignItems: 'center', gap: 12,
                padding: '10px 12px', background: theme.bg, borderRadius: 8,
                borderBottom: `1px solid ${theme.cardBorder}`,
              }}>
                <div style={{
                  width: 8, height: 8, borderRadius: '50%',
                  background: theme.accent, flexShrink: 0,
                  boxShadow: `0 0 0 4px ${theme.accentLight}`
                }} />
                <div style={{ flex: 1, minWidth: 0, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
                  <div style={{ fontSize: 14, color: theme.textPrimary, fontWeight: 500, display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                    <span style={{ color: theme.textPrimary, fontWeight: 600, flexShrink: 0 }}>{a.staff_name || 'System'}</span>
                    <span style={{ color: theme.textMuted }}>·</span>
                    <span className="pill-badge" style={{ color: theme.accent, fontFamily: 'monospace', fontWeight: 600, background: theme.accentLight, padding: '4px 12px', flexShrink: 0 }}>{a.client_phone || 'N/A'}</span>
                    {a.content && (
                      <span style={{
                        color: theme.textSecondary, fontSize: 13,
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                        maxWidth: 400, display: 'inline-block',
                      }}>{a.content}</span>
                    )}
                  </div>
                  <div style={{ fontSize: 12, color: theme.textSecondary, fontWeight: 500, flexShrink: 0 }}>
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
