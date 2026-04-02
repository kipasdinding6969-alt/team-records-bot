import { useEffect, useState, useCallback } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, getAuthState } from '../api'
import type { ClientDetail as TClientDetail, ClientComment } from '../types'
import { STATUS_COLORS, STATUS_LABELS } from '../types'
import { getLang, t } from '../i18n'
import { useTheme } from '../ThemeContext'
import { Spinner } from '../components/SharedUI'

const MILESTONES = [
  { key: 'contacted_at', label: 'detail.contacted_at' },
  { key: 'replied_at', label: 'detail.replied_at' },
  { key: 'registered_at', label: 'detail.registered_at' },
  { key: 'training_at', label: 'detail.training_at' },
  { key: 'first_order_at', label: 'detail.first_order_at' },
] as const

const PIPELINE_STEPS = [
  { key: 'contacted', label: 'pipeline.contacted' },
  { key: 'replied', label: 'pipeline.replied' },
  { key: 'registered', label: 'pipeline.registered' },
  { key: 'training_completed', label: 'pipeline.training_completed' },
  { key: 'bonus_withdrew', label: 'pipeline.bonus_withdrew' },
  { key: 'new_order', label: 'pipeline.new_order' },
] as const

const KILL_TYPES = [
  { value: 'register_kill', label: 'kill.register' },
  { value: 'new_order_kill', label: 'kill.new_order' },
  { value: 'pressure_kill', label: 'kill.pressure' },
  { value: 'salary_kill', label: 'kill.salary' },
] as const

const ROLE_TYPES = [
  { value: 'frontdesk', label: 'role_type.frontdesk' },
  { value: 'maintainer', label: 'role_type.maintainer' },
  { value: 'group_hype', label: 'role_type.group_hype' },
  { value: 'newbie_actor', label: 'role_type.newbie_actor' },
  { value: 'customer_service', label: 'role_type.customer_service' },
  { value: 'opener_legacy', label: 'role_type.opener_legacy' },
  { value: 'full_line', label: 'role_type.full_line' },
] as const

const CROSS_ROLE_OPTIONS = [
  { value: 'frontdesk', label: 'maintainer.role_frontdesk' },
  { value: 'opener', label: 'maintainer.role_opener' },
  { value: 'newbie', label: 'maintainer.role_newbie' },
  { value: 'hype', label: 'maintainer.role_hype' },
  { value: 'cs', label: 'maintainer.role_cs' },
  { value: 'maintenance', label: 'maintainer.role_mt' },
] as const

function Field({ label, value, accent }: { label: string; value: string | number | null | undefined; accent?: string }) {
  return (
    <div>
      <div className="field-label">{label}</div>
      <div className="fs-14 fw-600" style={accent ? { color: accent } : undefined}>{value || '—'}</div>
    </div>
  )
}

export default function ClientDetail() {
  const { theme } = useTheme()
  const { id } = useParams<{ id: string }>()
  const lang = getLang()
  const [client, setClient] = useState<TClientDetail | null>(null)
  const [links, setLinks] = useState<any[]>([])
  const [timeline, setTimeline] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const nav = useNavigate()

  const [linkedTimeline, setLinkedTimeline] = useState<any>(null)
  const [showLinked, setShowLinked] = useState(false)

  const [noteContent, setNoteContent] = useState('')
  const [noteType, setNoteType] = useState('comment')
  const [noteSaving, setNoteSaving] = useState(false)

  const [showLinkForm, setShowLinkForm] = useState(false)
  const [linkTargetId, setLinkTargetId] = useState('')
  const [linkType, setLinkType] = useState('related')
  const [linkNote, setLinkNote] = useState('')
  const [linkSaving, setLinkSaving] = useState(false)

  const [comments, setComments] = useState<ClientComment[]>([])
  const [commentContent, setCommentContent] = useState('')
  const [commentSaving, setCommentSaving] = useState(false)
  const [replyTo, setReplyTo] = useState<number | null>(null)
  const [editingComment, setEditingComment] = useState<number | null>(null)
  const [editContent, setEditContent] = useState('')

  // Knife Deposits state
  const [knives, setKnives] = useState<any[]>([])
  const [knivesLoading, setKnivesLoading] = useState(false)
  const [showKnifeModal, setShowKnifeModal] = useState(false)
  const [knifeForm, setKnifeForm] = useState({ knife_number: '1', amount: '', deposit_day: '', platform: 'MT5', notes: '' })
  const [knifeSubmitting, setKnifeSubmitting] = useState(false)

  // Pipeline state
  const [pipelineData, setPipelineData] = useState<any>(null)
  const [pipelineLoading, setPipelineLoading] = useState(false)
  const [showKillModal, setShowKillModal] = useState(false)
  const [killForm, setKillForm] = useState({ kill_type: 'register_kill', kill_knife: '' })
  const [killSubmitting, setKillSubmitting] = useState(false)
  const [showUnkillModal, setShowUnkillModal] = useState(false)
  const [unkillReason, setUnkillReason] = useState('')
  const [unkillSubmitting, setUnkillSubmitting] = useState(false)

  // Cross-Role Notes state
  const [roleNotes, setRoleNotes] = useState<any[]>([])
  const [roleNotesLoading, setRoleNotesLoading] = useState(false)
  const [roleNoteForm, setRoleNoteForm] = useState({ from_role: 'frontdesk', content: '' })
  const [roleNoteSaving, setRoleNoteSaving] = useState(false)

  // Role Assignments state
  const [clientRoles, setClientRoles] = useState<any[]>([])
  const [clientRolesLoading, setClientRolesLoading] = useState(false)
  const [showAssignRoleModal, setShowAssignRoleModal] = useState(false)
  const [assignRoleForm, setAssignRoleForm] = useState({ staff_id: '', role_type: 'frontdesk' })
  const [assignRoleSubmitting, setAssignRoleSubmitting] = useState(false)
  const [allStaff, setAllStaff] = useState<any[]>([])

  const auth = getAuthState()
  const clientId = id ? parseInt(id, 10) : 0

  const showMsg = (text: string) => {
    setMessage(text)
    setTimeout(() => setMessage(''), 3000)
  }

  const loadComments = useCallback(async () => {
    if (!clientId) return
    try {
      const c = await api.clientComments(clientId)
      setComments(c)
    } catch { showMsg(t('common.failed', lang)) }
  }, [clientId])

  const loadKnives = useCallback(async () => {
    if (!clientId) return
    setKnivesLoading(true)
    try {
      const data = await api.clientKnives(clientId)
      setKnives(Array.isArray(data) ? data : data?.knives || [])
    } catch { setKnives([]); showMsg(t('common.error', lang)) }
    setKnivesLoading(false)
  }, [clientId])

  const loadPipeline = useCallback(async () => {
    if (!clientId) return
    setPipelineLoading(true)
    try {
      const data = await api.clientPipeline(clientId)
      setPipelineData(data)
    } catch { setPipelineData(null); showMsg(t('common.error', lang)) }
    setPipelineLoading(false)
  }, [clientId])

  const loadRoleNotes = useCallback(async () => {
    if (!clientId) return
    setRoleNotesLoading(true)
    try {
      const data = await api.clientRoleNotes(clientId)
      setRoleNotes(Array.isArray(data) ? data : data?.notes || [])
    } catch { setRoleNotes([]); showMsg(t('common.error', lang)) }
    setRoleNotesLoading(false)
  }, [clientId])

  const loadClientRoles = useCallback(async () => {
    if (!clientId) return
    setClientRolesLoading(true)
    try {
      const data = await api.clientRoles(clientId)
      setClientRoles(Array.isArray(data) ? data : data?.roles || [])
    } catch { setClientRoles([]); showMsg(t('common.error', lang)) }
    setClientRolesLoading(false)
  }, [clientId])

  async function loadAll() {
    if (!clientId) return
    setLoading(true)
    try {
      const [c, l, tl] = await Promise.all([
        api.clientDetail(clientId),
        api.clientLinks(clientId).catch(() => []),
        api.clientTimeline(clientId).catch(() => []),
      ])
      setClient(c)
      setLinks(l)
      setTimeline(tl)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAll()
    loadComments()
    loadKnives()
    loadPipeline()
    loadRoleNotes()
    loadClientRoles()
  }, [id])

  // Load staff list for role assignment modal
  useEffect(() => {
    api.allStaff().then(setAllStaff).catch(() => setAllStaff([]))
  }, [])

  // Escape key handlers for modals
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setShowKnifeModal(false)
        setShowKillModal(false)
        setShowUnkillModal(false)
        setShowAssignRoleModal(false)
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [])

  async function handleAddNote() {
    if (!noteContent.trim()) return
    setNoteSaving(true)
    try {
      await api.addClientNote(clientId, { content: noteContent.trim(), note_type: noteType })
      setNoteContent('')
      await loadAll()
    } catch { showMsg(t('common.failed', lang)) }
    setNoteSaving(false)
  }

  async function handleAddLink() {
    if (!linkTargetId) return
    setLinkSaving(true)
    try {
      await api.createClientLink({
        client_id_a: clientId,
        client_id_b: parseInt(linkTargetId),
        link_type: linkType,
        note: linkNote || undefined,
      })
      setShowLinkForm(false)
      setLinkTargetId('')
      setLinkNote('')
      await loadAll()
    } catch { showMsg(t('common.failed', lang)) }
    setLinkSaving(false)
  }

  async function handleRemoveLink(linkId: number) {
    await api.deleteClientLink(linkId).catch(() => showMsg(t('common.error', lang)))
    await loadAll()
  }

  async function handleAddComment() {
    if (!commentContent.trim()) return
    setCommentSaving(true)
    try {
      await api.addClientComment(clientId, {
        content: commentContent.trim(),
        parent_comment_id: replyTo || undefined,
      })
      setCommentContent('')
      setReplyTo(null)
      await loadComments()
    } catch { showMsg(t('common.failed', lang)) }
    setCommentSaving(false)
  }

  async function handleEditComment(commentId: number) {
    if (!editContent.trim()) return
    try {
      await api.updateComment(commentId, editContent.trim())
      setEditingComment(null)
      setEditContent('')
      await loadComments()
    } catch { showMsg(t('common.failed', lang)) }
  }

  async function handleDeleteComment(commentId: number) {
    try {
      await api.deleteComment(commentId)
      await loadComments()
    } catch { showMsg(t('common.failed', lang)) }
  }

  async function handleAddKnife() {
    if (!knifeForm.amount) return
    setKnifeSubmitting(true)
    try {
      await api.addKnife(clientId, {
        knife_number: Number(knifeForm.knife_number),
        amount: parseFloat(knifeForm.amount),
        deposit_day: knifeForm.deposit_day ? Number(knifeForm.deposit_day) : undefined,
        platform: knifeForm.platform || undefined,
        notes: knifeForm.notes || undefined,
      })
      setShowKnifeModal(false)
      setKnifeForm({ knife_number: '1', amount: '', deposit_day: '', platform: 'MT5', notes: '' })
      await loadKnives()
    } catch { showMsg(t('common.failed', lang)) }
    setKnifeSubmitting(false)
  }

  async function handleKill() {
    if (!killForm.kill_type) return
    setKillSubmitting(true)
    try {
      await api.recordKill(clientId, {
        kill_type: killForm.kill_type,
        kill_knife: killForm.kill_knife ? Number(killForm.kill_knife) : undefined,
      })
      setShowKillModal(false)
      setKillForm({ kill_type: 'register_kill', kill_knife: '' })
      await loadPipeline()
    } catch { showMsg(t('common.failed', lang)) }
    setKillSubmitting(false)
  }

  async function handleUnkill() {
    if (!unkillReason.trim()) return
    setUnkillSubmitting(true)
    try {
      await api.unkillClient(clientId, unkillReason.trim())
      setShowUnkillModal(false)
      setUnkillReason('')
      await loadPipeline()
    } catch { showMsg(t('common.failed', lang)) }
    setUnkillSubmitting(false)
  }

  async function handleAddRoleNote() {
    if (!roleNoteForm.content.trim()) return
    setRoleNoteSaving(true)
    try {
      await api.addRoleNote(clientId, {
        from_role: roleNoteForm.from_role,
        content: roleNoteForm.content.trim(),
      })
      setRoleNoteForm(prev => ({ ...prev, content: '' }))
      await loadRoleNotes()
    } catch { showMsg(t('common.failed', lang)) }
    setRoleNoteSaving(false)
  }

  async function handleAssignRole() {
    if (!assignRoleForm.staff_id || !assignRoleForm.role_type) return
    setAssignRoleSubmitting(true)
    try {
      await api.assignRole(clientId, {
        staff_id: Number(assignRoleForm.staff_id),
        role_type: assignRoleForm.role_type,
      })
      setShowAssignRoleModal(false)
      setAssignRoleForm({ staff_id: '', role_type: 'frontdesk' })
      await loadClientRoles()
    } catch { showMsg(t('common.failed', lang)) }
    setAssignRoleSubmitting(false)
  }

  function buildThreaded(allComments: ClientComment[]): { comment: ClientComment; replies: ClientComment[] }[] {
    const topLevel = allComments.filter(c => !c.parent_comment_id)
    const repliesMap = new Map<number, ClientComment[]>()
    allComments.filter(c => c.parent_comment_id).forEach(c => {
      const arr = repliesMap.get(c.parent_comment_id!) || []
      arr.push(c)
      repliesMap.set(c.parent_comment_id!, arr)
    })
    return topLevel.map(c => ({
      comment: c,
      replies: repliesMap.get(c.id) || [],
    }))
  }

  if (loading) return <div className="text-secondary p-20 fs-14 fw-600">{t('common.loading', lang)}...</div>
  if (error) return <div className="alert alert-error">{error}</div>
  if (!client) return <div className="d-flex align-center justify-center min-h-200"><Spinner label="Loading..." /></div>

  const statusColor = STATUS_COLORS[client.status] || theme.textSecondary
  const totalDeposits = client.deposits.reduce((s, d) => s + d.amount, 0)
  const knifeTotal = knives.reduce((s, k) => s + (k.amount || 0), 0)

  const isKilled = pipelineData?.kill_type || pipelineData?.killed_at
  const canUnkill = isKilled && pipelineData?.kill_knife && pipelineData.kill_knife <= 2

  return (
    <div className="page-container">
      {message && (
        <div className="alert alert-error">{message}</div>
      )}

      {/* Client header card */}
      <div className="card mb-20">
        <div className="d-flex items-center gap-12 flex-wrap">
          <button
            className="btn-secondary"
            onClick={() => nav(-1)}
          >
            {t('detail.back', lang)}
          </button>
          <h1 className="page-title">{client.phone}</h1>
          <span className="status-badge-dynamic" style={{
            '--status-bg': `${statusColor}20`, '--status-color': statusColor, '--status-border': `${statusColor}40`,
          } as React.CSSProperties}>
            {t(`status.${client.status}`, lang) !== `status.${client.status}` ? t(`status.${client.status}`, lang) : (STATUS_LABELS[client.status] || client.status)}
          </span>
          {client.source && (
            <span className="text-secondary fs-14">{client.source}</span>
          )}
        </div>
      </div>

      {/* Two-column layout */}
      <div className="detail-grid">
        {/* LEFT COLUMN: Info + Milestones + Notes + Timeline + Comments */}
        <div className="flex-col gap-20">

          {/* Client Info Card */}
          <div className="card">
            <h3 className="section-title">{t('detail.info', lang)}</h3>
            <div className="form-grid-2col">
              <Field label={t('detail.phone', lang)} value={client.phone} accent={theme.accent} />
              <Field label={t('detail.source', lang)} value={client.source} />
              <Field label={t('detail.frontdesk', lang)} value={client.frontdesk_name} />
              <Field label={t('detail.team', lang)} value={client.team} />
              <Field label={t('detail.total_deposit', lang)} value={totalDeposits > 0 ? `$${totalDeposits.toFixed(2)}` : null} accent={theme.success} />
              <Field label={t('detail.created', lang)} value={client.created_at ? new Date(client.created_at).toLocaleDateString() : null} />
            </div>
          </div>

          {/* Milestones: horizontal timeline dots */}
          <div className="card">
            <h3 className="section-title">{t('detail.milestones', lang)}</h3>
            <div className="milestone-row">
              {MILESTONES.map((m, i) => {
                const val = (client as any)[m.key]
                const isActive = !!val
                return (
                  <div key={m.key} className="milestone-step">
                    <div className="milestone-content">
                      <div className={`milestone-dot ${isActive ? 'active' : 'inactive'}`} />
                      <div className={`milestone-label ${isActive ? 'text-primary' : 'text-secondary'}`}>
                        {t(m.label, lang)}
                      </div>
                      {val && (
                        <div className="milestone-date">
                          {new Date(val).toLocaleDateString()}
                        </div>
                      )}
                    </div>
                    {i < MILESTONES.length - 1 && (
                      <div className={`milestone-line ${isActive ? 'active' : 'inactive'}`} />
                    )}
                  </div>
                )
              })}
            </div>
          </div>

          {/* Add Note */}
          <div className="card">
            <h3 className="section-title">{t('detail.add_note', lang)}</h3>
            <div className="inline-form">
              <select
                className="input w-140"
                value={noteType}
                onChange={e => setNoteType(e.target.value)}
              >
                <option value="comment">{t('note_type.comment', lang)}</option>
                <option value="flag">{t('note_type.flag', lang)}</option>
                <option value="link_note">{t('note_type.link_note', lang)}</option>
              </select>
              <textarea
                className="input flex-1 textarea-resize"
                placeholder={t('detail.note_placeholder', lang)}
                value={noteContent}
                onChange={e => setNoteContent(e.target.value)}
                rows={2}
              />
              <button
                className={`btn-primary self-start${noteSaving || !noteContent.trim() ? ' opacity-50' : ''}`}
                onClick={handleAddNote}
                disabled={noteSaving || !noteContent.trim()}
              >
                {noteSaving ? t('common.saving', lang) : t('common.save', lang)}
              </button>
            </div>
          </div>

          {/* Linked Timeline Toggle */}
          {links.length > 0 && (
            <div className="card pointer" onClick={() => {
              if (!linkedTimeline) {
                api.linkedTimeline(clientId).then(setLinkedTimeline).catch(() => showMsg(t('common.error', lang)))
              }
              setShowLinked(!showLinked)
            }}>
              <div className="flex-between">
                <div className="section-title m-0">
                  {t('detail.linked_timeline', lang)} {linkedTimeline ? `(${linkedTimeline.timeline?.length || 0})` : ''}
                </div>
                <span className="fs-12 text-accent">{showLinked ? t('common.close', lang) : t('detail.linked_timeline', lang)}</span>
              </div>
              {showLinked && linkedTimeline && (
                <div className="mt-12">
                  {linkedTimeline.linked_client_ids?.length > 0 && (
                    <div className="mb-12 d-flex gap-8 flex-wrap items-center">
                      <span className="fs-11 text-secondary">{t('detail.linked_clients', lang)}:</span>
                      {linkedTimeline.linked_client_ids.map((lid: number) => (
                        <span key={lid} onClick={e => { e.stopPropagation(); nav(`/clients/${lid}`) }}
                          className="linked-chip">
                          #{lid}
                        </span>
                      ))}
                    </div>
                  )}
                  {(linkedTimeline.timeline || []).map((item: any, i: number) => (
                    <div key={`lt-${i}`} className="timeline-entry">
                      <span className={`timeline-dot ${item.timeline_type === 'deposit' ? 'timeline-dot-deposit'
                          : item.timeline_type === 'link' ? 'timeline-dot-link'
                          : item.client_id !== clientId ? 'timeline-dot-other'
                          : 'timeline-dot-default'}`}>
                        {item.timeline_type === 'deposit' ? '$' : item.timeline_type === 'link' ? '~' : item.client_id !== clientId ? `#${item.client_id}` : '-'}
                      </span>
                      <div className="flex-1">
                        <div className="fs-12 text-secondary d-flex justify-between">
                          <span>
                            {item.staff_name || item.author_name || '-'}
                            {item.client_phone && item.client_id !== clientId && (
                              <span className="text-accent ml-8 fs-11">({item.client_phone})</span>
                            )}
                          </span>
                          <span className="fs-11">{item.created_at ? new Date(item.created_at).toLocaleString() : ''}</span>
                        </div>
                        {item.content && <div className="fs-13 text-primary mt-8">{item.content}</div>}
                      </div>
                    </div>
                  ))}
                  {(linkedTimeline.timeline || []).length === 0 && (
                    <div className="text-secondary fs-13">{t('detail.no_notes', lang)}</div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Timeline */}
          <div className="card">
            <h3 className="section-title">
              {t('detail.timeline', lang)} <span className="text-muted fw-600">({timeline.length})</span>
            </h3>
            {timeline.length === 0 ? (
              <div className="text-secondary fs-14">{t('detail.no_notes', lang)}</div>
            ) : (
              <div className="timeline-vertical">
                {timeline.map((n, i) => (
                  <div
                    key={`${n.timeline_type || 'note'}-${n.id}-${i}`}
                    className="timeline-entry"
                  >
                    {/* Dot on the left border */}
                    <div className={`timeline-dot ${n.timeline_type === 'link' ? 'dot-accent'
                        : n.note_type === 'status_change' ? 'dot-success'
                        : n.note_type === 'flag' ? 'dot-warning'
                        : 'dot-muted'}`} />
                    <div className="timeline-header">
                      <span className="fs-13 fw-600 text-primary d-flex items-center gap-8">
                        {n.staff_name || n.author_name || t('detail.system', lang)}
                        {n.timeline_type === 'link' && (
                          <span className="pill-badge badge-warning fs-11">
                            LINK
                          </span>
                        )}
                        {n.note_type === 'status_change' && n.old_status && n.new_status && (
                          <span className="d-flex items-center gap-8 fs-12">
                            <span className="status-badge-dynamic" style={{ '--status-color': STATUS_COLORS[n.old_status] || 'var(--text-secondary)', '--status-bg': `${STATUS_COLORS[n.old_status] || 'var(--text-secondary)'}20` } as React.CSSProperties}>
                              {t(`status.${n.old_status}`, lang) !== `status.${n.old_status}` ? t(`status.${n.old_status}`, lang) : (STATUS_LABELS[n.old_status] || n.old_status)}
                            </span>
                            <span className="text-muted">{'->'}</span>
                            <span className="status-badge-dynamic" style={{ '--status-color': STATUS_COLORS[n.new_status] || 'var(--text-primary)', '--status-bg': `${STATUS_COLORS[n.new_status] || 'var(--text-secondary)'}20` } as React.CSSProperties}>
                              {t(`status.${n.new_status}`, lang) !== `status.${n.new_status}` ? t(`status.${n.new_status}`, lang) : (STATUS_LABELS[n.new_status] || n.new_status)}
                            </span>
                          </span>
                        )}
                      </span>
                      <span className="fs-12 text-secondary fw-600">
                        {n.created_at ? new Date(n.created_at).toLocaleString() : ''}
                      </span>
                    </div>
                    {n.content && (
                      <div className="timeline-content-block">
                        {n.content}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Comment Thread */}
          <div className="card">
            <h3 className="section-title">
              {t('comments.title', lang)} <span className="text-muted fw-600">({comments.length})</span>
            </h3>

            {/* Add comment form */}
            <div className="mb-20">
              {replyTo && (
                <div className="pill-badge badge-accent mb-8 d-flex items-center gap-8 p-12 rounded-8">
                  <span>{t('comments.reply', lang)}: #{replyTo}</span>
                  <button
                    onClick={() => setReplyTo(null)}
                    className="comment-action-btn delete-btn fw-700 fs-14"
                  >
                    x
                  </button>
                </div>
              )}
              <div className="inline-form">
                <textarea
                  className="input flex-1 textarea-resize"
                  placeholder={t('comments.placeholder', lang)}
                  value={commentContent}
                  onChange={e => setCommentContent(e.target.value)}
                  rows={2}
                />
                <button
                  className={`btn-primary self-start${commentSaving || !commentContent.trim() ? ' opacity-50' : ''}`}
                  onClick={handleAddComment}
                  disabled={commentSaving || !commentContent.trim()}
                >
                  {commentSaving ? t('common.saving', lang) : t('comments.submit', lang)}
                </button>
              </div>
            </div>

            {/* Comment list */}
            {comments.length === 0 ? (
              <div className="text-secondary fs-14">{t('comments.no_comments', lang)}</div>
            ) : (
              <div className="flex-col gap-12">
                {buildThreaded(comments).map(({ comment: c, replies }) => (
                  <div key={c.id}>
                    <CommentItem
                      comment={c}
                      theme={theme}
                      lang={lang}
                      auth={auth}
                      editingComment={editingComment}
                      editContent={editContent}
                      onReply={() => setReplyTo(c.id)}
                      onStartEdit={() => { setEditingComment(c.id); setEditContent(c.content) }}
                      onCancelEdit={() => { setEditingComment(null); setEditContent('') }}
                      onSaveEdit={() => handleEditComment(c.id)}
                      onDelete={() => handleDeleteComment(c.id)}
                      onEditContentChange={setEditContent}
                      indent={0}
                    />
                    {replies.map(r => (
                      <CommentItem
                        key={r.id}
                        comment={r}
                        theme={theme}
                        lang={lang}
                        auth={auth}
                        editingComment={editingComment}
                        editContent={editContent}
                        onReply={() => setReplyTo(c.id)}
                        onStartEdit={() => { setEditingComment(r.id); setEditContent(r.content) }}
                        onCancelEdit={() => { setEditingComment(null); setEditContent('') }}
                        onSaveEdit={() => handleEditComment(r.id)}
                        onDelete={() => handleDeleteComment(r.id)}
                        onEditContentChange={setEditContent}
                        indent={1}
                      />
                    ))}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* RIGHT COLUMN: Deposits + Knife Deposits + Pipeline + Cross-Role Notes + Role Assignments + Links */}
        <div className="flex-col gap-20">

          {/* Deposits */}
          <div className="card">
            <h3 className="section-title">
              {t('detail.deposits', lang)} <span className="text-muted fw-600">({client.deposits.length})</span>
            </h3>
            {client.deposits.length === 0 ? (
              <div className="text-secondary fs-14">{t('detail.no_deposits', lang)}</div>
            ) : (
              <div className="rounded-8 border-card overflow-hidden">
                <table className="data-grid-table w-full">
                  <thead>
                    <tr>
                      {[t('detail.amount', lang), t('detail.platform', lang), t('detail.date', lang)].map(h => (
                        <th key={h}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {client.deposits.map((d, i) => (
                      <tr key={d.id}>
                        <td className="cell-mono text-success fw-600">${d.amount.toFixed(2)} {d.currency}</td>
                        <td className="text-primary fw-600">{d.platform || '—'}</td>
                        <td className="cell-mono text-secondary fs-12">{d.deposit_date ? new Date(d.deposit_date).toLocaleDateString() : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* A. Knife Deposits Section */}
          <div className="card">
            <div className="flex-between mb-12">
              <h3 className="section-title m-0">
                {t('knife.title', lang)} <span className="text-muted fw-600">({knives.length})</span>
              </h3>
              <button className="btn-primary" onClick={() => setShowKnifeModal(true)}>
                + {t('knife.add', lang)}
              </button>
            </div>

            {knivesLoading ? (
              <div className="text-secondary fs-14">{t('common.loading', lang)}...</div>
            ) : knives.length === 0 ? (
              <div className="text-secondary fs-14">{t('knife.no_knives', lang) !== 'knife.no_knives' ? t('knife.no_knives', lang) : 'No knives recorded'}</div>
            ) : (
              <div className="rounded-8 border-card overflow-hidden">
                <table className="data-grid-table w-full">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>{t('knife.amount', lang)}</th>
                      <th>{t('knife.day', lang)}</th>
                      <th>{t('detail.platform', lang)}</th>
                      <th>{t('detail.link_note', lang)}</th>
                      <th>{t('detail.date', lang)}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {knives.map((k: any, idx: number) => {
                      const amt = k.amount || 0
                      return (
                        <tr key={k.id || idx}>
                          <td className="cell-mono fw-700">{k.knife_number || idx + 1}</td>
                          <td className={`cell-mono-right fw-700 ${amt >= 0 ? 'text-success' : 'text-danger'}`}>
                            ${Math.abs(amt).toLocaleString()}
                          </td>
                          <td className="cell-mono">{k.deposit_day || '—'}</td>
                          <td className="text-primary">{k.platform || '—'}</td>
                          <td className="fs-12 text-secondary">{k.notes || '—'}</td>
                          <td className="cell-mono text-secondary fs-12">{k.created_at ? new Date(k.created_at).toLocaleDateString() : '—'}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                  <tfoot>
                    <tr className="border-top">
                      <td className="fw-700 fs-14">{t('common.total', lang)}</td>
                      <td className={`cell-mono-right fw-700 fs-14 ${knifeTotal >= 0 ? 'text-success' : 'text-danger'}`}>
                        ${Math.abs(knifeTotal).toLocaleString()}
                      </td>
                      <td colSpan={4} />
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}
          </div>

          {/* B. Pipeline Status Section */}
          <div className="card">
            <h3 className="section-title">{t('pipeline.client_pipeline', lang)}</h3>

            {pipelineLoading ? (
              <div className="text-secondary fs-14">{t('common.loading', lang)}...</div>
            ) : (
              <div className="flex-col gap-12">
                {/* Pipeline milestone steps */}
                <div className="d-flex flex-wrap gap-8">
                  {PIPELINE_STEPS.map(step => {
                    const reached = pipelineData?.steps?.[step.key] || pipelineData?.[step.key]
                    return (
                      <span
                        key={step.key}
                        className={`pill-badge ${reached ? 'badge-success' : 'badge-info'} fs-12 fw-600`}
                      >
                        {reached ? '●' : '○'} {t(step.label, lang)}
                        {reached && typeof reached === 'string' && reached.length > 4 && (
                          <span className="fs-11"> ({new Date(reached).toLocaleDateString()})</span>
                        )}
                      </span>
                    )
                  })}
                </div>

                {/* Kill status */}
                {isKilled && (
                  <div className="flex-col gap-8">
                    <div className="d-flex items-center gap-8">
                      <span className="pill-badge badge-danger fs-12 fw-700">KILLED</span>
                      {pipelineData?.kill_type && (
                        <span className="pill-badge badge-warning fs-12 fw-600">
                          {t(`kill.${pipelineData.kill_type.replace('_kill', '')}`, lang) !== `kill.${pipelineData.kill_type.replace('_kill', '')}` ? t(`kill.${pipelineData.kill_type.replace('_kill', '')}`, lang) : pipelineData.kill_type}
                        </span>
                      )}
                      {pipelineData?.kill_knife && (
                        <span className="pill-badge badge-info fs-12 fw-600">
                          {t('kill.knife', lang)} #{pipelineData.kill_knife}
                        </span>
                      )}
                    </div>
                    {pipelineData?.killed_at && (
                      <div className="fs-12 text-secondary">
                        {new Date(pipelineData.killed_at).toLocaleString()}
                      </div>
                    )}
                  </div>
                )}

                {/* Unkill status */}
                {pipelineData?.unkilled_at && (
                  <div className="d-flex items-center gap-8">
                    <span className="pill-badge badge-success fs-12 fw-700">{t('kill.unkill', lang)}</span>
                    <span className="fs-12 text-secondary">
                      {new Date(pipelineData.unkilled_at).toLocaleString()}
                    </span>
                    {pipelineData?.unkill_reason && (
                      <span className="fs-12 text-primary">{pipelineData.unkill_reason}</span>
                    )}
                  </div>
                )}

                {/* Action buttons */}
                <div className="d-flex gap-8">
                  {!isKilled && (
                    <button className="btn-secondary text-danger" onClick={() => setShowKillModal(true)}>
                      Kill Client
                    </button>
                  )}
                  {canUnkill && (
                    <button className="btn-secondary text-success" onClick={() => setShowUnkillModal(true)}>
                      {t('kill.unkill', lang)}
                    </button>
                  )}
                </div>

                {canUnkill && (
                  <div className="fs-11 text-secondary">{t('kill.only_1_2', lang)}</div>
                )}
              </div>
            )}
          </div>

          {/* C. Cross-Role Notes Section */}
          <div className="card">
            <h3 className="section-title">
              {t('role_notes.title', lang)} <span className="text-muted fw-600">({roleNotes.length})</span>
            </h3>

            {roleNotesLoading ? (
              <div className="text-secondary fs-14">{t('common.loading', lang)}...</div>
            ) : roleNotes.length === 0 ? (
              <div className="text-secondary fs-14 mb-12">{t('role_notes.empty', lang) !== 'role_notes.empty' ? t('role_notes.empty', lang) : 'No role notes'}</div>
            ) : (
              <div className="flex-col gap-8 mb-12">
                {roleNotes.map((note: any, idx: number) => (
                  <div key={note.id || idx} className="d-flex gap-8 items-start">
                    <span className="pill-badge badge-accent fs-11 fw-700 nowrap">
                      {t(`role_notes.from`, lang)}: {t(`maintainer.role_${note.from_role === 'maintenance' ? 'mt' : note.from_role}`, lang) !== `maintainer.role_${note.from_role === 'maintenance' ? 'mt' : note.from_role}` ? t(`maintainer.role_${note.from_role === 'maintenance' ? 'mt' : note.from_role}`, lang) : note.from_role}
                    </span>
                    <div className="flex-1">
                      <div className="fs-13 text-primary">{note.content}</div>
                      <div className="fs-11 text-secondary">
                        {note.staff_name || note.author_name || ''}
                        {note.created_at ? ` — ${new Date(note.created_at).toLocaleString()}` : ''}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Add note form */}
            <div className="flex-col gap-8">
              <div className="d-flex gap-8">
                <select
                  className="input w-140"
                  value={roleNoteForm.from_role}
                  onChange={e => setRoleNoteForm(prev => ({ ...prev, from_role: e.target.value }))}
                >
                  {CROSS_ROLE_OPTIONS.map(opt => (
                    <option key={opt.value} value={opt.value}>{t(opt.label, lang)}</option>
                  ))}
                </select>
                <textarea
                  className="input flex-1 textarea-resize"
                  placeholder={t('role_notes.placeholder', lang)}
                  value={roleNoteForm.content}
                  onChange={e => setRoleNoteForm(prev => ({ ...prev, content: e.target.value }))}
                  rows={2}
                />
              </div>
              <button
                className={`btn-primary self-end${roleNoteSaving || !roleNoteForm.content.trim() ? ' opacity-50' : ''}`}
                onClick={handleAddRoleNote}
                disabled={roleNoteSaving || !roleNoteForm.content.trim()}
              >
                {roleNoteSaving ? t('common.saving', lang) : t('role_notes.add', lang)}
              </button>
            </div>
          </div>

          {/* D. Role Assignments Section */}
          <div className="card">
            <div className="flex-between mb-12">
              <h3 className="section-title m-0">
                {t('maintainer.role', lang)} <span className="text-muted fw-600">({clientRoles.length})</span>
              </h3>
              <button className="btn-primary" onClick={() => setShowAssignRoleModal(true)}>
                + {t('maintainer.role', lang)}
              </button>
            </div>

            {clientRolesLoading ? (
              <div className="text-secondary fs-14">{t('common.loading', lang)}...</div>
            ) : clientRoles.length === 0 ? (
              <div className="text-secondary fs-14">{t('maintainer.no_roles', lang) !== 'maintainer.no_roles' ? t('maintainer.no_roles', lang) : 'No roles assigned'}</div>
            ) : (
              <div className="flex-col gap-8">
                {clientRoles.map((role: any, idx: number) => {
                  const isActive = role.is_active !== false && !role.ended_at
                  return (
                    <div key={role.id || idx} className="d-flex items-center gap-8 flex-wrap">
                      <span className={`pill-badge ${isActive ? 'badge-success' : 'badge-danger'} fs-12 fw-700`}>
                        {isActive ? 'ACTIVE' : 'ENDED'}
                      </span>
                      <span className="pill-badge badge-info fs-12 fw-600">
                        {t(`role_type.${role.role_type}`, lang) !== `role_type.${role.role_type}` ? t(`role_type.${role.role_type}`, lang) : role.role_type}
                      </span>
                      <span className="fs-13 fw-600 text-primary">{role.staff_name || `Staff #${role.staff_id}`}</span>
                      {role.assigned_at && (
                        <span className="fs-11 text-secondary">{new Date(role.assigned_at).toLocaleDateString()}</span>
                      )}
                      {!isActive && role.end_reason && (
                        <span className="fs-11 text-warning">{role.end_reason}</span>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {/* Linked Clients */}
          <div className="card">
            <div className="flex-between mb-20">
              <h3 className="section-title m-0">
                {t('detail.links', lang)} <span className="text-muted fw-600">({links.length})</span>
              </h3>
              <button
                className={showLinkForm ? 'btn-secondary' : 'btn-primary'}
                onClick={() => setShowLinkForm(v => !v)}
              >
                {showLinkForm ? t('common.cancel', lang) : `+ ${t('detail.add_link', lang)}`}
              </button>
            </div>

            {showLinkForm && (
              <div className="inline-form flex-col gap-12 bg-elevated rounded-8 border-card p-20 mb-20">
                <input
                  className="input w-full"
                  type="number"
                  placeholder={t('detail.target_client_id', lang)}
                  value={linkTargetId}
                  onChange={e => setLinkTargetId(e.target.value)}
                />
                <select
                  className="input w-full"
                  value={linkType}
                  onChange={e => setLinkType(e.target.value)}
                >
                  {['related', 'same_person', 'referral', 'family'].map(lt => (
                    <option key={lt} value={lt}>{t(`link_type.${lt}`, lang)}</option>
                  ))}
                </select>
                <input
                  className="input w-full"
                  placeholder={t('detail.link_note', lang)}
                  value={linkNote}
                  onChange={e => setLinkNote(e.target.value)}
                />
                <button
                  className={`btn-primary${linkSaving || !linkTargetId ? ' opacity-50' : ''}`}
                  onClick={handleAddLink}
                  disabled={linkSaving || !linkTargetId}
                >
                  {linkSaving ? t('common.saving', lang) : t('common.save', lang)}
                </button>
              </div>
            )}

            {links.length === 0 ? (
              <div className="text-secondary fs-14">{t('detail.no_links', lang)}</div>
            ) : (
              <div className="flex-col gap-8">
                {links.map(lnk => {
                  const otherId = lnk.client_id_a === clientId ? lnk.client_id_b : lnk.client_id_a
                  const otherPhone = lnk.client_id_a === clientId ? lnk.phone_b : lnk.phone_a
                  return (
                    <div key={lnk.id} className="link-card">
                      <span
                        className="text-accent pointer fw-700 fs-14"
                        onClick={() => nav(`/clients/${otherId}`)}
                      >
                        #{otherId}
                      </span>
                      <span className="text-primary">{otherPhone}</span>
                      <span className="pill-badge badge-warning fs-11 text-uppercase">
                        {t(`link_type.${lnk.link_type}`, lang)}
                      </span>
                      <span className="text-secondary flex-1 fs-13">{lnk.note || ''}</span>
                      <button
                        className="btn-secondary btn-xs text-danger"
                        onClick={() => handleRemoveLink(lnk.id)}
                      >
                        {t('detail.remove_link', lang)}
                      </button>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Modals ── */}

      {/* Add Knife Deposit Modal */}
      {showKnifeModal && (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) setShowKnifeModal(false) }}>
          <div className="modal-content w-420">
            <h3 className="modal-title">{t('knife.add', lang)}</h3>
            <div className="form-grid">
              <div className="form-grid-2col">
                <label>
                  <span className="field-label">{t('knife.number', lang)} *</span>
                  <select className="input" value={knifeForm.knife_number} onChange={e => setKnifeForm(prev => ({ ...prev, knife_number: e.target.value }))}>
                    {[1,2,3,4,5,6,7,8].map(n => <option key={n} value={n}>{n}</option>)}
                  </select>
                </label>
                <label>
                  <span className="field-label">{t('knife.amount', lang)} *</span>
                  <input className="input" type="number" step="0.01" value={knifeForm.amount} onChange={e => setKnifeForm(prev => ({ ...prev, amount: e.target.value }))} required />
                </label>
              </div>
              <div className="form-grid-2col">
                <label>
                  <span className="field-label">{t('knife.day', lang)}</span>
                  <input className="input" type="number" value={knifeForm.deposit_day} onChange={e => setKnifeForm(prev => ({ ...prev, deposit_day: e.target.value }))} />
                </label>
                <label>
                  <span className="field-label">{t('detail.platform', lang)}</span>
                  <select className="input" value={knifeForm.platform} onChange={e => setKnifeForm(prev => ({ ...prev, platform: e.target.value }))}>
                    {['MT5', 'MT4', 'cTrader', 'Other'].map(p => <option key={p} value={p}>{p}</option>)}
                  </select>
                </label>
              </div>
              <label>
                <span className="field-label">{t('detail.link_note', lang)}</span>
                <textarea className="input textarea-resize min-h-60 h-auto" value={knifeForm.notes} onChange={e => setKnifeForm(prev => ({ ...prev, notes: e.target.value }))} />
              </label>
              <div className="modal-actions">
                <button className="btn-secondary flex-1" onClick={() => setShowKnifeModal(false)}>
                  {t('common.cancel', lang)}
                </button>
                <button
                  className="btn-primary flex-1"
                  onClick={handleAddKnife}
                  disabled={knifeSubmitting || !knifeForm.amount}
                >
                  {knifeSubmitting ? '...' : t('common.confirm', lang)}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Kill Client Modal */}
      {showKillModal && (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) setShowKillModal(false) }}>
          <div className="modal-content w-380">
            <h3 className="modal-title">Kill Client</h3>
            <div className="form-grid">
              <label>
                <span className="field-label">Kill Type *</span>
                <select className="input" value={killForm.kill_type} onChange={e => setKillForm(prev => ({ ...prev, kill_type: e.target.value }))}>
                  {KILL_TYPES.map(kt => (
                    <option key={kt.value} value={kt.value}>{t(kt.label, lang)}</option>
                  ))}
                </select>
              </label>
              <label>
                <span className="field-label">{t('kill.knife', lang)} #</span>
                <select className="input" value={killForm.kill_knife} onChange={e => setKillForm(prev => ({ ...prev, kill_knife: e.target.value }))}>
                  <option value="">—</option>
                  {[1,2,3,4,5,6,7,8].map(n => <option key={n} value={n}>{n}</option>)}
                </select>
              </label>
              <div className="modal-actions">
                <button className="btn-secondary flex-1" onClick={() => setShowKillModal(false)}>
                  {t('common.cancel', lang)}
                </button>
                <button
                  className="btn-primary flex-1 text-danger"
                  onClick={handleKill}
                  disabled={killSubmitting}
                >
                  {killSubmitting ? '...' : t('common.confirm', lang)}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Unkill Modal */}
      {showUnkillModal && (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) setShowUnkillModal(false) }}>
          <div className="modal-content w-380">
            <h3 className="modal-title">{t('kill.unkill', lang)}</h3>
            <div className="form-grid">
              <label>
                <span className="field-label">{t('kill.unkill_reason', lang)} *</span>
                <textarea className="input textarea-resize" value={unkillReason} onChange={e => setUnkillReason(e.target.value)} rows={3} />
              </label>
              <div className="fs-12 text-warning">{t('kill.only_1_2', lang)}</div>
              <div className="modal-actions">
                <button className="btn-secondary flex-1" onClick={() => setShowUnkillModal(false)}>
                  {t('common.cancel', lang)}
                </button>
                <button
                  className="btn-primary flex-1"
                  onClick={handleUnkill}
                  disabled={unkillSubmitting || !unkillReason.trim()}
                >
                  {unkillSubmitting ? '...' : t('common.confirm', lang)}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Assign Role Modal */}
      {showAssignRoleModal && (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) setShowAssignRoleModal(false) }}>
          <div className="modal-content w-400">
            <h3 className="modal-title">{t('maintainer.role', lang)}</h3>
            <div className="form-grid">
              <label>
                <span className="field-label">{t('maintainer.name', lang)} *</span>
                <select className="input" value={assignRoleForm.staff_id} onChange={e => setAssignRoleForm(prev => ({ ...prev, staff_id: e.target.value }))}>
                  <option value="">—</option>
                  {allStaff.map(s => (
                    <option key={s.id} value={s.id}>{s.display_name} ({s.role})</option>
                  ))}
                </select>
              </label>
              <label>
                <span className="field-label">{t('maintainer.role', lang)} *</span>
                <select className="input" value={assignRoleForm.role_type} onChange={e => setAssignRoleForm(prev => ({ ...prev, role_type: e.target.value }))}>
                  {ROLE_TYPES.map(rt => (
                    <option key={rt.value} value={rt.value}>{t(rt.label, lang)}</option>
                  ))}
                </select>
              </label>
              <div className="modal-actions">
                <button className="btn-secondary flex-1" onClick={() => setShowAssignRoleModal(false)}>
                  {t('common.cancel', lang)}
                </button>
                <button
                  className="btn-primary flex-1"
                  onClick={handleAssignRole}
                  disabled={assignRoleSubmitting || !assignRoleForm.staff_id}
                >
                  {assignRoleSubmitting ? '...' : t('common.confirm', lang)}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function CommentItem({
  comment: c,
  theme,
  lang,
  auth,
  editingComment,
  editContent,
  onReply,
  onStartEdit,
  onCancelEdit,
  onSaveEdit,
  onDelete,
  onEditContentChange,
  indent,
}: {
  comment: ClientComment
  theme: any
  lang: any
  auth: any
  editingComment: number | null
  editContent: string
  onReply: () => void
  onStartEdit: () => void
  onCancelEdit: () => void
  onSaveEdit: () => void
  onDelete: () => void
  onEditContentChange: (v: string) => void
  indent: number
}) {
  const isSystem = c.is_system
  const isDeleted = c.is_deleted
  const isOwn = auth?.staff_id === c.staff_id || auth?.user_id === c.staff_id
  const isEditing = editingComment === c.id

  return (
    <div
      className={`comment-item ${isSystem ? 'system' : ''} ${indent > 0 ? 'reply comment-indent-1' : ''}${isSystem ? ' opacity-75' : ''}`}
    >
      {/* Header */}
      <div className="comment-header">
        <div className="d-flex items-center gap-8">
          <span className={`fs-13 fw-700 ${isSystem ? 'text-muted' : 'text-primary'}`}>
            {isSystem ? t('comments.system', lang) : c.staff_name}
          </span>
          {indent > 0 && (
            <span className="pill-badge badge-accent fs-11">
              {t('comments.reply', lang)}
            </span>
          )}
          {c.updated_at && !isDeleted && (
            <span className="fs-11 text-muted italic">{t('comments.edited', lang)}</span>
          )}
        </div>
        <span className="fs-12 text-secondary fw-600">
          {c.created_at ? new Date(c.created_at).toLocaleString() : ''}
        </span>
      </div>

      {/* Content */}
      {isEditing ? (
        <div className="d-flex gap-8 items-start">
          <textarea
            className="input flex-1 textarea-resize"
            value={editContent}
            onChange={e => onEditContentChange(e.target.value)}
            rows={2}
          />
          <div className="flex-col gap-4">
            <button className="btn-primary fs-12 p-12" onClick={onSaveEdit}>
              {t('common.save', lang)}
            </button>
            <button className="btn-secondary fs-12 p-12" onClick={onCancelEdit}>
              {t('common.cancel', lang)}
            </button>
          </div>
        </div>
      ) : (
        <div className={`fs-14 lh-16 ${isDeleted ? 'text-muted italic' : (isSystem ? 'text-secondary' : 'text-primary')}`}>
          {isDeleted ? t('comments.deleted', lang) : c.content}
        </div>
      )}

      {/* Actions */}
      {!isSystem && !isDeleted && !isEditing && (
        <div className="comment-actions">
          <button onClick={onReply} className="comment-action-btn reply-btn">
            {t('comments.reply', lang)}
          </button>
          {isOwn && (
            <>
              <button onClick={onStartEdit} className="comment-action-btn edit-btn">
                {t('comments.edit', lang)}
              </button>
              <button onClick={onDelete} className="comment-action-btn delete-btn">
                {t('comments.delete', lang)}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
}
