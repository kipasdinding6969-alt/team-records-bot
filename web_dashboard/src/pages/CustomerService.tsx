import { useState } from 'react'
import { api } from '../api'
import { useTheme } from '../ThemeContext'
import { t, getLang } from '../i18n'
import { PageHeader, Spinner, Empty } from '../components/SharedUI'

export default function CustomerService() {
  const { theme } = useTheme()
  const [error, setError] = useState('')
  const lang = getLang()

  const [search, setSearch] = useState('')
  const [clients, setClients] = useState<any[]>([])
  const [selectedClient, setSelectedClient] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [noteContent, setNoteContent] = useState('')
  const [noteSaving, setNoteSaving] = useState(false)

  const handleSearch = async (e?: React.FormEvent) => {
    if (e) e.preventDefault()
    if (!search.trim()) return
    setLoading(true)
    try {
      const res = await api.clients({ search: search.trim() })
      setClients(res.clients)
      if (res.clients.length === 1) {
         await loadClientDetail(res.clients[0].id)
      } else {
         setSelectedClient(null)
      }
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const loadClientDetail = async (id: number) => {
    setLoading(true)
    try {
      const detail = await api.clientDetail(id)
      setSelectedClient(detail)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const handleAddNote = async () => {
    if (!noteContent.trim() || !selectedClient) return
    setNoteSaving(true)
    try {
      await api.addClientNote(selectedClient.id, { content: noteContent.trim(), note_type: 'comment' })
      setNoteContent('')
      loadClientDetail(selectedClient.id)
    } catch (e) {
      setError(t('common.failed', lang)); setTimeout(() => setError(''), 3000)
    } finally {
      setNoteSaving(false)
    }
  }

  return (
    <div className="page-container">
      {error && <div className="alert alert-error">{error}</div>}
      <PageHeader title={t('cs.title', lang)} />

      <div style={{ display: 'flex', gap: 20, alignItems: 'flex-start', flexWrap: 'wrap' }}>
        {/* LEFT PANEL: Search and List */}
        <div style={{ flex: '1 1 350px', minWidth: 300, display: 'flex', flexDirection: 'column', gap: 20 }}>
          <form onSubmit={handleSearch} style={{ display: 'flex', gap: 12 }}>
            <input
              className="input"
              style={{ flex: 1 }}
              placeholder={t('cs.quick_search', lang)}
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            <button type="submit" className="btn-primary">
              {t('common.search', lang)}
            </button>
          </form>

          <div className="card">
            <h3 className="section-title" style={{ margin: '0 0 12px' }}>{t('cs.search_results', lang)}</h3>
            {loading && !selectedClient ? <Spinner /> : clients.length === 0 ? <Empty /> : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {clients.map(c => (
                  <div
                    key={c.id}
                    onClick={() => loadClientDetail(c.id)}
                    style={{
                      padding: 12, borderRadius: 8, cursor: 'pointer',
                      background: selectedClient?.id === c.id ? theme.accentLight : theme.bgElevated,
                      border: `1px solid ${selectedClient?.id === c.id ? theme.accent : theme.cardBorder}`,
                      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 600, color: theme.textPrimary }}>{c.phone}</div>
                      <div style={{ fontSize: 12, color: theme.textSecondary }}>{c.frontdesk_name || t('org.unassigned', lang)}</div>
                    </div>
                    <span className="badge-info" style={{ fontSize: 12 }}>
                      {c.status}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* RIGHT PANEL: Detail Inline */}
        <div className="card" style={{ flex: '2 1 500px' }}>
          {selectedClient ? (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
                <div>
                  <h2 style={{ fontSize: 24, fontWeight: 700, margin: '0 0 8px', color: theme.textPrimary }}>{selectedClient.phone}</h2>
                  <div style={{ display: 'flex', gap: 12, fontSize: 13, color: theme.textSecondary }}>
                    <span>{t('cs.owner', lang)}: {selectedClient.frontdesk_name || '\u2014'}</span>
                    <span>{t('cs.status', lang)}: {selectedClient.status}</span>
                  </div>
                </div>
                <button className="btn-secondary" style={{ height: 32, padding: '0 12px', fontSize: 13 }}
                  onClick={() => { setError(t('common.coming_soon', lang) || 'Coming soon'); setTimeout(() => setError(''), 3000) }}
                >
                  {t('cs.handoff', lang)}
                </button>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 20 }}>
                <textarea
                  className="input"
                  value={noteContent}
                  onChange={e => setNoteContent(e.target.value)}
                  placeholder={t('cs.add_note', lang)}
                  style={{ resize: 'vertical', minHeight: 80, height: 'auto' }}
                />
                <button onClick={handleAddNote} disabled={noteSaving || !noteContent.trim()} className="btn-primary" style={{ alignSelf: 'flex-end' }}>
                  {noteSaving ? t('common.saving', lang) : t('cs.add_note', lang)}
                </button>
              </div>

              <h3 className="section-title" style={{ margin: '0 0 12px' }}>{t('cs.recent_interactions', lang)}</h3>
              {selectedClient.notes && selectedClient.notes.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  {selectedClient.notes.map((n: any) => (
                    <div key={n.id} style={{ background: theme.bgElevated, padding: 20, borderRadius: 8, border: `1px solid ${theme.cardBorder}` }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                         <span style={{ fontWeight: 600, fontSize: 13, color: theme.textPrimary }}>{n.staff_name || 'System'}</span>
                         <span style={{ fontSize: 12, color: theme.textSecondary }}>{new Date(n.created_at).toLocaleString()}</span>
                      </div>
                      <div style={{ fontSize: 14, color: theme.textSecondary }}>{n.content}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <Empty label={t("cs.no_interactions", lang)} />
              )}
            </div>
          ) : (
             <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 200 }}>
               <Empty label={t("cs.select_client", lang)} />
             </div>
          )}
        </div>
      </div>
    </div>
  )
}
