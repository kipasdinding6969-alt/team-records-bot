import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { clearAuthState, getAuthState } from '../api'
import ScopeBanner from './ScopeBanner'
import type { AuthState } from '../types'
import { ROLE_COLORS } from '../types'
import { t, getLang, setLang } from '../i18n'
import { getTheme, setTheme, resolveTheme, type ThemeMode } from '../theme'

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
  { path: '/permissions', labelKey: 'nav.permissions', icon: '🔐', end: false, adminOnly: true },
  { path: '/users', labelKey: 'nav.users', icon: '◎', end: false, adminOnly: true },
]

function buildNav(auth: AuthState | null) {
  if (!auth) return NAV_ALL.filter(n => !n.adminOnly)
  if (auth.role === 'member') {
    return NAV_ALL.filter(n => n.path === '/' || n.path === '/clients' || n.path === '/phone-lookup')
  }
  return NAV_ALL
}

export default function Layout() {
  const nav = useNavigate()
  const auth = getAuthState()
  const [themeMode, setThemeMode] = useState<ThemeMode>(getTheme())
  const [lang, setLangState] = useState(getLang())
  const theme = resolveTheme(themeMode)

  function toggleTheme() {
    const next: ThemeMode = themeMode === 'dark' ? 'light' : 'dark'
    setTheme(next)
    setThemeMode(next)
  }

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
      color: theme.textPrimary,
    }}>
      <aside style={{
        width: 220,
        background: theme.sidebarBg,
        display: 'flex',
        flexDirection: 'column',
        borderRight: `1px solid ${theme.sidebarBorder}`,
        flexShrink: 0,
      }}>
        <div style={{ padding: '20px 20px 14px', borderBottom: `1px solid ${theme.sidebarBorder}` }}>
          <div style={{ fontSize: 16, fontWeight: 700, color: theme.textPrimary, letterSpacing: 0.5 }}>
            {t('nav.brand', lang as any)}
          </div>
          <div style={{ fontSize: 11, color: theme.textSecondary, marginTop: 3 }}>
            {t('nav.brand_sub', lang as any)}
          </div>
        </div>

        {auth && (
          <div style={{ padding: '10px 20px 14px', borderBottom: `1px solid ${theme.sidebarBorder}` }}>
            <div style={{ fontSize: 13, color: theme.textPrimary, fontWeight: 600 }}>{auth.display_name}</div>
            <div style={{ marginTop: 4, display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{
                fontSize: 10,
                fontWeight: 700,
                color: ROLE_COLORS[auth.role] || '#7f848e',
                background: `${ROLE_COLORS[auth.role] || '#7f848e'}22`,
                border: `1px solid ${ROLE_COLORS[auth.role] || '#7f848e'}`,
                borderRadius: 3,
                padding: '1px 6px',
                letterSpacing: 0.5,
                textTransform: 'uppercase',
              }}>
                {roleLabel}
              </span>
              {auth.team_scope && (
                <span style={{ fontSize: 11, color: theme.textSecondary }}>{auth.team_scope}</span>
              )}
            </div>
          </div>
        )}

        {/* Theme + Lang toggles */}
        <div style={{
          display: 'flex', gap: 6, padding: '8px 20px',
          borderBottom: `1px solid ${theme.sidebarBorder}`,
        }}>
          <button
            onClick={toggleTheme}
            style={{
              flex: 1, padding: '4px 8px', fontSize: 11, cursor: 'pointer',
              background: theme.inputBg, border: `1px solid ${theme.inputBorder}`,
              color: theme.textSecondary, borderRadius: 4,
            }}
          >
            {themeMode === 'dark' ? '☀️' : '🌙'} {t(themeMode === 'dark' ? 'theme.light' : 'theme.dark', lang as any)}
          </button>
          <button
            onClick={toggleLang}
            style={{
              flex: 1, padding: '4px 8px', fontSize: 11, cursor: 'pointer',
              background: theme.inputBg, border: `1px solid ${theme.inputBorder}`,
              color: theme.textSecondary, borderRadius: 4,
            }}
          >
            🌐 {lang === 'zh' ? 'EN' : '中文'}
          </button>
        </div>

        <nav style={{ flex: 1, padding: '12px 0' }}>
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
                color: isActive ? theme.textPrimary : theme.textSecondary,
                background: isActive ? theme.activeNav : 'transparent',
                textDecoration: 'none',
                borderLeft: `3px solid ${isActive ? theme.activeNavBorder : 'transparent'}`,
                fontSize: 13,
                transition: 'all 0.15s',
              })}
            >
              <span style={{ fontSize: 14, minWidth: 18, textAlign: 'center' }}>{item.icon}</span>
              <span>{t(item.labelKey, lang as any)}</span>
            </NavLink>
          ))}
        </nav>
        <div style={{ padding: '16px 20px', borderTop: `1px solid ${theme.sidebarBorder}` }}>
          <button
            onClick={logout}
            style={{
              width: '100%', padding: '8px', background: 'transparent',
              border: `1px solid ${theme.textSecondary}`, color: theme.textSecondary,
              borderRadius: 4, cursor: 'pointer', fontSize: 12, letterSpacing: 0.5,
            }}
          >
            {t('nav.logout', lang as any)}
          </button>
        </div>
      </aside>
      <main style={{ flex: 1, overflow: 'auto', padding: 24, minWidth: 0 }}>
        <ScopeBanner auth={auth} />
        <Outlet />
      </main>
    </div>
  )
}
