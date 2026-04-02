import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, getRole } from '../api';
import { useTheme } from '../ThemeContext';
import { t, getLang } from '../i18n';

interface StaffDetailModalProps {
  staffId: number;
  onClose: () => void;
  onUpdate: () => void;
}

export function StaffDetailModal({ staffId, onClose, onUpdate }: StaffDetailModalProps) {
  const { theme } = useTheme();
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
      .catch(console.error)
      .finally(() => setLoading(false));

    api.staffGamification(staffId)
      .then(setGamification)
      .catch(console.error);
  }, [staffId]);

  if (!staff && !loading) {
    return null;
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
      console.error(e);
      setError(t('common.update_failed', lang as any));
      setTimeout(() => setError(''), 3000);
    } finally {
      setSaving(false);
    }
  };

  const canEdit = currentUserRole === 'owner' || currentUserRole === 'admin';

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
    }} onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={{
        background: theme.cardBg, borderRadius: theme.radiusCard, padding: theme.paddingCard, width: 500, maxWidth: '90vw',
        maxHeight: '90vh', overflowY: 'auto',
        boxShadow: theme.shadow, border: `1px solid ${theme.cardBorder}`
      }}>
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: theme.textSecondary }}>{t('common.loading', lang as any)}...</div>
        ) : (
          <>
            {error && (
              <div className="alert alert-error" style={{ marginBottom: 16 }}>
                {error}
              </div>
            )}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{
                  width: 48, height: 48, borderRadius: '50%', background: theme.accent, color: '#fff',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 24, fontWeight: 700
                }}>
                  {staff.display_name.charAt(0).toUpperCase()}
                </div>
                <div>
                  <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: theme.textPrimary }}>{staff.display_name}</h2>
                  <div style={{ fontSize: 13, color: theme.textSecondary, marginTop: 4 }}>
                    <span style={{
                      background: theme.activeNav, padding: '2px 8px', borderRadius: theme.radiusCard,
                      color: theme.accent, fontWeight: 600, fontSize: 11, textTransform: 'uppercase'
                    }}>{staff.role}</span>
                    <span style={{ marginLeft: 8 }}>{staff.team || t('org.unassigned', lang)}</span>
                  </div>
                </div>
              </div>
              <button onClick={onClose} style={{ background: 'transparent', border: 'none', color: theme.textSecondary, fontSize: 20, cursor: 'pointer' }}>×</button>
            </div>

            {!isEditing ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  <div className="metric-card" style={{ padding: 12 }}>
                    <div className="metric-label">{t('org.daily_target', lang)}</div>
                    <div className="metric-value" style={{ fontSize: 16, color: theme.textPrimary }}>{staff.daily_target}</div>
                  </div>
                  <div className="metric-card" style={{ padding: 12 }}>
                    <div className="metric-label">{t('staff.phone', lang)}</div>
                    <div className="metric-value" style={{ fontSize: 16, color: theme.textPrimary }}>{staff.phone || '—'}</div>
                  </div>
                  <div className="metric-card" style={{ padding: 12 }}>
                    <div className="metric-label">{t('staff.language', lang)}</div>
                    <div className="metric-value" style={{ fontSize: 16, color: theme.textPrimary }}>{staff.language || '—'}</div>
                  </div>
                  <div className="metric-card" style={{ padding: 12 }}>
                    <div className="metric-label">{t('team.clients', lang)}</div>
                    <div className="metric-value" style={{ fontSize: 16, color: theme.textPrimary }}>{staff.client_count}</div>
                  </div>
                </div>

                {gamification && (
                  <div style={{ marginTop: 12, padding: theme.paddingCard, borderRadius: theme.radiusCard, background: theme.cardBg, border: `1px solid ${theme.cardBorder}` }}>
                    <h3 style={{ fontSize: 16, fontWeight: 700, margin: '0 0 12px', display: 'flex', alignItems: 'center', gap: 8 }}>
                      🎮 {t('staff.gamification', lang)}
                    </h3>
                    {gamification.total_xp === 0 ? (
                      <div style={{ fontSize: 13, color: theme.textSecondary, fontStyle: 'italic' }}>{t('gamification.no_activity', lang)}</div>
                    ) : (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                        <div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 4, fontWeight: 600, color: theme.textSecondary }}>
                            <span>{t('gamification.xp', lang)}: <span style={{ color: theme.accent }}>{gamification.total_xp.toLocaleString()}</span></span>
                            {gamification.streak?.current_streak > 0 && <span style={{ color: theme.chartLine }}>🔥 {gamification.streak.current_streak} {t('gamification.streak', lang)}</span>}
                          </div>
                          <div style={{ height: 8, background: theme.bg, borderRadius: theme.radiusCard, overflow: 'hidden' }}>
                            <div style={{ height: '100%', width: `${Math.min(100, (gamification.total_xp % 1000) / 10)}%`, background: theme.accent, transition: 'width 1s ease-out' }} />
                          </div>
                        </div>
                        {gamification.badges?.length > 0 && (
                          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                            {gamification.badges.map((b: any, i: number) => (
                              <span key={i} title={b.name} style={{ fontSize: 24, filter: 'drop-shadow(0 2px 4px rgba(0,0,0,0.1))' }}>{b.emoji}</span>
                            ))}
                          </div>
                        )}
                        {gamification.recent_xp?.length > 0 && (
                          <div style={{ marginTop: 8, fontSize: 12, color: theme.textSecondary }}>
                            <strong style={{ display: 'block', marginBottom: 4 }}>{t('staff.recent_activity', lang)}</strong>
                            {gamification.recent_xp.slice(0, 3).map((xp: any, i: number) => (
                              <div key={i} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4, padding: '4px 8px', background: theme.bg, borderRadius: theme.radiusCard }}>
                                <span>{xp.action}</span>
                                <span style={{ color: theme.success, fontWeight: 600 }}>{t('gamification.plus_xp', lang).replace('{xp}', xp.xp_amount)}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}

                <div style={{ display: 'flex', gap: 12, marginTop: 10 }}>
                  {canEdit && (
                    <button className="glass-btn" onClick={() => setIsEditing(true)} style={{
                      flex: 1, padding: '10px', background: theme.cardBg, border: `1px solid ${theme.cardBorder}`,
                      borderRadius: theme.radiusBtn, color: theme.textPrimary, fontWeight: 600, cursor: 'pointer'
                    }}>
                      {t('org.edit_staff', lang)}
                    </button>
                  )}
                  <button className="glass-btn" onClick={() => { onClose(); nav(`/clients?search=${encodeURIComponent(staff.display_name)}`); }} style={{
                    flex: 1, padding: '10px', background: theme.accent, border: 'none',
                    borderRadius: theme.radiusBtn, color: '#fff', fontWeight: 600, cursor: 'pointer'
                  }}>
                    {t('org.view_clients', lang)}
                  </button>
                </div>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
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
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input
                    type="checkbox"
                    checked={editData.is_active}
                    onChange={e => setEditData({ ...editData, is_active: e.target.checked })}
                  />
                  <label style={{ fontSize: 13, color: theme.textPrimary }}>{t('staff.active', lang)}</label>
                </div>
                <div style={{ display: 'flex', gap: 12, marginTop: 10 }}>
                  <button className="glass-btn" onClick={() => setIsEditing(false)} style={{
                    flex: 1, padding: '10px', background: theme.cardBg, border: `1px solid ${theme.cardBorder}`,
                    borderRadius: theme.radiusBtn, color: theme.textPrimary, fontWeight: 600, cursor: 'pointer'
                  }}>
                    {t('common.cancel', lang)}
                  </button>
                  <button className="glass-btn" onClick={handleSave} disabled={saving} style={{
                    flex: 1, padding: '10px', background: theme.accent, border: 'none',
                    borderRadius: theme.radiusBtn, color: '#fff', fontWeight: 600, cursor: 'pointer', opacity: saving ? 0.7 : 1
                  }}>
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
