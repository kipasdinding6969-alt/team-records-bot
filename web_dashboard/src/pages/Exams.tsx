import { useEffect, useState } from 'react'
import { api, getAuthState } from '../api'
import { getLang, t } from '../i18n'
import { useTheme } from '../ThemeContext'
import type { Exam, ExamResultRow } from '../types'

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
  const [results, setResults] = useState<Record<number, ExamResultRow[]>>({})
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
    }).catch(() => { setError(t('common.error', lang)); setTimeout(() => setError(''), 3000) })
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

      <div className="toolbar mb-24">
        <h1 className="page-title">{t('exams.title', lang)}</h1>
        <div className="toolbar-spacer" />
        {isAdmin && (
          <button className="btn-primary" onClick={() => setShowModal(true)}>
            + {t('exams.create', lang)}
          </button>
        )}
      </div>

      {loading ? (
        <div className="empty-state text-center">{t('common.loading', lang)}</div>
      ) : (
        <>
          {/* Active exams */}
          <h2 className="section-title">{t('exams.active', lang)}</h2>
          {activeExams.length === 0 ? (
            <div className="empty-state mb-20">
              <div className="empty-text">{t('exams.no_active', lang)}</div>
            </div>
          ) : (
            <div className="d-flex flex-col gap-12 mb-20">
              {activeExams.map(exam => (
                <div className="card card-accent-border" key={exam.id}>
                  <div className="d-flex justify-between align-center mb-12">
                    <h3 className="heading-md text-accent">{exam.exam_name}</h3>
                    <div className="d-flex gap-8 align-center">
                      <span className="badge-success caption">
                        {t('exams.status_active', lang)}
                      </span>
                      {isAdmin && (
                        <button className="btn-danger btn-sm" onClick={() => handleClose(exam.id)}>
                          {t('exams.close', lang)}
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="subtitle mb-12">
                    {exam.start_date} ~ {exam.end_date}
                    {exam.team && <span> | {t('exams.team', lang)}: {exam.team}</span>}
                  </div>
                  <button className="btn-secondary btn-sm" onClick={() => toggleExpand(exam.id)}>
                    {expandedId === exam.id ? t('exams.hide_results', lang) : t('exams.view_results', lang)} {expandedId === exam.id ? '\u25B2' : '\u25BC'}
                  </button>

                  {expandedId === exam.id && (
                    <div className="mt-20">
                      {resultsLoading[exam.id] ? (
                        <div className="empty-state text-center">{t('common.loading', lang)}</div>
                      ) : (
                        <div className="overflow-x-auto border rounded-8">
                          <table className="data-grid-table">
                            <thead>
                              <tr>
                                <th>{t('exams.col_rank', lang)}</th>
                                <th>{t('exams.col_name', lang)}</th>
                                <th>{t('exams.col_team', lang)}</th>
                                <th className="text-right">{t('exams.col_powder', lang)}</th>
                                <th className="text-right">{t('exams.col_reply', lang)}</th>
                                <th className="text-right">{t('exams.col_registered', lang)}</th>
                                <th className="text-right">{t('exams.col_training', lang)}</th>
                                <th className="text-right">{t('exams.col_withdrawals', lang)}</th>
                                <th className="text-right">{t('exams.col_orders', lang)}</th>
                                <th className="text-right">{t('exams.col_conversion', lang)}</th>
                                <th className="text-right">{t('exams.col_kills', lang)}</th>
                              </tr>
                            </thead>
                            <tbody>
                              {(results[exam.id] || []).map((r, idx) => (
                                <tr key={idx}>
                                  <td className={`text-bold rank-${idx < 3 ? idx + 1 : 'default'}`}>
                                    {idx + 1}
                                  </td>
                                  <td className="text-bold">{r.display_name}</td>
                                  <td className="caption">{r.team || '\u2014'}</td>
                                  <td className="text-right cell-mono text-accent">{r.total_powder}</td>
                                  <td className="text-right cell-mono text-success">{r.avg_reply_rate}%</td>
                                  <td className="text-right cell-mono text-accent">{r.total_registrations}</td>
                                  <td className="text-right cell-mono text-warning">{r.total_training}</td>
                                  <td className="text-right cell-mono">{r.total_withdrawals}</td>
                                  <td className="text-right cell-mono text-bold text-success">{r.total_new_orders}</td>
                                  <td className="text-right cell-mono text-accent">{r.conversion_rate}%</td>
                                  <td className="text-right cell-mono text-danger">{r.total_new_kills}</td>
                                </tr>
                              ))}
                              {(results[exam.id] || []).length === 0 && (
                                <tr><td colSpan={11} className="text-center p-20 caption">{t('exams.no_results', lang)}</td></tr>
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
            className="d-flex align-center gap-8 cursor-pointer"
            onClick={() => setShowEnded(!showEnded)}
          >
            <h2 className="section-title mb-0">{t('exams.ended', lang)}</h2>
            <span className="caption text-accent">{showEnded ? '\u25B2' : '\u25BC'}</span>
            <span className="caption">({endedExams.length})</span>
          </div>

          {showEnded && (
            endedExams.length === 0 ? (
              <div className="empty-state">
                <div className="empty-text">{t('exams.no_ended', lang)}</div>
              </div>
            ) : (
              <div className="grid-auto-280 gap-12 mt-12">
                {endedExams.map(exam => (
                  <div className="card opacity-80" key={exam.id}>
                    <div className="heading-sm mb-8">{exam.exam_name}</div>
                    <div className="caption mb-8">{exam.start_date} ~ {exam.end_date}</div>
                    {exam.team && <div className="caption">{t('exams.team', lang)}: {exam.team}</div>}
                    <button className="btn-secondary btn-sm mt-12" onClick={(e) => { e.stopPropagation(); toggleExpand(exam.id) }}>
                      {expandedId === exam.id ? t('exams.hide_results', lang) : t('exams.view_results', lang)}
                    </button>
                    {expandedId === exam.id && (
                      <div className="mt-12 caption">
                        {resultsLoading[exam.id] ? t('common.loading', lang) : (
                          (results[exam.id] || []).length === 0 ? t('exams.no_results', lang) : (
                            <div className="overflow-x-auto">
                              <table className="data-grid-table table-sm">
                                <thead>
                                  <tr>
                                    <th>#</th>
                                    <th>{t('exams.col_name', lang)}</th>
                                    <th className="text-right">{t('exams.col_orders', lang)}</th>
                                    <th className="text-right">{t('exams.col_kills', lang)}</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {(results[exam.id] || []).slice(0, 5).map((r, idx) => (
                                    <tr key={idx}>
                                      <td className={`text-bold rank-${idx === 0 ? '1' : 'default'}`}>{idx + 1}</td>
                                      <td>{r.display_name}</td>
                                      <td className="text-right cell-mono">{r.total_new_orders}</td>
                                      <td className="text-right cell-mono text-danger">{r.total_new_kills}</td>
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
          <div className="modal-content modal-480">
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
