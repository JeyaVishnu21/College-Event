import React, { useState, useEffect } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { getPublicEventDetail } from '../services/api';
import Loading from '../components/Loading';
import StatusBadge from '../components/StatusBadge';

/**
 * EventDetails Page Component
 * Displays complete details for a single campus event:
 * - Event title, category, status, date, time, venue location & capacity.
 * - Full event description.
 * - Link back to the parent festival series.
 * - Crowd Monitoring status explicitly displayed as "Not Available" (pending model implementation).
 */
export default function EventDetails() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [event, setEvent] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);

  const handleShare = () => {
    try {
      if (navigator.clipboard) {
        navigator.clipboard.writeText(window.location.href);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }
    } catch {
      // Fallback
    }
  };

  useEffect(() => {
    let isMounted = true;
    const fetchEvent = async () => {
      setLoading(true);
      setError('');
      try {
        const res = await getPublicEventDetail(id);
        if (isMounted) {
          if (res.ok && res.data?.event) {
            setEvent(res.data.event);
          } else {
            setError(res.error || 'Event details not found.');
          }
        }
      } catch {
        if (isMounted) {
          setError('Network error connecting to backend service.');
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    if (id) {
      fetchEvent();
    }
    return () => {
      isMounted = false;
    };
  }, [id]);

  // Format single date
  const formatDate = (dateStr) => {
    if (!dateStr) return 'TBA';
    try {
      const d = new Date(dateStr);
      if (isNaN(d.getTime())) return dateStr;
      return d.toLocaleDateString('en-US', {
        weekday: 'long',
        month: 'long',
        day: 'numeric',
        year: 'numeric',
      });
    } catch {
      return dateStr;
    }
  };

  // Format time (HH:MM:SS -> 12hr)
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

  if (loading) {
    return (
      <div className="event-detail-page">
        <div className="content-container" style={{ padding: '4rem 1rem' }}>
          <Loading message="Loading event details and schedule..." />
        </div>
      </div>
    );
  }

  if (error || !event) {
    return (
      <div className="event-detail-page">
        <div className="content-container" style={{ padding: '4rem 1rem' }}>
          <div className="portal-empty-card">
            <h3>Event Not Available</h3>
            <p>{error || 'The requested event could not be found or is not open for public viewing.'}</p>
            <Link to="/" className="btn btn-primary btn-sm">
              &larr; Return to Home
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const timeSpan = event.start_time && event.end_time
    ? `${formatTime(event.start_time)} – ${formatTime(event.end_time)}`
    : (event.start_time ? formatTime(event.start_time) : 'Hours TBA');

  return (
    <div className="event-detail-page">
      <div className="content-container">
        {/* Styled Rich Explore Navigation Bar */}
        <header className="explore-nav-bar" aria-label="Page Navigation & Details">
          <div className="enb-left">
            <button
              type="button"
              className="enb-back-btn"
              onClick={() => navigate(-1)}
              title="Return to Previous Page"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="19" y1="12" x2="5" y2="12" />
                <polyline points="12 19 5 12 12 5" />
              </svg>
              <span>Back</span>
            </button>

            <div className="enb-divider" aria-hidden="true" />

            <nav className="enb-breadcrumbs" aria-label="Breadcrumbs">
              <Link to="/" className="enb-crumb">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
                  <polyline points="9 22 9 12 15 12 15 22" />
                </svg>
                <span>Home</span>
              </Link>
              <span className="enb-sep">›</span>
              {event.series_id ? (
                <>
                  <Link to={`/fest/${event.series_id}`} className="enb-crumb">
                    <span>{event.series_name || 'Festival'}</span>
                  </Link>
                  <span className="enb-sep">›</span>
                </>
              ) : (
                <>
                  <Link to="/#upcoming-events" className="enb-crumb">
                    <span>Events</span>
                  </Link>
                  <span className="enb-sep">›</span>
                </>
              )}
              <span className="enb-crumb current">
                <span className="enb-event-dot" aria-hidden="true" />
                {event.event_name}
              </span>
            </nav>
          </div>

          <div className="enb-right">
            <div className="enb-quick-info">
              <span className="enb-date-chip">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                  <circle cx="12" cy="10" r="3" />
                </svg>
                <span>{event.venue_name || 'Main Campus Venue'}</span>
              </span>

              <span className="enb-category-chip">
                {event.category || 'General'}
              </span>
            </div>

            <StatusBadge status={event.status || 'Upcoming'} />

            <button
              type="button"
              className="enb-share-btn"
              onClick={handleShare}
              title="Share or Copy Link"
            >
              {copied ? (
                <>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                  <span>Copied!</span>
                </>
              ) : (
                <>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="18" cy="5" r="3" />
                    <circle cx="6" cy="12" r="3" />
                    <circle cx="18" cy="19" r="3" />
                    <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
                    <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
                  </svg>
                  <span>Share</span>
                </>
              )}
            </button>
          </div>
        </header>

        {/* Main Event Details Grid: Content on Left, Crowd Monitoring Panel on Right */}
        <div className="event-detail-grid">
          {/* Left Column: Event Core Info */}
          <div className="event-main-card">
            {/* Top Badges */}
            <div className="event-meta-topbar">
              <span className="event-category-badge">{event.category || 'General'}</span>
              {event.series_name && event.series_id && (
                <Link to={`/fest/${event.series_id}`} className="event-series-link-badge">
                  Part of {event.series_name} &rarr;
                </Link>
              )}
              <StatusBadge status={event.status || 'Upcoming'} />
            </div>

            <h1 className="event-title-h1">{event.event_name}</h1>

            {/* Matrix Strip: Date, Hours, Venue, Capacity */}
            <div className="event-matrix-grid">
              <div className="em-box">
                <span className="em-label">Date</span>
                <span className="em-val">
                  {formatDate(event.event_date || event.start_date || event.approved_date || event.requested_date)}
                </span>
              </div>

              <div className="em-box">
                <span className="em-label">Hours</span>
                <span className="em-val">{timeSpan}</span>
              </div>

              <div className="em-box">
                <span className="em-label">Venue</span>
                <span className="em-val">{event.venue_name || 'Campus Venue TBA'}</span>
                {event.venue_location && (
                  <span className="em-sub">{event.venue_location}</span>
                )}
              </div>

              <div className="em-box">
                <span className="em-label">Venue Capacity</span>
                <span className="em-val">
                  {event.venue_capacity ? `${event.venue_capacity} seats` : 'Open Seating'}
                </span>
              </div>
            </div>

            {/* About This Event */}
            <div className="event-description-section">
              <h3 className="section-subtitle">About this Event</h3>
              <p className="event-full-description">
                {event.description || 'No detailed description has been registered for this campus event.'}
              </p>
            </div>

            {/* Part of Festival Series Banner */}
            {event.series_name && event.series_id && (
              <div className="event-parent-fest-box">
                <div className="epf-info">
                  <span className="epf-kicker">FESTIVAL SERIES</span>
                  <h4 className="epf-name">{event.series_name}</h4>
                  <p className="epf-desc">
                    This event is scheduled as part of the coordinated <strong>{event.series_name}</strong> campus festival.
                  </p>
                </div>
                <Link to={`/fest/${event.series_id}`} className="btn btn-secondary btn-sm">
                  Explore All {event.series_name} Events &rarr;
                </Link>
              </div>
            )}

            {/* Back action */}
            <div className="event-actions-bottom">
              <button type="button" onClick={() => navigate(-1)} className="btn btn-secondary btn-sm">
                &larr; Back
              </button>
              <Link to="/" className="btn btn-ghost btn-sm">
                Return to Campus Home
              </Link>
            </div>
          </div>

          {/* Right Column: Crowd Monitoring Panel */}
          <div className="event-side-panel">
            <div className="crowd-monitor-panel">
              <div className="cmp-header">
                <div className="cmp-header-icon" aria-hidden="true">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                    <circle cx="9" cy="7" r="4" />
                    <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                    <path d="M16 3.13a4 4 0 0 1 0 7.75" />
                  </svg>
                </div>
                <div>
                  <h3 className="cmp-title">Crowd Monitoring</h3>
                  <span className="cmp-sub">Campus Safety Surveillance</span>
                </div>
              </div>

              {/* Status display: Not Available (as requested: no fake data) */}
              <div className="cmp-status-box">
                <div className="cmp-status-pill unavailable">
                  <span className="cmp-dot" />
                  <span>Not Available</span>
                </div>

                <p className="cmp-notice">
                  Automated computer-vision crowd density monitoring is currently pending model implementation for this venue.
                </p>

                <div className="cmp-specs">
                  <div className="cmp-spec-row">
                    <span className="cmp-spec-lbl">Camera Feed</span>
                    <span className="cmp-spec-val">Standby</span>
                  </div>
                  <div className="cmp-spec-row">
                    <span className="cmp-spec-lbl">Estimated Attendees</span>
                    <span className="cmp-spec-val">Not Available</span>
                  </div>
                  <div className="cmp-spec-row">
                    <span className="cmp-spec-lbl">Capacity Threshold</span>
                    <span className="cmp-spec-val">{event.venue_capacity || 'N/A'}</span>
                  </div>
                </div>
              </div>

              <div className="cmp-footer-note">
                Real-time headcounts and bottleneck alerts will be automatically computed once the surveillance model is deployed.
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
