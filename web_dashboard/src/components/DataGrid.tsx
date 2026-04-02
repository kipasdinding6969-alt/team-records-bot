import React from 'react'
import { useTheme } from '../ThemeContext'
import { STATUS_COLORS, STATUS_LABELS } from '../types'
import { getLang, t } from '../i18n'

export interface Column<T> {
  key: string
  label: string
  render?: (item: T, index?: number) => React.ReactNode
  width?: string | number
  align?: 'left' | 'center' | 'right'
  monospace?: boolean
}

interface DataGridProps<T> {
  columns: Column<T>[]
  data: T[]
  onRowClick?: (item: T) => void
  stickyHeader?: boolean
  zebraStripes?: boolean
}

export function DataGrid<T extends { id?: number | string }>({
  columns,
  data,
  onRowClick,
}: DataGridProps<T>) {
  return (
    <div className="overflow-x">
      <table className="data-grid-table">
        <thead>
          <tr>
            {columns.map(col => (
              <th key={col.key} className={col.align === 'right' ? 'text-right' : col.align === 'center' ? 'text-center' : 'text-left'} style={col.width ? { width: col.width } : undefined}>
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((item, index) => (
            <tr
              key={item.id !== undefined ? item.id : index}
              onClick={() => onRowClick && onRowClick(item)}
              className={onRowClick ? 'pointer' : undefined}
            >
              {columns.map(col => (
                <td key={col.key} className={`${col.align === 'right' ? 'text-right' : col.align === 'center' ? 'text-center' : 'text-left'}${col.monospace ? ' cell-mono' : ''}`}>
                  {col.render ? col.render(item, index) : ((item as Record<string, unknown>)[col.key] as React.ReactNode ?? '\u2014')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function StatusBadge({ status }: { status: string }) {
  const lang = getLang()
  const color = STATUS_COLORS[status] || '#94a3b8'
  const label = t(`status.${status}`, lang) !== `status.${status}` ? t(`status.${status}`, lang) : (STATUS_LABELS[status] || status)
  return (
    <span className="status-badge-dynamic" style={{
      '--status-bg': `${color}18`,
      '--status-color': color,
      '--status-border': `${color}30`,
    } as React.CSSProperties}>
      {label}
    </span>
  )
}

export function formatPhone(phone: string) {
  if (!phone) return '\u2014'
  const p = phone.replace(/[^\d+]/g, '')
  if (p.startsWith('+86') && p.length === 14) return `+86 ${p.slice(3, 6)} ${p.slice(6, 10)} ${p.slice(10)}`
  if (p.startsWith('+') && p.length > 10) return `${p.slice(0, 3)} ${p.slice(3)}`
  return p
}
