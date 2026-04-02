import type { AuthState } from '../types'
import { t, getLang } from '../i18n'

interface Props {
  auth: AuthState | null
}

export default function ScopeBanner({ auth }: Props) {
  const lang = getLang()
  if (!auth || auth.role === 'owner') return null

  const message =
    auth.role === 'admin'
      ? t('scope.viewing_team', lang).replace('{scope}', auth.team_scope ?? t('common.all', lang))
      : t('scope.viewing_my', lang)

  return (
    <div className="scope-banner">
      <span className="scope-banner-icon">◈</span>
      <span className="scope-banner-text">{message}</span>
    </div>
  )
}
