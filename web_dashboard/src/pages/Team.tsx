import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
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
import { useTheme } from '../ThemeContext'
import { StaffDetailModal } from '../components/StaffDetailModal'

const TEAM_COLORS = ['#00b894', '#0f3460', '#00cec9', '#fdcb6e', '#74b9ff', '#a29bfe', '#fd79a8']

export default function Team() {
  const { theme } = useTheme()
  const nav = useNavigate()
  const [staff, setStaff] = useState<Staff[]>([])
  const [loading, setLoading] = useState(true)
  const [teams, setTeams] = useState<any[]>([])
  const [selectedStaffId, setSelectedStaffId] = useState<number | null>(null)

  useEffect(() => {
    Promise.all([
      api.staff(),
      api.orgChart()
    ])
      .then(([staffData, orgData]) => {
        setStaff(staffData)
        // Load performance for each team
        Promise.all(
          orgData.teams.map((t: any) => 
            api.teamPerformance(t.team).then(perf => ({
              ...t,
              performance: perf
            })).catch(() => ({ ...t, performance: null }))
          )
        ).then(setTeams)
      })
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

      {/* Team summaries */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 20, marginBottom: 32 }}>
        {teams.map(t => (
          <div key={t.team} className="glass-card" style={{
            background: theme.cardBg, border: `1px solid ${theme.cardBorder}`,
            borderRadius: 12, padding: 20,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }} onClick={() => nav(`/clients?search=${encodeURIComponent(t.team)}`)}>
                  <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: theme.textPrimary }}>{t.team}</h3>
                  <span style={{ fontSize: 14 }}>↗</span>
                </div>
                <div style={{ fontSize: 13, color: theme.textSecondary, marginTop: 4 }}>
                  <span className="pill-badge" style={{ background: theme.activeNav, color: theme.accent, padding: '2px 8px', borderRadius: 10 }}>
                    {t.member_count + (t.leader ? 1 : 0)} staff
                  </span>
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: 20, fontWeight: 700, color: theme.success }}>
                  ${(t.performance?.total_deposit || 0).toLocaleString()}
                </div>
                <div style={{ fontSize: 11, color: theme.textSecondary, textTransform: 'uppercase' }}>Today's Deposit</div>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
              <div style={{ background: theme.bg, padding: 10, borderRadius: 8, textAlign: 'center' }}>
                <div style={{ fontSize: 16, fontWeight: 600, color: theme.textPrimary }}>{t.performance?.new_leads || 0}</div>
                <div style={{ fontSize: 11, color: theme.textSecondary }}>New Leads</div>
              </div>
              <div style={{ background: theme.bg, padding: 10, borderRadius: 8, textAlign: 'center' }}>
                <div style={{ fontSize: 16, fontWeight: 600, color: theme.textPrimary }}>{t.performance?.new_orders || 0}</div>
                <div style={{ fontSize: 11, color: theme.textSecondary }}>Orders</div>
              </div>
              <div style={{ background: theme.bg, padding: 10, borderRadius: 8, textAlign: 'center' }}>
                <div style={{ fontSize: 16, fontWeight: 600, color: theme.textPrimary }}>{t.performance?.registered || 0}</div>
                <div style={{ fontSize: 11, color: theme.textSecondary }}>Registered</div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Leaderboard table */}
      <div className="glass-card"
        style={{
          background: theme.cardBg,
          border: `1px solid ${theme.cardBorder}`,
          borderRadius: 8,
          padding: 20,
          marginBottom: 24,
        }}
      >
        <SectionTitle>排行榜</SectionTitle>
        {staff.length === 0 ? (
          <Empty />
        ) : (
          <table className="data-grid-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${theme.cardBorder}` }}>
                {['排名', '姓名', '团队', '职位', 'XP', '连击', '总客户', '总订单', '今日新增', '今日下单'].map(h => (
                  <th
                    key={h}
                    style={{ padding: '8px 12px', textAlign: 'left', color: theme.textSecondary, fontWeight: 600 }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {staff.map((s, i) => (
                <tr className="data-grid-row"
                  key={s.id}
                  style={{ borderBottom: `1px solid ${theme.cardBorder}30`, cursor: 'pointer' }}
                  onClick={() => setSelectedStaffId(s.id)}
                >
                  <td style={{ padding: '10px 12px', color: i < 3 ? theme.chartLine : theme.textSecondary, fontWeight: i < 3 ? 700 : 400 }}>
                    #{i + 1}
                  </td>
                  <td style={{ padding: '10px 12px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{
                      width: 24, height: 24, borderRadius: '50%', background: theme.accent, color: '#fff',
                      display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700
                    }}>
                      {s.display_name.charAt(0).toUpperCase()}
                    </div>
                    {s.display_name}
                  </td>
                  <td style={{ padding: '10px 12px', color: theme.textSecondary }}>{s.team || '-'}</td>
                  <td style={{ padding: '10px 12px', color: theme.textSecondary, fontSize: 12 }}>
                    <span className="pill-badge" style={{ background: theme.activeNav, padding: '2px 6px', borderRadius: 4 }}>{s.role}</span>
                  </td>
                  <td style={{ padding: '10px 12px', color: theme.accent, fontWeight: 600 }}>
                    {s.xp_total.toLocaleString()}
                  </td>
                  <td style={{ padding: '10px 12px' }}>
                    <span style={{ color: s.current_streak > 0 ? theme.chartLine : theme.textSecondary }}>
                      {s.current_streak > 0 ? `🔥 ${s.current_streak}` : '0'}
                    </span>
                  </td>
                  <td style={{ padding: '10px 12px', color: theme.textSecondary }}>{s.total_clients}</td>
                  <td style={{ padding: '10px 12px', color: theme.accent }}>{s.total_orders}</td>
                  <td style={{ padding: '10px 12px', color: theme.chartLine }}>{s.today_leads}</td>
                  <td style={{ padding: '10px 12px', color: theme.accent }}>{s.today_orders}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Staff performance chart */}
      {chartData.length > 0 && (
        <div className="glass-card"
          style={{
            background: theme.cardBg,
            border: `1px solid ${theme.cardBorder}`,
            borderRadius: 8,
            padding: 20,
          }}
        >
          <SectionTitle>今日表现对比</SectionTitle>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={chartData} layout="vertical" margin={{ top: 0, right: 20, left: 40, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={theme.cardBorder} />
              <XAxis type="number" tick={{ fill: theme.textSecondary, fontSize: 11 }} />
              <YAxis type="category" dataKey="name" tick={{ fill: theme.textPrimary, fontSize: 12 }} width={80} />
              <Tooltip
                contentStyle={{ background: theme.cardBg, border: `1px solid ${theme.cardBorder}`, borderRadius: 4 }}
              />
              <Bar dataKey="今日新增" fill={theme.cardBorder} radius={[0, 3, 3, 0]}>
                {chartData.map((_, index) => (
                  <Cell key={index} fill={TEAM_COLORS[index % TEAM_COLORS.length]} />
                ))}
              </Bar>
              <Bar dataKey="今日下单" fill={theme.accent} radius={[0, 3, 3, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {selectedStaffId && (
        <StaffDetailModal
          staffId={selectedStaffId}
          onClose={() => setSelectedStaffId(null)}
          onUpdate={() => {
            setLoading(true);
            Promise.all([api.staff(), api.orgChart()]).then(([staffData, orgData]) => {
              setStaff(staffData);
              Promise.all(orgData.teams.map((t: any) => 
                api.teamPerformance(t.team).then(perf => ({ ...t, performance: perf })).catch(() => ({ ...t, performance: null }))
              )).then(setTeams);
            }).finally(() => setLoading(false));
          }}
        />
      )}
    </div>
  )
}
