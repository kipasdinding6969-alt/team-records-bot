import React from 'react'
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
  const lang = getLang()

  if (!pipeline || (pipeline as any).status === 'no_pipeline') {
    return (
      <div className="ptl-empty">
        {t('common.no_data', lang)}
      </div>
    )
  }

  const getStepStatus = (step: typeof PIPELINE_STEPS[number]): 'done' | 'pending' => {
    const val = (pipeline as any)[step.key]
    return val ? 'done' : 'pending'
  }

  const activeRole = roles.find(r => r.is_active && (r.role_type === 'maintenance' || r.role_type === 'full_line'))
  const frontdeskRole = roles.find(r => r.role_type === 'frontdesk')
  const isHandedOff = !!pipeline.insufficient_funds_at

  const killLabel = pipeline.kill_type
    ? `${KILL_LABELS[pipeline.kill_type]?.[lang] || pipeline.kill_type} ${pipeline.kill_knife || ''}${t('kill.knife', lang)}`
    : null

  return (
    <div className="ptl-wrap">
      <div className="section-title">
        {t('pipeline.client_pipeline', lang)}
      </div>

      {/* Pipeline steps bar */}
      <div className="ptl-steps">
        {PIPELINE_STEPS.map((step, i) => {
          const status = getStepStatus(step)
          const isDone = status === 'done'
          const isHandoff = step.key === 'insufficient_funds_at'
          const dotClass = ['ptl-dot', isDone ? 'done' : '', isDone && isHandoff ? 'handoff' : ''].filter(Boolean).join(' ')
          const labelClass = ['ptl-label', isDone ? 'done' : ''].filter(Boolean).join(' ')
          return (
            <div key={step.key} className="ptl-step">
              <div className={dotClass}>
                {step.icon}
              </div>
              <div className={labelClass}>
                {t(step.i18n, lang)}
              </div>
              {i < PIPELINE_STEPS.length - 1 && (
                <div className={`ptl-connector${isDone ? ' done' : ''}`} />
              )}
            </div>
          )
        })}
      </div>

      {/* Handoff indicator */}
      {isHandedOff && (
        <div className="ptl-handoff-banner">
          {t('pipeline.handoff', lang)}: {frontdeskRole?.staff_name || '?'} → {activeRole?.staff_name || '?'}
        </div>
      )}

      {/* Deposit stages */}
      <div className={`ptl-deposits${knives.length > 0 ? ' mb-12' : ''}`}>
        {pipeline.new_order_amount !== null && (
          <div className={`ptl-deposit-tag ${pipeline.new_order_amount > 0 ? 'success' : 'danger'}`}>
            {t('pipeline.new_order', lang)}: {pipeline.new_order_amount > 0 ? `$${pipeline.new_order_amount.toLocaleString()}` : 'Failed'}
          </div>
        )}
        {pipeline.pressure_amount !== null && (
          <div className={`ptl-deposit-tag ${pipeline.pressure_amount > 0 ? 'success' : 'danger'}`}>
            {t('pipeline.pressure', lang)}: {pipeline.pressure_amount > 0 ? `$${pipeline.pressure_amount.toLocaleString()}` : 'Failed'}
          </div>
        )}
      </div>

      {/* Knife deposits */}
      {knives.length > 0 && (
        <div className="ptl-knives">
          {knives.map(k => (
            <div key={k.knife_number} className={`ptl-knife-tag ${k.amount >= 0 ? 'accent' : 'danger'}`}>
              {k.knife_number}{t('kill.knife', lang)}: ${k.amount.toLocaleString()}
            </div>
          ))}
        </div>
      )}

      {/* Kill / Total */}
      <div className="ptl-summary">
        {killLabel && (
          <div className="ptl-kill-tag">
            {killLabel}
          </div>
        )}
        {pipeline.total_deposited > 0 && (
          <div className="ptl-total">
            {t('kill.total_deposited', lang)}: ${pipeline.total_deposited.toLocaleString()}
          </div>
        )}
        {pipeline.is_unkilled === 1 && (
          <div className="ptl-unkill-tag">
            {t('kill.unkill', lang)} {pipeline.unkill_reason ? `- ${pipeline.unkill_reason}` : ''}
          </div>
        )}
      </div>

      {/* Role assignments */}
      {roles.length > 0 && (
        <div className="ptl-roles">
          <div className="ptl-roles-list">
            {roles.map(r => (
              <div key={r.id} className={`ptl-role-pill ${r.is_active ? 'active' : 'inactive'}`}>
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
