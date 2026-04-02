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
      setTimeout(() => setMessage(null), 4000)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData(date)
  }, [])

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

    const totalPowder = totals.powder || 1
    totals.reply_pct = members.reduce((s: number, m: any) => s + (m.reply_pct || 0), 0) / members.length
    totals.conversion_pct = totalPowder > 0 ? ((totals.orders / totalPowder) * 100) : 0

    return (
      <div style={{ overflowX: 'auto' }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: tealAccent, textTransform: 'uppercase', marginBottom: 8, letterSpacing: 0.5 }}>{label}</div>
        <table className="data-grid-table">
          <thead>
            <tr>
              <th>{t('perf.name', lang)}</th>
              <th style={{ textAlign: 'right' }}>{t('perf.new_powder', lang)}</th>
              <th style={{ textAlign: 'right' }}>{t('perf.reply_rate', lang)}</th>
              <th style={{ textAlign: 'right' }}>{t('perf.register', lang)}</th>
              <th style={{ textAlign: 'right' }}>{t('perf.training', lang)}</th>
              <th style={{ textAlign: 'right' }}>{t('perf.withdraw', lang)}</th>
              <th style={{ textAlign: 'right' }}>{t('perf.new_order', lang)}</th>
              <th style={{ textAlign: 'right' }}>{t('perf.conversion', lang)}</th>
            </tr>
          </thead>
          <tbody>
            {members.map((m: any, idx: number) => (
              <tr key={m.staff_id || idx}>
                <td style={{ fontWeight: 600 }}>{m.name || m.display_name || '-'}</td>
                <td style={{ textAlign: 'right', fontWeight: 600 }}>{m.powder || 0}</td>
                <td style={{ textAlign: 'right' }}>{(m.reply_pct || 0).toFixed(0)}%</td>
                <td style={{ textAlign: 'right', fontWeight: 600, color: theme.success }}>{m.register || 0}</td>
                <td style={{ textAlign: 'right' }}>{m.training || 0}</td>
                <td style={{ textAlign: 'right' }}>{m.withdraw || 0}</td>
                <td style={{ textAlign: 'right', fontWeight: 600, color: tealAccent }}>{m.orders || 0}</td>
                <td style={{ textAlign: 'right' }}>{(m.conversion_pct || 0).toFixed(1)}%</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr style={{ borderTop: `2px solid ${theme.cardBorder}`, background: `${tealAccent}08` }}>
              <td style={{ fontWeight: 700, fontSize: 12, textTransform: 'uppercase' }}>{t('common.total', lang)}</td>
              <td style={{ textAlign: 'right', fontWeight: 700 }}>{totals.powder}</td>
              <td style={{ textAlign: 'right', fontWeight: 700 }}>{totals.reply_pct.toFixed(0)}%</td>
              <td style={{ textAlign: 'right', fontWeight: 700, color: theme.success }}>{totals.register}</td>
              <td style={{ textAlign: 'right', fontWeight: 700 }}>{totals.training}</td>
              <td style={{ textAlign: 'right', fontWeight: 700 }}>{totals.withdraw}</td>
              <td style={{ textAlign: 'right', fontWeight: 700, color: tealAccent }}>{totals.orders}</td>
              <td style={{ textAlign: 'right', fontWeight: 700 }}>{totals.conversion_pct.toFixed(1)}%</td>
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
        <div style={{
          padding: 12, marginBottom: 20, borderRadius: 8, fontSize: 13, fontWeight: 600,
          background: message.type === 'error' ? theme.dangerBg : theme.successBg,
          color: message.type === 'error' ? theme.danger : theme.success,
          border: `1px solid ${message.type === 'error' ? theme.danger : theme.success}40`,
        }}>
          {message.text}
        </div>
      )}

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
        <label style={{ fontSize: 14, fontWeight: 600, color: theme.textSecondary }}>{t('detail.date', lang)}:</label>
        <input className="input" type="date" value={date} onChange={e => handleDateChange(e.target.value)} style={{ width: 'auto' }} />
      </div>

      {loading ? <Spinner /> : groups.length === 0 ? <Empty label={t('common.no_data', lang)} /> : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(440px, 1fr))', gap: 20, marginBottom: 20 }}>
            {groups.map((g: any, idx: number) => (
              <div className="card" key={g.group_name || idx} style={{ overflow: 'hidden' }}>
                <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <div style={{ fontSize: 16, fontWeight: 700, color: theme.textPrimary }}>{g.group_name || g.team || `Group ${idx + 1}`}</div>
                    <div style={{ fontSize: 12, color: theme.textSecondary, marginTop: 4 }}>
                      {t('groups.leader', lang)}: <span style={{ fontWeight: 600, color: tealAccent }}>{g.leader_name || '-'}</span>
                    </div>
                  </div>
                  <div style={{
                    width: 36, height: 36, borderRadius: '50%', background: `${tealAccent}20`,
                    color: tealAccent, display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontWeight: 700, fontSize: 14,
                  }}>
                    {(g.today_members || g.members || []).length}
                  </div>
                </div>

                {renderStaffTable(g.today_members || g.members || [], t('groups.today_stats', lang))}

                {g.cumulative_members && g.cumulative_members.length > 0 && (
                  <div style={{ marginTop: 20, paddingTop: 20, borderTop: `1px solid ${theme.cardBorder}` }}>
                    {renderStaffTable(g.cumulative_members, t('groups.cumulative_stats', lang))}
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className="card" style={{ border: `2px solid ${tealAccent}40`, marginBottom: 20 }}>
            <h3 style={{ margin: '0 0 20px', fontSize: 16, fontWeight: 700, color: tealAccent }}>{t('groups.grand_total', lang)} - {t('groups.all_teams', lang)}</h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: 12 }}>
              {[
                { value: grandTotals.powder, label: t('perf.new_powder', lang), color: theme.textPrimary },
                { value: grandTotals.register, label: t('perf.register', lang), color: theme.success },
                { value: grandTotals.training, label: t('perf.training', lang), color: theme.textPrimary },
                { value: grandTotals.withdraw, label: t('perf.withdraw', lang), color: theme.textPrimary },
                { value: grandTotals.orders, label: t('perf.new_order', lang), color: tealAccent },
                { value: grandTotals.powder > 0 ? ((grandTotals.orders / grandTotals.powder) * 100).toFixed(1) + '%' : '0.0%', label: t('perf.conversion', lang), color: theme.accent },
              ].map((item, i) => (
                <div key={i} style={{ background: theme.bg, borderRadius: 8, padding: 12, textAlign: 'center', border: `1px solid ${theme.cardBorder}` }}>
                  <div style={{ fontSize: 24, fontWeight: 700, color: item.color }}>{item.value}</div>
                  <div style={{ fontSize: 12, color: theme.textSecondary, textTransform: 'uppercase', fontWeight: 600, marginTop: 8 }}>{item.label}</div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
