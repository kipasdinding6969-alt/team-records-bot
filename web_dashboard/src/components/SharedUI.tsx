import React from 'react'
import { useTheme } from '../ThemeContext'
import { getLang, t } from '../i18n'
import type { Theme } from '../theme'

export function PageHeader({ title, sub, theme: themeProp }: { title: string; sub?: string; theme?: Theme }) {
  return (
    <div className="page-header">
      <h1 className="page-title">{title}</h1>
      {sub && <div className="page-subtitle">{sub}</div>}
    </div>
  )
}

export function SectionTitle({ children, theme: themeProp, accent }: { children: React.ReactNode; theme?: Theme; accent?: boolean }) {
  return (
    <h3 className="section-title" style={accent ? { paddingLeft: 12, borderLeft: '3px solid var(--accent)' } : undefined}>
      {children}
    </h3>
  )
}

export function Spinner({ color, label }: { color?: string; label?: string }) {
  const { theme } = useTheme()
  return (
    <div className="empty-state" style={color ? { color } : undefined}>
      <div style={{ width: 24, height: 24, border: '3px solid currentColor', borderRightColor: 'transparent', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
      <div style={{ fontSize: 13, fontWeight: 500 }}>{label || t('common.loading', getLang())}</div>
    </div>
  )
}

export function Empty({ color, label }: { color?: string; label?: string }) {
  const lang = getLang()
  return (
    <div className="empty-state" style={color ? { color } : undefined}>
      <div className="empty-icon">{'\uD83D\uDCED'}</div>
      <div className="empty-text">{label || t('common.no_data', lang)}</div>
    </div>
  )
}

export function MessageBanner({ message, onDismiss }: { message: { type: 'success' | 'error'; text: string } | null; onDismiss?: () => void }) {
  if (!message) return null
  return (
    <div className={`alert ${message.type === 'error' ? 'alert-error' : 'alert-success'}`} style={{ justifyContent: 'space-between' }}>
      <span>{message.text}</span>
      {onDismiss && <button className="comment-action-btn" onClick={onDismiss}>&times;</button>}
    </div>
  )
}
