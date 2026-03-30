import { useState, useRef } from 'react'
import { Client, PipelineData } from '../types'
import { t, statusLabel } from '../i18n'
import { api } from '../api'
import ClientCard from './ClientCard'
import ClientDetail from './ClientDetail'

const ACTIVE_COLUMNS = ['new', 'contacted', 'replied', 'registered', 'training']
const ALL_COLUMNS = [...ACTIVE_COLUMNS, 'ordered', 'scheduled', 'ghosted', 'withdrew', 'blocked', 'dead']

interface Props {
  data: PipelineData
  lang: string
  onRefresh: () => void
  showToast: (msg: string) => void
}

export default function KanbanBoard({ data, lang, onRefresh, showToast }: Props) {
  const [selectedClientId, setSelectedClientId] = useState<number | null>(null)
  const [localData, setLocalData] = useState<PipelineData>(data)
  const dragClientRef = useRef<{ client: Client; fromStatus: string } | null>(null)
  const [dragOverStatus, setDragOverStatus] = useState<string | null>(null)

  // Update local data when prop changes
  if (data !== localData && !dragClientRef.current) {
    setLocalData(data)
  }

  function handleDragStart(e: React.DragEvent, client: Client) {
    dragClientRef.current = { client, fromStatus: client.status }
    e.dataTransfer.effectAllowed = 'move'
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred('medium')
  }

  function handleDragEnd() {
    dragClientRef.current = null
    setDragOverStatus(null)
  }

  function handleDragOver(e: React.DragEvent, status: string) {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    setDragOverStatus(status)
  }

  async function handleDrop(e: React.DragEvent, toStatus: string) {
    e.preventDefault()
    setDragOverStatus(null)
    const drag = dragClientRef.current
    if (!drag || drag.fromStatus === toStatus) return

    const { client } = drag
    // Optimistic update
    setLocalData(prev => {
      const next = { ...prev }
      next[drag.fromStatus] = (next[drag.fromStatus] ?? []).filter(c => c.id !== client.id)
      const updated = { ...client, status: toStatus }
      next[toStatus] = [updated, ...(next[toStatus] ?? [])]
      return next
    })

    try {
      await api.updateStatus(client.id, toStatus)
      showToast(t('success_updated', lang))
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred('success')
    } catch {
      showToast(t('error_update', lang))
      setLocalData(data) // revert
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred('error')
    }
    dragClientRef.current = null
  }

  const columns = ALL_COLUMNS.filter(s => (localData[s]?.length ?? 0) > 0 || ACTIVE_COLUMNS.includes(s))

  return (
    <div className="kanban-board">
      {columns.map(status => {
        const clients = localData[status] ?? []
        return (
          <div
            key={status}
            className={`kanban-column status-${status}`}
            onDragOver={e => handleDragOver(e, status)}
            onDrop={e => handleDrop(e, status)}
          >
            <div className="column-header">
              <div className="column-dot" />
              <span className="column-title">{statusLabel(status, lang)}</span>
              <span className="column-count">{clients.length}</span>
            </div>
            <div className={`column-cards ${dragOverStatus === status ? 'drag-over' : ''}`}>
              {clients.length === 0 ? (
                <div className="column-empty">—</div>
              ) : clients.map(client => (
                <ClientCard
                  key={client.id}
                  client={client}
                  lang={lang}
                  onClick={() => setSelectedClientId(client.id)}
                  onDragStart={e => handleDragStart(e, client)}
                  onDragEnd={handleDragEnd}
                />
              ))}
            </div>
          </div>
        )
      })}

      {selectedClientId !== null && (
        <ClientDetail
          clientId={selectedClientId}
          lang={lang}
          onClose={() => setSelectedClientId(null)}
          onUpdated={() => { setSelectedClientId(null); onRefresh() }}
          showToast={showToast}
        />
      )}
    </div>
  )
}
