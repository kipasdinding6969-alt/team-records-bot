import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import type { Client, FunnelStage } from '../types'
import { STATUS_COLORS, STATUS_LABELS } from '../types'
import { Empty, PageHeader, Spinner } from '../components/SharedUI'
import { DataGrid, formatPhone, Column } from '../components/DataGrid'
import { useTheme } from '../ThemeContext'
import { t, getLang } from '../i18n'

export default function Pipeline() {
  const { theme } = useTheme()
  const [error, setError] = useState('');
  const lang = getLang()
  const [funnel, setFunnel] = useState<FunnelStage[]>([])
  const [pipeline, setPipeline] = useState<Record<string, Client[]>>({})
  const [selected, setSelected] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const nav = useNavigate()

  useEffect(() => {
    Promise.all([api.funnel(), api.pipeline()])
      .then(([f, p]) => {
        setFunnel(f)
        setPipeline(p)
        if (f.length > 0) setSelected(f[0].stage)
      })
      .catch(e => { console.error(e); setError(t('common.update_failed', lang as any)); })
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Spinner />

  const selectedClients = selected ? pipeline[selected] || [] : []

  return (
    <div className="page-container">
      <PageHeader title={t('pipeline.title', lang)} sub={t('pipeline.description', lang)} />

      {error && <div className="alert alert-error">{error}</div>}

      {/* Funnel stages */}
      <div className="pipeline-grid">
        {funnel.map(stage => {
          const isSelected = selected === stage.stage;
          const color = STATUS_COLORS[stage.stage] || theme.textSecondary;
          return (
            <button
              className={`card pipeline-stage${isSelected ? ' pipeline-stage--selected' : ''}`}
              key={stage.stage}
              onClick={() => setSelected(stage.stage)}
              style={{ '--stage-color': color } as React.CSSProperties}
            >
              <div className="metric-value">
                {stage.count}
              </div>
              <div className="metric-label text-primary">
                {STATUS_LABELS[stage.stage] || stage.stage}
              </div>
              <span className="pill-badge pipeline-pct">
                {stage.pct}%
              </span>
            </button>
          )
        })}
      </div>

      {/* Filtered client list */}
      {selected && (
        <div className="card pipeline-card" style={{ '--stage-color': STATUS_COLORS[selected] || theme.textSecondary } as React.CSSProperties}>
          <div className="section-title pipeline-header">
            <div className="pipeline-dot" />
            {STATUS_LABELS[selected] || selected} <span className="text-muted pipeline-count">({selectedClients.length} {t('org.members', lang)})</span>
          </div>
          {selectedClients.length === 0 ? (
            <Empty />
          ) : (() => {
            const columns: Column<Client>[] = [
                { key: 'phone', label: t('clients.phone', lang), monospace: true, render: c => formatPhone(c.phone) },
                { key: 'source', label: t('clients.source', lang), render: c => <span className="text-secondary">{c.source || '—'}</span> },
                { key: 'frontdesk', label: t('clients.owner', lang), render: c => c.frontdesk_name || '—' },
                { key: 'team', label: t('detail.team', lang), render: c => <span className="text-secondary">{c.team || '—'}</span> },
                { key: 'deposit', label: t('clients.deposit', lang), monospace: true, render: c => c.total_deposited > 0 ? <span className="text-success">${c.total_deposited.toLocaleString()}</span> : <span className="text-secondary">—</span> },
                { key: 'created_at', label: t('clients.created_at', lang), monospace: true, render: c => <span className="text-secondary fs-12">{c.created_at ? new Date(c.created_at).toLocaleDateString() : '—'}</span> }
            ]
            return <DataGrid columns={columns} data={selectedClients} onRowClick={c => nav(`/clients/${c.id}`)} />
          })()}
        </div>
      )}
    </div>
  )
}
