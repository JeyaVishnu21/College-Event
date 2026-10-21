import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { getAlerts, markAlertRead, markAllAlertsRead } from '../services/api';

/**
 * Real-Time Crowd Safety Alerts View
 * -------------------------------------------------------------
 * Displays automated capacity exceedance and threshold warning notifications.
 * Shared between OrganizerDashboard (Tab 7) and AdministratorDashboard (Tab 7).
 */
export default function CrowdAlertsView({ role = 'organizer', onUnreadCountChange }) {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('all'); // 'all' | 'unread'
  const [scope, setScope] = useState('user'); // 'user' | 'all' (admins only)
  const [actionLoadingId, setActionLoadingId] = useState(null);
  const [markingAll, setMarkingAll] = useState(false);
  const [previewPhoto, setPreviewPhoto] = useState(null);

  const fetchAlertsData = useCallback(async (isSilent = false) => {
    if (!isSilent) setLoading(true);
    setError('');
    try {
      const res = await getAlerts({
        unread_only: filter === 'unread',
        scope: role === 'administrator' ? scope : 'user',
      });

      if (res.ok && res.data) {
        const fetchedAlerts = res.data.alerts || [];
        setAlerts(fetchedAlerts);
        const unread = typeof res.data.unread_count === 'number'
          ? res.data.unread_count
          : fetchedAlerts.filter((a) => a.status === 'unread').length;
        if (onUnreadCountChange) {
          onUnreadCountChange(unread);
        }
      } else {
        setError(res.error || 'Failed to load safety alerts.');
      }
    } catch {
      setError('Network communication failure while retrieving alerts.');
    } finally {
      if (!isSilent) setLoading(false);
    }
  }, [filter, scope, role, onUnreadCountChange]);

  useEffect(() => {
    fetchAlertsData();
  }, [fetchAlertsData]);

  const handleMarkAsRead = async (alertId) => {
    setActionLoadingId(alertId);
    try {
      const res = await markAlertRead(alertId);
      if (res.ok) {
        setAlerts((prev) =>
          prev.map((a) => (a.id === alertId ? { ...a, status: 'read' } : a))
        );
        if (onUnreadCountChange) {
          // decrement locally
          const remainingUnread = alerts.filter((a) => a.id !== alertId && a.status === 'unread').length;
          onUnreadCountChange(remainingUnread);
        }
      }
    } catch {
      // Ignored
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleMarkAllRead = async () => {
    setMarkingAll(true);
    try {
      const res = await markAllAlertsRead();
      if (res.ok) {
        setAlerts((prev) => prev.map((a) => ({ ...a, status: 'read' })));
        if (onUnreadCountChange) {
          onUnreadCountChange(0);
        }
      }
    } catch {
      // Ignored
    } finally {
      setMarkingAll(false);
    }
  };

  // Metrics
  const metrics = useMemo(() => {
    const total = alerts.length;
    const unread = alerts.filter((a) => a.status === 'unread').length;
    const critical = alerts.filter((a) => {
      const cap = Number(a.venue_capacity || 0);
      const detected = Number(a.detected_count || a.predicted_count || 0);
      return cap > 0 && detected >= cap;
    }).length;
    const warning = alerts.filter((a) => {
      const cap = Number(a.venue_capacity || 0);
      const thresh = Number(a.threshold || 0);
      const detected = Number(a.detected_count || a.predicted_count || 0);
      return detected >= thresh && (cap === 0 || detected < cap);
    }).length;
    return { total, unread, critical, warning };
  }, [alerts]);

  const formatTimestamp = (ts) => {
    if (!ts) return 'Just now';
    try {
      const d = new Date(ts);
      if (isNaN(d.getTime())) return ts;
      return d.toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return ts;
    }
  };

  return (
    <div className="tab-pane">
      <section className="portal-section-card">
        {/* Header Bar */}
        <div className="section-card-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
          <div className="header-title-stack">
            <h2 className="section-card-title">Real-Time Crowd Safety Alerts</h2>
            <span className="section-card-subtitle">
              Automated threshold exceedance and capacity breach notifications generated during live event surveillance
            </span>
          </div>

          <div className="header-actions" style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', flexWrap: 'wrap' }}>
            {role === 'administrator' && (
              <div className="btn-group" style={{ display: 'inline-flex', background: 'var(--bg-subtle)', borderRadius: 'var(--radius)', padding: '2px', border: '1px solid var(--border-color)' }}>
                <button
                  type="button"
                  className={`btn btn-sm ${scope === 'user' ? 'btn-primary' : 'btn-text'}`}
                  style={{ padding: '0.35rem 0.75rem', fontSize: '0.8rem', borderRadius: 'var(--radius-sm)' }}
                  onClick={() => setScope('user')}
                >
                  My Direct Alerts
                </button>
                <button
                  type="button"
                  className={`btn btn-sm ${scope === 'all' ? 'btn-primary' : 'btn-text'}`}
                  style={{ padding: '0.35rem 0.75rem', fontSize: '0.8rem', borderRadius: 'var(--radius-sm)' }}
                  onClick={() => setScope('all')}
                >
                  All Campus Incidents
                </button>
              </div>
            )}

            <div className="btn-group" style={{ display: 'inline-flex', background: 'var(--bg-subtle)', borderRadius: 'var(--radius)', padding: '2px', border: '1px solid var(--border-color)' }}>
              <button
                type="button"
                className={`btn btn-sm ${filter === 'all' ? 'btn-primary' : 'btn-text'}`}
                style={{ padding: '0.35rem 0.75rem', fontSize: '0.8rem', borderRadius: 'var(--radius-sm)' }}
                onClick={() => setFilter('all')}
              >
                All ({metrics.total})
              </button>
              <button
                type="button"
                className={`btn btn-sm ${filter === 'unread' ? 'btn-primary' : 'btn-text'}`}
                style={{ padding: '0.35rem 0.75rem', fontSize: '0.8rem', borderRadius: 'var(--radius-sm)' }}
                onClick={() => setFilter('unread')}
              >
                Unread ({metrics.unread})
              </button>
            </div>

            {metrics.unread > 0 && (
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={handleMarkAllRead}
                disabled={markingAll}
                style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.8rem' }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
                {markingAll ? 'Marking...' : 'Mark All Read'}
              </button>
            )}

            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => fetchAlertsData(false)}
              disabled={loading}
              title="Refresh Safety Alerts"
              style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.8rem' }}
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }}
              >
                <path d="M23 4v6h-6" />
                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
              </svg>
              Refresh
            </button>
          </div>
        </div>

        {/* Operational Telemetry KPI Counters */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: '1rem',
            padding: '1.25rem 1.5rem',
            borderBottom: '1px solid var(--border-color)',
            background: 'var(--bg-subtle)',
          }}
        >
          <div className="stat-card" style={{ padding: '1rem', background: 'var(--bg-surface)', borderRadius: 'var(--radius)', border: '1px solid var(--border-color)' }}>
            <span style={{ fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)', fontWeight: 600 }}>
              Total Alerts
            </span>
            <div style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--text-primary)', marginTop: '0.25rem' }}>
              {metrics.total}
            </div>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Historical exceedances</span>
          </div>

          <div
            className="stat-card"
            style={{
              padding: '1rem',
              background: metrics.unread > 0 ? 'var(--danger-bg)' : 'var(--bg-surface)',
              borderRadius: 'var(--radius)',
              border: `1px solid ${metrics.unread > 0 ? 'var(--danger-border)' : 'var(--border-color)'}`,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: metrics.unread > 0 ? 'var(--danger)' : 'var(--text-muted)', fontWeight: 600 }}>
                Unread Alerts
              </span>
              {metrics.unread > 0 && (
                <span
                  style={{
                    display: 'inline-block',
                    width: '8px',
                    height: '8px',
                    borderRadius: '50%',
                    backgroundColor: 'var(--danger)',
                    animation: 'pulse 1.5s infinite',
                  }}
                />
              )}
            </div>
            <div style={{ fontSize: '1.75rem', fontWeight: 700, color: metrics.unread > 0 ? 'var(--danger)' : 'var(--text-primary)', marginTop: '0.25rem' }}>
              {metrics.unread}
            </div>
            <span style={{ fontSize: '0.75rem', color: metrics.unread > 0 ? 'var(--danger)' : 'var(--text-muted)' }}>
              Require acknowledgement
            </span>
          </div>

          <div className="stat-card" style={{ padding: '1rem', background: 'var(--bg-surface)', borderRadius: 'var(--radius)', border: '1px solid var(--border-color)' }}>
            <span style={{ fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--danger)', fontWeight: 600 }}>
              Critical Breaches
            </span>
            <div style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--danger)', marginTop: '0.25rem' }}>
              {metrics.critical}
            </div>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Exceeded 100% capacity</span>
          </div>

          <div className="stat-card" style={{ padding: '1rem', background: 'var(--bg-surface)', borderRadius: 'var(--radius)', border: '1px solid var(--border-color)' }}>
            <span style={{ fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--warning)', fontWeight: 600 }}>
              Threshold Warnings
            </span>
            <div style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--warning)', marginTop: '0.25rem' }}>
              {metrics.warning}
            </div>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Reached capacity - 50</span>
          </div>
        </div>

        {/* Error Notification */}
        {error && (
          <div style={{ margin: '1rem 1.5rem', padding: '0.75rem 1rem', background: 'var(--danger-bg)', border: '1px solid var(--danger-border)', borderRadius: 'var(--radius)', color: 'var(--danger)', fontSize: '0.875rem' }}>
            {error}
          </div>
        )}

        {/* Alerts Content Area */}
        {loading ? (
          <div style={{ padding: '3.5rem 1.5rem', textAlign: 'center', color: 'var(--text-muted)' }}>
            <div
              style={{
                width: '36px',
                height: '36px',
                border: '3px solid var(--border-color)',
                borderTopColor: 'var(--primary)',
                borderRadius: '50%',
                margin: '0 auto 1rem auto',
                animation: 'spin 0.8s linear infinite',
              }}
            />
            <p style={{ fontSize: '0.9rem', fontWeight: 500 }}>Scanning safety telemetry and threshold logs...</p>
          </div>
        ) : alerts.length === 0 ? (
          <div className="alerts-status-panel">
            <div className="alerts-nominal-box">
              <div className="nominal-icon-ring" aria-hidden="true">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                  <polyline points="22 4 12 14.01 9 11.01" />
                </svg>
              </div>
              <h3 className="nominal-title">
                {filter === 'unread' ? 'No Unread Safety Alerts' : 'All Monitored Venues Nominal'}
              </h3>
              <p className="nominal-desc">
                {filter === 'unread'
                  ? 'All recent capacity exceedances have been reviewed and acknowledged.'
                  : 'Safety thresholds are actively enforced when photographs are uploaded. No venue capacity breaches or crowd bottleneck alerts have been recorded for your events.'}
              </p>
            </div>
          </div>
        ) : (
          <div style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {alerts.map((alert) => {
              const detected = Number(alert.detected_count || alert.predicted_count || 0);
              const capacity = Number(alert.venue_capacity || 0);
              const threshold = Number(alert.threshold || Math.max(0, capacity - 50));
              const isCritical = capacity > 0 && detected >= capacity;
              const isUnread = alert.status === 'unread';
              const occupancyPct = capacity > 0 ? Math.round((detected / capacity) * 100) : null;

              return (
                <div
                  key={alert.id}
                  style={{
                    background: isUnread ? (isCritical ? '#fffaf9' : '#fffdfa') : 'var(--bg-surface)',
                    border: `1px solid ${isUnread ? (isCritical ? 'var(--danger-border)' : 'var(--warning-border)') : 'var(--border-color)'}`,
                    borderLeft: `5px solid ${isCritical ? 'var(--danger)' : 'var(--warning)'}`,
                    borderRadius: 'var(--radius)',
                    padding: '1.25rem',
                    boxShadow: isUnread ? 'var(--shadow-md)' : 'var(--shadow-sm)',
                    transition: 'all var(--transition-fast)',
                  }}
                >
                  {/* Top Bar: Badges + Timestamp + Actions */}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.75rem', marginBottom: '0.75rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                      <span
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '0.35rem',
                          padding: '0.25rem 0.65rem',
                          borderRadius: '9999px',
                          fontSize: '0.75rem',
                          fontWeight: 700,
                          letterSpacing: '0.04em',
                          textTransform: 'uppercase',
                          background: isCritical ? 'var(--danger-bg)' : 'var(--warning-bg)',
                          color: isCritical ? 'var(--danger)' : 'var(--warning)',
                          border: `1px solid ${isCritical ? 'var(--danger-border)' : 'var(--warning-border)'}`,
                        }}
                      >
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                          {isCritical ? (
                            <>
                              <polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86 7.86 2" />
                              <line x1="12" y1="8" x2="12" y2="12" />
                              <line x1="12" y1="16" x2="12.01" y2="16" />
                            </>
                          ) : (
                            <>
                              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                              <line x1="12" y1="9" x2="12" y2="13" />
                              <line x1="12" y1="17" x2="12.01" y2="17" />
                            </>
                          )}
                        </svg>
                        {isCritical ? 'Critical Breach' : 'Capacity Warning'}
                      </span>

                      <span
                        style={{
                          padding: '0.2rem 0.55rem',
                          borderRadius: '9999px',
                          fontSize: '0.7rem',
                          fontWeight: 600,
                          textTransform: 'uppercase',
                          background: isUnread ? 'var(--primary-light)' : 'var(--bg-subtle)',
                          color: isUnread ? 'var(--primary)' : 'var(--text-muted)',
                          border: `1px solid ${isUnread ? 'var(--primary-border)' : 'var(--border-color)'}`,
                        }}
                      >
                        {isUnread ? '● Unread' : 'Acknowledged'}
                      </span>

                      {alert.event_name && (
                        <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                          {alert.event_name}
                        </span>
                      )}
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                        {formatTimestamp(alert.created_at)}
                      </span>

                      {isUnread && (
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          style={{ padding: '0.25rem 0.65rem', fontSize: '0.75rem' }}
                          onClick={() => handleMarkAsRead(alert.id)}
                          disabled={actionLoadingId === alert.id}
                        >
                          {actionLoadingId === alert.id ? 'Marking...' : 'Acknowledge'}
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Body & Venue Info */}
                  <div style={{ marginBottom: '0.85rem' }}>
                    <div style={{ fontSize: '0.95rem', fontWeight: 600, color: isCritical ? 'var(--danger)' : 'var(--text-primary)', marginBottom: '0.35rem' }}>
                      {alert.message}
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                      {alert.venue_name && (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem' }}>
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                            <circle cx="12" cy="10" r="3" />
                          </svg>
                          <strong>{alert.venue_name}</strong> {alert.venue_location ? `(${alert.venue_location})` : ''}
                        </span>
                      )}

                      {alert.recipient_name && role === 'administrator' && (
                        <span>
                          Targeted Recipient: <strong>{alert.recipient_name}</strong> ({alert.recipient_role})
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Density Telemetry Breakdown Bar */}
                  <div
                    style={{
                      background: 'var(--bg-subtle)',
                      borderRadius: 'var(--radius)',
                      padding: '0.75rem 1rem',
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))',
                      gap: '0.75rem',
                      alignItems: 'center',
                    }}
                  >
                    <div>
                      <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                        Detected Count
                      </span>
                      <div style={{ fontSize: '1.25rem', fontWeight: 700, color: isCritical ? 'var(--danger)' : 'var(--text-primary)' }}>
                        {detected.toLocaleString()}
                        <span style={{ fontSize: '0.75rem', fontWeight: 500, color: 'var(--text-muted)', marginLeft: '0.25rem' }}>people</span>
                      </div>
                    </div>

                    <div>
                      <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                        Threshold Trigger
                      </span>
                      <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--warning)' }}>
                        {threshold.toLocaleString()}
                        <span style={{ fontSize: '0.75rem', fontWeight: 500, color: 'var(--text-muted)', marginLeft: '0.25rem' }}>(Cap - 50)</span>
                      </div>
                    </div>

                    <div>
                      <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                        Venue Capacity
                      </span>
                      <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                        {capacity > 0 ? capacity.toLocaleString() : 'N/A'}
                        <span style={{ fontSize: '0.75rem', fontWeight: 500, color: 'var(--text-muted)', marginLeft: '0.25rem' }}>seats</span>
                      </div>
                    </div>

                    {occupancyPct !== null && (
                      <div>
                        <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                          Occupancy Rate
                        </span>
                        <div style={{ fontSize: '1.25rem', fontWeight: 700, color: isCritical ? 'var(--danger)' : 'var(--warning)' }}>
                          {occupancyPct}%
                        </div>
                      </div>
                    )}

                    {alert.image_path && (
                      <div style={{ textAlign: 'right' }}>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          style={{ fontSize: '0.75rem', display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}
                          onClick={() => setPreviewPhoto(alert.image_path)}
                        >
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                            <circle cx="8.5" cy="8.5" r="1.5" />
                            <polyline points="21 15 16 10 5 21" />
                          </svg>
                          View Photo
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Surveillance Photograph Modal */}
      {previewPhoto && (
        <div
          role="dialog"
          aria-modal="true"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15, 23, 42, 0.75)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
            padding: '1.5rem',
          }}
          onClick={() => setPreviewPhoto(null)}
        >
          <div
            style={{
              background: 'var(--bg-surface)',
              borderRadius: 'var(--radius-md)',
              maxWidth: '700px',
              width: '100%',
              overflow: 'hidden',
              boxShadow: 'var(--shadow-lg)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '1rem 1.25rem',
                borderBottom: '1px solid var(--border-color)',
              }}
            >
              <h3 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>
                Surveillance Crowd Photograph
              </h3>
              <button
                type="button"
                className="btn btn-text btn-sm"
                onClick={() => setPreviewPhoto(null)}
                style={{ fontSize: '1.25rem', padding: '0.2rem 0.5rem', cursor: 'pointer' }}
              >
                ✕
              </button>
            </div>
            <div style={{ padding: '1rem', background: '#000', display: 'flex', justifyContent: 'center' }}>
              <img
                src={previewPhoto.startsWith('/') ? previewPhoto : `/${previewPhoto}`}
                alt="Surveillance analysis capture"
                style={{ maxWidth: '100%', maxHeight: '65vh', objectFit: 'contain' }}
              />
            </div>
            <div style={{ padding: '0.75rem 1.25rem', textAlign: 'right', background: 'var(--bg-subtle)' }}>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => setPreviewPhoto(null)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
