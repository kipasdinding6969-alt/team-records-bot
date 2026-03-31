import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { clearAuthState, getAuthState } from '../api'
import ScopeBanner from './ScopeBanner'
import type { AuthState } from '../types'
import { ROLE_COLORS, ROLE_LABELS } from '../types'

const NAV_ALL = [
  { path: '/', label: '仪表盘', icon: '◈', end: true },
  { path: '/pipeline', label: '漏斗管道', icon: '▼', end: false },
  { path: '/team', label: '团队绩效', icon: '◉', end: false },
  { path: '/clients', label: '客户列表', icon: '≡', end: false },
  { path: '/reports', label: '报告分析', icon: '⌬', end: false },
  { path: '/users', label: '用户管理', icon: '◎', end: false, adminOnly: true },
]

function buildNav(auth: AuthState | null) {
  if (!auth) return NAV_ALL.filter(n => !n.adminOnly)
  if (auth.role === 'member') {
    return NAV_ALL.filter(n => n.path === '/' || n.path === '/clients')
  }
  return NAV_ALL
}

const S = {
  root: {
    display: 'flex',
    minHeight: '100vh',
    background: '#1a1a2e',
    color: '#e0e0e0',
  } as React.CSSProperties,
  sidebar: {
    width: 220,
    background: '#16213e',
    display: 'flex',
    flexDirection: 'column' as const,
    borderRight: '1px solid #0f3460',
    flexShrink: 0,
  },
  brand: {
    padding: '20px 20px 14px',
    borderBottom: '1px solid #0f3460',
  },
  brandTitle: { fontSize: 16, fontWeight: 700, color: '#e0e0e0', letterSpacing: 0.5 },
  brandSub: { fontSize: 11, color: '#7f848e', marginTop: 3 },
  userInfo: {
    padding: '10px 20px 14px',
    borderBottom: '1px solid #0f3460',
  },
  userName: { fontSize: 13, color: '#e0e0e0', fontWeight: 600 },
  nav: { flex: 1, padding: '12px 0' },
  main: { flex: 1, overflow: 'auto', padding: 24, minWidth: 0 },
  footer: { padding: '16px 20px', borderTop: '1px solid #0f3460' },
  logoutBtn: {
    width: '100%',
    padding: '8px',
    background: 'transparent',
    border: '1px solid #7f848e',
    color: '#7f848e',
    borderRadius: 4,
    cursor: 'pointer',
    fontSize: 12,
    letterSpacing: 0.5,
  },
}

export default function Layout() {
  const nav = useNavigate()
  const auth = getAuthState()

  function logout() {
    clearAuthState()
    nav('/login')
  }

  const navItems = buildNav(auth)

  return (
    <div style={S.root}>
      <aside style={S.sidebar}>
        <div style={S.brand}>
          <div style={S.brandTitle}>团队记录</div>
          <div style={S.brandSub}>Manager Dashboard</div>
        </div>

        {auth && (
          <div style={S.userInfo}>
            <div style={S.userName}>{auth.display_name}</div>
            <div style={{ marginTop: 4, display: 'flex', alignItems: 'center', gap: 6 }}>
              <span
                style={{
                  fontSize: 10,
                  fontWeight: 700,
                  color: ROLE_COLORS[auth.role] || '#7f848e',
                  background: `${ROLE_COLORS[auth.role] || '#7f848e'}22`,
                  border: `1px solid ${ROLE_COLORS[auth.role] || '#7f848e'}`,
                  borderRadius: 3,
                  padding: '1px 6px',
                  letterSpacing: 0.5,
                  textTransform: 'uppercase',
                }}
              >
                {ROLE_LABELS[auth.role] || auth.role}
              </span>
              {auth.team_scope && (
                <span style={{ fontSize: 11, color: '#7f848e' }}>{auth.team_scope}</span>
              )}
            </div>
          </div>
        )}

        <nav style={S.nav}>
          {navItems.map(item => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.end}
              style={({ isActive }) => ({
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '11px 20px',
                color: isActive ? '#e0e0e0' : '#7f848e',
                background: isActive ? '#0f3460' : 'transparent',
                textDecoration: 'none',
                borderLeft: `3px solid ${isActive ? '#00b894' : 'transparent'}`,
                fontSize: 13,
                transition: 'all 0.15s',
              })}
            >
              <span style={{ fontSize: 14, minWidth: 18, textAlign: 'center' }}>{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
        <div style={S.footer}>
          <button onClick={logout} style={S.logoutBtn}>
            退出登录
          </button>
        </div>
      </aside>
      <main style={S.main}>
        <ScopeBanner auth={auth} />
        <Outlet />
      </main>
    </div>
  )
}
