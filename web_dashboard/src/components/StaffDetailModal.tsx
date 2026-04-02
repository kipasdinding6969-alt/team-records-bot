import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, getRole } from '../api';
import { t, getLang } from '../i18n';

interface StaffDetailModalProps {
  staffId: number;
  onClose: () => void;
  onUpdate: () => void;
}

export function StaffDetailModal({ staffId, onClose, onUpdate }: StaffDetailModalProps) {
  const lang = getLang();
  const nav = useNavigate();
  const currentUserRole = getRole();
  const [staff, setStaff] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [isEditing, setIsEditing] = useState(false);
  const [editData, setEditData] = useState<any>({});
  const [saving, setSaving] = useState(false);
  const [gamification, setGamification] = useState<any>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handleEsc)
    return () => window.removeEventListener('keydown', handleEsc)
  }, [onClose])

  useEffect(() => {
    api.allStaff()
      .then(all => {
        const found = all.find((s: any) => s.id === staffId);
        setStaff(found);
        if (found) {
          setEditData({
            team: found.team || '',
            role: found.role || '',
            daily_target: found.daily_target || 0,
            is_active: found.is_active,
          });
        }
      })
      .catch(() => setError(t('common.error', lang)))
      .finally(() => setLoading(false));

    api.staffGamification(staffId)
      .then(setGamification)
      .catch(() => setError(t('common.error', lang)));
  }, [staffId]);

  if (!staff && !loading) {
    return (
      <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
        <div className="modal-content staff-modal-content">
          <div className="p-24 text-center text-muted">{t('staff.not_found', lang)}</div>
          <button className="btn-secondary" onClick={onClose}>{t('common.cancel', lang)}</button>
        </div>
      </div>
    );
  }

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.updateStaff(staffId, {
        team: editData.team || null,
        role: editData.role,
        daily_target: Number(editData.daily_target),
        is_active: editData.is_active,
      });
      onUpdate();
      setIsEditing(false);
      // Reload staff
      const all = await api.allStaff();
      setStaff(all.find((s: any) => s.id === staffId));
    } catch (e) {
      setError(t('common.update_failed', lang as any));
      setTimeout(() => setError(''), 3000);
    } finally {
      setSaving(false);
    }
  };

  const canEdit = currentUserRole === 'owner' || currentUserRole === 'admin';

  return (
    <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-content staff-modal-content">
        {loading ? (
          <div className="p-24 text-center text-muted">{t('common.loading', lang as any)}...</div>
        ) : (
          <>
            {error && (
              <div className="alert alert-error mb-16">
                {error}
              </div>
            )}
            <div className="d-flex justify-between items-start mb-20">
              <div className="d-flex items-center gap-12">
                <div className="avatar avatar-lg avatar-accent-solid">
                  {staff.display_name.charAt(0).toUpperCase()}
                </div>
                <div>
                  <h2 className="heading-sm fs-20">{staff.display_name}</h2>
                  <div className="fs-13 text-muted mt-4">
                    <span className="status-badge badge-accent text-uppercase">{staff.role}</span>
                    <span className="ml-8">{staff.team || t('org.unassigned', lang)}</span>
                  </div>
                </div>
              </div>
              <button className="modal-close-btn" onClick={onClose}>×</button>
            </div>

            {!isEditing ? (
              <div className="flex-col gap-12">
                <div className="grid-2col">
                  <div className="metric-card p-12">
                    <div className="metric-label">{t('org.daily_target', lang)}</div>
                    <div className="metric-value fs-16 text-primary">{staff.daily_target}</div>
                  </div>
                  <div className="metric-card p-12">
                    <div className="metric-label">{t('staff.phone', lang)}</div>
                    <div className="metric-value fs-16 text-primary">{staff.phone || '—'}</div>
                  </div>
                  <div className="metric-card p-12">
                    <div className="metric-label">{t('staff.language', lang)}</div>
                    <div className="metric-value fs-16 text-primary">{staff.language || '—'}</div>
                  </div>
                  <div className="metric-card p-12">
                    <div className="metric-label">{t('team.clients', lang)}</div>
                    <div className="metric-value fs-16 text-primary">{staff.client_count}</div>
                  </div>
                </div>

                {gamification && (
                  <div className="gamification-section mt-12">
                    <h3 className="heading-sm d-flex items-center gap-8 mb-12">
                      🎮 {t('staff.gamification', lang)}
                    </h3>
                    {gamification.total_xp === 0 ? (
                      <div className="fs-13 text-muted text-italic">{t('gamification.no_activity', lang)}</div>
                    ) : (
                      <div className="flex-col gap-12">
                        <div>
                          <div className="d-flex justify-between fs-13 mb-4 fw-600 text-muted">
                            <span>{t('gamification.xp', lang)}: <span className="text-accent">{gamification.total_xp.toLocaleString()}</span></span>
                            {gamification.streak?.current_streak > 0 && <span className="text-success">🔥 {gamification.streak.current_streak} {t('gamification.streak', lang)}</span>}
                          </div>
                          <div className="progress-bar">
                            <div className="progress-fill accent-bg-fill" style={{ width: `${Math.min(100, (gamification.total_xp % 1000) / 10)}%` }} />
                          </div>
                        </div>
                        {gamification.badges?.length > 0 && (
                          <div className="d-flex gap-8 flex-wrap">
                            {gamification.badges.map((b: any) => (
                              <span key={b.name} title={b.name} className="badge-emoji">{b.emoji}</span>
                            ))}
                          </div>
                        )}
                        {gamification.recent_xp?.length > 0 && (
                          <div className="mt-8 fs-12 text-muted">
                            <strong className="d-flex mb-4">{t('staff.recent_activity', lang)}</strong>
                            {gamification.recent_xp.slice(0, 3).map((xp: any) => (
                              <div key={`${xp.action}-${xp.xp_amount}`} className="d-flex justify-between mb-4 xp-activity-row">
                                <span>{xp.action}</span>
                                <span className="text-success fw-600">{t('gamification.plus_xp', lang).replace('{xp}', xp.xp_amount)}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}

                <div className="d-flex gap-12 mt-12">
                  {canEdit && (
                    <button className="btn-secondary flex-1" onClick={() => setIsEditing(true)}>
                      {t('org.edit_staff', lang)}
                    </button>
                  )}
                  <button className="btn-primary flex-1" onClick={() => { onClose(); nav(`/clients?search=${encodeURIComponent(staff.display_name)}`); }}>
                    {t('org.view_clients', lang)}
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex-col gap-12">
                <div>
                  <label className="field-label">{t('team.team', lang)}</label>
                  <input
                    className="input"
                    value={editData.team}
                    onChange={e => setEditData({ ...editData, team: e.target.value })}
                  />
                </div>
                <div>
                  <label className="field-label">{t('team.role', lang)}</label>
                  <select
                    className="input"
                    value={editData.role}
                    onChange={e => setEditData({ ...editData, role: e.target.value })}
                  >
                    <option value="viewer">{t('role.viewer', lang as any)}</option>
                    <option value="newbie">{t('role.newbie', lang as any)}</option>
                    <option value="frontdesk">{t('role.frontdesk', lang as any)}</option>
                    <option value="customer_service">{t('role.customer_service', lang as any)}</option>
                    {currentUserRole === 'owner' && (
                      <>
                        <option value="maintenance">{t('role.maintenance', lang as any)}</option>
                        <option value="leader">{t('role.leader', lang as any)}</option>
                        <option value="manager">{t('role.manager', lang as any)}</option>
                        <option value="admin">{t('role.admin', lang as any)}</option>
                      </>
                    )}
                  </select>
                </div>
                <div>
                  <label className="field-label">{t('org.daily_target', lang)}</label>
                  <input
                    className="input"
                    type="number"
                    value={editData.daily_target}
                    onChange={e => setEditData({ ...editData, daily_target: e.target.value })}
                  />
                </div>
                <div className="d-flex items-center gap-8">
                  <input
                    type="checkbox"
                    checked={editData.is_active}
                    onChange={e => setEditData({ ...editData, is_active: e.target.checked })}
                  />
                  <label className="fs-13 text-primary">{t('staff.active', lang)}</label>
                </div>
                <div className="d-flex gap-12 mt-12">
                  <button className="btn-secondary flex-1" onClick={() => setIsEditing(false)}>
                    {t('common.cancel', lang)}
                  </button>
                  <button className={`btn-primary flex-1${saving ? ' opacity-70' : ''}`} onClick={handleSave} disabled={saving}>
                    {saving ? t('common.saving', lang as any) : t('org.save_changes', lang as any)}
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
