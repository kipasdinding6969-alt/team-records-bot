import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import type { Client, ClientList } from '../types'
import { Empty, PageHeader, Spinner } from '../components/SharedUI'
import { DataGrid, StatusBadge, formatPhone, Column } from '../components/DataGrid'
import { useTheme } from '../ThemeContext'
import { t, getLang } from '../i18n'

const STATUSES = ['', 'new', 'contacted', 'replied', 'registered', 'training', 'ordered', 'withdrew', 'ghosted', 'dead']
const PER_PAGE = 50

export default function Clients() {
  const { theme } = useTheme()
  const [params, setParams] = useSearchParams()
  const [data, setData] = useState<ClientList | null>(null)
  const [loading, setLoading] = useState(true)
  const nav = useNavigate()
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') setShowAdd(false) }
    window.addEventListener('keydown', handleEsc)
    return () => window.removeEventListener('keydown', handleEsc)
  }, [])
  const [showAdd, setShowAdd] = useState(false)
  const [addPhone, setAddPhone] = useState('')
  const [addSource, setAddSource] = useState('web')
  const [addNickname, setAddNickname] = useState('')
  const [addAccountId, setAddAccountId] = useState('')
  const [addCategory, setAddCategory] = useState('')
  const [addRecruiter, setAddRecruiter] = useState('')
  const [addPlatform, setAddPlatform] = useState('')
  const [addError, setAddError] = useState('')
  const [addSuccess, setAddSuccess] = useState('')
  const [phoneStatus, setPhoneStatus] = useState<any>(null)
  const [checkTimer, setCheckTimer] = useState<any>(null)
  const [addSubmitting, setAddSubmitting] = useState(false)

  const status = params.get('status') || ''
  const search = params.get('search') || ''
  const page = parseInt(params.get('page') || '1', 10)

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    if (key !== 'page') next.delete('page')
    setParams(next)
  }

  useEffect(() => {
    setLoading(true)
    api.clients({ status: status || undefined, search: search || undefined, page, per_page: PER_PAGE })
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [status, search, page])

  const totalPages = data ? Math.ceil(data.total / PER_PAGE) : 1

  function checkPhone(phone: string) {
    if (checkTimer) clearTimeout(checkTimer)
    setPhoneStatus(null)
    setAddError('')
    if (phone.replace(/[^\d]/g, '').length < 5) return
    const timer = setTimeout(() => {
      api.phoneCheck(phone).then(setPhoneStatus).catch(() => {})
    }, 400)
    setCheckTimer(timer)
  }

  async function submitNewClient() {
    if (!addPhone.trim() || !addSource) return
    setAddSubmitting(true)
    setAddError('')
    setAddSuccess('')
    try {
      const res = await api.createClient({
        phone: addPhone.trim(), source: addSource,
        nickname: addNickname || undefined, account_id: addAccountId || undefined,
        category: addCategory || undefined, recruiter: addRecruiter || undefined,
        platform: addPlatform || undefined,
      })
      setAddSuccess(`Client #${res.client_id} created`)
      setAddPhone('')
      setAddNickname('')
      setPhoneStatus(null)
      setLoading(true)
      api.clients({ status: status || undefined, search: search || undefined, page, per_page: PER_PAGE })
        .then(setData).finally(() => setLoading(false))
    } catch (e: any) {
      const msg = typeof e.message === 'string' ? e.message : 'Failed to create client'
      setAddError(msg)
    } finally {
      setAddSubmitting(false)
    }
  }

  return (
    <div className="page-container">
      <PageHeader title={t('clients.title', getLang())} sub={t('clients.manage_sub', getLang())} />

      {/* Filter bar */}
      <div className="toolbar">
        <input
          className="input min-w-240"
          type="text"
          placeholder={t('clients.search', getLang())}
          value={search}
          onChange={e => setParam('search', e.target.value)}
        />
        <select
          className="input w-180"
          value={status}
          onChange={e => setParam('status', e.target.value)}
        >
          {STATUSES.map(s => (
            <option key={s} value={s}>
              {s ? (t(`status.${s}`, getLang()) !== `status.${s}` ? t(`status.${s}`, getLang()) : s) : t('clients.all_status', getLang())}
            </option>
          ))}
        </select>
        <button
          className="btn-secondary"
          onClick={() => api.exportClients(status || undefined, undefined).catch(console.error)}
        >
          {t('clients.export_csv', getLang())}
        </button>
        <button
          className="btn-primary"
          onClick={() => { setShowAdd(true); setAddError(''); setAddSuccess(''); setPhoneStatus(null) }}
        >
          + {t('clients.add', getLang())}
        </button>
        <div className="toolbar-spacer" />
        {data && (
          <span className="pagination-info">
            {t('clients.total_records', getLang()).replace('{count}', data.total.toLocaleString())}
          </span>
        )}
      </div>

      {/* Table */}
      {loading ? (
        <Spinner />
      ) : (
        <div className="card overflow-hidden">
          {!data || data.clients.length === 0 ? (
            <Empty />
          ) : (
            <>
              <DataGrid
                columns={[
                  { key: 'phone', label: t('clients.phone', getLang()), monospace: true, render: (c: Client) => formatPhone(c.phone) },
                  { key: 'status', label: t('clients.status', getLang()), render: (c: Client) => <StatusBadge status={c.status} /> },
                  { key: 'source', label: t('clients.source', getLang()), render: (c: Client) => <span className="text-secondary">{c.source || '—'}</span> },
                  { key: 'frontdesk', label: t('clients.owner', getLang()), render: (c: Client) => c.frontdesk_name || '—' },
                  { key: 'team', label: t('detail.team', getLang()), render: (c: Client) => <span className="text-secondary">{c.team || '—'}</span> },
                  { key: 'deposit', label: t('clients.deposit', getLang()), monospace: true, render: (c: Client) => c.total_deposited > 0 ? <span className="text-success">${c.total_deposited.toLocaleString()}</span> : <span className="text-secondary">—</span> },
                  { key: 'next_followup', label: t('clients.next_followup', getLang()), monospace: true, render: (c: Client) => <span className={`fs-12 ${c.next_followup ? 'text-warning' : 'text-secondary'}`}>{c.next_followup ? new Date(c.next_followup).toLocaleDateString() : '—'}</span> },
                  { key: 'created_at', label: t('clients.created_at', getLang()), monospace: true, render: (c: Client) => <span className="text-secondary fs-12">{c.created_at ? new Date(c.created_at).toLocaleDateString() : '—'}</span> },
                ]}
                data={data.clients}
                onRowClick={c => nav(`/clients/${c.id}`)}
              />
              {/* Pagination */}
              {totalPages > 1 && (
                <div className="pagination">
                  <button
                    className="btn-secondary"
                    onClick={() => setParam('page', String(page - 1))}
                    disabled={page <= 1}
                  >
                    {t('clients.prev', getLang())}
                  </button>
                  <span className="pagination-info">
                    {t('clients.page_info', getLang()).replace('{page}', String(page)).replace('{total}', String(totalPages))}
                  </span>
                  <button
                    className="btn-secondary"
                    onClick={() => setParam('page', String(page + 1))}
                    disabled={page >= totalPages}
                  >
                    {t('clients.next', getLang())}
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Add Client Modal */}
      {showAdd && (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) setShowAdd(false) }}>
          <div className="modal-content w-480">
            <h3 className="modal-title">{t('clients.add_title', getLang())}</h3>

            {/* Phone input with live check */}
            <div className="mb-20">
              <label className="field-label">{t('clients.phone_input', getLang())}</label>
              <div className="d-flex gap-12">
                <input
                  className="input flex-1 input-phone"
                  value={addPhone}
                  onChange={e => { setAddPhone(e.target.value); checkPhone(e.target.value) }}
                  placeholder="e.g. +60123456789"
                />
                <button className="btn-secondary" onClick={() => checkPhone(addPhone)}>
                  {t('clients.check_again', getLang())}
                </button>
              </div>
              {phoneStatus && (
                <div className={`phone-check-result ${phoneStatus.status === 'taken' ? 'badge-danger' : phoneStatus.status === 'available' ? 'badge-success' : 'badge-warning'}`}>
                  <div className={`dot ${phoneStatus.status === 'taken' ? 'dot-danger' : phoneStatus.status === 'available' ? 'dot-success' : 'dot-warning'}`} />
                  {phoneStatus.status === 'available' && (
                    <span className="fw-600">{t('clients.phone_available', getLang())}</span>
                  )}
                  {phoneStatus.status === 'own' && (
                    <span className="fw-600">{t('clients.phone_own', getLang())}</span>
                  )}
                  {phoneStatus.status === 'taken' && (
                    <span className="fw-600">
                      {t('clients.phone_taken', getLang()).replace('{owner}', phoneStatus.owner)} ({phoneStatus.submitted_at?.split('T')[0]})
                    </span>
                  )}
                </div>
              )}
            </div>

            {/* 2-column form grid */}
            <div className="form-grid-2col mb-20">
              {/* Source */}
              <div>
                <label className="field-label">{t('clients.source_label', getLang())}</label>
                <select
                  className="input"
                  value={addSource}
                  onChange={e => setAddSource(e.target.value)}
                >
                  {['web', 'telegram', 'whatsapp', 'referral', 'facebook', 'instagram', 'tiktok', 'other'].map(s => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>

              {/* Platform */}
              <div>
                <label className="field-label">{t('clients.platform_label', getLang())}</label>
                <select className="input" value={addPlatform} onChange={e => setAddPlatform(e.target.value)}
                 >
                  <option value="">{t('clients.select', getLang())}</option>
                  {['MT5', 'MT4', 'cTrader', 'Other'].map(p => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                </select>
              </div>

              {/* Nickname */}
              <div>
                <label className="field-label">{t('clients.nickname_label', getLang())}</label>
                <input className="input" value={addNickname} onChange={e => setAddNickname(e.target.value)}
                  placeholder={t('clients.optional', getLang())} />
              </div>

              {/* Account ID */}
              <div>
                <label className="field-label">{t('clients.account_id_label', getLang())}</label>
                <input className="input" value={addAccountId} onChange={e => setAddAccountId(e.target.value)}
                  placeholder={t('clients.optional', getLang())} />
              </div>

              {/* Category */}
              <div>
                <label className="field-label">{t('clients.category_label', getLang())}</label>
                <select className="input" value={addCategory} onChange={e => setAddCategory(e.target.value)}
                 >
                  <option value="">{t('clients.select', getLang())}</option>
                  {['UK表单粉', 'CA表单粉', 'AU表单粉', 'EU表单粉', 'US表单粉', 'SEA表单粉', 'Other'].map(c => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </div>

              {/* Recruiter */}
              <div>
                <label className="field-label">{t('clients.recruiter_label', getLang())}</label>
                <input className="input" value={addRecruiter} onChange={e => setAddRecruiter(e.target.value)}
                  placeholder={t('clients.optional', getLang())} />
              </div>
            </div>

            {addError && <div className="alert alert-error">{addError}</div>}
            {addSuccess && <div className="alert alert-success">{addSuccess}</div>}

            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setShowAdd(false)}>
                {t('common.cancel', getLang())}
              </button>
              <button
                className="btn-primary"
                onClick={submitNewClient}
                disabled={addSubmitting || phoneStatus?.status === 'taken'}
              >
                {addSubmitting ? '...' : t('clients.submit', getLang())}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
