import { useEffect, useState } from 'react'
import { api, getAuthState } from '../api'
import { getLang, t } from '../i18n'
import { useTheme } from '../ThemeContext'

interface Contest {
  id: number
  title: string
  metric: string
  target: number
  team: string | null
  start_date: string
  end_date: string
  status: string
  winner_name: string | null
}

interface LeaderboardEntry {
  staff_id: number
  display_name: string
  team: string
  score: number
}

export default function Contests() {
  const { theme } = useTheme()
  const [error, setError] = useState('');
  const lang = getLang()
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') setShowModal(false) }
    window.addEventListener('keydown', handleEsc)
    return () => window.removeEventListener('keydown', handleEsc)
  }, [])
  const auth = getAuthState()
  const [contests, setContests] = useState<Contest[]>([])
  const [leaderboards, setLeaderboards] = useState<Record<number, LeaderboardEntry[]>>({})
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [formData, setFormData] = useState({ title: '', metric: 'new_leads', target: 100, team: '', start_date: '', end_date: '' })

  const load = () => {
    setLoading(true)
    api.getContests()
      .then(async (data) => {
        setContests(data)
        const lbs: Record<number, LeaderboardEntry[]> = {}
        for (const c of data) {
          if (c.status === 'active') {
            try {
              lbs[c.id] = await api.contestLeaderboard(c.id)
            } catch {
              lbs[c.id] = []
            }
          }
        }
        setLeaderboards(lbs)
      })
      .catch(() => setError(t('common.error', lang)))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  useEffect(() => { if (error) { const id = setTimeout(() => setError(''), 5000); return () => clearTimeout(id) } }, [error])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      await api.createContest({
        ...formData,
        team: formData.team || undefined,
      })
      setShowModal(false)
      load()
    } catch (err) {
      setError(t('contests.create_failed', lang)); setTimeout(()=>setError(''), 3000)
    }
  }

  const activeContests = contests.filter(c => c.status === 'active')
  const pastContests = contests.filter(c => c.status === 'ended')

  const MetricLabels: Record<string, string> = {
    new_leads: t('targets.leads', lang),
    registered: t('perf.register', lang),
    deposits: t('targets.deposit', lang),
    orders: t('targets.orders', lang),
  }

  return (
    <div className="page-container">
      {error && <div className="alert alert-error">{error}</div>}

      <div className="toolbar mb-24">
        <h1 className="page-title">{t('contests.title', lang)}</h1>
        <div className="toolbar-spacer" />
        {(auth?.role === 'admin' || auth?.role === 'owner') && (
          <button className="btn-primary" onClick={() => setShowModal(true)}>
            + {t('contests.new', lang)}
          </button>
        )}
      </div>

      {loading ? (
        <div className="empty-state">{t('common.loading', lang)}</div>
      ) : (
        <>
          <h2 className="section-title">{t('contests.active', lang)}</h2>
          {activeContests.length === 0 ? (
            <div className="empty-state mb-24">{t('contests.no_active', lang)}</div>
          ) : (
            <div className="grid-auto-360 gap-20 mb-24">
              {activeContests.map(c => {
                const lb = leaderboards[c.id] || []
                const topScore = lb.length > 0 ? lb[0].score : 0
                return (
                  <div key={c.id} className="card">
                    <div className="d-flex justify-between align-center mb-12">
                      <h3 className="heading-sm text-accent">{c.title}</h3>
                      <span className="badge-warning caption">
                        {t('contests.ends', lang)} {c.end_date}
                      </span>
                    </div>
                    <div className="caption mb-20">
                      {t('contests.metric', lang)}: <strong>{MetricLabels[c.metric] || c.metric}</strong> | {t('contests.target', lang)}: <strong>{c.target}</strong>
                      {c.team && <span> | {t('contests.team_optional', lang)}: {c.team}</span>}
                    </div>

                    <table className="data-grid-table">
                      <thead>
                        <tr>
                          <th>#</th>
                          <th>{t('team.name', lang)}</th>
                          <th className="text-right">{t('contests.metric', lang)}</th>
                          <th className="w-120"></th>
                        </tr>
                      </thead>
                      <tbody>
                        {lb.slice(0, 5).map((entry, idx) => (
                          <tr key={entry.staff_id}>
                            <td className={`text-bold rank-${idx < 3 ? idx + 1 : 'default'}`}>{idx + 1}</td>
                            <td className="text-bold">{entry.display_name} <span className="caption">{entry.team}</span></td>
                            <td className="text-right text-bold text-accent">{entry.score}</td>
                            <td>
                              <div className="progress-bar-track">
                                <div className={`progress-bar-fill ${idx === 0 ? 'success' : 'accent'}`} style={{ width: `${Math.min(100, (entry.score / Math.max(c.target, topScore)) * 100)}%` }} />
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {lb.length === 0 && <div className="caption p-12-0">{t('contests.no_data', lang)}</div>}
                  </div>
                )
              })}
            </div>
          )}

          <h2 className="section-title">{t('contests.ended', lang)}</h2>
          {pastContests.length === 0 ? (
             <div className="empty-state">{t('contests.no_past', lang)}</div>
          ) : (
            <div className="grid-auto-260 gap-20">
              {pastContests.map(c => (
                <div key={c.id} className="card opacity-85">
                  <div className="heading-sm mb-8">{c.title}</div>
                  <div className="caption mb-12">{c.start_date} to {c.end_date}</div>
                  <div className="subtitle">
                    {t('contests.winner', lang)}: <strong className="text-warning">{c.winner_name || 'N/A'}</strong>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {showModal && (
        <div className="modal-overlay">
          <div className="modal-content">
            <h3 className="modal-title">{t('contests.new', lang)}</h3>
            <form onSubmit={handleSubmit} className="form-grid">
              <label>
                <span className="field-label">{t('contests.title_label', lang)}</span>
                <input className="input" required value={formData.title} onChange={e => setFormData({...formData, title: e.target.value})} />
              </label>
              <div className="form-grid-2col">
                <label>
                  <span className="field-label">{t('contests.metric', lang)}</span>
                  <select className="input" value={formData.metric} onChange={e => setFormData({...formData, metric: e.target.value})}>
                    <option value="new_leads">{t('targets.leads', lang)}</option>
                    <option value="registered">{t('perf.register', lang)}</option>
                    <option value="orders">{t('targets.orders', lang)}</option>
                    <option value="deposits">{t('targets.deposit', lang)}</option>
                  </select>
                </label>
                <label>
                  <span className="field-label">{t('contests.target', lang)}</span>
                  <input className="input" type="number" required value={formData.target} onChange={e => setFormData({...formData, target: Number(e.target.value)})} />
                </label>
              </div>
              <div className="form-grid-2col">
                <label>
                  <span className="field-label">{t('contests.start_date', lang)}</span>
                  <input className="input" type="date" required value={formData.start_date} onChange={e => setFormData({...formData, start_date: e.target.value})} />
                </label>
                <label>
                  <span className="field-label">{t('contests.end_date', lang)}</span>
                  <input className="input" type="date" required value={formData.end_date} onChange={e => setFormData({...formData, end_date: e.target.value})} />
                </label>
              </div>
              <label>
                <span className="field-label">{t('contests.team_optional', lang)}</span>
                <input className="input" placeholder={t('contests.team_hint', lang)} value={formData.team} onChange={e => setFormData({...formData, team: e.target.value})} />
              </label>
              <div className="modal-actions">
                <button type="button" className="btn-secondary" onClick={() => setShowModal(false)}>{t('common.cancel', lang)}</button>
                <button type="submit" className="btn-primary">{t('common.save', lang)}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
