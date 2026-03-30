import { Client } from '../types'
import { t, statusLabel } from '../i18n'

interface Props {
  client: Client
  lang: string
  onClick: () => void
  onDragStart: (e: React.DragEvent) => void
  onDragEnd: (e: React.DragEvent) => void
}

function isOverdue(client: Client): boolean {
  if (!client.next_followup) return false
  return new Date(client.next_followup) < new Date()
}

function formatPhone(phone: string): string {
  return phone.replace(/(\d{4})(\d{4})(\d+)/, '$1 $2 $3') ?? phone
}

export default function ClientCard({ client, lang, onClick, onDragStart, onDragEnd }: Props) {
  const overdue = isOverdue(client)

  return (
    <div
      className={`client-card status-${client.status}`}
      draggable
      onClick={onClick}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
    >
      <div className="card-phone">{formatPhone(client.phone)}</div>
      <div className="card-meta">
        {client.frontdesk_name && (
          <div className="card-meta-row">
            <span>👤</span>
            <span>{client.frontdesk_name}</span>
          </div>
        )}
        {client.source && (
          <div className="card-meta-row">
            <span>📌</span>
            <span>{client.source}</span>
          </div>
        )}
      </div>
      {client.total_deposited > 0 && (
        <div className="card-deposit">
          💰 {client.total_deposited.toLocaleString()}
        </div>
      )}
      {overdue && (
        <div className="card-overdue">⚠️ {t('client_overdue', lang)}</div>
      )}
    </div>
  )
}
