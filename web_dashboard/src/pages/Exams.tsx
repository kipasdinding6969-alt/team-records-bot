import { useEffect, useState } from 'react'
import { api, getAuthState } from '../api'
import { getLang, t } from '../i18n'
import { useTheme } from '../ThemeContext'

interface Exam {
  id: number
  exam_name: string
  start_date: string
  end_date: string
  team: string | null
  status: string
}

interface ExamResult {
  rank: number
  display_name: string
  team: string
  powder: number
  reply_rate: number
  registered: number
  training: number
  withdrawals: number
  orders: number
  conversion_rate: number
  kills: number
}

export default function Exams() {
  const { theme } = useTheme()
  const lang = getLang()
  const auth = getAuthState()
  const isAdmin = auth?.role === 'admin' || auth?.role === 'owner'

  const [exams, setExams] = useState<Exam[]>([])
  const [teams, setTeams] = useState<{ key: string; label: string }[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showModal, setShowModal] = useState(false)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [results, setResults] = useState<Record<number, ExamResult[]>>({})
  const [resultsLoading, setResultsLoading] = useState<Record<number, boolean>>({})
  const [showEnded, setShowEnded] = useState(false)
  const [formData, setFormData] = useState({ exam_name: '', start_date: '', end_date: '', team: '' })

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') setShowModal(false) }
    window.addEventListener('keydown', handleEsc)
    return () => window.removeEventListener('keydown', handleEsc)
  }, [])

  const load = () => {
    setLoading(true)
    api.getExams()
      .then(setExams)
      .catch(() => { setError(t('exams.load_failed', lang)); setTimeout(() => setError(''), 3000) })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
    api.allStaff().then(staff => {
      const uniqueTeams = [...new Set(staff.map((s: any) => s.team).filter(Boolean))]
      setTeams(uniqueTeams.map(t => ({ key: t, label: t })))
    }).catch(console.error)
  }, [])

  const toggleExpand = async (examId: number) => {
    if (expandedId === examId) {
      setExpandedId(null)
      return
    }
    setExpandedId(examId)
    if (!results[examId]) {
      setResultsLoading(prev => ({ ...prev, [examId]: true }))
      try {
        const data = await api.examResults(examId)
        setResults(prev => ({ ...prev, [examId]: data.results || data }))
      } catch {
        setError(t('exams.results_failed', lang)); setTimeout(() => setError(''), 3000)
      } finally {
        setResultsLoading(prev => ({ ...prev, [examId]: false }))
      }
    }
  }

  const handleClose = async (examId: number) => {
    try {
      await api.closeExam(examId)
      load()
    } catch {
      setError(t('exams.close_failed', lang)); setTimeout(() => setError(''), 3000)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      await api.createExam({
        exam_name: formData.exam_name,
        start_date: formData.start_date,
        end_date: formData.end_date,
        team: formData.team || undefined,
      })
      setShowModal(false)
      setFormData({ exam_name: '', start_date: '', end_date: '', team: '' })
      load()
    } catch {
      setError(t('exams.create_failed', lang)); setTimeout(() => setError(''), 3000)
    }
  }

  const activeExams = exams.filter(e => e.status === 'active')
  const endedExams = exams.filter(e => e.status !== 'active')

  return (
    <div className="page-container">
      {error && (
        <div className="alert alert-error">{error}</div>
      )}

      <div className="toolbar" style={{ marginBottom: 24 }}>
        <h1 className="page-title">{t('exams.title', lang)}</h1>
        <div className="toolbar-spacer" />
        {isAdmin && (
          <button className="btn-primary" onClick={() => setShowModal(true)}>
            + {t('exams.create', lang)}
          </button>
        )}
      </div>

      {loading ? (
        <div style={{ padding: 20, textAlign: 'center', color: theme.textSecondary }}>{t('common.loading', lang)}</div>
      ) : (
        <>
          {/* Active exams */}
          <h2 className="section-title">{t('exams.active', lang)}</h2>
          {activeExams.length === 0 ? (
            <div className="empty-state" style={{ marginBottom: 20 }}>
              <div className="empty-text">{t('exams.no_active', lang)}</div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 20, marginBottom: 20 }}>
              {activeExams.map(exam => (
                <div className="card" key={exam.id} style={{ border: `2px solid ${theme.accent}55` }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                    <h3 style={{ margin: 0, fontSize: 20, color: theme.accent }}>{exam.exam_name}</h3>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      <span className="badge-success" style={{ fontSize: 12 }}>
                        {t('exams.status_active', lang)}
                      </span>
                      {isAdmin && (
                        <button className="btn-danger" style={{ height: 32, padding: '0 12px', fontSize: 12 }} onClick={() => handleClose(exam.id)}>
                          {t('exams.close', lang)}
                        </button>
                      )}
                    </div>
                  </div>
                  <div style={{ fontSize: 14, color: theme.textSecondary, marginBottom: 12 }}>
                    {exam.start_date} ~ {exam.end_date}
                    {exam.team && <span> | {t('exams.team', lang)}: {exam.team}</span>}
                  </div>
                  <button className="btn-secondary" style={{ height: 32, padding: '0 12px', fontSize: 13 }} onClick={() => toggleExpand(exam.id)}>
                    {expandedId === exam.id ? t('exams.hide_results', lang) : t('exams.view_results', lang)} {expandedId === exam.id ? '\u25B2' : '\u25BC'}
                  </button>

                  {expandedId === exam.id && (
                    <div style={{ marginTop: 20 }}>
                      {resultsLoading[exam.id] ? (
                        <div style={{ padding: 20, textAlign: 'center', color: theme.textSecondary }}>{t('common.loading', lang)}</div>
                      ) : (
                        <div style={{ overflowX: 'auto', borderRadius: 8, border: `1px solid ${theme.cardBorder}` }}>
                          <table className="data-grid-table">
                            <thead>
                              <tr>
                                <th>{t('exams.col_rank', lang)}</th>
                                <th>{t('exams.col_name', lang)}</th>
                                <th>{t('exams.col_team', lang)}</th>
                                <th style={{ textAlign: 'right' }}>{t('exams.col_powder', lang)}</th>
                                <th style={{ textAlign: 'right' }}>{t('exams.col_reply', lang)}</th>
                                <th style={{ textAlign: 'right' }}>{t('exams.col_registered', lang)}</th>
                                <th style={{ textAlign: 'right' }}>{t('exams.col_training', lang)}</th>
                                <th style={{ textAlign: 'right' }}>{t('exams.col_withdrawals', lang)}</th>
                                <th style={{ textAlign: 'right' }}>{t('exams.col_orders', lang)}</th>
                                <th style={{ textAlign: 'right' }}>{t('exams.col_conversion', lang)}</th>
                                <th style={{ textAlign: 'right' }}>{t('exams.col_kills', lang)}</th>
                              </tr>
                            </thead>
                            <tbody>
                              {(results[exam.id] || []).map((r, idx) => (
                                <tr key={idx}>
                                  <td style={{ fontWeight: 700, color: idx === 0 ? '#fbbf24' : idx === 1 ? '#94a3b8' : idx === 2 ? '#b45309' : theme.textPrimary }}>
                                    {r.rank || idx + 1}
                                  </td>
                                  <td style={{ fontWeight: 600, color: theme.textPrimary }}>{r.display_name}</td>
                                  <td style={{ color: theme.textSecondary, fontSize: 12 }}>{r.team || '\u2014'}</td>
                                  <td style={{ textAlign: 'right', fontFamily: 'monospace', color: theme.accent }}>{r.powder}</td>
                                  <td style={{ textAlign: 'right', fontFamily: 'monospace', color: theme.success }}>{r.reply_rate}%</td>
                                  <td style={{ textAlign: 'right', fontFamily: 'monospace', color: theme.accent }}>{r.registered}</td>
                                  <td style={{ textAlign: 'right', fontFamily: 'monospace', color: theme.warning }}>{r.training}</td>
                                  <td style={{ textAlign: 'right', fontFamily: 'monospace' }}>{r.withdrawals}</td>
                                  <td style={{ textAlign: 'right', fontFamily: 'monospace', fontWeight: 700, color: theme.success }}>{r.orders}</td>
                                  <td style={{ textAlign: 'right', fontFamily: 'monospace', color: theme.accent }}>{r.conversion_rate}%</td>
                                  <td style={{ textAlign: 'right', fontFamily: 'monospace', color: theme.danger }}>{r.kills}</td>
                                </tr>
                              ))}
                              {(results[exam.id] || []).length === 0 && (
                                <tr><td colSpan={11} style={{ textAlign: 'center', color: theme.textSecondary, padding: 20 }}>{t('exams.no_results', lang)}</td></tr>
                              )}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Ended exams */}
          <div
            style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', marginBottom: showEnded ? 20 : 0 }}
            onClick={() => setShowEnded(!showEnded)}
          >
            <h2 className="section-title" style={{ margin: 0 }}>{t('exams.ended', lang)}</h2>
            <span style={{ fontSize: 12, color: theme.accent }}>{showEnded ? '\u25B2' : '\u25BC'}</span>
            <span style={{ fontSize: 12, color: theme.textSecondary }}>({endedExams.length})</span>
          </div>

          {showEnded && (
            endedExams.length === 0 ? (
              <div className="empty-state">
                <div className="empty-text">{t('exams.no_ended', lang)}</div>
              </div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 20, marginTop: 12 }}>
                {endedExams.map(exam => (
                  <div className="card" key={exam.id} style={{ opacity: 0.8 }}>
                    <div style={{ fontSize: 16, fontWeight: 600, color: theme.textPrimary, marginBottom: 8 }}>{exam.exam_name}</div>
                    <div style={{ fontSize: 12, color: theme.textSecondary, marginBottom: 8 }}>{exam.start_date} ~ {exam.end_date}</div>
                    {exam.team && <div style={{ fontSize: 12, color: theme.textSecondary }}>{t('exams.team', lang)}: {exam.team}</div>}
                    <button className="btn-secondary" style={{ marginTop: 12, height: 32, padding: '0 12px', fontSize: 13 }} onClick={(e) => { e.stopPropagation(); toggleExpand(exam.id) }}>
                      {expandedId === exam.id ? t('exams.hide_results', lang) : t('exams.view_results', lang)}
                    </button>
                    {expandedId === exam.id && (
                      <div style={{ marginTop: 12, fontSize: 13, color: theme.textSecondary }}>
                        {resultsLoading[exam.id] ? t('common.loading', lang) : (
                          (results[exam.id] || []).length === 0 ? t('exams.no_results', lang) : (
                            <div style={{ overflowX: 'auto' }}>
                              <table className="data-grid-table" style={{ fontSize: 12 }}>
                                <thead>
                                  <tr>
                                    <th>#</th>
                                    <th>{t('exams.col_name', lang)}</th>
                                    <th style={{ textAlign: 'right' }}>{t('exams.col_orders', lang)}</th>
                                    <th style={{ textAlign: 'right' }}>{t('exams.col_kills', lang)}</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {(results[exam.id] || []).slice(0, 5).map((r, idx) => (
                                    <tr key={idx}>
                                      <td style={{ fontWeight: 700, color: idx === 0 ? '#fbbf24' : theme.textPrimary }}>{r.rank || idx + 1}</td>
                                      <td>{r.display_name}</td>
                                      <td style={{ textAlign: 'right', fontFamily: 'monospace' }}>{r.orders}</td>
                                      <td style={{ textAlign: 'right', fontFamily: 'monospace', color: theme.danger }}>{r.kills}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          )
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )
          )}
        </>
      )}

      {/* Create Exam Modal */}
      {showModal && (
        <div className="modal-overlay">
          <div className="modal-content" style={{ width: 480 }}>
            <h3 className="modal-title">{t('exams.create', lang)}</h3>
            <form onSubmit={handleSubmit} className="form-grid">
              <label>
                <span className="field-label">{t('exams.exam_name', lang)}</span>
                <input className="input" required value={formData.exam_name} onChange={e => setFormData({ ...formData, exam_name: e.target.value })} />
              </label>
              <div className="form-grid-2col">
                <label>
                  <span className="field-label">{t('exams.start_date', lang)}</span>
                  <input className="input" type="date" required value={formData.start_date} onChange={e => setFormData({ ...formData, start_date: e.target.value })} />
                </label>
                <label>
                  <span className="field-label">{t('exams.end_date', lang)}</span>
                  <input className="input" type="date" required value={formData.end_date} onChange={e => setFormData({ ...formData, end_date: e.target.value })} />
                </label>
              </div>
              <label>
                <span className="field-label">{t('exams.team_optional', lang)}</span>
                <select className="input" value={formData.team} onChange={e => setFormData({ ...formData, team: e.target.value })}>
                  <option value="">{t('exams.all_teams', lang)}</option>
                  {teams.map(tm => (
                    <option key={tm.key} value={tm.key}>{tm.label}</option>
                  ))}
                </select>
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
