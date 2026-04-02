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
    <div style={{
      display: 'flex',
      minHeight: '100vh',
      background: theme.bg,
      color: theme.textPrimary,
      fontFamily: theme.fontFamily,
    }}>
      {/* Mobile overlay backdrop */}
      {isMobile && sidebarOpen && (
        <div
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 25, backdropFilter: 'blur(4px)' }}
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* --- Sidebar --- */}
      <aside className="glass-panel" style={{
        width: 240,
        display: 'flex',
        flexDirection: 'column',
        flexShrink: 0,
        zIndex: 30,
        borderRight: `1px solid ${theme.glassBorder}`,
        transition: 'transform 0.3s ease',
        position: isMobile ? 'fixed' : 'relative',
        height: isMobile ? '100vh' : '100%',
        transform: isMobile && !sidebarOpen ? 'translateX(-240px)' : 'translateX(0)',
        background: theme.sidebarBg,
      }}>
        {/* Brand */}
        <div style={{ padding: '20px 20px 16px', display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 8, background: theme.accent,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: '#fff', fontWeight: 'bold', fontSize: 18,
            boxShadow: `0 4px 16px ${theme.accentLight}`,
          }}>
            T
          </div>
          <div>
            <div style={{ fontSize: 15, fontWeight: 700, color: theme.textPrimary, letterSpacing: '-0.02em' }}>
              {t('nav.brand', lang as 'en' | 'zh')}
            </div>
            <div style={{ fontSize: 11, color: theme.textSecondary, marginTop: 2, fontWeight: 500 }}>
              {t('nav.brand_sub', lang as 'en' | 'zh')}
            </div>
          </div>
        </div>

        {/* User card */}
        {auth && (
          <div style={{ padding: '0 12px 12px', borderBottom: `1px solid ${theme.glassBorder}` }}>
            <div className="glass-card" style={{ borderRadius: theme.radiusCard, padding: 12, display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{
                width: 36, height: 36, borderRadius: '50%',
                background: theme.accentLight,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: theme.accent, fontWeight: 600, fontSize: 15,
              }}>
                {auth.display_name.charAt(0).toUpperCase()}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 14, color: theme.textPrimary, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {auth.display_name}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
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

        {/* Navigation */}
        <nav style={{ flex: 1, padding: '8px 0', display: 'flex', flexDirection: 'column', gap: 2, overflowY: 'auto' }}>
          {navItems.map(item => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.end}
              className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
              style={{ padding: '8px 12px' }}
              onClick={() => isMobile && setSidebarOpen(false)}
            >
              <span className="nav-item-icon">{item.icon}</span>
              <span>{t(item.labelKey, lang as 'en' | 'zh')}</span>
            </NavLink>
          ))}
        </nav>

        {/* Footer — theme / lang / logout */}
        <div style={{ borderTop: `1px solid ${theme.glassBorder}`, padding: 12 }}>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="glass-btn" onClick={toggleTheme} style={{ flex: 1 }}>
              {themeMode === 'dark' ? '\u2600\uFE0F' : '\uD83C\uDF19'}
            </button>
            <button className="glass-btn" onClick={toggleLang} style={{ flex: 1 }}>
              {lang === 'zh' ? 'EN' : '\u4E2D\u6587'}
            </button>
            <button className="glass-btn" onClick={logout} style={{ flex: 1, background: theme.dangerBg, color: theme.danger, borderColor: 'transparent' }}>
              {t('nav.logout', lang as 'en' | 'zh')}
            </button>
          </div>
        </div>
      </aside>

      {/* --- Main content --- */}
      <main style={{ flex: 1, overflow: 'auto', display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        {/* Header: 52px, search + status */}
        <header className="glass-panel" style={{
          height: 52,
          display: 'flex',
          alignItems: 'center',
          padding: '0 24px',
          flexShrink: 0,
          position: 'sticky',
          top: 0,
          zIndex: 10,
          borderBottom: `1px solid ${theme.glassBorder}`,
          gap: 12,
        }}>
          {isMobile && (
            <button
              className="glass-btn"
              onClick={() => setSidebarOpen(true)}
              style={{ background: 'transparent', border: 'none', color: theme.textPrimary, fontSize: 20, cursor: 'pointer', padding: 4 }}
            >
              {'\u2630'}
            </button>
          )}
          {isMobile && (
            <div style={{ fontSize: 13, fontWeight: 600, color: theme.textSecondary }}>
              {t('nav.brand', lang as 'en' | 'zh')}
            </div>
          )}
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 12, justifyContent: 'flex-end' }}>
            <div style={{ position: 'relative', flex: 1, maxWidth: 320 }}>
              <input
                type="text"
                placeholder={t('common.search', lang as 'en' | 'zh') + '...'}
                className="input"
                style={{ paddingLeft: 32, width: '100%' }}
                onKeyDown={e => {
                  if (e.key === 'Enter') {
                    const val = (e.target as HTMLInputElement).value.trim()
                    if (val) nav(`/clients?search=${encodeURIComponent(val)}`)
                  }
                }}
              />
              <span style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', fontSize: 14, color: theme.textMuted }}>
                {'\u2315'}
              </span>
            </div>
            <div style={{
              cursor: 'default', padding: '4px 10px', borderRadius: 8,
              background: theme.successBg, border: `1px solid ${theme.success}33`,
              color: theme.success, fontSize: 11, fontWeight: 600,
              display: 'flex', alignItems: 'center', gap: 6,
            }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: theme.success, display: 'inline-block' }} />
              OK
            </div>
          </div>
        </header>

        {/* Content area */}
        <div style={{ flex: 1, minWidth: 0, maxWidth: 1400, margin: '0 auto', width: '100%' }}>
          <ScopeBanner auth={auth} />
          <Outlet />
        </div>
      </main>
    </div>
  )
}
