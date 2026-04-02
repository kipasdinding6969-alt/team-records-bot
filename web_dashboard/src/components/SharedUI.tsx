import React from 'react'
import { getLang, t } from '../i18n'

export function PageHeader({ title, sub }: { title: string; sub?: string }) {
  return (
    <div className="page-header">
      <h1 className="page-title">{title}</h1>
      {sub && <div className="page-subtitle">{sub}</div>}
    </div>
  )
}

export function SectionTitle({ children, accent }: { children: React.ReactNode; accent?: boolean }) {
  return (
    <h3 className={`section-title${accent ? ' border-left-accent px-12' : ''}`}>
      {children}
    </h3>
  )
}

export function Spinner({ color, label }: { color?: string; label?: string }) {
  return (
    <div className="empty-state" style={color ? { color } : undefined}>
      <div className="spinner-ring" />
      <div className="fs-13 fw-500">{label || t('common.loading', getLang())}</div>
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
    <div className={`alert ${message.type === 'error' ? 'alert-error' : 'alert-success'} justify-between`}>
      <span>{message.text}</span>
      {onDismiss && <button className="comment-action-btn" onClick={onDismiss}>&times;</button>}
    </div>
  )
}
