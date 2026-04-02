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
import { STATUS_COLORS } from '../types'
import { Empty, PageHeader, SectionTitle, Spinner } from '../components/SharedUI'
import { useTheme } from '../ThemeContext'
import { t, getLang } from '../i18n'

type Period = 'daily' | 'weekly' | 'monthly'

export default function Reports() {
  const { theme } = useTheme()
  const lang = getLang()
  const [error, setError] = useState('');
  const [period, setPeriod] = useState<Period>('daily')
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [trends, setTrends] = useState<Trends | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([api.dashboard(), api.trends()])
      .then(([statsData, trendsData]) => {
        setStats(statsData)
        setTrends(trendsData)
      })
      .catch(e => { console.error(e); setError(t('common.error', lang)); })
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Spinner />

  const donutData = stats
    ? Object.entries(stats.by_status)
        .filter(([, v]) => v > 0)
        .map(([k, v]) => ({ name: t(`status.${k}`, getLang()) !== `status.${k}` ? t(`status.${k}`, getLang()) : k, value: v, status: k }))
    : []

  return (
    <div className="page-container">
      {error && <div className="alert alert-error">{error}</div>}

      <div className="toolbar">
        <PageHeader title={t('reports.title', getLang())} />
        <div className="toolbar-spacer" />
        <div className="tab-bar mb-0">
          {(['daily', 'weekly', 'monthly'] as Period[]).map(p => (
            <button
              className={`tab-btn ${period === p ? 'active' : ''}`}
              key={p}
              onClick={() => setPeriod(p)}
            >
              {t(`reports.${p}`, getLang())}
            </button>
          ))}
        </div>
        <button
          className="btn-secondary"
          onClick={() => api.exportReport(period).catch(e => { console.error(e); setError(t('common.update_failed', lang)); })}
        >
          {t('reports.export', getLang())}
        </button>
      </div>

      {/* Line charts: new clients + orders */}
      <div className="grid-2col gap-12 mb-20">
        <div className="card">
          <SectionTitle>{t('reports.new_client_trend', getLang())}</SectionTitle>
          {!trends?.daily_new.length ? (
            <Empty />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={trends.daily_new} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={theme.cardBorder} />
                <XAxis
                  dataKey="day"
                  tick={{ fill: theme.textSecondary, fontSize: 12 }}
                  tickFormatter={(v: string) => v.slice(5)}
                  interval="preserveStartEnd"
                />
                <YAxis tick={{ fill: theme.textSecondary, fontSize: 12 }} />
                <Tooltip
                  contentStyle={{ background: theme.cardBg, border: `1px solid ${theme.cardBorder}`, borderRadius: 8 }}
                />
                <Line type="monotone" dataKey="new_clients" stroke={theme.accent} dot={false} strokeWidth={2} name={t('reports.new_clients_label', getLang())} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="card">
          <SectionTitle>{t('reports.order_trend', getLang())}</SectionTitle>
          {!trends?.daily_orders.length ? (
            <Empty />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={trends.daily_orders} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={theme.cardBorder} />
                <XAxis
                  dataKey="day"
                  tick={{ fill: theme.textSecondary, fontSize: 12 }}
                  tickFormatter={(v: string) => v.slice(5)}
                  interval="preserveStartEnd"
                />
                <YAxis tick={{ fill: theme.textSecondary, fontSize: 12 }} />
                <Tooltip
                  contentStyle={{ background: theme.cardBg, border: `1px solid ${theme.cardBorder}`, borderRadius: 8 }}
                />
                <Line type="monotone" dataKey="orders" stroke={theme.chartLine} dot={false} strokeWidth={2} name={t('reports.orders_label', getLang())} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Deposit trend + status donut */}
      <div className="grid-2fr-1fr gap-12 mb-20">
        <div className="card">
          <SectionTitle>{t('reports.deposit_trend_30', getLang())}</SectionTitle>
          {!trends?.daily_deposits.length ? (
            <Empty />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={trends.daily_deposits} margin={{ top: 4, right: 8, left: -12, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={theme.cardBorder} />
                <XAxis
                  dataKey="day"
                  tick={{ fill: theme.textSecondary, fontSize: 12 }}
                  tickFormatter={(v: string) => v.slice(5)}
                  interval="preserveStartEnd"
                />
                <YAxis tick={{ fill: theme.textSecondary, fontSize: 12 }} tickFormatter={(v: number) => `$${v}`} />
                <Tooltip
                  contentStyle={{ background: theme.cardBg, border: `1px solid ${theme.cardBorder}`, borderRadius: 8 }}
                  formatter={(v: number) => [`$${v.toFixed(0)}`, t('reports.deposit_label', getLang())]}
                />
                <Bar dataKey="total" fill={theme.accent} radius={[4, 4, 0, 0]} name={t('reports.deposit_label', getLang())} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Status distribution donut */}
        <div className="card">
          <SectionTitle>{t('reports.status_distribution', getLang())}</SectionTitle>
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
                    <Cell key={index} fill={STATUS_COLORS[entry.status] || theme.textSecondary} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ background: theme.cardBg, border: `1px solid ${theme.cardBorder}`, borderRadius: 8 }}
                />
                <Legend
                  wrapperStyle={{ fontSize: 12, color: theme.textSecondary }}
                  iconSize={8}
                />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Conversion rate card */}
      {stats && (
        <div className="card d-flex gap-16">
          <div>
            <div className="field-label mb-8">
              {t('reports.overall_conversion', getLang())}
            </div>
            <div className="metric-value text-accent">
              {stats.conversion_rate}%
            </div>
            <div className="caption mt-4">
              {stats.by_status['ordered'] || 0} {t('reports.orders_label', getLang())} / {stats.total_clients} {t('dash.total_clients', getLang())}
            </div>
          </div>
          <div>
            <div className="field-label mb-8">
              {t('reports.total_deposit', getLang())}
            </div>
            <div className="metric-value text-accent">
              ${stats.total_deposits.toLocaleString(undefined, { maximumFractionDigits: 0 })}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
