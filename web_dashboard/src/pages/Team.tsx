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
import { api, getAuthState } from '../api'
import type { Staff } from '../types'
import { Empty, PageHeader, SectionTitle, Spinner } from '../components/SharedUI'
import { useTheme } from '../ThemeContext'
import { t, getLang } from '../i18n'
import { StaffDetailModal } from '../components/StaffDetailModal'

const TEAM_COLORS = ['#00b894', '#0f3460', '#00cec9', '#fdcb6e', '#74b9ff', '#7f848e', '#fd79a8']

export default function Team() {
  const { theme } = useTheme()
  const [error, setError] = useState('');
  const nav = useNavigate()
  const lang = getLang()
  const [staff, setStaff] = useState<Staff[]>([])
  const [loading, setLoading] = useState(true)
  const [teams, setTeams] = useState<any[]>([])
  const [selectedStaffId, setSelectedStaffId] = useState<number | null>(null)

  const [targets, setTargets] = useState<any[]>([])
  const [showTargetModal, setShowTargetModal] = useState(false)
  const [targetForm, setTargetForm] = useState({ team: '', period_type: 'monthly', period_start: '', period_end: '', target_leads: '', target_orders: '', target_deposit: '' })
  const auth = getAuthState()
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') setShowTargetModal(false) }
    window.addEventListener('keydown', handleEsc)
    return () => window.removeEventListener('keydown', handleEsc)
  }, [])

  const load = () => {
    setLoading(true)
    Promise.all([
      api.staff(),
      api.orgChart(),
      api.getTargets()
    ])
      .then(([staffData, orgData, targetsData]) => {
        setStaff(staffData)
        setTargets(targetsData)
        Promise.all(
          orgData.teams.map((teamNode: any) =>
            api.teamPerformance(teamNode.team).then(perf => ({
              ...teamNode,
              performance: perf
            })).catch(() => ({ ...teamNode, performance: null }))
          )
        ).then(setTeams)
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
  }, [])

  const handleTargetSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      await api.setTarget({
        ...targetForm,
        target_leads: Number(targetForm.target_leads) || undefined,
        target_orders: Number(targetForm.target_orders) || undefined,
        target_deposit: Number(targetForm.target_deposit) || undefined,
      })
      setShowTargetModal(false)
      load()
    } catch (e) {
      console.error(e)
      setError(t('common.update_failed', lang)); setTimeout(()=>setError(''), 3000)
    }
  }

  const getBarColor = (pct: number) => pct >= 80 ? theme.success : pct >= 50 ? theme.warning : theme.danger

  if (loading) return <Spinner />

  const chartData = staff.slice(0, 10).map(s => ({
    name: s.display_name,
    [t('team.today_leads', lang)]: s.today_leads,
    [t('team.today_orders', lang)]: s.today_orders,
  }))

  return (
    <div className="page-container">
      <PageHeader title={t('team.title', lang)} />

      {error && <div className="alert alert-error">{error}</div>}

      {/* Targets Section */}
      <div className="toolbar" style={{ marginTop: 24 }}>
        <h2 className="section-title" style={{ margin: 0 }}>{t('targets.title', lang)}</h2>
        <div className="toolbar-spacer" />
        {(auth?.role === 'admin' || auth?.role === 'owner') && (
          <button className="btn-primary" onClick={() => setShowTargetModal(true)}>
            + {t('targets.set', lang)}
          </button>
        )}
      </div>

      {targets.length > 0 ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 20, marginBottom: 20 }}>
          {targets.map(targetItem => {
            const teamPerf = teams.find(tm => tm.team === targetItem.team)?.performance || {}

            const leadsActual = teamPerf.new_leads || 0
            const ordersActual = teamPerf.new_orders || 0
            const depActual = teamPerf.total_deposit || 0

            const leadsPct = Math.min(100, (leadsActual / (targetItem.target_leads || 1)) * 100) || 0
            const ordersPct = Math.min(100, (ordersActual / (targetItem.target_orders || 1)) * 100) || 0
            const depPct = Math.min(100, (depActual / (targetItem.target_deposit || 1)) * 100) || 0

            const bar = (label: string, actual: number, targetValue: number | null, pct: number, prefix='') => {
              if (!targetValue) return null
              return (
                <div key={label} style={{ marginBottom: 12 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4, fontWeight: 600, color: theme.textSecondary }}>
                    <span>{label}</span>
                    <span>{prefix}{actual} / {prefix}{targetValue} ({pct.toFixed(0)}%)</span>
                  </div>
                  <div style={{ height: 8, background: theme.bg, borderRadius: 4, overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${pct}%`, background: getBarColor(pct), borderRadius: 4 }} />
                  </div>
                </div>
              )
            }

            return (
              <div key={targetItem.id} className="card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <h3 style={{ margin: 0, fontSize: 16, color: theme.textPrimary }}>{targetItem.team === 'all' ? t('common.all', lang) : targetItem.team}</h3>
                  <span className="pill-badge badge-info">{targetItem.period_type}</span>
                </div>
                <div style={{ fontSize: 12, color: theme.textSecondary, marginBottom: 12 }}>{targetItem.period_start} ~ {targetItem.period_end}</div>
                {bar(t('targets.leads', lang), leadsActual, targetItem.target_leads, leadsPct)}
                {bar(t('targets.orders', lang), ordersActual, targetItem.target_orders, ordersPct)}
                {bar(t('team.today_deposit', lang), depActual, targetItem.target_deposit, depPct, '$')}
              </div>
            )
          })}
        </div>
      ) : (
        <div className="empty-state" style={{ marginBottom: 20 }}>{t('common.no_data', lang)}</div>
      )}

      {/* Team summaries */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 20, marginBottom: 20 }}>
        {teams.map(teamInfo => (
          <div key={teamInfo.team} className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }} onClick={() => nav(`/clients?search=${encodeURIComponent(teamInfo.team)}`)}>
                  <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: theme.textPrimary }}>{teamInfo.team}</h3>
                  <span style={{ fontSize: 14, color: theme.textSecondary }}>&#x2197;</span>
                </div>
                <div style={{ fontSize: 13, color: theme.textSecondary, marginTop: 4 }}>
                  <span className="pill-badge" style={{ background: theme.activeNav, color: theme.accent }}>
                    {teamInfo.member_count + (teamInfo.leader ? 1 : 0)} {t('org.members', lang)}
                  </span>
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: 20, fontWeight: 700, color: theme.success }}>
                  ${(teamInfo.performance?.total_deposit || 0).toLocaleString()}
                </div>
                <div style={{ fontSize: 12, color: theme.textSecondary, textTransform: 'uppercase' }}>{t('team.todays_deposit', lang)}</div>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
              <div className="metric-card">
                <div className="metric-value" style={{ fontSize: 16, color: theme.textPrimary }}>{teamInfo.performance?.new_leads || 0}</div>
                <div className="metric-label">{t('team.new_leads', lang)}</div>
              </div>
              <div className="metric-card">
                <div className="metric-value" style={{ fontSize: 16, color: theme.textPrimary }}>{teamInfo.performance?.new_orders || 0}</div>
                <div className="metric-label">{t('team.orders', lang)}</div>
              </div>
              <div className="metric-card">
                <div className="metric-value" style={{ fontSize: 16, color: theme.textPrimary }}>{teamInfo.performance?.registered || 0}</div>
                <div className="metric-label">{t('team.registered', lang)}</div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Leaderboard table */}
      <div className="card" style={{ marginBottom: 20 }}>
        <SectionTitle>{t('team.leaderboard', lang)}</SectionTitle>
        {staff.length === 0 ? (
          <Empty />
        ) : (
          <table className="data-grid-table">
            <thead>
              <tr>
                {[t('lb_rank', lang), t('team.name', lang), t('team.team', lang), t('team.role', lang), t('team.xp', lang), t('team.streak', lang), t('team.clients', lang), t('team.orders', lang), t('team.today_leads', lang), t('team.today_orders', lang)].map(h => (
                  <th key={h}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {staff.map((s, i) => (
                <tr
                  key={s.id}
                  style={{ cursor: 'pointer' }}
                  onClick={() => setSelectedStaffId(s.id)}
                >
                  <td style={{ color: i < 3 ? theme.chartLine : theme.textSecondary, fontWeight: i < 3 ? 700 : 400 }}>
                    #{i + 1}
                  </td>
                  <td style={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{
                      width: 24, height: 24, borderRadius: '50%', background: theme.accent, color: '#fff',
                      display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 700
                    }}>
                      {s.display_name.charAt(0).toUpperCase()}
                    </div>
                    {s.display_name}
                  </td>
                  <td style={{ color: theme.textSecondary }}>{s.team || '-'}</td>
                  <td>
                    <span className="pill-badge" style={{ background: theme.accentLight, fontSize: 12 }}>{s.role}</span>
                  </td>
                  <td style={{ color: theme.accent, fontWeight: 600 }}>
                    {s.xp_total.toLocaleString()}
                  </td>
                  <td>
                    <span style={{ color: s.current_streak > 0 ? theme.chartLine : theme.textSecondary }}>
                      {s.current_streak > 0 ? `${s.current_streak}d` : '0'}
                    </span>
                  </td>
                  <td style={{ color: theme.textSecondary }}>{s.total_clients}</td>
                  <td style={{ color: theme.accent }}>{s.total_orders}</td>
                  <td style={{ color: theme.chartLine }}>{s.today_leads}</td>
                  <td style={{ color: theme.accent }}>{s.today_orders}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Staff performance chart */}
      {chartData.length > 0 && (
        <div className="card" style={{ marginBottom: 20 }}>
          <SectionTitle>{t('team.today_comparison', lang)}</SectionTitle>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={chartData} layout="vertical" margin={{ top: 0, right: 20, left: 40, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={theme.cardBorder} />
              <XAxis type="number" tick={{ fill: theme.textSecondary, fontSize: 12 }} />
              <YAxis type="category" dataKey="name" tick={{ fill: theme.textPrimary, fontSize: 12 }} width={80} />
              <Tooltip
                contentStyle={{ background: theme.cardBg, border: `1px solid ${theme.cardBorder}`, borderRadius: 8 }}
              />
              <Bar dataKey={t('team.today_leads', lang)} fill={theme.cardBorder} radius={[0, 4, 4, 0]}>
                {chartData.map((_, index) => (
                  <Cell key={index} fill={TEAM_COLORS[index % TEAM_COLORS.length]} />
                ))}
              </Bar>
              <Bar dataKey={t('team.today_orders', lang)} fill={theme.accent} radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {selectedStaffId && (
        <StaffDetailModal
          staffId={selectedStaffId}
          onClose={() => setSelectedStaffId(null)}
          onUpdate={load}
        />
      )}

      {/* Target Modal */}
      {showTargetModal && (
        <div className="modal-overlay">
          <div className="modal-content">
            <h3 className="modal-title">{t('targets.set', lang)}</h3>
            <form onSubmit={handleTargetSubmit} className="form-grid" style={{ gap: 12 }}>
              <label>
                <span className="field-label">{t('nav.team', lang)}</span>
                <input className="input" required placeholder={t('targets.team_hint', lang)} value={targetForm.team} onChange={e => setTargetForm({...targetForm, team: e.target.value})} />
              </label>
              <div className="form-grid-2col">
                <label>
                  <span className="field-label">{t('team.role', lang)}</span>
                  <select className="input" value={targetForm.period_type} onChange={e => setTargetForm({...targetForm, period_type: e.target.value})}>
                    <option value="weekly">{t('reports.weekly', lang)}</option>
                    <option value="monthly">{t('reports.monthly', lang)}</option>
                    <option value="quarterly">{t('reports.quarterly', lang)}</option>
                  </select>
                </label>
                <label>
                  <span className="field-label">{t('perf.date_from', lang)}</span>
                  <input className="input" type="date" required value={targetForm.period_start} onChange={e => setTargetForm({...targetForm, period_start: e.target.value})} />
                </label>
              </div>
              <label>
                <span className="field-label">{t('perf.date_to', lang)}</span>
                <input className="input" type="date" required value={targetForm.period_end} onChange={e => setTargetForm({...targetForm, period_end: e.target.value})} />
              </label>
              <div style={{ display: 'flex', gap: 12 }}>
                <label style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <span style={{ fontSize: 13, color: theme.textSecondary }}>{t('targets.leads', lang)}</span>
                  <input className="input" type="number" value={targetForm.target_leads} onChange={e => setTargetForm({...targetForm, target_leads: e.target.value})} />
                </label>
                <label style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <span style={{ fontSize: 13, color: theme.textSecondary }}>{t('targets.orders', lang)}</span>
                  <input className="input" type="number" value={targetForm.target_orders} onChange={e => setTargetForm({...targetForm, target_orders: e.target.value})} />
                </label>
                <label style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <span style={{ fontSize: 13, color: theme.textSecondary }}>{t('targets.deposit', lang)}</span>
                  <input className="input" type="number" value={targetForm.target_deposit} onChange={e => setTargetForm({...targetForm, target_deposit: e.target.value})} />
                </label>
              </div>
              <div className="modal-actions">
                <button type="button" className="btn-secondary" onClick={() => setShowTargetModal(false)}>{t('common.cancel', lang)}</button>
                <button type="submit" className="btn-primary">{t('common.save', lang)}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
