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
import { STATUS_LABELS } from '../types'

const CARD_STYLE: React.CSSProperties = {
  background: '#16213e',
  border: '1px solid #0f3460',
  borderRadius: 8,
  padding: '20px 24px',
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
  return (
    <div style={CARD_STYLE}>
      <div style={{ fontSize: 12, color: '#7f848e', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.8 }}>
        {label}
      </div>
      <div style={{ fontSize: 28, fontWeight: 700, color: accent || '#e0e0e0' }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: '#7f848e', marginTop: 4 }}>{sub}</div>}
    </div>
  )
}

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [funnel, setFunnel] = useState<FunnelStage[]>([])
  const [trends, setTrends] = useState<Trends | null>(null)
  const [activity, setActivity] = useState<Activity[]>([])
  const [loading, setLoading] = useState(true)
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date())

  async function load() {
    try {
      const [s, f, t, a] = await Promise.all([
        api.dashboard(),
        api.funnel(),
        api.trends(),
        api.activity(),
      ])
      setStats(s)
      setFunnel(f)
      setTrends(t)
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

  if (loading) return <Spinner />

  return (
    <div>
      <PageHeader title="仪表盘" sub={`最后更新: ${lastRefresh.toLocaleTimeString('zh')}`} />

      {/* Overview cards */}
      {stats && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
            gap: 16,
            marginBottom: 24,
          }}
        >
          <StatCard label="总客户" value={stats.total_clients} />
          <StatCard label="活跃客户" value={stats.total_active} accent="#00b894" />
          <StatCard label="今日新增" value={stats.today_new} accent="#fdcb6e" />
          <StatCard label="今日下单" value={stats.today_orders} accent="#00b894" />
          <StatCard label="今日存款" value={`$${stats.today_deposits.toFixed(0)}`} accent="#00cec9" />
          <StatCard label="转化率" value={`${stats.conversion_rate}%`} />
          <StatCard label="逾期跟进" value={stats.overdue_followups} accent={stats.overdue_followups > 0 ? '#ff7675' : '#7f848e'} />
          <StatCard label="团队人数" value={stats.total_staff} />
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, marginBottom: 24 }}>
        {/* Funnel chart */}
        <div style={CARD_STYLE}>
          <SectionTitle>漏斗分析</SectionTitle>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={funnel} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#0f3460" />
              <XAxis
                dataKey="stage"
                tick={{ fill: '#7f848e', fontSize: 11 }}
                tickFormatter={(v: string) => STATUS_LABELS[v] || v}
              />
              <YAxis tick={{ fill: '#7f848e', fontSize: 11 }} />
              <Tooltip
                contentStyle={{ background: '#16213e', border: '1px solid #0f3460', borderRadius: 4 }}
                labelFormatter={(v: string) => STATUS_LABELS[v] || v}
              />
              <Bar dataKey="count" fill="#0f3460" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Daily new clients trend */}
        <div style={CARD_STYLE}>
          <SectionTitle>新客户趋势 (30天)</SectionTitle>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart
              data={trends?.daily_new || []}
              margin={{ top: 4, right: 8, left: -20, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#0f3460" />
              <XAxis
                dataKey="day"
                tick={{ fill: '#7f848e', fontSize: 10 }}
                tickFormatter={(v: string) => v.slice(5)}
                interval="preserveStartEnd"
              />
              <YAxis tick={{ fill: '#7f848e', fontSize: 11 }} />
              <Tooltip
                contentStyle={{ background: '#16213e', border: '1px solid #0f3460', borderRadius: 4 }}
              />
              <Line
                type="monotone"
                dataKey="new_clients"
                stroke="#00b894"
                dot={false}
                strokeWidth={2}
                name="新客户"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Activity feed */}
      <div style={CARD_STYLE}>
        <SectionTitle>最近动态</SectionTitle>
        {activity.length === 0 ? (
          <Empty />
        ) : (
          <div>
            {activity.map(a => (
              <div
                key={a.id}
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 12,
                  padding: '10px 0',
                  borderBottom: '1px solid #0f346040',
                }}
              >
                <div
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: '50%',
                    background: '#00b894',
                    marginTop: 5,
                    flexShrink: 0,
                  }}
                />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, color: '#e0e0e0', lineHeight: 1.4 }}>
                    <span style={{ color: '#7f848e' }}>{a.staff_name || '系统'}</span>
                    {' — '}
                    <span style={{ color: '#74b9ff', fontFamily: 'monospace', fontSize: 12 }}>
                      {a.client_phone || '-'}
                    </span>
                    {a.content && (
                      <span
                        style={{
                          marginLeft: 8,
                          color: '#aaa',
                          fontSize: 12,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                          maxWidth: 300,
                          display: 'inline-block',
                          verticalAlign: 'middle',
                        }}
                      >
                        {a.content}
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: 11, color: '#7f848e', marginTop: 2 }}>
                    {a.created_at ? new Date(a.created_at).toLocaleString('zh') : ''}
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

export function PageHeader({ title, sub }: { title: string; sub?: string }) {
  return (
    <div style={{ marginBottom: 24 }}>
      <h1 style={{ fontSize: 22, fontWeight: 700, color: '#e0e0e0' }}>{title}</h1>
      {sub && <div style={{ fontSize: 12, color: '#7f848e', marginTop: 4 }}>{sub}</div>}
    </div>
  )
}

export function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontSize: 13, fontWeight: 600, color: '#7f848e', marginBottom: 16, letterSpacing: 0.5, textTransform: 'uppercase' }}>
      {children}
    </div>
  )
}

export function Spinner() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200, color: '#7f848e' }}>
      加载中...
    </div>
  )
}

export function Empty() {
  return <div style={{ color: '#7f848e', fontSize: 13, padding: '16px 0' }}>暂无数据</div>
}
