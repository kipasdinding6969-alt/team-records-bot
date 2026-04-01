import type { AuthState } from '../types'
import { useTheme } from '../ThemeContext'

interface Props {
  auth: AuthState | null
}

export default function ScopeBanner({ auth }: Props) {
  const { theme } = useTheme()
  if (!auth || auth.role === 'owner') return null

  const message =
    auth.role === 'admin'
      ? `查看数据: ${auth.team_scope ?? '全部'} 团队`
      : '查看数据: 我的客户'

  return (
    <div
      style={{
        background: theme.activeNav,
        borderLeft: '3px solid #00b894',
        padding: '8px 14px',
        marginBottom: 20,
        borderRadius: '0 4px 4px 0',
        display: 'flex',
        alignItems: 'center',
        gap: 8,
      }}
    >
      <span style={{ fontSize: 13, color: '#00b894', fontWeight: 600 }}>◈</span>
      <span style={{ fontSize: 13, color: '#e0e0e0' }}>{message}</span>
    </div>
  )
}
