import { useState, useEffect } from 'react'
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
  { path: '/', labelKey: 'nav.dashboard', icon: '\u25C8', end: true },
  { path: '/pipeline', labelKey: 'nav.pipeline', icon: '\u25BC', end: false },
  { path: '/team', labelKey: 'nav.team', icon: '\u25C9', end: false },
  { path: '/clients', labelKey: 'nav.clients', icon: '\u2261', end: false },
  { path: '/frontdesk', labelKey: 'nav.frontdesk', icon: '\u2726', end: false },
  { path: '/groups', labelKey: 'nav.groups', icon: '\u2295', end: false },
  { path: '/maintainer', labelKey: 'nav.maintainer', icon: '\u2318', end: false, adminOnly: true },
  { path: '/cs', labelKey: 'nav.customer_service', icon: '\u2298', end: false },
  { path: '/group-interactions', labelKey: 'nav.group_interactions', icon: '\u229E', end: false },
  { path: '/cs-finance', labelKey: 'nav.cs_finance', icon: '\uD83D\uDCB0', end: false },
  { path: '/phone-lookup', labelKey: 'nav.phone_lookup', icon: '\u260E', end: false },
  { path: '/reports', labelKey: 'nav.reports', icon: '\u232C', end: false },
  { path: '/performance', labelKey: 'nav.performance', icon: '\u229E', end: false },
  { path: '/performance-detail', labelKey: 'nav.performance_detail', icon: '\u229F', end: false },
  { path: '/contests', labelKey: 'nav.contests', icon: '\uD83C\uDFC6', end: false },
  { path: '/exams', labelKey: 'nav.exams', icon: '\uD83D\uDCCB', end: false, adminOnly: true },
  { path: '/templates', labelKey: 'nav.templates', icon: '\uD83D\uDCDD', end: false, adminOnly: true },
  { path: '/org-chart', labelKey: 'nav.org_chart', icon: '\u22A1', end: false, adminOnly: true },
  { path: '/permissions', labelKey: 'nav.permissions', icon: '\uD83D\uDD10', end: false, adminOnly: true },
  { path: '/users', labelKey: 'nav.users', icon: '\u25CE', end: false, adminOnly: true },
]

function buildNav(auth: AuthState | null) {
  if (!auth) return NAV_ALL.filter(n => !n.adminOnly)
  if (auth.role === 'member') {
    return NAV_ALL.filter(n => n.path === '/' || n.path === '/clients' || n.path === '/phone-lookup' || n.path === '/performance' || n.path === '/contests')
  }
  return NAV_ALL
}

function useIsMobile(breakpoint = 768) {
  const [isMobile, setIsMobile] = useState(typeof window !== 'undefined' ? window.innerWidth < breakpoint : false)
  useEffect(() => {
    const handler = () => setIsMobile(window.innerWidth < breakpoint)
    window.addEventListener('resize', handler)
    return () => window.removeEventListener('resize', handler)
  }, [breakpoint])
  return isMobile
}

export default function Layout() {
  const isMobile = useIsMobile()
  const nav = useNavigate()
  const auth = getAuthState()
  const { theme, mode: themeMode, toggleTheme } = useTheme()
  const [lang, setLangState] = useState(getLang())
  const [sidebarOpen, setSidebarOpen] = useState(false)

  function toggleLang() {
    const next = lang === 'zh' ? 'en' : 'zh'
    setLang(next as 'en' | 'zh')
    setLangState(next as 'en' | 'zh')
  }

  function logout() {
    clearAuthState()
    nav('/login')
  }

  const navItems = buildNav(auth)
  const roleLabel = t(`role.${auth?.role || 'member'}`, lang as 'en' | 'zh')

  return (
    <div className="layout-root">
      {/* Mobile overlay backdrop */}
      {isMobile && sidebarOpen && (
        <div
          className="mobile-overlay"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* --- Sidebar --- */}
      <aside className={`layout-sidebar glass-panel${isMobile ? ' mobile' : ''}${isMobile && !sidebarOpen ? ' collapsed' : ''}`}>
        {/* Brand */}
        <div className="sidebar-brand">
          <div className="sidebar-brand-icon">
            T
          </div>
          <div>
            <div className="sidebar-brand-title">
              {t('nav.brand', lang as 'en' | 'zh')}
            </div>
            <div className="sidebar-brand-sub">
              {t('nav.brand_sub', lang as 'en' | 'zh')}
            </div>
          </div>
        </div>

        {/* User card */}
        {auth && (
          <div className="sidebar-user">
            <div className="sidebar-user-card glass-card">
              <div className="sidebar-user-avatar">
                {auth.display_name.charAt(0).toUpperCase()}
              </div>
              <div className="sidebar-user-info">
                <div className="sidebar-user-name">
                  {auth.display_name}
                </div>
                <div className="sidebar-user-meta">
                  <span className="role-badge-dynamic" style={{
                    '--role-color': ROLE_COLORS[auth.role] || undefined,
                    '--role-bg': ROLE_COLORS[auth.role] ? `${ROLE_COLORS[auth.role]}1a` : undefined,
                  } as React.CSSProperties}>
                    {roleLabel}
                  </span>
                  {auth.team_scope && (
                    <span className="sidebar-user-scope">
                      {auth.team_scope}
                    </span>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Navigation */}
        <nav className="sidebar-nav">
          {navItems.map(item => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.end}
              className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
              onClick={() => isMobile && setSidebarOpen(false)}
            >
              <span className="nav-item-icon">{item.icon}</span>
              <span>{t(item.labelKey, lang as 'en' | 'zh')}</span>
            </NavLink>
          ))}
        </nav>

        {/* Footer — theme / lang / logout */}
        <div className="sidebar-footer">
          <div className="sidebar-footer-btns">
            <button className="glass-btn flex-1" onClick={toggleTheme}>
              {themeMode === 'dark' ? '\u2600\uFE0F' : '\uD83C\uDF19'}
            </button>
            <button className="glass-btn flex-1" onClick={toggleLang}>
              {lang === 'zh' ? 'EN' : '\u4E2D\u6587'}
            </button>
            <button className="glass-btn flex-1 glass-btn-danger" onClick={logout}>
              {t('nav.logout', lang as 'en' | 'zh')}
            </button>
          </div>
        </div>
      </aside>

      {/* --- Main content --- */}
      <main className="layout-main">
        {/* Header: 52px, search + status */}
        <header className="layout-header glass-panel">
          {isMobile && (
            <button
              className="burger-btn glass-btn"
              onClick={() => setSidebarOpen(true)}
            >
              {'\u2630'}
            </button>
          )}
          {isMobile && (
            <div className="mobile-brand">
              {t('nav.brand', lang as 'en' | 'zh')}
            </div>
          )}
          <div className="header-actions">
            <div className="search-input-wrap">
              <input
                type="text"
                placeholder={t('common.search', lang as 'en' | 'zh') + '...'}
                className="input"
                onKeyDown={e => {
                  if (e.key === 'Enter') {
                    const val = (e.target as HTMLInputElement).value.trim()
                    if (val) nav(`/clients?search=${encodeURIComponent(val)}`)
                  }
                }}
              />
              <span className="search-icon">{'\u2315'}</span>
            </div>
            <div className="status-ok">
              <span className="dot" />
              OK
            </div>
          </div>
        </header>

        {/* Content area */}
        <div className="layout-content">
          <ScopeBanner auth={auth} />
          <Outlet />
        </div>
      </main>
    </div>
  )
}
