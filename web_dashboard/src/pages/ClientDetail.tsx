import { useEffect, useState, useCallback } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, getAuthState } from '../api'
import type { ClientDetail as TClientDetail, ClientComment } from '../types'
import { STATUS_COLORS, STATUS_LABELS } from '../types'
import { getLang, t } from '../i18n'
import { useTheme } from '../ThemeContext'

const MILESTONES = [
  { key: 'contacted_at', label: 'detail.contacted_at' },
  { key: 'replied_at', label: 'detail.replied_at' },
  { key: 'registered_at', label: 'detail.registered_at' },
  { key: 'training_at', label: 'detail.training_at' },
  { key: 'first_order_at', label: 'detail.first_order_at' },
] as const

function Field({ label, value, accent }: { label: string; value: string | number | null | undefined; accent?: string }) {
  return (
    <div>
      <div className="field-label">{label}</div>
      <div className="fs-14 fw-600" style={{ color: accent || undefined }}>{value || '—'}</div>
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

  const auth = getAuthState()
  const clientId = id ? parseInt(id, 10) : 0

  const loadComments = useCallback(async () => {
    if (!clientId) return
    try {
      const c = await api.clientComments(clientId)
      setComments(c)
    } catch { setMessage(t('common.failed', lang)); setTimeout(() => setMessage(''), 3000) }
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
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadAll(); loadComments() }, [id])

  async function handleAddNote() {
    if (!noteContent.trim()) return
    setNoteSaving(true)
    try {
      await api.addClientNote(clientId, { content: noteContent.trim(), note_type: noteType })
      setNoteContent('')
      await loadAll()
    } catch { setMessage(t('common.failed', lang)); setTimeout(() => setMessage(''), 3000) }
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
    } catch { setMessage(t('common.failed', lang)); setTimeout(() => setMessage(''), 3000) }
    setLinkSaving(false)
  }

  async function handleRemoveLink(linkId: number) {
    await api.deleteClientLink(linkId).catch(() => null)
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
    } catch { setMessage(t('common.failed', lang)); setTimeout(() => setMessage(''), 3000) }
    setCommentSaving(false)
  }

  async function handleEditComment(commentId: number) {
    if (!editContent.trim()) return
    try {
      await api.updateComment(commentId, editContent.trim())
      setEditingComment(null)
      setEditContent('')
      await loadComments()
    } catch { setMessage(t('common.failed', lang)); setTimeout(() => setMessage(''), 3000) }
  }

  async function handleDeleteComment(commentId: number) {
    try {
      await api.deleteComment(commentId)
      await loadComments()
    } catch { setMessage(t('common.failed', lang)); setTimeout(() => setMessage(''), 3000) }
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
  if (!client) return null

  const statusColor = STATUS_COLORS[client.status] || theme.textSecondary
  const totalDeposits = client.deposits.reduce((s, d) => s + d.amount, 0)

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
          <span className="status-badge" style={{
            background: `${statusColor}20`, color: statusColor, border: `1px solid ${statusColor}40`,
          }}>
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
                className="input"
                value={noteType}
                onChange={e => setNoteType(e.target.value)}
                style={{ width: 140 }}
              >
                <option value="comment">{t('note_type.comment', lang)}</option>
                <option value="flag">{t('note_type.flag', lang)}</option>
                <option value="link_note">{t('note_type.link_note', lang)}</option>
              </select>
              <textarea
                className="input flex-1"
                placeholder={t('detail.note_placeholder', lang)}
                value={noteContent}
                onChange={e => setNoteContent(e.target.value)}
                rows={2}
                style={{ resize: 'vertical' }}
              />
              <button
                className="btn-primary self-start"
                onClick={handleAddNote}
                disabled={noteSaving || !noteContent.trim()}
                style={{ opacity: noteSaving || !noteContent.trim() ? 0.5 : 1 }}
              >
                {noteSaving ? t('common.saving', lang) : t('common.save', lang)}
              </button>
            </div>
          </div>

          {/* Linked Timeline Toggle */}
          {links.length > 0 && (
            <div className="card pointer" onClick={() => {
              if (!linkedTimeline) {
                api.linkedTimeline(clientId).then(setLinkedTimeline).catch(() => {})
              }
              setShowLinked(!showLinked)
            }}>
              <div className="flex-between">
                <div className="section-title" style={{ margin: 0 }}>
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
                      <span className="timeline-dot" style={{
                        ...(item.timeline_type === 'deposit' ? { background: theme.successBg, color: theme.success }
                          : item.timeline_type === 'link' ? { background: `${theme.accent}20`, color: theme.accent }
                          : item.client_id !== clientId ? { background: theme.warningBg, color: theme.warning }
                          : { background: theme.bgElevated, color: theme.textSecondary }),
                      }}>
                        {item.timeline_type === 'deposit' ? '$' : item.timeline_type === 'link' ? '~' : item.client_id !== clientId ? `#${item.client_id}` : '-'}
                      </span>
                      <div className="flex-1">
                        <div className="fs-12 text-secondary d-flex justify-between">
                          <span>
                            {item.staff_name || item.author_name || '-'}
                            {item.client_phone && item.client_id !== clientId && (
                              <span className="text-accent" style={{ marginLeft: 8, fontSize: 10 }}>({item.client_phone})</span>
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
                    <div className="timeline-dot" style={{
                      background: n.timeline_type === 'link' ? theme.accent
                        : n.note_type === 'status_change' ? theme.success
                        : n.note_type === 'flag' ? theme.warning
                        : theme.textMuted,
                    }} />
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
                            <span className="status-badge" style={{ color: STATUS_COLORS[n.old_status] || 'var(--text-secondary)', background: `${STATUS_COLORS[n.old_status] || 'var(--text-secondary)'}20` }}>
                              {t(`status.${n.old_status}`, lang) !== `status.${n.old_status}` ? t(`status.${n.old_status}`, lang) : (STATUS_LABELS[n.old_status] || n.old_status)}
                            </span>
                            <span className="text-muted">{'->'}</span>
                            <span className="status-badge" style={{ color: STATUS_COLORS[n.new_status] || 'var(--text-primary)', background: `${STATUS_COLORS[n.new_status] || 'var(--text-secondary)'}20` }}>
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
                  className="input flex-1"
                  placeholder={t('comments.placeholder', lang)}
                  value={commentContent}
                  onChange={e => setCommentContent(e.target.value)}
                  rows={2}
                  style={{ resize: 'vertical' }}
                />
                <button
                  className="btn-primary self-start"
                  onClick={handleAddComment}
                  disabled={commentSaving || !commentContent.trim()}
                  style={{ opacity: commentSaving || !commentContent.trim() ? 0.5 : 1 }}
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

        {/* RIGHT COLUMN: Deposits + Links */}
        <div className="flex-col gap-20">

          {/* Deposits */}
          <div className="card">
            <h3 className="section-title">
              {t('detail.deposits', lang)} <span className="text-muted fw-600">({client.deposits.length})</span>
            </h3>
            {client.deposits.length === 0 ? (
              <div className="text-secondary fs-14">{t('detail.no_deposits', lang)}</div>
            ) : (
              <div className="rounded-8 border-card" style={{ overflow: 'hidden' }}>
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

          {/* Linked Clients */}
          <div className="card">
            <div className="flex-between mb-20">
              <h3 className="section-title" style={{ margin: 0 }}>
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
                  className="btn-primary"
                  onClick={handleAddLink}
                  disabled={linkSaving || !linkTargetId}
                  style={{ opacity: linkSaving || !linkTargetId ? 0.5 : 1 }}
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
                      <span className="pill-badge badge-warning fs-11" style={{ textTransform: 'uppercase' }}>
                        {t(`link_type.${lnk.link_type}`, lang)}
                      </span>
                      <span className="text-secondary flex-1 fs-13">{lnk.note || ''}</span>
                      <button
                        className="btn-secondary text-danger fs-12"
                        onClick={() => handleRemoveLink(lnk.id)}
                        style={{ padding: '4px 12px' }}
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
      className={`comment-item ${isSystem ? 'system' : ''} ${indent > 0 ? 'reply' : ''}`}
      style={{
        marginLeft: indent * 20,
        marginTop: indent > 0 ? 8 : 0,
        opacity: isSystem ? 0.75 : 1,
        borderLeftColor: indent > 0 ? theme.accent : undefined,
      }}
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
            <span className="fs-11 text-muted" style={{ fontStyle: 'italic' }}>{t('comments.edited', lang)}</span>
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
            className="input flex-1"
            value={editContent}
            onChange={e => onEditContentChange(e.target.value)}
            rows={2}
            style={{ resize: 'vertical' }}
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
        <div className={`fs-14 ${isDeleted ? 'text-muted' : (isSystem ? 'text-secondary' : 'text-primary')}`}
          style={{
            lineHeight: 1.6,
            fontStyle: isDeleted ? 'italic' : 'normal',
          }}>
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
