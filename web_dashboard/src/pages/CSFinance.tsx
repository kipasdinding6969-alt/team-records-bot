import { useEffect, useState } from 'react'
import { api } from '../api'
import { getLang, t } from '../i18n'
import { useTheme } from '../ThemeContext'

const COUNTRIES = [
  { value: 'Norway', key: 'cs_finance.norway' },
  { value: 'Sweden', key: 'cs_finance.sweden' },
  { value: 'Switzerland', key: 'cs_finance.switzerland' },
  { value: 'France', key: 'cs_finance.france' },
  { value: 'USA', key: 'cs_finance.usa' },
  { value: 'Canada', key: 'cs_finance.canada' },
  { value: 'Australia', key: 'cs_finance.australia' },
  { value: 'UK', key: 'cs_finance.uk' },
  { value: 'Ireland', key: 'cs_finance.ireland' },
  { value: 'Finland', key: 'cs_finance.finland' },
]

interface CryptoEntry {
  id: number
  date: string
  txn_type: string
  client_name: string
  amount_usdt: number
  country: string
  situation: string
}

interface CountrySummary {
  country: string
  new_orders: number
  deposit_count: number
  total_deposits: number
  avg_per_client: number
}

export default function CSFinance() {
  const { theme } = useTheme()
  const lang = getLang()

  const [tab, setTab] = useState<'crypto' | 'daily'>('crypto')

  const [ledger, setLedger] = useState<CryptoEntry[]>([])
  const [ledgerLoading, setLedgerLoading] = useState(true)
  const [fromDate, setFromDate] = useState(() => {
    const d = new Date(); d.setDate(d.getDate() - 30); return d.toISOString().split('T')[0]
  })
  const [toDate, setToDate] = useState(() => new Date().toISOString().split('T')[0])
  const [showTxnModal, setShowTxnModal] = useState(false)
  const [txnForm, setTxnForm] = useState({ txn_type: 'in', client_name: '', amount_usdt: '', country: COUNTRIES[0].value, situation: '' })
  const [error, setError] = useState('')

  const [dailyDate, setDailyDate] = useState(() => new Date().toISOString().split('T')[0])
  const [dailyData, setDailyData] = useState<CountrySummary[]>([])
  const [dailyLoading, setDailyLoading] = useState(false)

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') setShowTxnModal(false) }
    window.addEventListener('keydown', handleEsc)
    return () => window.removeEventListener('keydown', handleEsc)
  }, [])

  const loadLedger = () => {
    setLedgerLoading(true)
    api.cryptoLedger(fromDate, toDate)
      .then(setLedger)
      .catch(() => { setError(t('cs_finance.load_failed', lang)); setTimeout(() => setError(''), 3000) })
      .finally(() => setLedgerLoading(false))
  }

  const loadDaily = () => {
    setDailyLoading(true)
    api.dailyFinancial(dailyDate)
      .then(data => setDailyData(data.countries || []))
      .catch(() => { setError(t('cs_finance.load_failed', lang)); setTimeout(() => setError(''), 3000) })
      .finally(() => setDailyLoading(false))
  }

  useEffect(() => { loadLedger() }, [fromDate, toDate])
  useEffect(() => { if (tab === 'daily') loadDaily() }, [dailyDate, tab])

  const handleAddTxn = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      await api.addCryptoTransaction({
        txn_type: txnForm.txn_type,
        client_name: txnForm.client_name,
        amount_usdt: parseFloat(txnForm.amount_usdt),
        country: txnForm.country,
        situation: txnForm.situation,
      })
      setShowTxnModal(false)
      setTxnForm({ txn_type: 'in', client_name: '', amount_usdt: '', country: 'Norway', situation: '' })
      loadLedger()
    } catch {
      setError(t('cs_finance.add_failed', lang)); setTimeout(() => setError(''), 3000)
    }
  }

  const totalIn = ledger.filter(e => e.txn_type === 'in').reduce((s, e) => s + e.amount_usdt, 0)
  const totalOut = ledger.filter(e => e.txn_type === 'out').reduce((s, e) => s + e.amount_usdt, 0)
  const balance = totalIn - totalOut

  return (
    <div className="page-container">
      {error && (
        <div className="alert alert-error">{error}</div>
      )}

      <h1 className="page-title mb-24">{t('cs_finance.title', lang)}</h1>

      <div className="tab-bar">
        <button className={`tab-btn ${tab === 'crypto' ? 'active' : ''}`} onClick={() => setTab('crypto')}>
          {t('cs_finance.crypto_ledger', lang)}
        </button>
        <button className={`tab-btn ${tab === 'daily' ? 'active' : ''}`} onClick={() => setTab('daily')}>
          {t('cs_finance.daily_summary', lang)}
        </button>
      </div>

      {/* Crypto Ledger Tab */}
      {tab === 'crypto' && (
        <div>
          <div className="toolbar">
            <input className="input width-auto" type="date" value={fromDate} onChange={e => setFromDate(e.target.value)} />
            <span className="text-secondary">~</span>
            <input className="input width-auto" type="date" value={toDate} onChange={e => setToDate(e.target.value)} />
            <div className="toolbar-spacer" />
            <button className="btn-primary" onClick={() => setShowTxnModal(true)}>
              + {t('cs_finance.add_transaction', lang)}
            </button>
          </div>

          {ledgerLoading ? (
            <div className="empty-state text-center">{t('common.loading', lang)}</div>
          ) : (
            <>
              <div className="card overflow-hidden mb-20">
                <table className="data-grid-table">
                  <thead>
                    <tr>
                      <th>{t('cs_finance.col_date', lang)}</th>
                      <th>{t('cs_finance.col_direction', lang)}</th>
                      <th>{t('cs_finance.col_client', lang)}</th>
                      <th className="text-right">{t('cs_finance.col_amount', lang)}</th>
                      <th>{t('cs_finance.col_country', lang)}</th>
                      <th>{t('cs_finance.col_situation', lang)}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ledger.map(entry => (
                      <tr key={entry.id}>
                        <td className="text-nowrap">{entry.date}</td>
                        <td>
                          <span className={`${entry.txn_type === 'in' ? 'badge-success' : 'badge-danger'} caption`}>
                            {entry.txn_type === 'in' ? 'IN' : 'OUT'}
                          </span>
                        </td>
                        <td className="text-bold">{entry.client_name}</td>
                        <td className={`text-right cell-mono text-bold ${entry.txn_type === 'in' ? 'text-success' : 'text-danger'}`}>
                          {entry.txn_type === 'in' ? '+' : '-'}{entry.amount_usdt.toLocaleString()} USDT
                        </td>
                        <td>{entry.country}</td>
                        <td className="text-secondary text-truncate max-w-200">{entry.situation}</td>
                      </tr>
                    ))}
                    {ledger.length === 0 && (
                      <tr><td colSpan={6} className="text-center p-24 caption">{t('cs_finance.no_data', lang)}</td></tr>
                    )}
                  </tbody>
                </table>
              </div>

              {/* Running totals */}
              <div className="d-flex gap-20 flex-wrap">
                <div className="stat-card flex-1 min-w-180 text-center">
                  <div className="metric-label mb-8">{t('cs_finance.total_in', lang)}</div>
                  <div className="metric-value cell-mono text-success">+{totalIn.toLocaleString()} USDT</div>
                </div>
                <div className="stat-card flex-1 min-w-180 text-center">
                  <div className="metric-label mb-8">{t('cs_finance.total_out', lang)}</div>
                  <div className="metric-value cell-mono text-danger">-{totalOut.toLocaleString()} USDT</div>
                </div>
                <div className="stat-card flex-1 min-w-180 text-center stat-card-accent">
                  <div className="metric-label mb-8">{t('cs_finance.balance', lang)}</div>
                  <div className={`metric-value cell-mono ${balance >= 0 ? 'text-success' : 'text-danger'}`}>{balance >= 0 ? '+' : ''}{balance.toLocaleString()} USDT</div>
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* Daily Summary Tab */}
      {tab === 'daily' && (
        <div>
          <div className="toolbar">
            <input className="input width-auto" type="date" value={dailyDate} onChange={e => setDailyDate(e.target.value)} />
          </div>

          {dailyLoading ? (
            <div className="empty-state text-center">{t('common.loading', lang)}</div>
          ) : dailyData.length === 0 ? (
            <div className="empty-state">
              <div className="empty-text">{t('cs_finance.no_daily', lang)}</div>
            </div>
          ) : (
            <div className="grid-auto-240 gap-20">
              {COUNTRIES.map(c => {
                const data = dailyData.find(d => d.country === c.value) || { country: c.value, new_orders: 0, deposit_count: 0, total_deposits: 0, avg_per_client: 0 }
                return (
                  <div className="card" key={c.value}>
                    <div className="heading-sm text-accent mb-20">{t(c.key, lang)}</div>
                    <div className="grid-2col gap-12">
                      <div className="metric-card">
                        <div className="metric-value metric-value-md text-success">{data.new_orders}</div>
                        <div className="metric-label">{t('cs_finance.new_orders', lang)}</div>
                      </div>
                      <div className="metric-card">
                        <div className="metric-value metric-value-md text-accent">{data.deposit_count}</div>
                        <div className="metric-label">{t('cs_finance.deposit_count', lang)}</div>
                      </div>
                      <div className="metric-card">
                        <div className="metric-value metric-value-md cell-mono text-success">${data.total_deposits.toLocaleString()}</div>
                        <div className="metric-label">{t('cs_finance.total_deposits', lang)}</div>
                      </div>
                      <div className="metric-card">
                        <div className="metric-value metric-value-md cell-mono text-warning">${data.avg_per_client.toLocaleString()}</div>
                        <div className="metric-label">{t('cs_finance.avg_per_client', lang)}</div>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* Add Transaction Modal */}
      {showTxnModal && (
        <div className="modal-overlay">
          <div className="modal-content modal-480">
            <h3 className="modal-title">{t('cs_finance.add_transaction', lang)}</h3>
            <form onSubmit={handleAddTxn} className="form-grid">
              <label>
                <span className="field-label">{t('cs_finance.txn_type', lang)}</span>
                <select className="input" value={txnForm.txn_type} onChange={e => setTxnForm({ ...txnForm, txn_type: e.target.value })}>
                  <option value="in">{t('cs_finance.type_in', lang)}</option>
                  <option value="out">{t('cs_finance.type_out', lang)}</option>
                </select>
              </label>
              <label>
                <span className="field-label">{t('cs_finance.client_name', lang)}</span>
                <input className="input" required value={txnForm.client_name} onChange={e => setTxnForm({ ...txnForm, client_name: e.target.value })} />
              </label>
              <div className="form-grid-2col">
                <label>
                  <span className="field-label">{t('cs_finance.amount_usdt', lang)}</span>
                  <input className="input" type="number" step="0.01" required value={txnForm.amount_usdt} onChange={e => setTxnForm({ ...txnForm, amount_usdt: e.target.value })} />
                </label>
                <label>
                  <span className="field-label">{t('cs_finance.country', lang)}</span>
                  <select className="input" value={txnForm.country} onChange={e => setTxnForm({ ...txnForm, country: e.target.value })}>
                    {COUNTRIES.map(c => <option key={c.value} value={c.value}>{t(c.key, lang)}</option>)}
                  </select>
                </label>
              </div>
              <label>
                <span className="field-label">{t('cs_finance.situation', lang)}</span>
                <input className="input" value={txnForm.situation} onChange={e => setTxnForm({ ...txnForm, situation: e.target.value })} />
              </label>
              <div className="modal-actions">
                <button type="button" className="btn-secondary" onClick={() => setShowTxnModal(false)}>{t('common.cancel', lang)}</button>
                <button type="submit" className="btn-primary">{t('common.save', lang)}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
