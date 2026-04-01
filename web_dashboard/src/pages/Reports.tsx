import { useEffect, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api } from '../api'
import type { DashboardStats, Trends } from '../types'
import { STATUS_COLORS, STATUS_LABELS } from '../types'
import { Empty, PageHeader, SectionTitle, Spinner } from './Dashboard'
import { useTheme } from '../ThemeContext'

type Period = 'daily' | 'weekly' | 'monthly'

export default function Reports() {
  const { theme } = useTheme()
  const [period, setPeriod] = useState<Period>('daily')
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [trends, setTrends] = useState<Trends | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([api.dashboard(), api.trends()])
      .then(([s, t]) => {
        setStats(s)
        setTrends(t)
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Spinner />

  const donutData = stats
    ? Object.entries(stats.by_status)
        .filter(([, v]) => v > 0)
        .map(([k, v]) => ({ name: STATUS_LABELS[k] || k, value: v, status: k }))
    : []

  const CARD: React.CSSProperties = {
    background: theme.cardBg,
    border: `1px solid ${theme.cardBorder}`,
    borderRadius: 8,
    padding: 20,
    marginBottom: 24,
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <PageHeader title="报告分析" />
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {(['daily', 'weekly', 'monthly'] as Period[]).map(p => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              style={{
                padding: '6px 14px',
                background: period === p ? '${theme.cardBorder}' : 'transparent',
                border: `1px solid ${theme.cardBorder}`,
                borderRadius: 4,
                color: period === p ? '${theme.textPrimary}' : theme.textSecondary,
                cursor: 'pointer',
                fontSize: 12,
              }}
            >
              {p === 'daily' ? '日报' : p === 'weekly' ? '周报' : '月报'}
            </button>
          ))}
          <button
            onClick={() => api.exportReport(period).catch(console.error)}
            style={{
              padding: '6px 14px',
              background: `${theme.accent}20`,
              border: `1px solid ${theme.accent}`,
              borderRadius: 4,
              color: theme.accent,
              cursor: 'pointer',
              fontSize: 12,
              marginLeft: 8,
            }}
          >
            导出报告
          </button>
        </div>
      </div>

      {/* Line charts: new clients + orders */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, marginBottom: 0 }}>
        <div style={CARD}>
          <SectionTitle>新客户趋势</SectionTitle>
          {!trends?.daily_new.length ? (
            <Empty />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={trends.daily_new} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="${theme.cardBorder}" />
                <XAxis
                  dataKey="day"
                  tick={{ fill: theme.textSecondary, fontSize: 10 }}
                  tickFormatter={(v: string) => v.slice(5)}
                  interval="preserveStartEnd"
                />
                <YAxis tick={{ fill: theme.textSecondary, fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ background: theme.cardBg, border: `1px solid ${theme.cardBorder}`, borderRadius: 4 }}
                />
                <Line type="monotone" dataKey="new_clients" stroke="${theme.accent}" dot={false} strokeWidth={2} name="新客户" />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>

        <div style={CARD}>
          <SectionTitle>下单趋势</SectionTitle>
          {!trends?.daily_orders.length ? (
            <Empty />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={trends.daily_orders} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="${theme.cardBorder}" />
                <XAxis
                  dataKey="day"
                  tick={{ fill: theme.textSecondary, fontSize: 10 }}
                  tickFormatter={(v: string) => v.slice(5)}
                  interval="preserveStartEnd"
                />
                <YAxis tick={{ fill: theme.textSecondary, fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ background: theme.cardBg, border: `1px solid ${theme.cardBorder}`, borderRadius: 4 }}
                />
                <Line type="monotone" dataKey="orders" stroke="${theme.chartLine}" dot={false} strokeWidth={2} name="下单" />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Deposit trend + status donut */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 24 }}>
        <div style={CARD}>
          <SectionTitle>存款趋势 (30天)</SectionTitle>
          {!trends?.daily_deposits.length ? (
            <Empty />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={trends.daily_deposits} margin={{ top: 4, right: 8, left: -10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="${theme.cardBorder}" />
                <XAxis
                  dataKey="day"
                  tick={{ fill: theme.textSecondary, fontSize: 10 }}
                  tickFormatter={(v: string) => v.slice(5)}
                  interval="preserveStartEnd"
                />
                <YAxis tick={{ fill: theme.textSecondary, fontSize: 11 }} tickFormatter={(v: number) => `$${v}`} />
                <Tooltip
                  contentStyle={{ background: theme.cardBg, border: `1px solid ${theme.cardBorder}`, borderRadius: 4 }}
                  formatter={(v: number) => [`$${v.toFixed(0)}`, '存款']}
                />
                <Bar dataKey="total" fill="${theme.accent}" radius={[3, 3, 0, 0]} name="存款" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Status distribution donut */}
        <div style={CARD}>
          <SectionTitle>状态分布</SectionTitle>
          {donutData.length === 0 ? (
            <Empty />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={donutData}
                  cx="50%"
                  cy="50%"
                  innerRadius={55}
                  outerRadius={85}
                  paddingAngle={2}
                  dataKey="value"
                >
                  {donutData.map((entry, index) => (
                    <Cell key={index} fill={STATUS_COLORS[entry.status] || '${theme.textSecondary}'} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ background: theme.cardBg, border: `1px solid ${theme.cardBorder}`, borderRadius: 4 }}
                />
                <Legend
                  wrapperStyle={{ fontSize: 11, color: theme.textSecondary }}
                  iconSize={8}
                />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Conversion rate card */}
      {stats && (
        <div style={{ ...CARD, display: 'flex', gap: 40, alignItems: 'center' }}>
          <div>
            <div style={{ fontSize: 12, color: theme.textSecondary, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 }}>
              整体转化率
            </div>
            <div style={{ fontSize: 40, fontWeight: 700, color: theme.accent }}>
              {stats.conversion_rate}%
            </div>
            <div style={{ fontSize: 12, color: theme.textSecondary, marginTop: 4 }}>
              {stats.by_status['ordered'] || 0} 下单 / {stats.total_clients} 总客户
            </div>
          </div>
          <div>
            <div style={{ fontSize: 12, color: theme.textSecondary, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 }}>
              总存款
            </div>
            <div style={{ fontSize: 40, fontWeight: 700, color: theme.accent }}>
              ${stats.total_deposits.toLocaleString(undefined, { maximumFractionDigits: 0 })}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
