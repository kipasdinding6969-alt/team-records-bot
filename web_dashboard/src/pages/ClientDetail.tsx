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
  const { theme } = useTheme()
  return (
    <div>
      <div className="field-label">{label}</div>
      <div style={{ fontSize: 15, fontWeight: 500, color: accent || theme.textPrimary }}>{value || '—'}</div>
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

  if (loading) return <div style={{ color: theme.textSecondary, padding: 20, fontSize: 15, fontWeight: 500 }}>{t('common.loading', lang)}...</div>
  if (error) return <div style={{ color: theme.danger, padding: 20, fontSize: 15, fontWeight: 500 }}>{error}</div>
  if (!client) return null

  const statusColor = STATUS_COLORS[client.status] || theme.textSecondary
  const totalDeposits = client.deposits.reduce((s, d) => s + d.amount, 0)

  return (
    <div className="page-container" style={{ maxWidth: 1400, margin: '0 auto', color: theme.textPrimary }}>
      {message && (
        <div style={{ padding: '12px', marginBottom: 20, background: theme.dangerBg, color: theme.danger, borderRadius: 8, fontSize: 13, border: `1px solid ${theme.danger}40` }}>
          {message}
        </div>
      )}

      {/* Client header card */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <button
            className="btn-secondary"
            onClick={() => nav(-1)}
          >
            {t('detail.back', lang)}
          </button>
          <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0, letterSpacing: '-0.02em' }}>{client.phone}</h1>
          <span style={{
            padding: '4px 12px', borderRadius: 8,
            background: `${statusColor}20`, color: statusColor, border: `1px solid ${statusColor}40`,
            fontSize: 13, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5,
          }}>
            {t(`status.${client.status}`, lang) !== `status.${client.status}` ? t(`status.${client.status}`, lang) : (STATUS_LABELS[client.status] || client.status)}
          </span>
          {client.source && (
            <span style={{ color: theme.textSecondary, fontSize: 14 }}>{client.source}</span>
          )}
        </div>
      </div>

      {/* Two-column layout: 65% left, 35% right */}
      <div style={{ display: 'grid', gridTemplateColumns: '65% 35%', gap: 20 }}>
        {/* LEFT COLUMN: Info + Milestones + Notes + Timeline + Comments */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

          {/* Client Info Card */}
          <div className="card">
            <h3 className="field-label" style={{ fontSize: 14, marginBottom: 20, display: 'flex', alignItems: 'center', gap: 8 }}>{t('detail.info', lang)}</h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
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
            <h3 className="field-label" style={{ fontSize: 14, marginBottom: 20, display: 'flex', alignItems: 'center', gap: 8 }}>{t('detail.milestones', lang)}</h3>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 0, overflow: 'auto' }}>
              {MILESTONES.map((m, i) => {
                const val = (client as any)[m.key]
                const isActive = !!val
                return (
                  <div key={m.key} style={{ display: 'flex', alignItems: 'center', flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flex: 1 }}>
                      <div style={{
                        width: 16, height: 16, borderRadius: '50%', flexShrink: 0,
                        background: isActive ? theme.success : theme.cardBorder,
                        border: `2px solid ${isActive ? theme.success : theme.cardBorder}`,
                        marginBottom: 8,
                      }} />
                      <div style={{ fontSize: 11, fontWeight: 600, color: isActive ? theme.textPrimary : theme.textSecondary, textAlign: 'center', lineHeight: 1.3 }}>
                        {t(m.label, lang)}
                      </div>
                      {val && (
                        <div style={{ fontSize: 10, color: theme.textSecondary, marginTop: 4 }}>
                          {new Date(val).toLocaleDateString()}
                        </div>
                      )}
                    </div>
                    {i < MILESTONES.length - 1 && (
                      <div style={{ height: 2, flex: 1, background: isActive ? theme.success : theme.cardBorder, marginTop: -20, minWidth: 12 }} />
                    )}
                  </div>
                )
              })}
            </div>
          </div>

          {/* Add Note */}
          <div className="card">
            <h3 className="field-label" style={{ fontSize: 14, marginBottom: 20, display: 'flex', alignItems: 'center', gap: 8 }}>{t('detail.add_note', lang)}</h3>
            <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
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
                className="input"
                placeholder={t('detail.note_placeholder', lang)}
                value={noteContent}
                onChange={e => setNoteContent(e.target.value)}
                rows={2}
                style={{ flex: 1, resize: 'vertical', fontFamily: 'inherit' }}
              />
              <button
                className="btn-primary"
                onClick={handleAddNote}
                disabled={noteSaving || !noteContent.trim()}
                style={{ opacity: noteSaving || !noteContent.trim() ? 0.5 : 1, alignSelf: 'flex-start' }}
              >
                {noteSaving ? t('common.saving', lang) : t('common.save', lang)}
              </button>
            </div>
          </div>

          {/* Linked Timeline Toggle */}
          {links.length > 0 && (
            <div className="card" style={{ cursor: 'pointer' }} onClick={() => {
              if (!linkedTimeline) {
                api.linkedTimeline(clientId).then(setLinkedTimeline).catch(() => {})
              }
              setShowLinked(!showLinked)
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div className="field-label" style={{ marginBottom: 0 }}>
                  {t('detail.linked_timeline', lang)} {linkedTimeline ? `(${linkedTimeline.timeline?.length || 0})` : ''}
                </div>
                <span style={{ fontSize: 12, color: theme.accent }}>{showLinked ? t('common.close', lang) : t('detail.linked_timeline', lang)}</span>
              </div>
              {showLinked && linkedTimeline && (
                <div style={{ marginTop: 12 }}>
                  {linkedTimeline.linked_client_ids?.length > 0 && (
                    <div style={{ marginBottom: 12, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                      <span style={{ fontSize: 11, color: theme.textSecondary }}>{t('detail.linked_clients', lang)}:</span>
                      {linkedTimeline.linked_client_ids.map((lid: number) => (
                        <span key={lid} onClick={e => { e.stopPropagation(); nav(`/clients/${lid}`) }}
                          style={{
                            fontSize: 11, padding: '4px 8px', borderRadius: 8,
                            background: `${theme.accent}20`, color: theme.accent, cursor: 'pointer', fontWeight: 600,
                          }}>
                          #{lid}
                        </span>
                      ))}
                    </div>
                  )}
                  {(linkedTimeline.timeline || []).map((item: any, i: number) => (
                    <div key={`lt-${i}`} style={{
                      padding: '8px 0', borderBottom: i < linkedTimeline.timeline.length - 1 ? `1px solid ${theme.cardBorder}` : 'none',
                      display: 'flex', gap: 12, alignItems: 'flex-start',
                    }}>
                      <span style={{
                        fontSize: 9, padding: '2px 8px', borderRadius: 8, fontWeight: 700, flexShrink: 0, marginTop: 4,
                        ...(item.timeline_type === 'deposit' ? { background: theme.successBg, color: theme.success }
                          : item.timeline_type === 'link' ? { background: `${theme.accent}20`, color: theme.accent }
                          : item.client_id !== clientId ? { background: theme.warningBg, color: theme.warning }
                          : { background: theme.bgElevated, color: theme.textSecondary }),
                      }}>
                        {item.timeline_type === 'deposit' ? '$' : item.timeline_type === 'link' ? '~' : item.client_id !== clientId ? `#${item.client_id}` : '-'}
                      </span>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: 12, color: theme.textSecondary, display: 'flex', justifyContent: 'space-between' }}>
                          <span>
                            {item.staff_name || item.author_name || '-'}
                            {item.client_phone && item.client_id !== clientId && (
                              <span style={{ marginLeft: 8, fontSize: 10, color: theme.accent }}>({item.client_phone})</span>
                            )}
                          </span>
                          <span style={{ fontSize: 11 }}>{item.created_at ? new Date(item.created_at).toLocaleString() : ''}</span>
                        </div>
                        {item.content && <div style={{ fontSize: 13, color: theme.textPrimary, marginTop: 4 }}>{item.content}</div>}
                      </div>
                    </div>
                  ))}
                  {(linkedTimeline.timeline || []).length === 0 && (
                    <div style={{ color: theme.textSecondary, fontSize: 13 }}>{t('detail.no_notes', lang)}</div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Timeline */}
          <div className="card">
            <h3 className="field-label" style={{ fontSize: 14, marginBottom: 20, display: 'flex', alignItems: 'center', gap: 8 }}>
              {t('detail.timeline', lang)} <span style={{ color: theme.textMuted, fontWeight: 500 }}>({timeline.length})</span>
            </h3>
            {timeline.length === 0 ? (
              <div style={{ color: theme.textSecondary, fontSize: 14 }}>{t('detail.no_notes', lang)}</div>
            ) : (
              <div style={{ borderLeft: `2px solid ${theme.cardBorder}`, paddingLeft: 20, marginLeft: 8 }}>
                {timeline.map((n, i) => (
                  <div
                    key={`${n.timeline_type || 'note'}-${n.id}-${i}`}
                    style={{
                      paddingBottom: i < timeline.length - 1 ? 20 : 0,
                      marginBottom: i < timeline.length - 1 ? 20 : 0,
                      borderBottom: i < timeline.length - 1 ? `1px solid ${theme.cardBorder}` : 'none',
                      position: 'relative',
                    }}
                  >
                    {/* Dot on the left border */}
                    <div style={{
                      position: 'absolute', left: -27, top: 4,
                      width: 12, height: 12, borderRadius: '50%',
                      background: n.timeline_type === 'link' ? theme.accent
                        : n.note_type === 'status_change' ? theme.success
                        : n.note_type === 'flag' ? theme.warning
                        : theme.textMuted,
                      border: `2px solid ${theme.cardBg}`,
                      boxShadow: `0 0 0 1px ${theme.cardBorder}`,
                    }} />
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, flexWrap: 'wrap', gap: 8 }}>
                      <span style={{ fontSize: 13, fontWeight: 600, color: theme.textPrimary, display: 'flex', alignItems: 'center', gap: 8 }}>
                        {n.staff_name || n.author_name || t('detail.system', lang)}
                        {n.timeline_type === 'link' && (
                          <span style={{ fontSize: 10, background: theme.warningBg, color: theme.warning, border: `1px solid ${theme.warning}40`, padding: '2px 8px', borderRadius: 8, fontWeight: 700, letterSpacing: 0.5 }}>
                            LINK
                          </span>
                        )}
                        {n.note_type === 'status_change' && n.old_status && n.new_status && (
                          <span style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
                            <span style={{ color: STATUS_COLORS[n.old_status] || theme.textSecondary, fontWeight: 600, background: `${STATUS_COLORS[n.old_status] || theme.textSecondary}20`, padding: '2px 8px', borderRadius: 8 }}>
                              {t(`status.${n.old_status}`, lang) !== `status.${n.old_status}` ? t(`status.${n.old_status}`, lang) : (STATUS_LABELS[n.old_status] || n.old_status)}
                            </span>
                            <span style={{ color: theme.textMuted }}>{'->'}</span>
                            <span style={{ color: STATUS_COLORS[n.new_status] || theme.textPrimary, fontWeight: 600, background: `${STATUS_COLORS[n.new_status] || theme.textSecondary}20`, padding: '2px 8px', borderRadius: 8 }}>
                              {t(`status.${n.new_status}`, lang) !== `status.${n.new_status}` ? t(`status.${n.new_status}`, lang) : (STATUS_LABELS[n.new_status] || n.new_status)}
                            </span>
                          </span>
                        )}
                      </span>
                      <span style={{ fontSize: 12, color: theme.textSecondary, fontWeight: 500 }}>
                        {n.created_at ? new Date(n.created_at).toLocaleString() : ''}
                      </span>
                    </div>
                    {n.content && (
                      <div style={{ fontSize: 14, color: theme.textSecondary, lineHeight: 1.6, background: theme.bgElevated, padding: '12px', borderRadius: 8, border: `1px solid ${theme.cardBorder}` }}>
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
            <h3 className="field-label" style={{ fontSize: 14, marginBottom: 20, display: 'flex', alignItems: 'center', gap: 8 }}>
              {t('comments.title', lang)} <span style={{ color: theme.textMuted, fontWeight: 500 }}>({comments.length})</span>
            </h3>

            {/* Add comment form */}
            <div style={{ marginBottom: 20 }}>
              {replyTo && (
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8,
                  padding: '8px 12px', background: theme.accentLight, borderRadius: 8,
                  fontSize: 12, color: theme.accent, fontWeight: 600,
                }}>
                  <span>{t('comments.reply', lang)}: #{replyTo}</span>
                  <button
                    onClick={() => setReplyTo(null)}
                    style={{ background: 'none', border: 'none', color: theme.textSecondary, cursor: 'pointer', fontSize: 14, fontWeight: 700, padding: '0 4px' }}
                  >
                    x
                  </button>
                </div>
              )}
              <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                <textarea
                  className="input"
                  placeholder={t('comments.placeholder', lang)}
                  value={commentContent}
                  onChange={e => setCommentContent(e.target.value)}
                  rows={2}
                  style={{ flex: 1, resize: 'vertical', fontFamily: 'inherit' }}
                />
                <button
                  className="btn-primary"
                  onClick={handleAddComment}
                  disabled={commentSaving || !commentContent.trim()}
                  style={{ alignSelf: 'flex-start', opacity: commentSaving || !commentContent.trim() ? 0.5 : 1 }}
                >
                  {commentSaving ? t('common.saving', lang) : t('comments.submit', lang)}
                </button>
              </div>
            </div>

            {/* Comment list */}
            {comments.length === 0 ? (
              <div style={{ color: theme.textSecondary, fontSize: 14 }}>{t('comments.no_comments', lang)}</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
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
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

          {/* Deposits */}
          <div className="card">
            <h3 className="field-label" style={{ fontSize: 14, marginBottom: 20, display: 'flex', alignItems: 'center', gap: 8 }}>
              {t('detail.deposits', lang)} <span style={{ color: theme.textMuted, fontWeight: 500 }}>({client.deposits.length})</span>
            </h3>
            {client.deposits.length === 0 ? (
              <div style={{ color: theme.textSecondary, fontSize: 14 }}>{t('detail.no_deposits', lang)}</div>
            ) : (
              <div style={{ overflow: 'hidden', borderRadius: 8, border: `1px solid ${theme.cardBorder}` }}>
                <table className="data-grid-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
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
                        <td style={{ color: theme.success, fontWeight: 600, fontFamily: 'monospace' }}>${d.amount.toFixed(2)} {d.currency}</td>
                        <td style={{ color: theme.textPrimary, fontWeight: 500 }}>{d.platform || '—'}</td>
                        <td style={{ color: theme.textSecondary, fontSize: 12, fontFamily: 'monospace' }}>{d.deposit_date ? new Date(d.deposit_date).toLocaleDateString() : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Linked Clients */}
          <div className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <h3 className="field-label" style={{ fontSize: 14, margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
                {t('detail.links', lang)} <span style={{ color: theme.textMuted, fontWeight: 500 }}>({links.length})</span>
              </h3>
              <button
                className={showLinkForm ? 'btn-secondary' : 'btn-primary'}
                onClick={() => setShowLinkForm(v => !v)}
              >
                {showLinkForm ? t('common.cancel', lang) : `+ ${t('detail.add_link', lang)}`}
              </button>
            </div>

            {showLinkForm && (
              <div style={{ background: theme.bgElevated, borderRadius: 8, border: `1px solid ${theme.cardBorder}`, padding: 20, marginBottom: 20, display: 'flex', flexDirection: 'column', gap: 12 }}>
                <input
                  className="input"
                  type="number"
                  placeholder={t('detail.target_client_id', lang)}
                  value={linkTargetId}
                  onChange={e => setLinkTargetId(e.target.value)}
                  style={{ width: '100%' }}
                />
                <select
                  className="input"
                  value={linkType}
                  onChange={e => setLinkType(e.target.value)}
                  style={{ width: '100%' }}
                >
                  {['related', 'same_person', 'referral', 'family'].map(lt => (
                    <option key={lt} value={lt}>{t(`link_type.${lt}`, lang)}</option>
                  ))}
                </select>
                <input
                  className="input"
                  placeholder={t('detail.link_note', lang)}
                  value={linkNote}
                  onChange={e => setLinkNote(e.target.value)}
                  style={{ width: '100%' }}
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
              <div style={{ color: theme.textSecondary, fontSize: 14 }}>{t('detail.no_links', lang)}</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {links.map(lnk => {
                  const otherId = lnk.client_id_a === clientId ? lnk.client_id_b : lnk.client_id_a
                  const otherPhone = lnk.client_id_a === clientId ? lnk.phone_b : lnk.phone_a
                  return (
                    <div key={lnk.id} style={{ display: 'flex', gap: 8, padding: 12, background: theme.bgElevated, borderRadius: 8, border: `1px solid ${theme.cardBorder}`, fontSize: 14, alignItems: 'center', flexWrap: 'wrap' }}>
                      <span
                        style={{ color: theme.accent, cursor: 'pointer', fontWeight: 700, fontSize: 14 }}
                        onClick={() => nav(`/clients/${otherId}`)}
                      >
                        #{otherId}
                      </span>
                      <span style={{ color: theme.textPrimary }}>{otherPhone}</span>
                      <span style={{
                        fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 8,
                        background: theme.warningBg, color: theme.warning, border: `1px solid ${theme.warning}40`, letterSpacing: 0.5, textTransform: 'uppercase',
                      }}>
                        {t(`link_type.${lnk.link_type}`, lang)}
                      </span>
                      <span style={{ color: theme.textSecondary, flex: 1, fontSize: 13 }}>{lnk.note || ''}</span>
                      <button
                        className="btn-secondary"
                        onClick={() => handleRemoveLink(lnk.id)}
                        style={{ color: theme.danger, fontSize: 12, padding: '4px 12px' }}
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

      {/* Responsive: stack on mobile */}
      <style>{`
        @media (max-width: 768px) {
          .page-container > div:nth-child(3) {
            grid-template-columns: 1fr !important;
          }
        }
      `}</style>
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
    <div style={{
      marginLeft: indent * 20,
      marginTop: indent > 0 ? 8 : 0,
      padding: 16,
      background: isSystem ? theme.bg : theme.cardBg,
      border: `1px solid ${theme.cardBorder}`,
      borderLeft: indent > 0 ? `3px solid ${theme.accent}` : `1px solid ${theme.cardBorder}`,
      borderRadius: 8,
      opacity: isSystem ? 0.75 : 1,
    }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, flexWrap: 'wrap', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 13, fontWeight: 700, color: isSystem ? theme.textMuted : theme.textPrimary }}>
            {isSystem ? t('comments.system', lang) : c.staff_name}
          </span>
          {indent > 0 && (
            <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 8, background: theme.accentLight, color: theme.accent, fontWeight: 600 }}>
              {t('comments.reply', lang)}
            </span>
          )}
          {c.updated_at && !isDeleted && (
            <span style={{ fontSize: 11, color: theme.textMuted, fontStyle: 'italic' }}>{t('comments.edited', lang)}</span>
          )}
        </div>
        <span style={{ fontSize: 12, color: theme.textSecondary, fontWeight: 500 }}>
          {c.created_at ? new Date(c.created_at).toLocaleString() : ''}
        </span>
      </div>

      {/* Content */}
      {isEditing ? (
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
          <textarea
            className="input"
            value={editContent}
            onChange={e => onEditContentChange(e.target.value)}
            rows={2}
            style={{ flex: 1, resize: 'vertical', fontFamily: 'inherit' }}
          />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <button className="btn-primary" onClick={onSaveEdit}
              style={{ padding: '8px 12px', fontSize: 12 }}>
              {t('common.save', lang)}
            </button>
            <button className="btn-secondary" onClick={onCancelEdit}
              style={{ padding: '8px 12px', fontSize: 12 }}>
              {t('common.cancel', lang)}
            </button>
          </div>
        </div>
      ) : (
        <div style={{
          fontSize: 14, lineHeight: 1.6,
          color: isDeleted ? theme.textMuted : (isSystem ? theme.textSecondary : theme.textPrimary),
          fontStyle: isDeleted ? 'italic' : 'normal',
        }}>
          {isDeleted ? t('comments.deleted', lang) : c.content}
        </div>
      )}

      {/* Actions */}
      {!isSystem && !isDeleted && !isEditing && (
        <div style={{ display: 'flex', gap: 12, marginTop: 12 }}>
          <button onClick={onReply} style={{ background: 'none', border: 'none', color: theme.accent, fontSize: 12, fontWeight: 600, cursor: 'pointer', padding: 0 }}>
            {t('comments.reply', lang)}
          </button>
          {isOwn && (
            <>
              <button onClick={onStartEdit} style={{ background: 'none', border: 'none', color: theme.textSecondary, fontSize: 12, fontWeight: 600, cursor: 'pointer', padding: 0 }}>
                {t('comments.edit', lang)}
              </button>
              <button onClick={onDelete} style={{ background: 'none', border: 'none', color: theme.danger, fontSize: 12, fontWeight: 600, cursor: 'pointer', padding: 0 }}>
                {t('comments.delete', lang)}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
}
