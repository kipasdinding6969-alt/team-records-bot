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
  cardBg,
  cardBorder,
  textSecondary,
  textPrimary,
  shadowHover,
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
  shadowHover: string
}) {
  return (
    <div 
      style={{
        background: cardBg, border: `1px solid ${cardBorder}`,
        borderRadius: 16, padding: '24px', boxShadow: shadow,
        display: 'flex', flexDirection: 'column', gap: 12,
        transition: 'all 0.3s ease',
        cursor: 'default'
      }}
      onMouseOver={e => { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = shadowHover; e.currentTarget.style.borderColor = accent ? accent : cardBorder; }}
      onMouseOut={e => { e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = shadow; e.currentTarget.style.borderColor = cardBorder; }}
    >
      <div style={{ fontSize: 13, fontWeight: 600, color: textSecondary, textTransform: 'uppercase', letterSpacing: 0.5, display: 'flex', alignItems: 'center', gap: 8 }}>
        {accent && <div style={{ width: 8, height: 8, borderRadius: '50%', background: accent }} />}
        {label}
      </div>
      <div style={{ fontSize: 36, fontWeight: 700, color: textPrimary, letterSpacing: '-0.03em', lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ fontSize: 13, color: textSecondary, fontWeight: 500 }}>{sub}</div>}
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
    shadowHover: theme.shadowHover,
  }

  const CARD_STYLE: React.CSSProperties = {
    background: theme.cardBg,
    border: `1px solid ${theme.cardBorder}`,
    borderRadius: 16,
    padding: '24px',
    boxShadow: theme.shadow,
    transition: 'all 0.3s ease',
  }

  if (loading) return <Spinner color={theme.textSecondary} label={t('dash.loading', lang)} />

  const statusLabel = (v: string) => t(`status.${v}`, lang) || v

  return (
    <div>
      <PageHeader title={t('nav.dashboard', lang)} sub={`Last updated: ${lastRefresh.toLocaleTimeString()}`} theme={theme} />

      {stats && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
          gap: 24,
          marginBottom: 32,
        }}>
          <StatCard label={t('dash.total_clients', lang)} value={stats.total_clients.toLocaleString()} {...cardProps} />
          <StatCard label={t('dash.active_clients', lang)} value={stats.total_active.toLocaleString()} accent={theme.accent} {...cardProps} />
          <StatCard label={t('dash.today_new', lang)} value={stats.today_new.toLocaleString()} accent={theme.chartLine} {...cardProps} />
          <StatCard label={t('dash.today_orders', lang)} value={stats.today_orders.toLocaleString()} accent={theme.success} {...cardProps} />
          <StatCard label={t('dash.today_deposits', lang)} value={`$${stats.today_deposits.toLocaleString()}`} accent={theme.success} {...cardProps} />
          <StatCard label={t('dash.conversion', lang)} value={`${stats.conversion_rate}%`} {...cardProps} />
          <StatCard label={t('dash.overdue', lang)} value={stats.overdue_followups.toLocaleString()} accent={stats.overdue_followups > 0 ? theme.danger : theme.textSecondary} {...cardProps} />
          <StatCard label={t('dash.total_staff', lang)} value={stats.total_staff.toLocaleString()} {...cardProps} />
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: 24, marginBottom: 32 }}>
        <div style={CARD_STYLE}>
          <SectionTitle theme={theme}>📊 {t('dash.funnel', lang)}</SectionTitle>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={funnel} margin={{ top: 20, right: 20, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={theme.cardBorder} vertical={false} />
              <XAxis dataKey="stage" tick={{ fill: theme.textSecondary, fontSize: 12, fontWeight: 500 }} tickFormatter={statusLabel} axisLine={false} tickLine={false} dy={10} />
              <YAxis tick={{ fill: theme.textSecondary, fontSize: 12, fontWeight: 500 }} axisLine={false} tickLine={false} />
              <Tooltip cursor={{ fill: theme.accentLight, opacity: 0.4 }} contentStyle={{ background: theme.cardBg, border: `1px solid ${theme.cardBorder}`, borderRadius: 12, color: theme.textPrimary, boxShadow: theme.shadowHover, fontWeight: 600, padding: '12px 16px' }} itemStyle={{ color: theme.textPrimary, fontSize: 14 }} labelStyle={{ color: theme.textSecondary, marginBottom: 8, fontSize: 13, textTransform: 'uppercase' }} labelFormatter={statusLabel} />
              <Bar dataKey="count" fill={theme.chartBar} radius={[6, 6, 0, 0]} maxBarSize={60} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div style={CARD_STYLE}>
          <SectionTitle theme={theme}>📈 {t('dash.new_clients_trend', lang)}</SectionTitle>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={trends?.daily_new || []} margin={{ top: 20, right: 20, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={theme.cardBorder} vertical={false} />
              <XAxis dataKey="day" tick={{ fill: theme.textSecondary, fontSize: 12, fontWeight: 500 }} tickFormatter={(v: string) => v.slice(5)} interval="preserveStartEnd" axisLine={false} tickLine={false} dy={10} />
              <YAxis tick={{ fill: theme.textSecondary, fontSize: 12, fontWeight: 500 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ background: theme.cardBg, border: `1px solid ${theme.cardBorder}`, borderRadius: 12, color: theme.textPrimary, boxShadow: theme.shadowHover, fontWeight: 600, padding: '12px 16px' }} itemStyle={{ color: theme.textPrimary, fontSize: 14 }} labelStyle={{ color: theme.textSecondary, marginBottom: 8, fontSize: 13 }} />
              <Line type="monotone" dataKey="new_clients" stroke={theme.chartLine} dot={{ fill: theme.chartLine, strokeWidth: 2, r: 4 }} activeDot={{ r: 6, strokeWidth: 0 }} strokeWidth={3} name={t('dash.new_clients_trend', lang)} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div style={CARD_STYLE}>
        <SectionTitle theme={theme}>⚡ {t('dash.recent_activity', lang)}</SectionTitle>
        {activity.length === 0 ? (
          <Empty color={theme.textSecondary} />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {activity.map(a => (
              <div key={a.id} style={{
                display: 'flex', alignItems: 'center', gap: 16,
                padding: '16px', background: theme.bg, borderRadius: 8, border: `1px solid ${theme.cardBorder}`,
              }}>
                <div style={{
                  width: 12, height: 12, borderRadius: '50%',
                  background: theme.accent, flexShrink: 0,
                  boxShadow: `0 0 0 4px ${theme.accentLight}`
                }} />
                <div style={{ flex: 1, minWidth: 0, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ fontSize: 14, color: theme.textPrimary, fontWeight: 500, display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ color: theme.textPrimary, fontWeight: 600 }}>{a.staff_name || 'System'}</span>
                    <span style={{ color: theme.textMuted }}>•</span>
                    <span className="pill-badge" style={{ color: theme.accent, fontFamily: 'monospace', fontWeight: 600, background: theme.accentLight, padding: '4px 12px',  }}>{a.client_phone || 'N/A'}</span>
                    {a.content && (
                      <span style={{
                        color: theme.textSecondary, fontSize: 14,
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                        maxWidth: 400, display: 'inline-block',
                      }}>{a.content}</span>
                    )}
                  </div>
                  <div style={{ fontSize: 12, color: theme.textSecondary, fontWeight: 500 }}>
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

export function PageHeader({ title, sub, theme: themeProp }: { title: string; sub?: string; theme?: any }) {
  const { theme: ctxTheme } = useTheme()
  const th = themeProp || ctxTheme
  return (
    <div style={{ marginBottom: 32 }}>
      <h1 style={{ fontSize: 28, fontWeight: 700, color: th.textPrimary, letterSpacing: '-0.02em', margin: '0 0 8px' }}>{title}</h1>
      {sub && <div style={{ fontSize: 14, color: th.textSecondary, fontWeight: 500 }}>{sub}</div>}
    </div>
  )
}

export function SectionTitle({ children, theme: themeProp }: { children: React.ReactNode; theme?: any }) {
  const { theme: ctxTheme } = useTheme()
  const th = themeProp || ctxTheme
  return (
    <div style={{ fontSize: 14, fontWeight: 700, color: th.textPrimary, marginBottom: 20, letterSpacing: 0.5, textTransform: 'uppercase' }}>
      {children}
    </div>
  )
}

export function Spinner({ color, label }: { color?: string; label?: string }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, alignItems: 'center', justifyContent: 'center', height: 300, color: color || '#64748b' }}>
      <div style={{ width: 32, height: 32, border: '3px solid currentColor', borderRightColor: 'transparent', borderRadius: '50%', animation: 'spin 1s linear infinite' }}>
        <style>{`@keyframes spin { 100% { transform: rotate(360deg); } }`}</style>
      </div>
      <div style={{ fontSize: 14, fontWeight: 500 }}>{label || 'Loading...'}</div>
    </div>
  )
}

export function Empty({ color, label }: { color?: string, label?: string }) {
  return (
    <div className="empty-state" style={{ 
      margin: '48px auto', 
      padding: '48px 24px',
      textAlign: 'center',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      maxWidth: 400,
      background: 'linear-gradient(180deg, rgba(120, 120, 120, 0.03) 0%, rgba(120, 120, 120, 0.08) 100%)',
      borderRadius: 24,
      border: '1px dashed rgba(150, 150, 150, 0.2)',
      boxShadow: 'inset 0 2px 12px rgba(0, 0, 0, 0.02)'
    }}>
      <div style={{ 
        fontSize: 56, 
        marginBottom: 20, 
        opacity: 0.7,
        filter: 'drop-shadow(0 8px 16px rgba(0,0,0,0.1))'
      }}>📭</div>
      <div style={{ fontSize: 18, fontWeight: 700, color: color || '#888', letterSpacing: '-0.01em' }}>{label || 'No Data Found'}</div>
      <div style={{ fontSize: 14, marginTop: 8, color: '#999', lineHeight: 1.5, fontWeight: 500 }}>
        There are currently no records to display. Try adjusting your filters or check back later when new data arrives.
      </div>
    </div>
  )
}
