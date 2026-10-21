import React, { useState, useEffect } from 'react';
import StatusBadge from './StatusBadge';
import { getPublicEventDetail } from '../services/api';
import Loading from './Loading';

/**
 * Event Details Modal for Student Portal
 * Displays verified event information, venue specifications, schedule,
 * and real crowd monitoring data.
 * Adheres strictly to the requirement:
 * "If crowd-analysis data is not currently exposed by the backend:
 *  Display a clean empty state: 'Crowd information will appear when monitoring data is available.'
 *  DO NOT INVENT A CROWD COUNT."
 */
export default function EventDetailsModal({ eventId, initialEvent, onClose }) {
  const [eventData, setEventData] = useState(initialEvent || null);
  const [loading, setLoading] = useState(!initialEvent);
  const [fetchError, setFetchError] = useState('');

  useEffect(() => {
    let isMounted = true;
    const loadDetail = async () => {
      if (!eventId) return;
      setLoading(true);
      setFetchError('');
      try {
        const res = await getPublicEventDetail(eventId);
        if (isMounted) {
          if (res.ok && res.data?.event) {
            setEventData(res.data.event);
          } else {
            setFetchError(res.error || 'Unable to load complete event details.');
          }
        }
      } catch {
        if (isMounted) {
          setFetchError('Connection error while retrieving event details.');
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    loadDetail();
    return () => {
      isMounted = false;
    };
  }, [eventId]);

  // Trap Escape key to close modal
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  if (!eventId) return null;

  const ev = eventData || initialEvent;

  // Format date safely
  const formatDate = (dateStr) => {
    if (!dateStr) return 'To be announced';
    try {
      const d = new Date(dateStr);
      if (isNaN(d.getTime())) return dateStr;
      return d.toLocaleDateString('en-US', {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric',
      });
    } catch {
      return dateStr;
    }
  };

  const formatTime = (timeStr) => {
    if (!timeStr) return '';
    const parts = timeStr.split(':');
    if (parts.length >= 2) {
      const h = parseInt(parts[0], 10);
      const m = parts[1];
      const ampm = h >= 12 ? 'PM' : 'AM';
      const formattedH = h % 12 || 12;
      return `${formattedH}:${m} ${ampm}`;
    }
    return timeStr;
  };

  const crowdInfo = ev?.crowd_info;
  const isCrowdAvailable = Boolean(crowdInfo?.available && crowdInfo?.estimated_crowd !== null && crowdInfo?.estimated_crowd !== undefined);

  return (
    <div className="student-modal-overlay" onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="modal-event-title">
      <div className="student-modal" onClick={(e) => e.stopPropagation()}>
        {/* Modal Header */}
        <div className="student-modal-header">
          <div>
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '0.35rem', flexWrap: 'wrap' }}>
              {ev?.series_name && (
                <span className="student-fest-tag">
                  {ev.series_name}
                </span>
              )}
              <span className="student-fest-tag" style={{ color: 'var(--primary)', borderColor: 'var(--primary-border)' }}>
                {ev?.category || 'General'}
              </span>
              <StatusBadge status={ev?.status || 'Upcoming'} />
            </div>
            <h2 id="modal-event-title" className="student-modal-title">
              {ev?.event_name || 'Event Details'}
            </h2>
          </div>
          <button
            type="button"
            className="student-modal-close"
            onClick={onClose}
            aria-label="Close event details"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Modal Body */}
        <div className="student-modal-body">
          {loading && !eventData ? (
            <div style={{ padding: '2rem 0' }}>
              <Loading message="Fetching verified event record..." />
            </div>
          ) : (
            <>
              {fetchError && (
                <div className="form-error-banner" role="alert">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ flexShrink: 0 }}>
                    <circle cx="12" cy="12" r="10" />
                    <line x1="12" y1="8" x2="12" y2="12" />
                    <line x1="12" y1="16" x2="12.01" y2="16" />
                  </svg>
                  <span>{fetchError}</span>
                </div>
              )}

              {/* Event Description */}
              <div>
                <h3 className="student-modal-section-title">Event Overview</h3>
                <p className="student-modal-desc">
                  {ev?.description || 'No description has been submitted for this event.'}
                </p>
                {ev?.series_description && (
                  <p className="student-modal-desc" style={{ marginTop: '0.5rem', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                    <strong>About {ev.series_name}:</strong> {ev.series_description}
                  </p>
                )}
              </div>

              {/* Schedule & Venue Specifications Grid */}
              <div>
                <h3 className="student-modal-section-title">Schedule &amp; Location Details</h3>
                <div className="student-modal-specs-grid">
                  <div className="student-modal-spec-card">
                    <span className="student-modal-spec-label">Event Date</span>
                    <span className="student-modal-spec-value">
                      {formatDate(ev?.start_date || ev?.approved_date || ev?.requested_date)}
                    </span>
                  </div>

                  <div className="student-modal-spec-card">
                    <span className="student-modal-spec-label">Schedule Hours</span>
                    <span className="student-modal-spec-value">
                      {ev?.start_time && ev?.end_time
                        ? `${formatTime(ev.start_time)} to ${formatTime(ev.end_time)}`
                        : 'To be announced'}
                    </span>
                  </div>

                  <div className="student-modal-spec-card">
                    <span className="student-modal-spec-label">Assigned Venue</span>
                    <span className="student-modal-spec-value">
                      {ev?.venue_name || 'To be announced'}
                    </span>
                  </div>

                  <div className="student-modal-spec-card">
                    <span className="student-modal-spec-label">Venue Location</span>
                    <span className="student-modal-spec-value">
                      {ev?.venue_location || 'Campus Grounds'}
                    </span>
                  </div>

                  <div className="student-modal-spec-card">
                    <span className="student-modal-spec-label">Venue Capacity</span>
                    <span className="student-modal-spec-value">
                      {ev?.venue_capacity ? `${ev.venue_capacity} seats` : 'To be confirmed'}
                    </span>
                  </div>

                  <div className="student-modal-spec-card">
                    <span className="student-modal-spec-label">Operational Status</span>
                    <span className="student-modal-spec-value" style={{ textTransform: 'capitalize' }}>
                      {ev?.status || 'Upcoming'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Real Crowd Status Monitoring Section */}
              <div>
                <h3 className="student-modal-section-title">Crowd Analysis &amp; Safety Status</h3>
                {isCrowdAvailable ? (
                  <div className="student-crowd-box student-crowd-box-active">
                    <div className="student-crowd-box-title">
                      <span className="status-badge-dot" style={{ backgroundColor: crowdInfo?.crowd_status === 'High Crowd' ? '#b91c1c' : '#15803d' }} />
                      <span>Live Crowd Monitoring Active</span>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '0.75rem', marginTop: '0.75rem' }}>
                      <div>
                        <span className="student-modal-spec-label">Estimated Attendees</span>
                        <p style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                          {crowdInfo.estimated_crowd}
                        </p>
                      </div>
                      <div>
                        <span className="student-modal-spec-label">Crowd Density Level</span>
                        <p style={{ fontSize: '1rem', fontWeight: 600, color: crowdInfo.crowd_status === 'High Crowd' ? 'var(--danger)' : 'var(--success)' }}>
                          {crowdInfo.crowd_status || 'Normal Crowd'}
                        </p>
                      </div>
                      {crowdInfo.last_analyzed && (
                        <div>
                          <span className="student-modal-spec-label">Last Analysis Time</span>
                          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                            {new Date(crowdInfo.last_analyzed).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          </p>
                        </div>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="student-crowd-box student-crowd-box-empty">
                    <div className="student-crowd-box-title">
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: 'var(--text-muted)' }}>
                        <circle cx="12" cy="12" r="10" />
                        <line x1="12" y1="16" x2="12" y2="12" />
                        <line x1="12" y1="8" x2="12.01" y2="8" />
                      </svg>
                      <span>Crowd Monitoring Status</span>
                    </div>
                    <p className="student-crowd-empty-msg">
                      Crowd information will appear when monitoring data is available.
                    </p>
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        {/* Modal Footer */}
        <div className="student-modal-footer">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onClose}
          >
            Close Details
          </button>
        </div>
      </div>
    </div>
  );
}
