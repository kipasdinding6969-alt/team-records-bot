import { useEffect, useState } from 'react'
import { api, getAuthState } from '../api'
import { useTheme } from '../ThemeContext'
import { t, getLang } from '../i18n'
import { PageHeader, Spinner, Empty } from '../components/SharedUI'
import type { GroupCompareData, GroupCompareRow } from '../types'

export default function GroupOverview() {
  const { theme } = useTheme()
  const lang = getLang()
  const auth = getAuthState()

  const [loading, setLoading] = useState(true)
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10))
  const [groups, setGroups] = useState<GroupCompareData[]>([])
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const loadData = async (selectedDate: string) => {
    setLoading(true)
    try {
      const res = await api.groupCompare(selectedDate)
      setGroups(res.groups || [])
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      setMessage({ type: 'error', text: msg || t('common.error', lang) })
      setTimeout(() => setMessage(null), 3000)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData(date)
  }, [date])

  const handleDateChange = (newDate: string) => {
    setDate(newDate)
  }

  const renderStaffTable = (members: GroupCompareRow[], label: string) => {
    if (!members || members.length === 0) return <Empty label={t('common.no_data', lang)} />

    // Normalize field names
    const normalized = members.map(m => ({
      staff_id: m.staff_id,
      name: m.display_name || '-',
      powder: m.powder_count || 0,
      reply_pct: m.reply_rate || 0,
      register: m.completed_registration || 0,
      training: m.completed_training || 0,
      withdraw: m.withdrawal || 0,
      orders: m.new_order || 0,
      conversion_pct: m.conversion_rate || 0,
    }))

    const totals = normalized.reduce((acc, m) => ({
      powder: acc.powder + m.powder,
      register: acc.register + m.register,
      training: acc.training + m.training,
      withdraw: acc.withdraw + m.withdraw,
      orders: acc.orders + m.orders,
    }), { powder: 0, register: 0, training: 0, withdraw: 0, orders: 0 })

    const avgReply = normalized.length > 0
      ? normalized.reduce((s, m) => s + m.reply_pct, 0) / normalized.length : 0
    const convPct = totals.powder > 0 ? (totals.orders / totals.powder) * 100 : 0

    return (
      <div className="overflow-x">
        <div className="label-sm text-accent mb-8">{label}</div>
        <table className="data-grid-table">
          <thead>
            <tr>
              <th>{t('perf.name', lang)}</th>
              <th className="text-right">{t('perf.new_powder', lang)}</th>
              <th className="text-right">{t('perf.reply_rate', lang)}</th>
              <th className="text-right">{t('perf.register', lang)}</th>
              <th className="text-right">{t('perf.training', lang)}</th>
              <th className="text-right">{t('perf.withdraw', lang)}</th>
              <th className="text-right">{t('perf.new_order', lang)}</th>
              <th className="text-right">{t('perf.conversion', lang)}</th>
            </tr>
          </thead>
          <tbody>
            {normalized.map((m, idx) => (
              <tr key={m.staff_id || idx}>
                <td className="text-bold">{m.name}</td>
                <td className="text-right text-bold">{m.powder}</td>
                <td className="text-right">{m.reply_pct.toFixed(1)}%</td>
                <td className="text-right text-bold text-success">{m.register}</td>
                <td className="text-right">{m.training}</td>
                <td className="text-right">{m.withdraw}</td>
                <td className="text-right text-bold text-accent">{m.orders}</td>
                <td className="text-right">{m.conversion_pct.toFixed(1)}%</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="group-total-row">
              <td className="text-bold label-sm text-uppercase">{t('common.total', lang)}</td>
              <td className="text-right text-bold">{totals.powder}</td>
              <td className="text-right text-bold">{avgReply.toFixed(1)}%</td>
              <td className="text-right text-bold text-success">{totals.register}</td>
              <td className="text-right text-bold">{totals.training}</td>
              <td className="text-right text-bold">{totals.withdraw}</td>
              <td className="text-right text-bold text-accent">{totals.orders}</td>
              <td className="text-right text-bold">{convPct.toFixed(1)}%</td>
            </tr>
          </tfoot>
        </table>
      </div>
    )
  }

  // Grand totals from API response (team-level totals)
  const grandTotals = groups.reduce((acc, g) => {
    const t = g.totals || {}
    acc.new_leads += t.new_leads || 0
    acc.registered += t.registered || 0
    acc.training += t.training || 0
    acc.withdrew += t.withdrew || 0
    acc.orders += t.orders || 0
    acc.killed += t.killed || 0
    acc.total += t.total_clients || 0
    return acc
  }, { new_leads: 0, registered: 0, training: 0, withdrew: 0, orders: 0, killed: 0, total: 0 })

  return (
    <div className="page-container">
      <PageHeader title={t('groups.title', lang)} />

      {message && (
        <div className={`alert ${message.type === 'error' ? 'alert-error' : 'alert-success'}`}>
          {message.text}
        </div>
      )}

      <div className="d-flex align-center gap-12 mb-20">
        <label className="field-label">{t('detail.date', lang)}:</label>
        <input className="input width-auto" type="date" value={date} onChange={e => handleDateChange(e.target.value)} />
      </div>

      {loading ? <Spinner /> : groups.length === 0 ? <Empty label={t('common.no_data', lang)} /> : (
        <>
          <div className="grid-auto-440 mb-20">
            {groups.map((g: GroupCompareData, idx: number) => (
              <div className="card overflow-hidden" key={g.team || idx}>
                <div className="group-card-header">
                  <div>
                    <div className="heading-sm">{g.team || `Group ${idx + 1}`}</div>
                    <div className="caption mt-4">
                      {t('groups.leader', lang)}: <span className="text-bold text-accent">{g.leader || '-'}</span>
                    </div>
                  </div>
                  <div className="group-member-count">
                    {g.totals?.total_clients ?? (g.today || []).length}
                  </div>
                </div>

                {renderStaffTable(g.today || [], t('groups.today_stats', lang))}

                {g.cumulative && g.cumulative.length > 0 && (
                  <div className="mt-20 pt-20 border-top">
                    {renderStaffTable(g.cumulative, t('groups.cumulative_stats', lang))}
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className="card group-grand-total mb-20">
            <h3 className="heading-sm text-accent mb-20">{t('groups.grand_total', lang)} - {t('groups.all_teams', lang)}</h3>
            <div className="grand-total-grid">
              {[
                { value: grandTotals.new_leads, label: t('perf.new_powder', lang), cls: '' },
                { value: grandTotals.registered, label: t('perf.register', lang), cls: 'text-success' },
                { value: grandTotals.training, label: t('perf.training', lang), cls: '' },
                { value: grandTotals.withdrew, label: t('perf.withdraw', lang), cls: '' },
                { value: grandTotals.orders, label: t('perf.new_order', lang), cls: 'text-accent' },
                { value: grandTotals.total > 0 ? ((grandTotals.orders / grandTotals.total) * 100).toFixed(1) + '%' : '0.0%', label: t('perf.conversion', lang), cls: 'text-accent' },
              ].map((item) => (
                <div key={item.label} className="grand-total-item">
                  <div className={`grand-total-value ${item.cls}`}>{item.value}</div>
                  <div className="grand-total-label">{item.label}</div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
