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
  admin: { bg: 'rgba(248,113,113,0.15)', color: '#f87171' },
  manager: { bg: 'rgba(251,191,36,0.15)', color: '#fbbf24' },
  leader: { bg: 'rgba(45,212,191,0.15)', color: '#2dd4bf' },
  maintenance: { bg: 'rgba(52,211,153,0.15)', color: '#34d399' },
  frontdesk: { bg: 'rgba(127,132,142,0.15)', color: '#7f848e' },
  customer_service: { bg: 'rgba(13,148,136,0.15)', color: '#0d9488' },
  newbie: { bg: 'rgba(251,191,36,0.15)', color: '#fbbf24' },
  viewer: { bg: 'rgba(127,132,142,0.15)', color: '#7f848e' },
}

export default function OrgChart() {
  const { theme } = useTheme()
  const lang = getLang()
  const nav = useNavigate()
  const [data, setData] = useState<OrgData | null>(null)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [selectedStaffId, setSelectedStaffId] = useState<number | null>(null)
  const [collapsedTeams, setCollapsedTeams] = useState<Set<string>>(new Set())

  const toggleCollapse = (team: string) => {
    setCollapsedTeams(prev => {
      const next = new Set(prev)
      if (next.has(team)) next.delete(team)
      else next.add(team)
      return next
    })
  }

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

  if (loading && !data) return <div style={{ padding: 32, color: theme.textSecondary }}>{t('common.loading', lang)}</div>
  if (!data) return <div style={{ padding: 32, color: theme.textSecondary }}>{t('common.error', lang)}</div>

  const totalStaff = data.teams.reduce((sum, tm) => sum + tm.member_count + (tm.leader ? 1 : 0), 0) + data.unassigned.length
  const totalClients = data.teams.reduce((sum, tm) => sum + tm.total_clients, 0)

  const filterStaff = (staffList: StaffNode[]) => {
    if (!search) return staffList
    const lower = search.toLowerCase()
    return staffList.filter(s =>
      s.display_name.toLowerCase().includes(lower) ||
      (s.tg_username && s.tg_username.toLowerCase().includes(lower))
    )
  }

  const filteredTeams = data.teams.map(tm => ({
    ...tm,
    leader: tm.leader && filterStaff([tm.leader]).length > 0 ? tm.leader : null,
    members: filterStaff(tm.members)
  })).filter(t => t.leader || t.members.length > 0 || t.team.toLowerCase().includes(search.toLowerCase()))

  const filteredUnassigned = filterStaff(data.unassigned)

  return (
    <div className="page-container">
      <div className="toolbar">
        <h1 className="page-title">{t('org.title', lang)}</h1>
        <div className="toolbar-spacer" />
        <input
          className="input"
          type="text"
          placeholder={t("org.search_staff", lang)}
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ width: 260 }}
        />
      </div>

      {/* Summary bar */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 20 }}>
        {[
          { label: t('org.total_teams', lang), value: data.teams.length, color: theme.accent },
          { label: t('org.total_staff', lang), value: totalStaff, color: theme.success },
          { label: t('org.active_clients', lang), value: totalClients, color: theme.warning },
        ].map(s => (
          <div key={s.label} className="stat-card">
            <div className="stat-value" style={{ color: s.color }}>{s.value}</div>
            <div className="stat-label">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Team cards with collapsible nodes */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: 20 }}>
        {filteredTeams.map(team => {
          const isCollapsed = collapsedTeams.has(team.team)
          return (
            <div key={team.team} className="card" style={{ padding: 0, overflow: 'hidden' }}>
              {/* Team header - clickable to collapse */}
              <div
                style={{
                  padding: '12px 20px', borderBottom: `1px solid ${theme.cardBorder}`,
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  cursor: 'pointer',
                }}
                onClick={() => toggleCollapse(team.team)}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontSize: 13, color: theme.textSecondary, transition: 'transform 0.2s', display: 'inline-block', transform: isCollapsed ? 'rotate(-90deg)' : 'rotate(0deg)' }}>&#x25BC;</span>
                  <span style={{ fontSize: 14, fontWeight: 700, color: theme.textPrimary }}>{team.team}</span>
                  <span style={{ fontSize: 12, color: theme.textSecondary }}>
                    {team.members.length} {t('org.members', lang)}
                  </span>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <span className="badge-success" style={{ fontSize: 12 }}>
                    ${team.total_deposit?.toLocaleString() || 0}
                  </span>
                  <span className="badge-warning" style={{ fontSize: 12 }}>
                    {team.total_clients} {t('org.active_clients', lang)}
                  </span>
                </div>
              </div>

              {!isCollapsed && (
                <>
                  {/* Leader */}
                  {team.leader && (
                    <div
                      style={{
                        padding: '8px 20px', borderBottom: `1px solid ${theme.cardBorder}`,
                        display: 'flex', alignItems: 'center', gap: 8,
                        background: theme.activeNav,
                        cursor: 'pointer',
                      }}
                      onClick={() => setSelectedStaffId(team.leader!.id)}
                    >
                      <div style={{
                        width: 32, height: 32, borderRadius: '50%', background: theme.accent, color: '#fff',
                        display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 14
                      }}>
                        {team.leader.display_name.charAt(0).toUpperCase()}
                      </div>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontWeight: 600, fontSize: 13 }}>{team.leader.display_name}</div>
                        <div style={{ fontSize: 12, color: theme.textSecondary }}>
                          {t('org.leader', lang)} · {team.leader.active_clients} {t('org.active_clients', lang)}
                        </div>
                      </div>
                      <RoleBadge role={team.leader.role} />
                    </div>
                  )}

                  {/* Members */}
                  {team.members.map(m => (
                    <div key={m.id} style={{
                      padding: '8px 20px', borderBottom: `1px solid ${theme.cardBorder}15`,
                      display: 'flex', alignItems: 'center', gap: 8,
                      cursor: 'pointer', transition: 'background 0.1s',
                    }}
                    onClick={() => setSelectedStaffId(m.id)}
                    onMouseEnter={e => (e.currentTarget.style.background = theme.activeNav)}
                    onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                    >
                      <div style={{
                        width: 24, height: 24, borderRadius: 12, background: theme.inputBorder, color: theme.textSecondary,
                        display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 600, fontSize: 12
                      }}>
                        {m.display_name.charAt(0).toUpperCase()}
                      </div>
                      <div style={{ flex: 1 }}>
                        <span style={{ fontSize: 13 }}>{m.display_name}</span>
                        {m.tg_username && (
                          <span style={{ fontSize: 12, color: theme.textSecondary, marginLeft: 8 }}>@{m.tg_username}</span>
                        )}
                      </div>
                      {m.daily_target ? (
                         <span style={{ fontSize: 12, color: theme.success, fontWeight: 600 }}>T:{m.daily_target}</span>
                      ) : null}
                      <span style={{ fontSize: 12, color: theme.textSecondary, fontFamily: 'monospace' }}>
                        C:{m.active_clients}
                      </span>
                      <RoleBadge role={m.role} />
                      {m.override_count > 0 && (
                        <span className="badge-danger" style={{ fontSize: 12, fontWeight: 600 }}>
                          {m.override_count}
                        </span>
                      )}
                    </div>
                  ))}
                </>
              )}
            </div>
          )
        })}
      </div>

      {/* Unassigned */}
      {filteredUnassigned.length > 0 && (
        <div style={{ marginTop: 24 }}>
          <h3 className="section-title">
            {t('org.unassigned', lang)} ({filteredUnassigned.length})
          </h3>
          <div className="card">
            {filteredUnassigned.map(s => (
              <div key={s.id} style={{
                padding: '8px 0', display: 'flex', alignItems: 'center', gap: 8,
                borderBottom: `1px solid ${theme.cardBorder}15`, cursor: 'pointer'
              }} onClick={() => setSelectedStaffId(s.id)}
              onMouseEnter={e => (e.currentTarget.style.background = theme.activeNav)}
              onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
              >
                <div style={{
                  width: 24, height: 24, borderRadius: '50%', background: theme.inputBorder, color: theme.textSecondary,
                  display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 600, fontSize: 12
                }}>
                  {s.display_name.charAt(0).toUpperCase()}
                </div>
                <span style={{ fontSize: 13 }}>{s.display_name}</span>
                <RoleBadge role={s.role} />
                <span style={{ fontSize: 12, color: theme.textSecondary, marginLeft: 'auto' }}>
                  {s.active_clients} {t('org.active_clients', lang)}
                </span>
                <select
                  className="input"
                  style={{ width: 'auto', marginLeft: 8 }}
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
      fontSize: 12, fontWeight: 600, padding: '2px 8px', borderRadius: 12,
      background: style.bg, color: style.color, textTransform: 'uppercase',
    }}>
      {role}
    </span>
  )
}
