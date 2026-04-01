import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { clearAuthState, getAuthState } from '../api'
import ScopeBanner from './ScopeBanner'
import type { AuthState } from '../types'
import { ROLE_COLORS } from '../types'
import { t, getLang, setLang } from '../i18n'
import { useTheme } from '../ThemeContext'

interface NavItem {
  path: string
  labelKey: string
  icon: string
  end: boolean
  adminOnly?: boolean
}

const NAV_ALL: NavItem[] = [
  { path: '/', labelKey: 'nav.dashboard', icon: '◈', end: true },
  { path: '/pipeline', labelKey: 'nav.pipeline', icon: '▼', end: false },
  { path: '/team', labelKey: 'nav.team', icon: '◉', end: false },
  { path: '/clients', labelKey: 'nav.clients', icon: '≡', end: false },
  { path: '/phone-lookup', labelKey: 'nav.phone_lookup', icon: '☎', end: false },
  { path: '/reports', labelKey: 'nav.reports', icon: '⌬', end: false },
  { path: '/performance', labelKey: 'nav.performance', icon: '⊞', end: false },
  { path: '/org-chart', labelKey: 'nav.org_chart', icon: '⊡', end: false, adminOnly: true },
  { path: '/permissions', labelKey: 'nav.permissions', icon: '🔐', end: false, adminOnly: true },
  { path: '/users', labelKey: 'nav.users', icon: '◎', end: false, adminOnly: true },
]

function buildNav(auth: AuthState | null) {
  if (!auth) return NAV_ALL.filter(n => !n.adminOnly)
  if (auth.role === 'member') {
    return NAV_ALL.filter(n => n.path === '/' || n.path === '/clients' || n.path === '/phone-lookup' || n.path === '/performance')
  }
  return NAV_ALL
}

export default function Layout() {
  const nav = useNavigate()
  const auth = getAuthState()
  const { theme, mode: themeMode, toggleTheme } = useTheme()
  const [lang, setLangState] = useState(getLang())

  function toggleLang() {
    const next = lang === 'zh' ? 'en' : 'zh'
    setLang(next as any)
    setLangState(next as any)
  }

  function logout() {
    clearAuthState()
    nav('/login')
  }

  const navItems = buildNav(auth)
  const roleLabel = t(`role.${auth?.role || 'member'}`, lang as any)

  return (
    <div style={{
      display: 'flex',
      minHeight: '100vh',
      background: theme.bg,
      backgroundImage: theme.glowAmbient,
      backgroundAttachment: 'fixed',
      color: theme.textPrimary,
      fontFamily: theme.fontFamily,
    }}>
      <style>{`
        /* Hyper-Creative Global CSS */
        ::selection {
          background: ${theme.accentLight};
          color: ${theme.accent};
        }
        ::-webkit-scrollbar {
          width: 8px;
          height: 8px;
        }
        ::-webkit-scrollbar-track {
          background: transparent;
        }
        ::-webkit-scrollbar-thumb {
          background: ${theme.cardBorder};
          border-radius: 9999px;
        }
        ::-webkit-scrollbar-thumb:hover {
          background: ${theme.textMuted};
        }

        .glass-panel {
          background: ${theme.glassBg} !important;
          backdrop-filter: blur(16px);
          -webkit-backdrop-filter: blur(16px);
          border: 1px solid ${theme.glassBorder} !important;
        }

        .glass-card {
          background: ${theme.glassBg} !important;
          backdrop-filter: blur(12px);
          -webkit-backdrop-filter: blur(12px);
          border: 1px solid ${theme.glassBorder} !important;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .glass-card:hover {
          transform: translateY(-2px);
          box-shadow: ${theme.shadowHover} !important;
          border-color: ${theme.accentLight} !important;
        }

        .glass-btn {
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
          position: relative;
          overflow: hidden;
        }
        .glass-btn:hover {
          transform: translateY(-1px);
          box-shadow: ${theme.shadowHover} !important;
          filter: brightness(1.1);
        }
        .glass-btn:active {
          transform: translateY(1px);
        }

        .glass-table-row {
          transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .glass-table-row:hover {
          background: ${theme.navHoverBg} !important;
          transform: translateY(-1px);
          box-shadow: 0 4px 12px rgba(0,0,0,0.05);
        }

        .pill-badge {
          border-radius: 9999px !important;
          padding: 4px 10px !important;
          font-weight: 600 !important;
          letter-spacing: 0.02em;
        }

        .empty-state {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 64px 24px;
          text-align: center;
          color: ${theme.textSecondary};
          background: ${theme.glassBg};
          border-radius: 16px;
          border: 1px dashed ${theme.cardBorder};
          backdrop-filter: blur(12px);
        }

        .nav-inactive {
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .nav-inactive:hover {
          background: ${theme.navHoverBg} !important;
          color: ${theme.textPrimary} !important;
          transform: translateX(4px);
        }

        .nav-active {
          position: relative;
          color: ${theme.activeNavText} !important;
          background: ${theme.activeNav} !important;
          font-weight: 600 !important;
          box-shadow: inset 3px 0 0 ${theme.accent};
        }
      `}</style>

      <aside className="glass-panel" style={{
        width: 260,
        display: 'flex',
        flexDirection: 'column',
        flexShrink: 0,
        zIndex: 20,
        borderRight: `1px solid ${theme.glassBorder}`,
      }}>
        <div style={{ padding: '24px 24px 16px', display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 10, background: theme.accent, 
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: '#fff', fontWeight: 'bold', fontSize: 18,
            boxShadow: `0 4px 16px ${theme.accentLight}`
          }}>
            T
          </div>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700, color: theme.textPrimary, letterSpacing: '-0.02em' }}>
              {t('nav.brand', lang as any)}
            </div>
            <div style={{ fontSize: 12, color: theme.textSecondary, marginTop: 2, fontWeight: 500 }}>
              {t('nav.brand_sub', lang as any)}
            </div>
          </div>
        </div>

        {auth && (
          <div style={{ padding: '0 24px 20px', borderBottom: `1px solid ${theme.glassBorder}` }}>
            <div className="glass-card" style={{ borderRadius: 12, padding: 12, display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{ width: 36, height: 36, borderRadius: '50%', background: theme.accentLight, display: 'flex', alignItems: 'center', justifyContent: 'center', color: theme.accent, fontWeight: 600 }}>
                {auth.display_name.charAt(0).toUpperCase()}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 14, color: theme.textPrimary, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {auth.display_name}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4 }}>
                  <span className="pill-badge" style={{
                    fontSize: 10,
                    color: ROLE_COLORS[auth.role] || theme.textSecondary,
                    background: `${ROLE_COLORS[auth.role] || theme.textMuted}1a`,
                    textTransform: 'uppercase',
                  }}>
                    {roleLabel}
                  </span>
                  {auth.team_scope && (
                    <span style={{ fontSize: 11, color: theme.textSecondary, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontWeight: 500 }}>
                      {auth.team_scope}
                    </span>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        <nav style={{ flex: 1, padding: '24px 0', display: 'flex', flexDirection: 'column', gap: 6, overflowY: 'auto' }}>
          {navItems.map(item => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.end}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                margin: '0 16px',
                padding: '10px 16px',
                borderRadius: 12,
                color: theme.textSecondary,
                textDecoration: 'none',
                fontSize: 14,
              }}
              className={({ isActive }) => isActive ? 'nav-active' : 'nav-inactive'}
            >
              <span style={{ fontSize: 16, minWidth: 20, textAlign: 'center', opacity: 0.9 }}>{item.icon}</span>
              <span>{t(item.labelKey, lang as any)}</span>
            </NavLink>
          ))}
        </nav>
        
        <div style={{
          display: 'flex', gap: 8, padding: '16px',
          borderTop: `1px solid ${theme.glassBorder}`,
        }}>
          <button
            className="glass-btn"
            onClick={toggleTheme}
            style={{
              flex: 1, padding: '10px', fontSize: 13, cursor: 'pointer',
              background: theme.glassBg, border: `1px solid ${theme.glassBorder}`,
              color: theme.textSecondary, borderRadius: 10, fontWeight: 600,
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
            }}
          >
            {themeMode === 'dark' ? '☀️' : '🌙'}
          </button>
          <button
            className="glass-btn"
            onClick={toggleLang}
            style={{
              flex: 1, padding: '10px', fontSize: 13, cursor: 'pointer',
              background: theme.glassBg, border: `1px solid ${theme.glassBorder}`,
              color: theme.textSecondary, borderRadius: 10, fontWeight: 600,
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
            }}
          >
            🌐 {lang === 'zh' ? 'EN' : '中文'}
          </button>
        </div>

        <div style={{ padding: '0 16px 16px' }}>
          <button
            className="glass-btn"
            onClick={logout}
            style={{
              width: '100%', padding: '10px', background: theme.dangerBg,
              border: `1px solid transparent`, color: theme.danger,
              borderRadius: 10, cursor: 'pointer', fontSize: 13, fontWeight: 600,
            }}
          >
            {t('nav.logout', lang as any)}
          </button>
        </div>
      </aside>
      
      <main style={{ flex: 1, overflow: 'auto', display: 'flex', flexDirection: 'column' }}>
        <header className="glass-panel" style={{
          height: 64,
          display: 'flex',
          alignItems: 'center',
          padding: '0 32px',
          flexShrink: 0,
          position: 'sticky',
          top: 0,
          zIndex: 10,
          borderBottom: `1px solid ${theme.glassBorder}`,
        }}>
          <div style={{ flex: 1 }}></div>
          <div className="glass-btn" style={{ cursor: 'default', padding: '6px 12px', borderRadius: 9999, background: theme.successBg, border: `1px solid ${theme.success}33`, color: theme.success, fontSize: 12, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: theme.success, display: 'inline-block', boxShadow: `0 0 8px ${theme.success}` }}></span>
            System Operational
          </div>
        </header>
        
        <div style={{ padding: '32px', flex: 1, minWidth: 0, maxWidth: 1400, margin: '0 auto', width: '100%' }}>
          <ScopeBanner auth={auth} />
          <Outlet />
        </div>
      </main>
    </div>
  )
}
