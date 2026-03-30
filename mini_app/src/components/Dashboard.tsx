import { Stats } from '../types'
import { t, statusLabel } from '../i18n'

const PIPELINE_STATUSES = [
  'new', 'contacted', 'replied', 'registered', 'training', 'ordered',
]

interface Props {
  stats: Stats
  lang: string
}

export default function Dashboard({ stats, lang }: Props) {
  const maxCount = Math.max(1, ...PIPELINE_STATUSES.map(s => stats.by_status[s] ?? 0))

  return (
    <div className="dashboard">
      <div className="dashboard-title">{t('today_title', lang)}</div>

      <div className="stats-grid">
        <div className="stat-card highlight">
          <span className="stat-value">{stats.today_new}</span>
          <span className="stat-label">{t('today_new_leads', lang)}</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">{stats.today_contacts}</span>
          <span className="stat-label">{t('today_contacts', lang)}</span>
        </div>
        <div className="stat-card gold">
          <span className="stat-value">{stats.today_orders}</span>
          <span className="stat-label">{t('today_orders', lang)}</span>
        </div>
        <div className={`stat-card ${stats.overdue_followups > 0 ? 'warning' : ''}`}>
          <span className="stat-value">{stats.overdue_followups}</span>
          <span className="stat-label">{t('today_overdue', lang)}</span>
        </div>
        <div className="stat-card success">
          <span className="stat-value">{stats.total_active}</span>
          <span className="stat-label">{t('today_active', lang)}</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">{stats.total_clients}</span>
          <span className="stat-label">{t('today_total', lang)}</span>
        </div>
      </div>

      <div className="pipeline-section">
        <div className="pipeline-section-title">{t('today_pipeline', lang)}</div>
        {PIPELINE_STATUSES.map(status => {
          const count = stats.by_status[status] ?? 0
          const pct = (count / maxCount) * 100
          return (
            <div key={status} className={`pipeline-row status-${status}`}>
              <span className="pipeline-row-label">{statusLabel(status, lang)}</span>
              <div className="pipeline-bar-bg">
                <div className="pipeline-bar-fill" style={{ width: `${pct}%` }} />
              </div>
              <span className="pipeline-row-count">{count}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
