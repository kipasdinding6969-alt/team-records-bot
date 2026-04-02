import { useState, useEffect } from 'react'
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

  useEffect(() => { if (error) { const id = setTimeout(() => setError(''), 5000); return () => clearTimeout(id) } }, [error])

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
      setError(t('common.error', lang))
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
      setError(t('common.error', lang))
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

      <div className="content-split">
        {/* LEFT PANEL: Search and List */}
        <div className="content-split-sidebar d-flex flex-col gap-20">
          <form onSubmit={handleSearch} className="d-flex gap-12">
            <input
              className="input flex-1"
              placeholder={t('cs.quick_search', lang)}
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            <button type="submit" className="btn-primary">
              {t('common.search', lang)}
            </button>
          </form>

          <div className="card">
            <h3 className="section-title mb-12">{t('cs.search_results', lang)}</h3>
            {loading && !selectedClient ? <Spinner /> : clients.length === 0 ? <Empty /> : (
              <div className="d-flex flex-col gap-8">
                {clients.map(c => (
                  <div
                    key={c.id}
                    onClick={() => loadClientDetail(c.id)}
                    className={`search-result-item ${selectedClient?.id === c.id ? 'active' : ''}`}
                  >
                    <div>
                      <div className="heading-sm">{c.phone}</div>
                      <div className="caption">{c.frontdesk_name || t('org.unassigned', lang)}</div>
                    </div>
                    <span className="badge-info caption">
                      {c.status}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* RIGHT PANEL: Detail Inline */}
        <div className="card content-split-main">
          {selectedClient ? (
            <div>
              <div className="d-flex justify-between align-start mb-20">
                <div>
                  <h2 className="heading-lg mb-8">{selectedClient.phone}</h2>
                  <div className="d-flex gap-12 caption">
                    <span>{t('cs.owner', lang)}: {selectedClient.frontdesk_name || '\u2014'}</span>
                    <span>{t('cs.status', lang)}: {selectedClient.status}</span>
                  </div>
                </div>
              </div>

              <div className="d-flex flex-col gap-12 mb-20">
                <textarea
                  className="input textarea-resize-v"
                  value={noteContent}
                  onChange={e => setNoteContent(e.target.value)}
                  placeholder={t('cs.add_note', lang)}
                />
                <button onClick={handleAddNote} disabled={noteSaving || !noteContent.trim()} className="btn-primary align-self-end">
                  {noteSaving ? t('common.saving', lang) : t('cs.add_note', lang)}
                </button>
              </div>

              <h3 className="section-title mb-12">{t('cs.recent_interactions', lang)}</h3>
              {selectedClient.notes && selectedClient.notes.length > 0 ? (
                <div className="d-flex flex-col gap-12">
                  {selectedClient.notes.map((n: any) => (
                    <div key={n.id} className="note-card">
                      <div className="d-flex justify-between mb-8">
                         <span className="label-sm">{n.staff_name || 'System'}</span>
                         <span className="caption">{new Date(n.created_at).toLocaleString()}</span>
                      </div>
                      <div className="subtitle">{n.content}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <Empty label={t("cs.no_interactions", lang)} />
              )}
            </div>
          ) : (
             <div className="d-flex align-center justify-center min-h-200">
               <Empty label={t("cs.select_client", lang)} />
             </div>
          )}
        </div>
      </div>
    </div>
  )
}
