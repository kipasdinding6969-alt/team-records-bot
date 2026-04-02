import { useEffect, useState } from 'react'
import { api, getAuthState } from '../api'
import { useTheme } from '../ThemeContext'
import { t, getLang } from '../i18n'
import { PageHeader, Spinner, Empty } from '../components/SharedUI'

export default function GroupOverview() {
  const { theme } = useTheme()
  const lang = getLang()
  const auth = getAuthState()

  const [loading, setLoading] = useState(true)
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10))
  const [groups, setGroups] = useState<any[]>([])
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const loadData = async (selectedDate: string) => {
    setLoading(true)
    try {
      const res = await api.groupCompare(selectedDate)
      setGroups(res.groups || [])
    } catch (e: any) {
      setMessage({ type: 'error', text: e.message || t('common.error', lang) })
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
    loadData(newDate)
  }

  const tealAccent = theme.accent

  const renderStaffTable = (members: any[], label: string) => {
    if (!members || members.length === 0) return <Empty label={t('common.no_data', lang)} />

    const totals = members.reduce((acc, m) => ({
      powder: acc.powder + (m.powder || 0),
      reply_pct: 0,
      register: acc.register + (m.register || 0),
      training: acc.training + (m.training || 0),
      withdraw: acc.withdraw + (m.withdraw || 0),
      orders: acc.orders + (m.orders || 0),
      conversion_pct: 0,
    }), { powder: 0, reply_pct: 0, register: 0, training: 0, withdraw: 0, orders: 0, conversion_pct: 0 })

    const totalPowder = totals.powder
    totals.reply_pct = members.reduce((s: number, m: any) => s + (m.reply_pct || 0), 0) / members.length
    totals.conversion_pct = totalPowder > 0 ? ((totals.orders / totalPowder) * 100) : 0

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
            {members.map((m: any, idx: number) => (
              <tr key={m.staff_id || idx}>
                <td className="text-bold">{m.name || m.display_name || '-'}</td>
                <td className="text-right text-bold">{m.powder || 0}</td>
                <td className="text-right">{(m.reply_pct || 0).toFixed(1)}%</td>
                <td className="text-right text-bold text-success">{m.register || 0}</td>
                <td className="text-right">{m.training || 0}</td>
                <td className="text-right">{m.withdraw || 0}</td>
                <td className="text-right text-bold text-accent">{m.orders || 0}</td>
                <td className="text-right">{(m.conversion_pct || 0).toFixed(1)}%</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="group-total-row">
              <td className="text-bold label-sm text-uppercase">{t('common.total', lang)}</td>
              <td className="text-right text-bold">{totals.powder}</td>
              <td className="text-right text-bold">{totals.reply_pct.toFixed(1)}%</td>
              <td className="text-right text-bold text-success">{totals.register}</td>
              <td className="text-right text-bold">{totals.training}</td>
              <td className="text-right text-bold">{totals.withdraw}</td>
              <td className="text-right text-bold text-accent">{totals.orders}</td>
              <td className="text-right text-bold">{totals.conversion_pct.toFixed(1)}%</td>
            </tr>
          </tfoot>
        </table>
      </div>
    )
  }

  const grandTotals = groups.reduce((acc, g) => {
    const todayMembers = g.today_members || g.members || []
    todayMembers.forEach((m: any) => {
      acc.powder += m.powder || 0
      acc.register += m.register || 0
      acc.training += m.training || 0
      acc.withdraw += m.withdraw || 0
      acc.orders += m.orders || 0
    })
    return acc
  }, { powder: 0, register: 0, training: 0, withdraw: 0, orders: 0 })

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
            {groups.map((g: any, idx: number) => (
              <div className="card overflow-hidden" key={g.group_name || idx}>
                <div className="group-card-header">
                  <div>
                    <div className="heading-sm">{g.group_name || g.team || `Group ${idx + 1}`}</div>
                    <div className="caption mt-4">
                      {t('groups.leader', lang)}: <span className="text-bold text-accent">{g.leader_name || '-'}</span>
                    </div>
                  </div>
                  <div className="group-member-count">
                    {(g.today_members || g.members || []).length}
                  </div>
                </div>

                {renderStaffTable(g.today_members || g.members || [], t('groups.today_stats', lang))}

                {g.cumulative_members && g.cumulative_members.length > 0 && (
                  <div className="mt-20 pt-20 border-top">
                    {renderStaffTable(g.cumulative_members, t('groups.cumulative_stats', lang))}
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className="card group-grand-total mb-20">
            <h3 className="heading-sm text-accent mb-20">{t('groups.grand_total', lang)} - {t('groups.all_teams', lang)}</h3>
            <div className="grand-total-grid">
              {[
                { value: grandTotals.powder, label: t('perf.new_powder', lang), cls: '' },
                { value: grandTotals.register, label: t('perf.register', lang), cls: 'text-success' },
                { value: grandTotals.training, label: t('perf.training', lang), cls: '' },
                { value: grandTotals.withdraw, label: t('perf.withdraw', lang), cls: '' },
                { value: grandTotals.orders, label: t('perf.new_order', lang), cls: 'text-accent' },
                { value: grandTotals.powder > 0 ? ((grandTotals.orders / grandTotals.powder) * 100).toFixed(1) + '%' : '0.0%', label: t('perf.conversion', lang), cls: 'text-accent' },
              ].map((item, i) => (
                <div key={i} className="grand-total-item">
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
