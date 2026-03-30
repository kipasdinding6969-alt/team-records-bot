import { useEffect, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api } from '../api'
import type { Staff } from '../types'
import { Empty, PageHeader, SectionTitle, Spinner } from './Dashboard'

const TEAM_COLORS = ['#00b894', '#0f3460', '#00cec9', '#fdcb6e', '#74b9ff', '#a29bfe', '#fd79a8']

export default function Team() {
  const [staff, setStaff] = useState<Staff[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.staff()
      .then(setStaff)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Spinner />

  const chartData = staff.slice(0, 10).map(s => ({
    name: s.display_name,
    今日新增: s.today_leads,
    今日下单: s.today_orders,
  }))

  return (
    <div>
      <PageHeader title="团队绩效" />

      {/* Leaderboard table */}
      <div
        style={{
          background: '#16213e',
          border: '1px solid #0f3460',
          borderRadius: 8,
          padding: 20,
          marginBottom: 24,
        }}
      >
        <SectionTitle>排行榜</SectionTitle>
        {staff.length === 0 ? (
          <Empty />
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #0f3460' }}>
                {['排名', '姓名', '团队', '职位', 'XP', '连击', '总客户', '总订单', '今日新增', '今日下单'].map(h => (
                  <th
                    key={h}
                    style={{ padding: '8px 12px', textAlign: 'left', color: '#7f848e', fontWeight: 600 }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {staff.map((s, i) => (
                <tr
                  key={s.id}
                  style={{ borderBottom: '1px solid #0f346030' }}
                >
                  <td style={{ padding: '10px 12px', color: i < 3 ? '#fdcb6e' : '#7f848e', fontWeight: i < 3 ? 700 : 400 }}>
                    #{i + 1}
                  </td>
                  <td style={{ padding: '10px 12px', fontWeight: 600 }}>{s.display_name}</td>
                  <td style={{ padding: '10px 12px', color: '#7f848e' }}>{s.team || '-'}</td>
                  <td style={{ padding: '10px 12px', color: '#7f848e', fontSize: 12 }}>{s.role}</td>
                  <td style={{ padding: '10px 12px', color: '#00b894', fontWeight: 600 }}>
                    {s.xp_total.toLocaleString()}
                  </td>
                  <td style={{ padding: '10px 12px' }}>
                    <span style={{ color: s.current_streak > 0 ? '#fdcb6e' : '#7f848e' }}>
                      {s.current_streak > 0 ? `🔥 ${s.current_streak}` : '0'}
                    </span>
                  </td>
                  <td style={{ padding: '10px 12px', color: '#7f848e' }}>{s.total_clients}</td>
                  <td style={{ padding: '10px 12px', color: '#00b894' }}>{s.total_orders}</td>
                  <td style={{ padding: '10px 12px', color: '#fdcb6e' }}>{s.today_leads}</td>
                  <td style={{ padding: '10px 12px', color: '#00b894' }}>{s.today_orders}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Staff performance chart */}
      {chartData.length > 0 && (
        <div
          style={{
            background: '#16213e',
            border: '1px solid #0f3460',
            borderRadius: 8,
            padding: 20,
          }}
        >
          <SectionTitle>今日表现对比</SectionTitle>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={chartData} layout="vertical" margin={{ top: 0, right: 20, left: 40, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#0f3460" />
              <XAxis type="number" tick={{ fill: '#7f848e', fontSize: 11 }} />
              <YAxis type="category" dataKey="name" tick={{ fill: '#e0e0e0', fontSize: 12 }} width={80} />
              <Tooltip
                contentStyle={{ background: '#16213e', border: '1px solid #0f3460', borderRadius: 4 }}
              />
              <Bar dataKey="今日新增" fill="#0f3460" radius={[0, 3, 3, 0]}>
                {chartData.map((_, index) => (
                  <Cell key={index} fill={TEAM_COLORS[index % TEAM_COLORS.length]} />
                ))}
              </Bar>
              <Bar dataKey="今日下单" fill="#00b894" radius={[0, 3, 3, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
