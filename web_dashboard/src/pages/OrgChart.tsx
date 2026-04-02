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

const ROLE_BADGE: Record<string, string> = {
  admin: 'role-admin',
  manager: 'role-manager',
  leader: 'role-leader',
  maintenance: 'role-maintenance',
  frontdesk: 'role-frontdesk',
  customer_service: 'role-cs',
  newbie: 'role-newbie',
  viewer: 'role-viewer',
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

  if (loading && !data) return <div className="empty-state">{t('common.loading', lang)}</div>
  if (!data) return <div className="empty-state">{t('common.error', lang)}</div>

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
          className="input w-260"
          type="text"
          placeholder={t("org.search_staff", lang)}
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>

      {/* Summary bar */}
      <div className="grid-3col gap-12 mb-20">
        {[
          { label: t('org.total_teams', lang), value: data.teams.length, cls: 'text-accent' },
          { label: t('org.total_staff', lang), value: totalStaff, cls: 'text-success' },
          { label: t('org.active_clients', lang), value: totalClients, cls: 'text-warning' },
        ].map(s => (
          <div key={s.label} className="stat-card">
            <div className={`stat-value ${s.cls}`}>{s.value}</div>
            <div className="stat-label">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Team cards with collapsible nodes */}
      <div className="grid-auto-360 gap-20">
        {filteredTeams.map(team => {
          const isCollapsed = collapsedTeams.has(team.team)
          return (
            <div key={team.team} className="card p-0 overflow-hidden">
              {/* Team header - clickable to collapse */}
              <div
                className="org-team-header cursor-pointer"
                onClick={() => toggleCollapse(team.team)}
              >
                <div className="d-flex align-center gap-8">
                  <span className={`collapse-arrow ${isCollapsed ? 'collapsed' : ''}`}>&#x25BC;</span>
                  <span className="label-sm text-bold">{team.team}</span>
                  <span className="caption">
                    {team.members.length} {t('org.members', lang)}
                  </span>
                </div>
                <div className="d-flex gap-8">
                  <span className="badge-success caption">
                    ${team.total_deposit?.toLocaleString() || 0}
                  </span>
                  <span className="badge-warning caption">
                    {team.total_clients} {t('org.active_clients', lang)}
                  </span>
                </div>
              </div>

              {!isCollapsed && (
                <>
                  {/* Leader */}
                  {team.leader && (
                    <div
                      className="org-leader-row cursor-pointer"
                      onClick={() => setSelectedStaffId(team.leader!.id)}
                    >
                      <div className="avatar-circle avatar-accent">
                        {team.leader.display_name.charAt(0).toUpperCase()}
                      </div>
                      <div className="flex-1">
                        <div className="label-sm text-bold">{team.leader.display_name}</div>
                        <div className="caption">
                          {t('org.leader', lang)} · {team.leader.active_clients} {t('org.active_clients', lang)}
                        </div>
                      </div>
                      <RoleBadge role={team.leader.role} />
                    </div>
                  )}

                  {/* Members */}
                  {team.members.map(m => (
                    <div key={m.id}
                      className="org-member-row cursor-pointer hoverable"
                      onClick={() => setSelectedStaffId(m.id)}
                    >
                      <div className="avatar-circle avatar-muted avatar-sm">
                        {m.display_name.charAt(0).toUpperCase()}
                      </div>
                      <div className="flex-1">
                        <span className="caption text-bold">{m.display_name}</span>
                        {m.tg_username && (
                          <span className="caption text-secondary ml-8">@{m.tg_username}</span>
                        )}
                      </div>
                      {m.daily_target ? (
                         <span className="caption text-success text-bold">T:{m.daily_target}</span>
                      ) : null}
                      <span className="caption cell-mono text-secondary">
                        C:{m.active_clients}
                      </span>
                      <RoleBadge role={m.role} />
                      {m.override_count > 0 && (
                        <span className="badge-danger caption text-bold">
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
        <div className="mt-24">
          <h3 className="section-title">
            {t('org.unassigned', lang)} ({filteredUnassigned.length})
          </h3>
          <div className="card">
            {filteredUnassigned.map(s => (
              <div key={s.id}
                className="org-member-row cursor-pointer hoverable"
                onClick={() => setSelectedStaffId(s.id)}
              >
                <div className="avatar-circle avatar-muted avatar-sm">
                  {s.display_name.charAt(0).toUpperCase()}
                </div>
                <span className="caption text-bold">{s.display_name}</span>
                <RoleBadge role={s.role} />
                <span className="caption ml-auto">
                  {s.active_clients} {t('org.active_clients', lang)}
                </span>
                <select
                  className="input width-auto ml-8"
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
  const cls = ROLE_BADGE[role] || ROLE_BADGE.viewer
  return (
    <span className={`pill-badge ${cls}`}>
      {role}
    </span>
  )
}
