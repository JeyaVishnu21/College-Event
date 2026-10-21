import React, { useState, useEffect, useMemo } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getPublicSeriesDetail } from '../services/api';
import Loading from '../components/Loading';
import StatusBadge from '../components/StatusBadge';

/**
 * FestDetails Page Component
 * Displays complete details about a specific festival series:
 * - What the festival is (name, dates, description, total events).
 * - All scheduled events organized under this festival.
 * - Clicking any event navigates to /event/:id for complete event details.
 */
export default function FestDetails() {
  const { id } = useParams();
  const [fest, setFest] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Filtering events inside this fest
  const [searchQuery, setSearchQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');
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
    const fetchFest = async () => {
      setLoading(true);
      setError('');
      try {
        const res = await getPublicSeriesDetail(id);
        if (isMounted) {
          if (res.ok && res.data?.series) {
            setFest(res.data.series);
          } else {
            setError(res.error || 'Unable to load festival details.');
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
      fetchFest();
    }
    return () => {
      isMounted = false;
    };
  }, [id]);

  // Format date range helper
  const formatDateRange = (startDate, endDate) => {
    if (!startDate && !endDate) return 'Dates TBA';
    try {
      const s = startDate ? new Date(startDate).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '';
      const e = endDate ? new Date(endDate).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '';
      if (s && e) {
        if (s === e) return s;
        return `${s} – ${e}`;
      }
      return s || e;
    } catch {
      return `${startDate || ''} – ${endDate || ''}`;
    }
  };

  // Format single date
  const formatDate = (dateStr) => {
    if (!dateStr) return 'TBA';
    try {
      const d = new Date(dateStr);
      if (isNaN(d.getTime())) return dateStr;
      return d.toLocaleDateString('en-US', {
        weekday: 'short',
        month: 'short',
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

  // Categories available in this fest
  const categories = useMemo(() => {
    if (!fest?.events) return ['all'];
    const cats = new Set(fest.events.map((e) => e.category || 'General'));
    return ['all', ...Array.from(cats)];
  }, [fest]);

  // Filtered events
  const filteredEvents = useMemo(() => {
    if (!fest?.events) return [];
    return fest.events.filter((e) => {
      const matchCat = categoryFilter === 'all' || (e.category || 'General').toLowerCase() === categoryFilter.toLowerCase();
      const matchSearch =
        searchQuery === '' ||
        (e.event_name || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
        (e.description || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
        (e.venue_name || '').toLowerCase().includes(searchQuery.toLowerCase());
      return matchCat && matchSearch;
    });
  }, [fest, categoryFilter, searchQuery]);

  if (loading) {
    return (
      <div className="fest-detail-page">
        <div className="content-container" style={{ padding: '4rem 1rem' }}>
          <Loading message="Loading festival program and scheduled events..." />
        </div>
      </div>
    );
  }

  if (error || !fest) {
    return (
      <div className="fest-detail-page">
        <div className="content-container" style={{ padding: '4rem 1rem' }}>
          <div className="portal-empty-card">
            <h3>Festival Series Not Found</h3>
            <p>{error || 'The requested campus festival series does not exist or has been removed.'}</p>
            <Link to="/" className="btn btn-primary btn-sm">
              &larr; Return to Festivals
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="fest-detail-page">
      <div className="content-container">
        {/* Styled Rich Explore Navigation Bar */}
        <header className="explore-nav-bar" aria-label="Page Navigation & Details">
          <div className="enb-left">
            <Link to="/" className="enb-back-btn" title="Return to Campus Festivals">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="19" y1="12" x2="5" y2="12" />
                <polyline points="12 19 5 12 12 5" />
              </svg>
              <span>Back to Campus</span>
            </Link>

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
              <Link to="/#available-fests" className="enb-crumb">
                <span>Campus Festivals</span>
              </Link>
              <span className="enb-sep">›</span>
              <span className="enb-crumb current">
                <span className="enb-fest-dot" aria-hidden="true" />
                {fest.name}
              </span>
            </nav>
          </div>

          <div className="enb-right">
            <div className="enb-quick-info">
              <span className="enb-date-chip">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                  <line x1="16" y1="2" x2="16" y2="6" />
                  <line x1="8" y1="2" x2="8" y2="6" />
                </svg>
                <span>{formatDateRange(fest.start_date, fest.end_date)}</span>
              </span>

              <span className="enb-events-chip">
                <span className="chip-count">{fest.total_events || fest.events?.length || 0}</span>
                <span>Events</span>
              </span>
            </div>

            <StatusBadge status={fest.computed_status || fest.status || 'Upcoming'} />

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

        {/* Big Series Banner Card (Styled like Screenshot 3) */}
        <div className="series-banner-card">
          <div className="series-banner-top">
            <span className="series-kicker">CAMPUS SERIES</span>
            <StatusBadge status={fest.computed_status || fest.status || 'Upcoming'} />
          </div>

          <h1 className="series-banner-title">{fest.name}</h1>

          <p className="series-banner-desc">
            {fest.description || 'Annual collegiate festival bringing together departmental cohorts, competitions, and technical showcases.'}
          </p>

          <div className="series-banner-meta-grid">
            <div className="sbm-item">
              <span className="sbm-val">{fest.total_events || fest.events?.length || 0}</span>
              <span className="sbm-lbl">GROUPED EVENTS</span>
            </div>
            <div className="sbm-divider" aria-hidden="true" />
            <div className="sbm-item">
              <span className="sbm-val">{formatDateRange(fest.start_date, fest.end_date)}</span>
              <span className="sbm-lbl">SCHEDULE DURATION</span>
            </div>
          </div>
        </div>

        {/* Section: Events organized under this fest */}
        <div className="series-events-section">
          <div className="series-events-header">
            <div>
              <span className="section-kicker">FESTIVAL PROGRAM</span>
              <h2 className="section-title">Events in {fest.name}</h2>
              <p className="section-sub">
                Click any event below to view its complete schedule, venue details, and crowd monitoring status.
              </p>
            </div>

            {/* Filter toolbar */}
            <div className="fest-filter-toolbar">
              <div className="fest-search-box">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                  <circle cx="11" cy="11" r="8" />
                  <line x1="21" y1="21" x2="16.65" y2="16.65" />
                </svg>
                <input
                  type="text"
                  placeholder="Search events in this fest..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="fest-search-input"
                />
                {searchQuery && (
                  <button type="button" onClick={() => setSearchQuery('')} className="fest-search-clear">
                    &times;
                  </button>
                )}
              </div>

              <div className="fest-cat-pills">
                {categories.map((cat) => (
                  <button
                    key={cat}
                    type="button"
                    className={`fest-cat-pill ${categoryFilter === cat ? 'active' : ''}`}
                    onClick={() => setCategoryFilter(cat)}
                  >
                    {cat === 'all' ? 'All Categories' : cat}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Events List */}
          {filteredEvents.length === 0 ? (
            <div className="series-empty-events">
              <div className="empty-events-icon" aria-hidden="true">&#128197;</div>
              <h3>No Events Match Your Filter</h3>
              <p>Try clearing your search query or selecting "All Categories".</p>
              {(searchQuery || categoryFilter !== 'all') && (
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => {
                    setSearchQuery('');
                    setCategoryFilter('all');
                  }}
                >
                  Reset Filters
                </button>
              )}
            </div>
          ) : (
            <div className="series-events-grid">
              {filteredEvents.map((ev) => {
                const timeSpan = ev.start_time && ev.end_time
                  ? `${formatTime(ev.start_time)} – ${formatTime(ev.end_time)}`
                  : (ev.start_time ? formatTime(ev.start_time) : 'Time TBA');

                return (
                  <article key={ev.id} className="fest-event-card">
                    <div className="fec-topbar">
                      <span className="fec-category">{ev.category || 'General'}</span>
                      <StatusBadge status={ev.status || 'Upcoming'} />
                    </div>

                    <h3 className="fec-title">{ev.event_name}</h3>

                    <p className="fec-desc">
                      {ev.description || 'Campus competition scheduled under this festival series.'}
                    </p>

                    <div className="fec-details-list">
                      <div className="fec-detail-row">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                          <line x1="16" y1="2" x2="16" y2="6" />
                          <line x1="8" y1="2" x2="8" y2="6" />
                          <line x1="3" y1="10" x2="21" y2="10" />
                        </svg>
                        <span>{formatDate(ev.event_date || ev.start_date || ev.requested_date)}</span>
                      </div>

                      <div className="fec-detail-row">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <circle cx="12" cy="12" r="10" />
                          <polyline points="12 6 12 12 16 14" />
                        </svg>
                        <span>{timeSpan}</span>
                      </div>

                      <div className="fec-detail-row">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                          <circle cx="12" cy="10" r="3" />
                        </svg>
                        <span>{ev.venue_name || 'Venue TBA'}{ev.venue_location ? ` (${ev.venue_location})` : ''}</span>
                      </div>
                    </div>

                    <div className="fec-footer">
                      <span className="crowd-status-pill unavailable">
                        Crowd Monitoring: Not Available
                      </span>

                      <Link to={`/event/${ev.id}`} className="btn btn-primary btn-sm">
                        View Event Details &rarr;
                      </Link>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
