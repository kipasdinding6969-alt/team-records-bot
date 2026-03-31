export type ThemeMode = 'dark' | 'light'

const THEME_KEY = 'dashboard_theme'

export function getTheme(): ThemeMode {
  return (localStorage.getItem(THEME_KEY) as ThemeMode) || 'dark'
}

export function setTheme(mode: ThemeMode) {
  localStorage.setItem(THEME_KEY, mode)
}

export interface Theme {
  bg: string
  cardBg: string
  cardBorder: string
  sidebarBg: string
  sidebarBorder: string
  textPrimary: string
  textSecondary: string
  accent: string
  accentHover: string
  activeNav: string
  activeNavBorder: string
  inputBg: string
  inputBorder: string
  shadow: string
  badgeGreen: string
  badgeYellow: string
  badgeRed: string
  chartBar: string
  chartLine: string
}

export const darkTheme: Theme = {
  bg: '#1a1a2e',
  cardBg: '#16213e',
  cardBorder: '#0f3460',
  sidebarBg: '#16213e',
  sidebarBorder: '#0f3460',
  textPrimary: '#e0e0e0',
  textSecondary: '#7f848e',
  accent: '#00b894',
  accentHover: '#00d2a4',
  activeNav: '#0f3460',
  activeNavBorder: '#00b894',
  inputBg: '#0f3460',
  inputBorder: '#16213e',
  shadow: '0 2px 8px rgba(0,0,0,0.3)',
  badgeGreen: '#00b89433',
  badgeYellow: '#fdcb6e33',
  badgeRed: '#d6303133',
  chartBar: '#00b894',
  chartLine: '#fdcb6e',
}

export const lightTheme: Theme = {
  bg: '#faf7f2',
  cardBg: '#fffdf9',
  cardBorder: '#e8e0d4',
  sidebarBg: '#faf5ed',
  sidebarBorder: '#e8e0d4',
  textPrimary: '#2d2a26',
  textSecondary: '#7f848e',
  accent: '#2bb5a0',
  accentHover: '#239e8c',
  activeNav: '#f0ebe3',
  activeNavBorder: '#2bb5a0',
  inputBg: '#f5f0e8',
  inputBorder: '#e0d8cc',
  shadow: '0 2px 8px rgba(80,60,30,0.07)',
  badgeGreen: '#d6f0e0',
  badgeYellow: '#fef3c7',
  badgeRed: '#fee2e2',
  chartBar: '#2bb5a0',
  chartLine: '#e8a735',
}

export function resolveTheme(mode: ThemeMode): Theme {
  return mode === 'light' ? lightTheme : darkTheme
}
