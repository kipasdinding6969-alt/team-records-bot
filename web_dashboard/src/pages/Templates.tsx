import { useEffect, useState } from 'react'
import { api, getAuthState } from '../api'
import { getLang, t } from '../i18n'
import { useTheme } from '../ThemeContext'

interface Template {
  id: number
  name: string
  content: string
  category: string
  is_default: boolean
  created_by_name: string
}

export default function Templates() {
  const { theme } = useTheme()
  const [error, setError] = useState('');
  const lang = getLang()
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') setShowModal(false) }
    window.addEventListener('keydown', handleEsc)
    return () => window.removeEventListener('keydown', handleEsc)
  }, [])
  const [templates, setTemplates] = useState<Template[]>([])
  const [loading, setLoading] = useState(true)
  const [filterCat, setFilterCat] = useState<string>('all')
  const [showModal, setShowModal] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [formData, setFormData] = useState({ name: '', content: '', category: 'general' })

  const categories = ['all', 'general', 'followup', 'greeting', 'closing']

  const load = () => {
    setLoading(true)
    api.getTemplates()
      .then(setTemplates)
      .catch(console.error)
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      if (editId) {
        await api.updateTemplate(editId, formData)
      } else {
        await api.createTemplate(formData)
      }
      setShowModal(false)
      load()
    } catch (err) {
      setError(t('templates.save_failed', lang)); setTimeout(()=>setError(''), 3000)
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm(t('common.confirm', lang))) return
    try {
      await api.deleteTemplate(id)
      load()
    } catch (err) {
      setError(t('templates.delete_failed', lang)); setTimeout(()=>setError(''), 3000)
    }
  }

  const filtered = filterCat === 'all' ? templates : templates.filter(t => t.category === filterCat)

  return (
    <div className="page-container">
      {error && <div className="alert alert-error">{error}</div>}

      <div className="toolbar">
        <h1 className="page-title">{t('templates.title', lang)}</h1>
        <div className="toolbar-spacer" />
        <button
          className="btn-primary"
          onClick={() => { setEditId(null); setFormData({ name: '', content: '', category: 'general' }); setShowModal(true) }}
        >
          + {t('templates.new', lang)}
        </button>
      </div>

      <div className="tab-bar">
        {categories.map(c => (
          <button
            key={c}
            className={`tab-btn ${filterCat === c ? 'active' : ''}`}
            onClick={() => setFilterCat(c)}
          >
            {c === 'all' ? t('templates.all', lang) : c.charAt(0).toUpperCase() + c.slice(1)}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="empty-state">{t('common.loading', lang)}</div>
      ) : (
        <div className="template-grid">
          {filtered.map(tpl => (
            <div key={tpl.id} className="card template-card">
              <div className="template-card-header">
                <div>
                  <div className="template-card-title">{tpl.name}</div>
                  <span className="pill-badge badge-info">{tpl.category}</span>
                </div>
                <div className="template-card-actions">
                  <button className="btn-secondary btn-sm" onClick={() => { setEditId(tpl.id); setFormData({ name: tpl.name, content: tpl.content, category: tpl.category }); setShowModal(true) }}>{t('common.edit', lang)}</button>
                  <button className="btn-danger btn-sm" onClick={() => handleDelete(tpl.id)}>{t('common.delete', lang)}</button>
                </div>
              </div>
              <pre className="template-preview">
                {tpl.content}
              </pre>
              <div className="template-meta">
                {t('templates.by', lang)} {tpl.created_by_name}
              </div>
            </div>
          ))}
        </div>
      )}

      {showModal && (
        <div className="modal-overlay">
          <div className="modal-content">
            <h3 className="modal-title">{editId ? t('common.edit', lang) : t('templates.new', lang)}</h3>
            <form onSubmit={handleSubmit} className="form-grid">
              <label>
                <span className="field-label">{t('templates.name', lang)}</span>
                <input className="input" required value={formData.name} onChange={e => setFormData({...formData, name: e.target.value})} />
              </label>
              <label>
                <span className="field-label">{t('templates.category', lang)}</span>
                <select className="input" value={formData.category} onChange={e => setFormData({...formData, category: e.target.value})}>
                  <option value="general">{t('templates.general', lang)}</option>
                  <option value="followup">{t('templates.followup', lang)}</option>
                  <option value="greeting">{t('templates.greeting', lang)}</option>
                  <option value="closing">{t('templates.closing', lang)}</option>
                </select>
              </label>
              <label>
                <span className="field-label">{t('templates.content', lang)}</span>
                <textarea className="input template-textarea" required rows={6} value={formData.content} onChange={e => setFormData({...formData, content: e.target.value})} />
              </label>
              <div className="modal-actions">
                <button type="button" className="btn-secondary" onClick={() => setShowModal(false)}>{t('common.cancel', lang)}</button>
                <button type="submit" className="btn-primary">{t('common.save', lang)}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
