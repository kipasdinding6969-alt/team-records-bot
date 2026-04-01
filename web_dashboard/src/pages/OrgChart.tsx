import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, getRole } from '../api'
import { useTheme } from '../ThemeContext'
import { t, getLang } from '../i18n'
import { StaffDetailModal } from '../components/StaffDetailModal'

interface StaffNode {
  id: number
  display_name: string
  role: string
  team: string
  active_clients: number
  override_count: number
  last_active_at: string | null
  tg_username: string | null
  daily_target?: number
}

interface TeamNode {
  team: string
  leader: StaffNode | null
  members: StaffNode[]
  member_count: number
  total_clients: number
  total_deposit?: number
}

interface OrgData {
  teams: TeamNode[]
  unassigned: StaffNode[]
}

const ROLE_BADGE: Record<string, { bg: string; color: string }> = {
  admin: { bg: '#fee2e2', color: '#dc2626' },
  manager: { bg: '#fef3c7', color: '#d97706' },
  leader: { bg: '#dbeafe', color: '#2563eb' },
  maintenance: { bg: '#d1fae5', color: '#059669' },
  frontdesk: { bg: '#f3f4f6', color: '#4b5563' },
  customer_service: { bg: '#ede9fe', color: '#7c3aed' },
  newbie: { bg: '#fef9c3', color: '#a16207' },
  viewer: { bg: '#f1f5f9', color: '#64748b' },
}

export default function OrgChart() {
  const { theme } = useTheme()
  const lang = getLang()
  const nav = useNavigate()
  const [data, setData] = useState<OrgData | null>(null)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [selectedStaffId, setSelectedStaffId] = useState<number | null>(null)

  const loadData = () => {
    setLoading(true)
    api.orgChart()
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadData()
  }, [])

  if (loading && !data) return <div style={{ padding: 40, color: theme.textSecondary }}>{t('common.loading', lang)}</div>
  if (!data) return <div style={{ padding: 40, color: theme.textSecondary }}>{t('common.error', lang)}</div>

  const totalStaff = data.teams.reduce((s, t) => s + t.member_count + (t.leader ? 1 : 0), 0) + data.unassigned.length
  const totalClients = data.teams.reduce((s, t) => s + t.total_clients, 0)

  const filterStaff = (staffList: StaffNode[]) => {
    if (!search) return staffList
    const lower = search.toLowerCase()
    return staffList.filter(s => 
      s.display_name.toLowerCase().includes(lower) || 
      (s.tg_username && s.tg_username.toLowerCase().includes(lower))
    )
  }

  const filteredTeams = data.teams.map(t => ({
    ...t,
    leader: t.leader && filterStaff([t.leader]).length > 0 ? t.leader : null,
    members: filterStaff(t.members)
  })).filter(t => t.leader || t.members.length > 0 || t.team.toLowerCase().includes(search.toLowerCase()))

  const filteredUnassigned = filterStaff(data.unassigned)

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2 style={{ fontSize: 18, fontWeight: 700, margin: 0 }}>{t('org.title', lang)}</h2>
        <input 
          type="text" 
          placeholder="Search staff..." 
          value={search} 
          onChange={e => setSearch(e.target.value)}
          style={{
            padding: '8px 16px', borderRadius: 8, border: `1px solid ${theme.inputBorder}`,
            background: theme.inputBg, color: theme.textPrimary, outline: 'none', width: 240,
            boxShadow: theme.shadow
          }}
        />
      </div>

      {/* Summary bar */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 24, flexWrap: 'wrap' }}>
        {[
          { label: t('org.total_teams', lang), value: data.teams.length, color: '#3b82f6' },
          { label: t('org.total_staff', lang), value: totalStaff, color: '#22c55e' },
          { label: t('org.active_clients', lang), value: totalClients, color: '#f59e0b' },
        ].map(s => (
          <div key={s.label} className="glass-card" style={{
            background: theme.cardBg, border: `1px solid ${theme.cardBorder}`,
            borderRadius: 10, padding: '14px 24px', minWidth: 140,
          }}>
            <div style={{ fontSize: 24, fontWeight: 700, color: s.color }}>{s.value}</div>
            <div style={{ fontSize: 12, color: theme.textSecondary, marginTop: 2 }}>{s.label}</div>
          </div>
        ))}
      </div>

      {/* Team cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: 20 }}>
        {filteredTeams.map(team => (
          <div key={team.team} className="glass-card" style={{
            background: theme.cardBg, border: `1px solid ${theme.cardBorder}`,
            borderRadius: 12, overflow: 'hidden',
          }}>
            {/* Team header */}
            <div style={{
              padding: '14px 18px', borderBottom: `1px solid ${theme.cardBorder}`,
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            }}>
              <div>
                <span style={{ fontSize: 15, fontWeight: 700 }}>{team.team}</span>
                <span style={{ fontSize: 11, color: theme.textSecondary, marginLeft: 8 }}>
                  {team.members.length} {t('org.members', lang)}
                </span>
              </div>
              <div style={{ display: 'flex', gap: 6 }}>
                <span className="pill-badge" style={{
                  fontSize: 11, fontWeight: 600, color: '#059669',
                  background: '#d1fae5', padding: '2px 8px', borderRadius: 10,
                }}>
                  ${team.total_deposit?.toLocaleString() || 0}
                </span>
                <span className="pill-badge" style={{
                  fontSize: 11, fontWeight: 600, color: '#f59e0b',
                  background: '#fef3c7', padding: '2px 8px', borderRadius: 10,
                }}>
                  {team.total_clients} clients
                </span>
                <span className="pill-badge" style={{
                  fontSize: 11, fontWeight: 600, color: '#2563eb',
                  background: '#dbeafe', padding: '2px 8px', borderRadius: 10,
                }}>
                  Avg Tgt: {team.members.length > 0 ? Math.round(team.members.reduce((s, m) => s + (m.daily_target || 0), 0) / team.members.length) : 0}
                </span>
              </div>
            </div>

            {/* Leader */}
            {team.leader && (
              <div style={{
                padding: '12px 18px', borderBottom: `1px solid ${theme.cardBorder}`,
                display: 'flex', alignItems: 'center', gap: 10,
                background: `${theme.activeNav}`,
                cursor: 'pointer', transition: 'background 0.2s',
              }}
              onClick={() => setSelectedStaffId(team.leader!.id)}
              >
                <div style={{
                  width: 32, height: 32, borderRadius: '50%', background: '#3b82f6', color: '#fff',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 14
                }}>
                  {team.leader.display_name.charAt(0).toUpperCase()}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, fontSize: 13 }}>{team.leader.display_name} 👑</div>
                  <div style={{ fontSize: 11, color: theme.textSecondary }}>
                    {t('org.leader', lang)} · {team.leader.active_clients} {t('org.active_clients', lang)}
                  </div>
                </div>
                <RoleBadge role={team.leader.role} />
              </div>
            )}

            {/* Members */}
            {team.members.map(m => (
              <div key={m.id} style={{
                padding: '10px 18px', borderBottom: `1px solid ${theme.cardBorder}15`,
                display: 'flex', alignItems: 'center', gap: 10,
                cursor: 'pointer', transition: 'background 0.1s',
              }}
              onClick={() => setSelectedStaffId(m.id)}
              onMouseEnter={e => (e.currentTarget.style.background = theme.activeNav)}
              onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
              >
                <div style={{
                  width: 24, height: 24, borderRadius: '50%', background: theme.inputBorder, color: theme.textSecondary,
                  display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 600, fontSize: 11
                }}>
                  {m.display_name.charAt(0).toUpperCase()}
                </div>
                <div style={{ flex: 1 }}>
                  <span style={{ fontSize: 13 }}>{m.display_name}</span>
                  {m.tg_username && (
                    <span style={{ fontSize: 11, color: theme.textSecondary, marginLeft: 6 }}>@{m.tg_username}</span>
                  )}
                </div>
                {m.daily_target ? (
                   <span style={{ fontSize: 11, color: theme.success, fontWeight: 600 }}>T:{m.daily_target}</span>
                ) : null}
                <span style={{ fontSize: 11, color: theme.textSecondary, fontFamily: 'monospace', marginLeft: 4 }}>
                  C:{m.active_clients}
                </span>
                <RoleBadge role={m.role} />
                {m.override_count > 0 && (
                  <span className="pill-badge" style={{
                    fontSize: 10, background: '#fee2e2', color: '#dc2626',
                    padding: '1px 5px', borderRadius: 8, fontWeight: 600,
                  }}>
                    {m.override_count}
                  </span>
                )}
              </div>
            ))}
          </div>
        ))}
      </div>

      {/* Unassigned */}
      {filteredUnassigned.length > 0 && (
        <div style={{ marginTop: 24 }}>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: theme.textSecondary, marginBottom: 10 }}>
            {t('org.unassigned', lang)} ({filteredUnassigned.length})
          </h3>
          <div className="glass-card" style={{
            background: theme.cardBg, border: `1px solid ${theme.cardBorder}`,
            borderRadius: 8, padding: 4,
          }}>
            {filteredUnassigned.map(s => (
              <div key={s.id} style={{
                padding: '8px 14px', display: 'flex', alignItems: 'center', gap: 10,
                borderBottom: `1px solid ${theme.cardBorder}15`, cursor: 'pointer'
              }} onClick={() => setSelectedStaffId(s.id)}
              onMouseEnter={e => (e.currentTarget.style.background = theme.activeNav)}
              onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
              >
                <div style={{
                  width: 24, height: 24, borderRadius: '50%', background: theme.inputBorder, color: theme.textSecondary,
                  display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 600, fontSize: 11
                }}>
                  {s.display_name.charAt(0).toUpperCase()}
                </div>
                <span style={{ fontSize: 13 }}>{s.display_name}</span>
                <RoleBadge role={s.role} />
                <span style={{ fontSize: 11, color: theme.textSecondary, marginLeft: 'auto' }}>
                  {s.active_clients} clients
                </span>
                <select 
                  style={{
                    padding: '2px 6px', fontSize: 11, borderRadius: 4, marginLeft: 8,
                    border: `1px solid ${theme.inputBorder}`, background: theme.inputBg, color: theme.textPrimary, outline: 'none'
                  }}
                  value=""
                  onClick={e => e.stopPropagation()}
                  onChange={e => {
                    if (e.target.value) {
                      api.updateStaff(s.id, { team: e.target.value }).then(loadData).catch(console.error)
                    }
                  }}
                >
                  <option value="" disabled>{t('org.assign_team', lang)}</option>
                  {data.teams.map(t => <option key={t.team} value={t.team}>{t.team}</option>)}
                </select>
              </div>
            ))}
          </div>
        </div>
      )}

      {selectedStaffId && (
        <StaffDetailModal 
          staffId={selectedStaffId} 
          onClose={() => setSelectedStaffId(null)} 
          onUpdate={loadData}
        />
      )}
    </div>
  )
}

function RoleBadge({ role }: { role: string }) {
  const style = ROLE_BADGE[role] || ROLE_BADGE.viewer
  return (
    <span className="pill-badge" style={{
      fontSize: 10, fontWeight: 600, padding: '1px 6px', borderRadius: 4,
      background: style.bg, color: style.color, textTransform: 'uppercase',
    }}>
      {role}
    </span>
  )
}
