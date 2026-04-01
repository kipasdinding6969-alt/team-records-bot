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
  activeNav: string
  activeNavText: string
  activeNavBorder: string
  inputBg: string
  inputBorder: string
  shadow: string
  shadowHover: string
  danger: string
  dangerBg: string
  success: string
  successBg: string
  warning: string
  warningBg: string
  badgeGreen: string
  badgeYellow: string
  badgeRed: string
  chartBar: string
  chartLine: string
  glassBg: string
  glassBorder: string
  glowAmbient: string
  navHoverBg: string
}

export const darkTheme: Theme = {
  fontFamily: "'Inter', -apple-system, sans-serif",
  bg: '#000000',
  cardBg: '#121212',
  cardBorder: '#262626',
  sidebarBg: '#000000',
  sidebarBorder: '#262626',
  textPrimary: '#ffffff',
  textSecondary: '#a1a1aa',
  textMuted: '#52525b',
  accent: '#818cf8', // Made accent slightly brighter for hyper-creative look
  accentHover: '#a5b4fc',
  accentLight: 'rgba(129, 140, 248, 0.15)',
  activeNav: 'linear-gradient(90deg, rgba(129, 140, 248, 0.15) 0%, transparent 100%)',
  activeNavText: '#ffffff',
  activeNavBorder: '#818cf8',
  inputBg: '#121212',
  inputBorder: '#262626',
  shadow: '0 4px 20px -2px rgba(0, 0, 0, 0.6)',
  shadowHover: '0 12px 30px -4px rgba(129, 140, 248, 0.2), 0 4px 6px -4px rgba(0, 0, 0, 0.5)',
  danger: '#f87171',
  dangerBg: 'rgba(248, 113, 113, 0.15)',
  success: '#34d399',
  successBg: 'rgba(52, 211, 153, 0.15)',
  warning: '#fbbf24',
  warningBg: 'rgba(251, 191, 36, 0.15)',
  badgeGreen: 'rgba(52, 211, 153, 0.15)',
  badgeYellow: 'rgba(251, 191, 36, 0.15)',
  badgeRed: 'rgba(248, 113, 113, 0.15)',
  chartBar: '#818cf8',
  chartLine: '#34d399',
  glassBg: 'rgba(18, 18, 18, 0.5)',
  glassBorder: 'rgba(255, 255, 255, 0.08)',
  glowAmbient: 'radial-gradient(circle at 50% -20%, rgba(99, 102, 241, 0.15), rgba(0, 0, 0, 0) 60%), radial-gradient(circle at 100% 50%, rgba(139, 92, 246, 0.08), rgba(0, 0, 0, 0) 50%)',
  navHoverBg: 'rgba(255, 255, 255, 0.05)',
}

export const lightTheme: Theme = {
  fontFamily: "'Inter', -apple-system, sans-serif",
  bg: '#f7f8fa',
  cardBg: '#ffffff',
  cardBorder: '#e5e7eb',
  sidebarBg: '#f7f8fa',
  sidebarBorder: '#e5e7eb',
  textPrimary: '#0f172a',
  textSecondary: '#64748b',
  textMuted: '#94a3b8',
  accent: '#6366f1',
  accentHover: '#4f46e5',
  accentLight: 'rgba(99, 102, 241, 0.1)',
  activeNav: 'linear-gradient(90deg, rgba(99, 102, 241, 0.1) 0%, transparent 100%)',
  activeNavText: '#0f172a',
  activeNavBorder: '#6366f1',
  inputBg: '#ffffff',
  inputBorder: '#d1d5db',
  shadow: '0 4px 20px -2px rgba(0, 0, 0, 0.05)',
  shadowHover: '0 12px 30px -4px rgba(99, 102, 241, 0.15), 0 4px 6px -4px rgba(0, 0, 0, 0.05)',
  danger: '#ef4444',
  dangerBg: '#fee2e2',
  success: '#10b981',
  successBg: '#d1fae5',
  warning: '#f59e0b',
  warningBg: '#fef3c7',
  badgeGreen: '#d1fae5',
  badgeYellow: '#fef3c7',
  badgeRed: '#fee2e2',
  chartBar: '#6366f1',
  chartLine: '#10b981',
  glassBg: 'rgba(255, 255, 255, 0.7)',
  glassBorder: 'rgba(0, 0, 0, 0.05)',
  glowAmbient: 'radial-gradient(circle at 50% -20%, rgba(99, 102, 241, 0.08), rgba(255, 255, 255, 0) 60%), radial-gradient(circle at 100% 50%, rgba(139, 92, 246, 0.05), rgba(255, 255, 255, 0) 50%)',
  navHoverBg: 'rgba(0, 0, 0, 0.03)',
}

export function resolveTheme(mode: ThemeMode): Theme {
  return mode === 'light' ? lightTheme : darkTheme
}