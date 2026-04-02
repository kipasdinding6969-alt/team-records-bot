import React from 'react'
import { useTheme } from '../ThemeContext'
import { getLang, t } from '../i18n'
import type { ClientPipelineStatus, ClientRoleAssignment, KnifeDeposit } from '../types'
import { KILL_LABELS, ROLE_TYPE_LABELS } from '../types'

interface PipelineTimelineProps {
  pipeline: ClientPipelineStatus | null
  roles: ClientRoleAssignment[]
  knives: KnifeDeposit[]
}

const PIPELINE_STEPS = [
  { key: 'contacted_at', i18n: 'pipeline.contacted', icon: '1' },
  { key: 'replied_at', i18n: 'pipeline.replied', icon: '2' },
  { key: 'registered_at', i18n: 'pipeline.registered', icon: '3' },
  { key: 'training_completed_at', i18n: 'pipeline.training_completed', icon: '4' },
  { key: 'bonus_withdrew_at', i18n: 'pipeline.bonus_withdrew', icon: '5' },
  { key: 'day1_complete', i18n: 'pipeline.day1_complete', icon: 'D1' },
  { key: 'day2_training_at', i18n: 'pipeline.day2_training', icon: '6' },
  { key: 'own_tasks_started_at', i18n: 'pipeline.own_tasks', icon: '7' },
  { key: 'insufficient_funds_at', i18n: 'pipeline.insufficient_funds', icon: 'HO' },
] as const

export default function PipelineTimeline({ pipeline, roles, knives }: PipelineTimelineProps) {
  const { theme } = useTheme()
  const lang = getLang()

  if (!pipeline || (pipeline as any).status === 'no_pipeline') {
    return (
      <div style={{ padding: 16, color: theme.textSecondary, textAlign: 'center', fontSize: 13 }}>
        {t('common.no_data', lang)}
      </div>
    )
  }

  const getStepStatus = (step: typeof PIPELINE_STEPS[number]): 'done' | 'pending' => {
    const val = (pipeline as any)[step.key]
    return val ? 'done' : 'pending'
  }

  const activeRole = roles.find(r => r.is_active && (r.role_type === 'maintainer' || r.role_type === 'full_line'))
  const frontdeskRole = roles.find(r => r.role_type === 'frontdesk')
  const isHandedOff = !!pipeline.insufficient_funds_at

  const killLabel = pipeline.kill_type
    ? `${KILL_LABELS[pipeline.kill_type]?.[lang] || pipeline.kill_type} ${pipeline.kill_knife || ''}${t('kill.knife', lang)}`
    : null

  return (
    <div style={{ background: theme.cardBg, border: `1px solid ${theme.cardBorder}`, borderRadius: 12, padding: 16, marginBottom: 16 }}>
      <div className="section-title">
        {t('pipeline.client_pipeline', lang)}
      </div>

      {/* Pipeline steps bar */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 16, overflowX: 'auto' }}>
        {PIPELINE_STEPS.map((step, i) => {
          const status = getStepStatus(step)
          const isDone = status === 'done'
          const isHandoff = step.key === 'insufficient_funds_at'
          return (
            <div key={step.key} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <div style={{
                width: 32, height: 32, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 10, fontWeight: 700,
                background: isDone ? (isHandoff ? theme.warning : theme.accent) : theme.bg,
                color: isDone ? '#fff' : theme.textMuted,
                border: `2px solid ${isDone ? (isHandoff ? theme.warning : theme.accent) : theme.cardBorder}`,
                transition: 'all 0.2s',
              }}>
                {step.icon}
              </div>
              <div style={{ fontSize: 10, color: isDone ? theme.textPrimary : theme.textMuted, fontWeight: isDone ? 600 : 400, whiteSpace: 'nowrap', maxWidth: 60, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {t(step.i18n, lang)}
              </div>
              {i < PIPELINE_STEPS.length - 1 && (
                <div style={{ width: 12, height: 2, background: isDone ? theme.accent : theme.cardBorder }} />
              )}
            </div>
          )
        })}
      </div>

      {/* Handoff indicator */}
      {isHandedOff && (
        <div style={{
          padding: '8px 12px', borderRadius: 8, marginBottom: 12,
          background: theme.warningBg, border: `1px solid ${theme.warning}40`,
          fontSize: 12, fontWeight: 600, color: theme.warning,
          display: 'flex', alignItems: 'center', gap: 8,
        }}>
          {t('pipeline.handoff', lang)}: {frontdeskRole?.staff_name || '?'} → {activeRole?.staff_name || '?'}
        </div>
      )}

      {/* Deposit stages */}
      <div style={{ display: 'flex', gap: 12, marginBottom: knives.length > 0 ? 12 : 0, flexWrap: 'wrap' }}>
        {pipeline.new_order_amount !== null && (
          <div style={{
            padding: '8px 14px', borderRadius: 8,
            background: pipeline.new_order_amount > 0 ? theme.successBg : theme.dangerBg,
            border: `1px solid ${pipeline.new_order_amount > 0 ? theme.success : theme.danger}40`,
            fontSize: 13, fontWeight: 600,
            color: pipeline.new_order_amount > 0 ? theme.success : theme.danger,
          }}>
            {t('pipeline.new_order', lang)}: {pipeline.new_order_amount > 0 ? `$${pipeline.new_order_amount.toLocaleString()}` : 'Failed'}
          </div>
        )}
        {pipeline.pressure_amount !== null && (
          <div style={{
            padding: '8px 14px', borderRadius: 8,
            background: pipeline.pressure_amount > 0 ? theme.successBg : theme.dangerBg,
            border: `1px solid ${pipeline.pressure_amount > 0 ? theme.success : theme.danger}40`,
            fontSize: 13, fontWeight: 600,
            color: pipeline.pressure_amount > 0 ? theme.success : theme.danger,
          }}>
            {t('pipeline.pressure', lang)}: {pipeline.pressure_amount > 0 ? `$${pipeline.pressure_amount.toLocaleString()}` : 'Failed'}
          </div>
        )}
      </div>

      {/* Knife deposits */}
      {knives.length > 0 && (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
          {knives.map(k => (
            <div key={k.knife_number} style={{
              padding: '6px 10px', borderRadius: 8, fontSize: 12, fontWeight: 600,
              background: k.amount >= 0 ? theme.accentLight : theme.dangerBg,
              color: k.amount >= 0 ? theme.accent : theme.danger,
              border: `1px solid ${k.amount >= 0 ? theme.accent : theme.danger}30`,
              fontFamily: 'monospace',
            }}>
              {k.knife_number}{t('kill.knife', lang)}: ${k.amount.toLocaleString()}
            </div>
          ))}
        </div>
      )}

      {/* Kill / Total */}
      <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
        {killLabel && (
          <div style={{
            padding: '6px 12px', borderRadius: 8,
            background: theme.dangerBg, color: theme.danger,
            border: `1px solid ${theme.danger}40`,
            fontSize: 12, fontWeight: 700,
          }}>
            {killLabel}
          </div>
        )}
        {pipeline.total_deposited > 0 && (
          <div style={{ fontSize: 14, fontWeight: 700, color: theme.success, fontFamily: 'monospace' }}>
            {t('kill.total_deposited', lang)}: ${pipeline.total_deposited.toLocaleString()}
          </div>
        )}
        {pipeline.is_unkilled === 1 && (
          <div style={{
            padding: '4px 10px', borderRadius: 8,
            background: theme.warningBg, color: theme.warning,
            fontSize: 11, fontWeight: 600,
          }}>
            {t('kill.unkill', lang)} {pipeline.unkill_reason ? `- ${pipeline.unkill_reason}` : ''}
          </div>
        )}
      </div>

      {/* Role assignments */}
      {roles.length > 0 && (
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: `1px solid ${theme.cardBorder}` }}>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {roles.map(r => (
              <div key={r.id} style={{
                padding: '4px 10px', borderRadius: 9999, fontSize: 11, fontWeight: 600,
                background: r.is_active ? theme.accentLight : theme.bg,
                color: r.is_active ? theme.accent : theme.textMuted,
                border: `1px solid ${r.is_active ? theme.accent : theme.cardBorder}40`,
                opacity: r.is_active ? 1 : 0.6,
              }}>
                {ROLE_TYPE_LABELS[r.role_type]?.[lang] || r.role_type}: {r.staff_name || `#${r.staff_id}`}
                {!r.is_active && r.handoff_reason ? ` (${r.handoff_reason})` : ''}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
