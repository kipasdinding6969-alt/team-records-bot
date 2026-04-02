export type ThemeMode = 'dark' | 'light'

const THEME_KEY = 'dashboard_theme'

export function getTheme(): ThemeMode {
  return (localStorage.getItem(THEME_KEY) as ThemeMode) || 'dark'
}

export function setTheme(mode: ThemeMode) {
  localStorage.setItem(THEME_KEY, mode)
}

export interface Theme {
  fontFamily: string
  bg: string
  bgElevated: string
  cardBg: string
  cardBorder: string
  sidebarBg: string
  sidebarBorder: string
  textPrimary: string
  textSecondary: string
  textMuted: string
  accent: string
  accentHover: string
  accentLight: string
  accentSubtle: string
  activeNav: string
  activeNavText: string
  activeNavBorder: string
  inputBg: string
  inputBorder: string
  shadow: string
  shadowHover: string
  shadowCard: string
  danger: string
  dangerBg: string
  success: string
  successBg: string
  warning: string
  warningBg: string
  info: string
  infoBg: string
  badgeGreen: string
  badgeYellow: string
  badgeRed: string
  chartBar: string
  chartLine: string
  glassBg: string
  glassBorder: string
  glowAmbient: string
  navHoverBg: string
  radiusCard: number
  radiusBtn: number
  radiusInput: number
  paddingCard: number
  paddingInput: string
  gapSection: number
  marginCard: number
}

export const darkTheme: Theme = {
  fontFamily: "'Inter', -apple-system, sans-serif",
  bg: '#1a2233',
  bgElevated: '#1f2a3c',
  cardBg: '#243247',
  cardBorder: 'rgba(255, 255, 255, 0.09)',
  sidebarBg: '#1a2233',
  sidebarBorder: 'rgba(255, 255, 255, 0.07)',
  textPrimary: '#f1f5f9',
  textSecondary: '#94a3b8',
  textMuted: '#6b7a8d',
  accent: '#2dd4bf',
  accentHover: '#5eead4',
  accentLight: 'rgba(45, 212, 191, 0.14)',
  accentSubtle: 'rgba(45, 212, 191, 0.07)',
  activeNav: 'rgba(45, 212, 191, 0.14)',
  activeNavText: '#f1f5f9',
  activeNavBorder: '#2dd4bf',
  inputBg: '#243247',
  inputBorder: 'rgba(255, 255, 255, 0.12)',
  shadow: '0 1px 3px rgba(0, 0, 0, 0.16), 0 1px 2px rgba(0, 0, 0, 0.1)',
  shadowHover: '0 8px 25px -5px rgba(0, 0, 0, 0.25), 0 4px 6px -4px rgba(0, 0, 0, 0.12)',
  shadowCard: '0 1px 4px rgba(0, 0, 0, 0.1)',
  danger: '#fb7185',
  dangerBg: 'rgba(251, 113, 133, 0.14)',
  success: '#34d399',
  successBg: 'rgba(52, 211, 153, 0.14)',
  warning: '#fbbf24',
  warningBg: 'rgba(251, 191, 36, 0.14)',
  info: '#94a3b8',
  infoBg: 'rgba(148, 163, 184, 0.12)',
  badgeGreen: 'rgba(52, 211, 153, 0.14)',
  badgeYellow: 'rgba(251, 191, 36, 0.14)',
  badgeRed: 'rgba(251, 113, 133, 0.14)',
  chartBar: '#2dd4bf',
  chartLine: '#34d399',
  glassBg: 'rgba(36, 50, 71, 0.75)',
  glassBorder: 'rgba(255, 255, 255, 0.07)',
  glowAmbient: 'none',
  navHoverBg: 'rgba(255, 255, 255, 0.05)',
  radiusCard: 12,
  radiusBtn: 8,
  radiusInput: 8,
  paddingCard: 20,
  paddingInput: '0 14px',
  gapSection: 20,
  marginCard: 20,
}

export const lightTheme: Theme = {
  fontFamily: "'Inter', -apple-system, sans-serif",
  bg: '#f8fafc',
  bgElevated: '#f1f5f9',
  cardBg: '#ffffff',
  cardBorder: '#e2e8f0',
  sidebarBg: '#ffffff',
  sidebarBorder: '#e2e8f0',
  textPrimary: '#0f172a',
  textSecondary: '#475569',
  textMuted: '#64748b',
  accent: '#0d9488',
  accentHover: '#0f766e',
  accentLight: 'rgba(13, 148, 136, 0.1)',
  accentSubtle: 'rgba(13, 148, 136, 0.04)',
  activeNav: 'rgba(13, 148, 136, 0.08)',
  activeNavText: '#0f172a',
  activeNavBorder: '#0d9488',
  inputBg: '#ffffff',
  inputBorder: '#d1d5db',
  shadow: '0 1px 3px rgba(0, 0, 0, 0.08), 0 1px 2px rgba(0, 0, 0, 0.06)',
  shadowHover: '0 10px 25px -4px rgba(13, 148, 136, 0.12), 0 4px 6px -4px rgba(0, 0, 0, 0.05)',
  shadowCard: '0 1px 3px rgba(0, 0, 0, 0.06)',
  danger: '#ef4444',
  dangerBg: '#fee2e2',
  success: '#10b981',
  successBg: '#d1fae5',
  warning: '#f59e0b',
  warningBg: '#fef3c7',
  info: '#64748b',
  infoBg: 'rgba(100, 116, 139, 0.08)',
  badgeGreen: '#d1fae5',
  badgeYellow: '#fef3c7',
  badgeRed: '#fee2e2',
  chartBar: '#0d9488',
  chartLine: '#10b981',
  glassBg: 'rgba(255, 255, 255, 0.9)',
  glassBorder: 'rgba(0, 0, 0, 0.06)',
  glowAmbient: 'none',
  navHoverBg: 'rgba(0, 0, 0, 0.03)',
  radiusCard: 12,
  radiusBtn: 8,
  radiusInput: 8,
  paddingCard: 20,
  paddingInput: '0 14px',
  gapSection: 20,
  marginCard: 20,
}

export function resolveTheme(mode: ThemeMode): Theme {
  return mode === 'light' ? lightTheme : darkTheme
}

/** Inject theme tokens as CSS variables on :root so global CSS classes work */
export function applyThemeCssVars(theme: Theme): void {
  const root = document.documentElement
  root.style.setProperty('--bg', theme.bg)
  root.style.setProperty('--bg-elevated', theme.bgElevated)
  root.style.setProperty('--card-bg', theme.cardBg)
  root.style.setProperty('--card-border', theme.cardBorder)
  root.style.setProperty('--sidebar-bg', theme.sidebarBg)
  root.style.setProperty('--sidebar-border', theme.sidebarBorder)
  root.style.setProperty('--text-primary', theme.textPrimary)
  root.style.setProperty('--text-secondary', theme.textSecondary)
  root.style.setProperty('--text-muted', theme.textMuted)
  root.style.setProperty('--accent', theme.accent)
  root.style.setProperty('--accent-hover', theme.accentHover)
  root.style.setProperty('--accent-light', theme.accentLight)
  root.style.setProperty('--accent-subtle', theme.accentSubtle)
  root.style.setProperty('--input-bg', theme.inputBg)
  root.style.setProperty('--input-border', theme.inputBorder)
  root.style.setProperty('--danger', theme.danger)
  root.style.setProperty('--danger-bg', theme.dangerBg)
  root.style.setProperty('--success', theme.success)
  root.style.setProperty('--success-bg', theme.successBg)
  root.style.setProperty('--warning', theme.warning)
  root.style.setProperty('--warning-bg', theme.warningBg)
  root.style.setProperty('--info', theme.info)
  root.style.setProperty('--info-bg', theme.infoBg)
  root.style.setProperty('--shadow', theme.shadow)
  root.style.setProperty('--shadow-hover', theme.shadowHover)
  root.style.setProperty('--shadow-card', theme.shadowCard)
  root.style.setProperty('--nav-hover-bg', theme.navHoverBg)
  root.style.setProperty('--glass-bg', theme.glassBg)
  root.style.setProperty('--glass-border', theme.glassBorder)
  root.style.setProperty('--scrollbar-thumb', theme.cardBorder)
}
