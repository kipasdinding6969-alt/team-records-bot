import type { AuthState } from '../types'
import { useTheme } from '../ThemeContext'
import { t, getLang } from '../i18n'

interface Props {
  auth: AuthState | null
}

export default function ScopeBanner({ auth }: Props) {
  const { theme } = useTheme()
  const lang = getLang()
  if (!auth || auth.role === 'owner') return null

  const message =
    auth.role === 'admin'
      ? t('scope.viewing_team', lang).replace('{scope}', auth.team_scope ?? t('common.all', lang))
      : t('scope.viewing_my', lang)

  return (
    <div
      style={{
        background: theme.activeNav,
        borderLeft: `3px solid ${theme.accent}`,
        padding: '8px 14px',
        marginBottom: 20,
        borderRadius: '0 8px 8px 0',
        display: 'flex',
        alignItems: 'center',
        gap: 8,
      }}
    >
      <span style={{ fontSize: 13, color: theme.accent, fontWeight: 600 }}>◈</span>
      <span style={{ fontSize: 13, color: theme.textPrimary }}>{message}</span>
    </div>
  )
}
