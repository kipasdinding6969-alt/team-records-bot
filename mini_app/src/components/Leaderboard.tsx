import { LeaderboardEntry } from '../types'
import { t } from '../i18n'

interface Props {
  entries: LeaderboardEntry[]
  lang: string
}

export default function Leaderboard({ entries, lang }: Props) {
  return (
    <div className="leaderboard">
      <div className="lb-title">{t('lb_title', lang)}</div>

      {entries.length === 0 ? (
        <div style={{ color: 'var(--tg-hint)', textAlign: 'center', padding: 32 }}>
          {t('loading', lang)}
        </div>
      ) : entries.map((entry, i) => (
        <div key={entry.id} className="lb-card">
          <div className={`lb-rank rank-${i + 1}`}>{i + 1}</div>
          <div className="lb-info">
            <div className="lb-name">{entry.display_name}</div>
            {entry.team && <div className="lb-team">团队: {entry.team}</div>}
            {entry.badges.length > 0 && (
              <div className="lb-badges">
                {entry.badges.slice(0, 5).map(b => b.emoji).join('')}
              </div>
            )}
          </div>
          <div className="lb-stats">
            <div className="lb-xp">{entry.xp_total.toLocaleString()} XP</div>
            {entry.current_streak > 0 && (
              <div className="lb-streak">🔥 {entry.current_streak}天</div>
            )}
            <div className="lb-today">
              {t('lb_leads', lang)}: {entry.today_leads} · {t('lb_orders', lang)}: {entry.today_orders}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
