import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { clearToken } from '../api'

const NAV = [
  { path: '/', label: '仪表盘', icon: '◈', end: true },
  { path: '/pipeline', label: '漏斗管道', icon: '▼', end: false },
  { path: '/team', label: '团队绩效', icon: '◉', end: false },
  { path: '/clients', label: '客户列表', icon: '≡', end: false },
  { path: '/reports', label: '报告分析', icon: '⌬', end: false },
]

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
    padding: '20px 20px 16px',
    borderBottom: '1px solid #0f3460',
  },
  brandTitle: { fontSize: 16, fontWeight: 700, color: '#e0e0e0', letterSpacing: 0.5 },
  brandSub: { fontSize: 11, color: '#7f848e', marginTop: 3 },
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

  function logout() {
    clearToken()
    nav('/login')
  }

  return (
    <div style={S.root}>
      <aside style={S.sidebar}>
        <div style={S.brand}>
          <div style={S.brandTitle}>团队记录</div>
          <div style={S.brandSub}>Manager Dashboard</div>
        </div>
        <nav style={S.nav}>
          {NAV.map(item => (
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
        <Outlet />
      </main>
    </div>
  )
}
