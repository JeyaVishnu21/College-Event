import React, { useState, useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { getEventSeries, getPublicEvents, getPublicVenues } from '../services/api';
import Loading from '../components/Loading';
import StatusBadge from '../components/StatusBadge';

const CURRENT_YEAR = new Date().getFullYear();

/**
 * College Event Portal - Main Landing Page
 * -------------------------------------------------------------
 * Built according to user requirements and reference screenshots:
 * 1. Hero Section ("What's happening around campus?"):
 *    - Left: Campus Pulse badge, big title, subtitle, search bar, quick explore category tags.
 *    - Right: Ongoing Fest (or closest scheduled fest if none is active), date, schedule, View Fest link.
 * 2. Next on Campus (Campus Calendar):
 *    - Spotlight card for the very next event on campus with date block, tags, venue, time, and View Event link.
 * 3. Festival & Event Series (Campus Series):
 *    - Deep navy series cards from Screenshot 3 with Grouped Events tally, Schedule Duration, and Explore Series.
 * 4. All Scheduled Events Directory:
 *    - Event lineup with venue, date, time, and "Crowd Monitoring: Not Available" (no fake data).
 * 5. Campus Venues & Directions (Before Footer):
 *    - Clear campus venues directory with locations, capacities, and step-by-step walking directions.
 * 6. Decorated Institutional Footer:
 *    - Modern 4-column footer with emblem, links, and system telemetry note.
 */
export default function Home() {
  const [fests, setFests] = useState([]);
  const [events, setEvents] = useState([]);
  const [venues, setVenues] = useState([]);
  const [loadingFests, setLoadingFests] = useState(true);
  const [loadingEvents, setLoadingEvents] = useState(true);
  const [loadingVenues, setLoadingVenues] = useState(true);
  const [errorMsg, setErrorMsg] = useState('');

  // Search & Filter state
  const [searchQuery, setSearchQuery] = useState('');
  const [activeCategory, setActiveCategory] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');

  // Load campus festivals
  useEffect(() => {
    let isMounted = true;
    const fetchFests = async () => {
      setLoadingFests(true);
      try {
        const res = await getEventSeries();
        if (isMounted && res.ok && res.data?.series) {
          setFests(res.data.series);
        }
      } catch {
        if (isMounted) setErrorMsg('Unable to connect to campus event service.');
      } finally {
        if (isMounted) setLoadingFests(false);
      }
    };
    fetchFests();
    return () => { isMounted = false; };
  }, []);

  // Load campus events
  useEffect(() => {
    let isMounted = true;
    const fetchEvents = async () => {
      setLoadingEvents(true);
      try {
        const res = await getPublicEvents();
        if (isMounted && res.ok && res.data?.events) {
          setEvents(res.data.events);
        }
      } catch {
        // Silently catch fallback
      } finally {
        if (isMounted) setLoadingEvents(false);
      }
    };
    fetchEvents();
    return () => { isMounted = false; };
  }, []);

  // Load campus venues with walking directions
  useEffect(() => {
    let isMounted = true;
    const fetchVenues = async () => {
      setLoadingVenues(true);
      try {
        const res = await getPublicVenues();
        if (isMounted && res.ok && res.data?.venues) {
          setVenues(res.data.venues);
        }
      } catch {
        // Silently catch fallback
      } finally {
        if (isMounted) setLoadingVenues(false);
      }
    };
    fetchVenues();
    return () => { isMounted = false; };
  }, []);

  // Helpers
  const formatDateRange = (startDate, endDate) => {
    if (!startDate && !endDate) return 'Dates TBA';
    try {
      const s = startDate ? new Date(startDate).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '';
      const e = endDate ? new Date(endDate).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '';
      if (s && e) {
        if (s === e) return s;
        return `${s} - ${e}`;
      }
      return s || e;
    } catch {
      return `${startDate || ''} - ${endDate || ''}`;
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return 'TBA';
    try {
      const d = new Date(dateStr);
      if (isNaN(d.getTime())) return dateStr;
      return d.toLocaleDateString('en-GB', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      });
    } catch {
      return dateStr;
    }
  };

  const parseDateParts = (dateStr) => {
    if (!dateStr) return { day: '01', month: 'OCT', year: '2026' };
    try {
      const d = new Date(dateStr);
      if (isNaN(d.getTime())) return { day: '01', month: 'OCT', year: '2026' };
      const day = String(d.getDate()).padStart(2, '0');
      const month = d.toLocaleDateString('en-GB', { month: 'short' }).toUpperCase();
      const year = String(d.getFullYear());
      return { day, month, year };
    } catch {
      return { day: '01', month: 'OCT', year: '2026' };
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

  // Identify the Fest for the Right Column of the Hero:
  // "in the right side of the what happening put the fest which is ongoing if no fest is ongoing then show the ffest which is scheduled close"
  const heroFest = useMemo(() => {
    if (!fests || fests.length === 0) return null;

    // 1. Check for ongoing festival
    const ongoing = fests.find((f) => {
      const st = (f.computed_status || f.status || '').toLowerCase();
      return st.includes('ongoing') || st.includes('active');
    });
    if (ongoing) return { fest: ongoing, isOngoing: true };

    // 2. Otherwise find the upcoming fest scheduled closest
    const upcomingList = fests.filter((f) => {
      const st = (f.computed_status || f.status || '').toLowerCase();
      return st.includes('upcoming');
    });

    if (upcomingList.length > 0) {
      // Sort by start_date ascending
      const sorted = [...upcomingList].sort((a, b) => {
        if (!a.start_date) return 1;
        if (!b.start_date) return -1;
        return new Date(a.start_date) - new Date(b.start_date);
      });
      return { fest: sorted[0], isOngoing: false };
    }

    // Fallback: Return first available fest
    return { fest: fests[0], isOngoing: false };
  }, [fests]);

  // Next event on campus for the "Next on Campus" spotlight
  const nextEvent = useMemo(() => {
    if (!events || events.length === 0) return null;
    const upcomingEvents = events.filter((e) => {
      const st = (e.status || e.computed_status || '').toLowerCase();
      return st.includes('upcoming') || st.includes('approved') || st.includes('ongoing');
    });
    return upcomingEvents.length > 0 ? upcomingEvents[0] : events[0];
  }, [events]);

  // Filtered festivals for the Festival & Event Series stack
  const filteredFests = useMemo(() => {
    return fests.filter((fest) => {
      const matchesSearch =
        searchQuery === '' ||
        (fest.name || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
        (fest.description || '').toLowerCase().includes(searchQuery.toLowerCase());

      const computed = (fest.computed_status || fest.status || '').toLowerCase();
      let matchesStatus = true;
      if (statusFilter === 'upcoming') {
        matchesStatus = computed.includes('upcoming');
      } else if (statusFilter === 'active') {
        matchesStatus = computed.includes('ongoing') || computed.includes('active');
      } else if (statusFilter === 'completed') {
        matchesStatus = computed.includes('completed');
      }

      return matchesSearch && matchesStatus;
    });
  }, [fests, searchQuery, statusFilter]);

  // Filtered events for the All Events directory
  const filteredEvents = useMemo(() => {
    return events.filter((ev) => {
      const matchesSearch =
        searchQuery === '' ||
        (ev.event_name || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
        (ev.description || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
        (ev.venue_name || '').toLowerCase().includes(searchQuery.toLowerCase());

      const matchesCat =
        activeCategory === 'all' ||
        (ev.category || '').toLowerCase() === activeCategory.toLowerCase();

      return matchesSearch && matchesCat;
    });
  }, [events, searchQuery, activeCategory]);

  return (
    <div className="campus-brochure-page">
      <main className="content-container brochure-main-layout">
        {/* ============================================================== */}
        {/* 1. HERO SECTION: "What's happening around campus?"             */}
        {/*    (Format matching user reference screenshot)                 */}
        {/* ============================================================== */}
        <section className="campus-pulse-hero" aria-label="Campus Pulse Overview">
          <div className="hero-two-col-grid">
            {/* Left Column: Campus Pulse & Search */}
            <div className="hero-left-column">
              <div className="pulse-pill-badge">
                <span className="ppb-dot" aria-hidden="true" />
                <span>CAMPUS PULSE</span>
              </div>

              <h1 className="hero-main-heading">
                What's happening <br />
                around campus?
              </h1>

              <p className="hero-sub-text">
                Discover college events, schedules, venues and crowd information.
              </p>

              {/* Search Bar matching screenshot */}
              <form
                className="hero-search-bar"
                onSubmit={(e) => {
                  e.preventDefault();
                  const target = document.getElementById('upcoming-events');
                  if (target) target.scrollIntoView({ behavior: 'smooth' });
                }}
              >
                <div className="hsb-input-wrap">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                    <circle cx="11" cy="11" r="8" />
                    <line x1="21" y1="21" x2="16.65" y2="16.65" />
                  </svg>
                  <input
                    type="text"
                    placeholder="Search events, clubs, festivals..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="hsb-input"
                  />
                  {searchQuery && (
                    <button
                      type="button"
                      className="hsb-clear-btn"
                      onClick={() => setSearchQuery('')}
                      aria-label="Clear search"
                    >
                      &times;
                    </button>
                  )}
                </div>
                <button type="submit" className="btn btn-primary hsb-btn">
                  Search
                </button>
              </form>

              {/* Quick Explore Category Tags */}
              <div className="hero-explore-row">
                <span className="her-label">Explore:</span>
                <div className="her-tags">
                  {['all', 'Technical', 'Cultural', 'Sports', 'Workshops', 'Competitions'].map((cat) => (
                    <button
                      key={cat}
                      type="button"
                      className={`her-tag ${activeCategory.toLowerCase() === cat.toLowerCase() ? 'active' : ''}`}
                      onClick={() => setActiveCategory(cat.toLowerCase())}
                    >
                      {cat === 'all' ? 'All Lineups' : cat}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Right Column: Ongoing Fest / Closest Scheduled Fest */}
            <div className="hero-right-column">
              {loadingFests ? (
                <div className="hero-fest-card hero-fest-loading">
                  <Loading message="Checking campus festivals..." />
                </div>
              ) : heroFest?.fest ? (
                <article className="hero-fest-card" aria-label="Featured Campus Festival">
                  <div className="hfc-header-row">
                    <span className="hfc-kicker">
                      {heroFest.isOngoing ? 'ONGOING FEST' : 'UPCOMING FEST'}
                    </span>
                    <span className={`hfc-status-pill ${heroFest.isOngoing ? 'status-ongoing' : 'status-upcoming'}`}>
                      {heroFest.isOngoing ? 'Ongoing Now' : 'Upcoming'}
                    </span>
                  </div>

                  <span className="hfc-fest-tag">CAMPUS FESTIVAL</span>

                  <h2 className="hfc-title">
                    <Link to={`/fest/${heroFest.fest.id}`}>
                      {heroFest.fest.name}
                    </Link>
                  </h2>

                  <div className="hfc-meta-list">
                    <div className="hfc-meta-item">
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                        <line x1="16" y1="2" x2="16" y2="6" />
                        <line x1="8" y1="2" x2="8" y2="6" />
                      </svg>
                      <span>{formatDateRange(heroFest.fest.start_date, heroFest.fest.end_date)}</span>
                    </div>

                    <div className="hfc-meta-item">
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <circle cx="12" cy="12" r="10" />
                        <polyline points="12 6 12 12 16 14" />
                      </svg>
                      <span>
                        {heroFest.fest.event_count !== undefined
                          ? `${heroFest.fest.event_count} Grouped Events Scheduled`
                          : 'Flagship Multi-Event Program'}
                      </span>
                    </div>

                    <div className="hfc-meta-item">
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                        <circle cx="12" cy="10" r="3" />
                      </svg>
                      <span>Main University Campus Venues</span>
                    </div>
                  </div>

                  <p className="hfc-desc">
                    {heroFest.fest.description
                      ? (heroFest.fest.description.length > 130
                          ? `${heroFest.fest.description.substring(0, 130)}...`
                          : heroFest.fest.description)
                      : 'Flagship university festival bringing students together for educational and cultural competitions.'}
                  </p>

                  <div className="hfc-btn-wrap">
                    <Link to={`/fest/${heroFest.fest.id}`} className="btn btn-primary hfc-action-btn">
                      View Fest &rarr;
                    </Link>
                  </div>
                </article>
              ) : (
                <div className="hero-fest-card">
                  <span className="hfc-kicker">CAMPUS FESTIVALS</span>
                  <h3 className="hfc-title">No Festival Series Active</h3>
                  <p className="hfc-desc">Upcoming campus festivals will be announced here shortly.</p>
                </div>
              )}
            </div>
          </div>
        </section>

        {/* ============================================================== */}
        {/* 2. NEXT ON CAMPUS SECTION (Matches Screenshot middle row)      */}
        {/* ============================================================== */}
        <section id="next-on-campus" className="next-on-campus-section" aria-label="Next on Campus Event">
          <div className="noc-header-bar">
            <div>
              <span className="section-kicker">CAMPUS CALENDAR</span>
              <h2 className="section-main-heading">Next on Campus</h2>
              <p className="section-sub-heading">See what is happening on campus next.</p>
            </div>
            <a href="#upcoming-events" className="noc-full-link">
              View Full Lineup &darr;
            </a>
          </div>

          {nextEvent ? (
            (() => {
              const dateParts = parseDateParts(nextEvent.start_date || nextEvent.event_date || nextEvent.requested_date);
              const timeDisplay = nextEvent.start_time && nextEvent.end_time
                ? `${formatTime(nextEvent.start_time)} – ${formatTime(nextEvent.end_time)}`
                : (nextEvent.start_time ? formatTime(nextEvent.start_time) : 'Hours TBA');

              return (
                <div className="noc-card-row">
                  <div className="noc-date-box" aria-label={`Date: ${dateParts.day} ${dateParts.month} ${dateParts.year}`}>
                    <span className="noc-date-day">{dateParts.day}</span>
                    <span className="noc-date-month">{dateParts.month}</span>
                    <span className="noc-date-year">{dateParts.year}</span>
                  </div>

                  <div className="noc-info-content">
                    <div className="noc-tag-line">
                      <span className="noc-category-tag">{nextEvent.category || 'Technical'}</span>
                      <span className="noc-status-tag">{nextEvent.status || 'Upcoming'}</span>
                      {nextEvent.series_name && (
                        <span className="noc-series-tag">{nextEvent.series_name}</span>
                      )}
                    </div>

                    <h3 className="noc-event-title">
                      <Link to={`/event/${nextEvent.id}`}>{nextEvent.event_name}</Link>
                    </h3>

                    <div className="noc-event-meta">
                      <div className="nem-item">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <circle cx="12" cy="12" r="10" />
                          <polyline points="12 6 12 12 16 14" />
                        </svg>
                        <span>{timeDisplay}</span>
                      </div>
                      <div className="nem-item">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                          <circle cx="12" cy="10" r="3" />
                        </svg>
                        <span>{nextEvent.venue_name || 'Science Lab Complex'}{nextEvent.venue_location ? ` (${nextEvent.venue_location})` : ''}</span>
                      </div>
                    </div>
                  </div>

                  <div className="noc-action-wrap">
                    <Link to={`/event/${nextEvent.id}`} className="btn btn-primary noc-btn-view">
                      View Event &gt;
                    </Link>
                  </div>
                </div>
              );
            })()
          ) : (
            <div className="series-empty-box">
              <p>No upcoming events currently scheduled.</p>
            </div>
          )}
        </section>

        {/* ============================================================== */}
        {/* 3. FESTIVAL & EVENT SERIES SECTION (Matches Screenshot 3)      */}
        {/* ============================================================== */}
        <section id="available-fests" className="campus-series-section" aria-labelledby="series-section-title">
          <div className="section-title-bar">
            <div>
              <span className="section-kicker">CAMPUS SERIES</span>
              <h2 id="series-section-title" className="section-main-heading">
                Festival &amp; Event Series
              </h2>
              <p className="section-sub-heading">
                Annual college festivals and coordinated multi-event programs.
              </p>
            </div>

            {/* Filter pills for festival series */}
            <div className="catalog-status-pills">
              <button
                type="button"
                className={`catalog-pill ${statusFilter === 'all' ? 'active' : ''}`}
                onClick={() => setStatusFilter('all')}
              >
                All Series ({fests.length})
              </button>
              <button
                type="button"
                className={`catalog-pill ${statusFilter === 'upcoming' ? 'active' : ''}`}
                onClick={() => setStatusFilter('upcoming')}
              >
                Upcoming
              </button>
              <button
                type="button"
                className={`catalog-pill ${statusFilter === 'active' ? 'active' : ''}`}
                onClick={() => setStatusFilter('active')}
              >
                Ongoing
              </button>
            </div>
          </div>

          {loadingFests ? (
            <div className="brochure-loading-box">
              <Loading message="Loading campus festival series..." />
            </div>
          ) : filteredFests.length === 0 ? (
            <div className="series-empty-box">
              <div className="series-empty-icon" aria-hidden="true">&#127914;</div>
              <h3>No Festival Series Found</h3>
              <p>Festival series will appear here when events are grouped into a college program.</p>
            </div>
          ) : (
            <div className="series-cards-stack">
              {filteredFests.map((fest) => {
                const eventCount = fest.event_count !== undefined ? fest.event_count : (fest.events?.length || 0);

                return (
                  <article key={fest.id} className="series-card-dark">
                    <div className="series-card-body">
                      <div className="series-card-topbar">
                        <span className="series-kicker-tag">CAMPUS SERIES</span>
                        <StatusBadge status={fest.computed_status || fest.status || 'Upcoming'} />
                      </div>

                      <h2 className="series-card-title">
                        <Link to={`/fest/${fest.id}`} className="series-title-link">
                          {fest.name}
                        </Link>
                      </h2>

                      <p className="series-card-desc">
                        {fest.description || 'Annual college fest bringing students together for educational and cultural competitions.'}
                      </p>

                      <div className="series-card-bottom-row">
                        <div className="series-meta-block">
                          <div className="series-stat-group">
                            <span className="series-stat-number">{eventCount}</span>
                            <span className="series-stat-label">GROUPED EVENTS</span>
                          </div>

                          <div className="series-stat-group">
                            <span className="series-stat-number" style={{ fontSize: '1.05rem', fontWeight: 600 }}>
                              {formatDateRange(fest.start_date, fest.end_date)}
                            </span>
                            <span className="series-stat-label">SCHEDULE DURATION</span>
                          </div>
                        </div>

                        <div className="series-card-action">
                          <Link to={`/fest/${fest.id}`} className="btn-explore-series">
                            Explore Series
                          </Link>
                        </div>
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </section>

        {/* ============================================================== */}
        {/* 4. UPCOMING EVENTS DIRECTORY                                    */}
        {/* ============================================================== */}
        <section id="upcoming-events" className="upcoming-events-section" aria-labelledby="events-dir-title">
          <div className="section-title-bar">
            <div>
              <span className="section-kicker">EVENT DIRECTORY</span>
              <h2 id="events-dir-title" className="section-main-heading">
                All Scheduled Events
              </h2>
              <p className="section-sub-heading">
                Explore individual competitions, workshops, and exhibitions scheduled across campus venues.
              </p>
            </div>
          </div>

          {loadingEvents ? (
            <div className="brochure-loading-box">
              <Loading message="Loading scheduled campus events..." />
            </div>
          ) : filteredEvents.length === 0 ? (
            <div className="series-empty-box">
              <div className="series-empty-icon" aria-hidden="true">&#128197;</div>
              <h3>No Events Match Your Query</h3>
              <p>Try resetting the category filter or searching with different keywords.</p>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => {
                  setSearchQuery('');
                  setActiveCategory('all');
                }}
              >
                Reset Search
              </button>
            </div>
          ) : (
            <div className="upcoming-events-grid">
              {filteredEvents.map((ev) => {
                const timeSpan = ev.start_time && ev.end_time
                  ? `${formatTime(ev.start_time)} – ${formatTime(ev.end_time)}`
                  : (ev.start_time ? formatTime(ev.start_time) : 'Time TBA');

                return (
                  <article key={ev.id} className="upcoming-event-item">
                    <div className="uei-header">
                      <div className="uei-tags">
                        <span className="uei-category-tag">{ev.category || 'General'}</span>
                        {ev.series_name && (
                          <Link to={`/fest/${ev.series_id}`} className="uei-series-tag">
                            {ev.series_name}
                          </Link>
                        )}
                      </div>
                      <StatusBadge status={ev.status || 'Upcoming'} />
                    </div>

                    <h3 className="uei-title">
                      <Link to={`/event/${ev.id}`}>{ev.event_name}</Link>
                    </h3>

                    <p className="uei-desc">
                      {ev.description || 'Campus competition scheduled under university event operations.'}
                    </p>

                    <div className="uei-meta-list">
                      <div className="uei-meta-item">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                          <line x1="16" y1="2" x2="16" y2="6" />
                          <line x1="8" y1="2" x2="8" y2="6" />
                        </svg>
                        <span>{formatDate(ev.event_date || ev.start_date || ev.requested_date)}</span>
                      </div>

                      <div className="uei-meta-item">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <circle cx="12" cy="12" r="10" />
                          <polyline points="12 6 12 12 16 14" />
                        </svg>
                        <span>{timeSpan}</span>
                      </div>

                      <div className="uei-meta-item">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                          <circle cx="12" cy="10" r="3" />
                        </svg>
                        <span>{ev.venue_name || 'Venue TBA'}{ev.venue_location ? ` (${ev.venue_location})` : ''}</span>
                      </div>
                    </div>

                    <div className="uei-footer">
                      {/* Honest Crowd Monitoring Status: Not Available (no fake/test data) */}
                      <span className="crowd-status-pill unavailable">
                        Crowd Monitoring: Not Available
                      </span>

                      <Link to={`/event/${ev.id}`} className="btn btn-secondary btn-sm">
                        Event Details &rarr;
                      </Link>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </section>

        {/* ============================================================== */}
        {/* 5. CAMPUS VENUES & DIRECTIONS (Right before the footer)         */}
        {/* ============================================================== */}
        <section id="venues-directions" className="venues-directions-section" aria-labelledby="venues-title">
          <div className="section-title-bar">
            <div>
              <span className="section-kicker">CAMPUS NAVIGATION &amp; ACCESSIBILITY</span>
              <h2 id="venues-title" className="section-main-heading">
                Campus Venues &amp; Directions
              </h2>
              <p className="section-sub-heading">
                Find your way to auditorium halls, seminar complexes, and indoor arenas with walking directions and venue capacities.
              </p>
            </div>
          </div>

          {loadingVenues ? (
            <div className="brochure-loading-box">
              <Loading message="Loading campus venues and navigation routes..." />
            </div>
          ) : (
            <div className="venues-grid-layout">
              {venues.map((venue) => (
                <article key={venue.id} className="venue-guide-card">
                  <div className="vgc-header">
                    <div>
                      <span className="vgc-zone-tag">{venue.zone || 'Campus Zone'}</span>
                      <h3 className="vgc-name">{venue.name}</h3>
                      <span className="vgc-location-sub">{venue.location}</span>
                    </div>
                    <div className="vgc-capacity-pill">
                      <span className="vgc-cap-num">{venue.capacity || 'TBA'}</span>
                      <span className="vgc-cap-lbl">Capacity</span>
                    </div>
                  </div>

                  <div className="vgc-landmark-row">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                      <circle cx="12" cy="10" r="3" />
                    </svg>
                    <span>Landmark: <strong>{venue.landmark || venue.location}</strong></span>
                  </div>

                  <div className="vgc-directions-box">
                    <span className="vgc-dir-heading">
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                        <polyline points="9 18 15 12 9 6" />
                      </svg>
                      Walking Directions:
                    </span>
                    <p className="vgc-directions-text">
                      {venue.directions || `Navigate to ${venue.location}. Follow departmental signage.`}
                    </p>
                  </div>

                  <div className="vgc-footer">
                    <span className="vgc-status-active">
                      <span className="vgc-status-dot" aria-hidden="true" />
                      Open for Scheduled Events
                    </span>
                    <a
                      href="#upcoming-events"
                      className="vgc-browse-link"
                      onClick={() => setSearchQuery(venue.name)}
                    >
                      Filter Events Here &rarr;
                    </a>
                  </div>
                </article>
              ))}
            </div>
          )}

          {/* Practical Campus Navigation Guide Banner */}
          <div className="campus-navigation-banner">
            <div className="cnb-icon-wrap" aria-hidden="true">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <path d="M16.2 7.8l-2 6.3-6.4 2 2-6.3z" />
              </svg>
            </div>
            <div className="cnb-info">
              <h4 className="cnb-title">Visitor &amp; Student Navigation Tips</h4>
              <p className="cnb-text">
                All campus venues feature wheelchair-accessible ramps on ground entries. For inter-venue transit between North and South academic zones, campus pedestrian walkways are lit and signposted. Plan to arrive at least 15 minutes before competition kick-off.
              </p>
            </div>
          </div>
        </section>
      </main>

      {/* ============================================================== */}
      {/* 6. DECORATED MODERN INSTITUTIONAL FOOTER                       */}
      {/* ============================================================== */}
      <footer className="decorated-institutional-footer">
        <div className="footer-top-accent-line" aria-hidden="true" />
        <div className="content-container footer-content-wrap">
          <div className="footer-columns-grid">
            {/* Column 1: Brand & College Portal Mission */}
            <div className="footer-col brand-col">
              <div className="footer-brand-header">
                <div className="footer-emblem-badge" aria-hidden="true">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                    <line x1="16" y1="2" x2="16" y2="6" />
                    <line x1="8" y1="2" x2="8" y2="6" />
                    <line x1="3" y1="10" x2="21" y2="10" />
                  </svg>
                </div>
                <div>
                  <h3 className="footer-brand-title">College Event Portal</h3>
                  <span className="footer-brand-sub">Campus Festival Discovery &amp; Operations</span>
                </div>
              </div>
              <p className="footer-brand-desc">
                Centralized university directory for student symposiums, annual cultural fests,
                and scheduled athletic tournaments across campus venues.
              </p>
              <div className="footer-live-badge">
                <span className="flb-dot" aria-hidden="true" />
                <span>Campus Event Operations &bull; Academic Year {CURRENT_YEAR}</span>
              </div>
            </div>

            {/* Column 2: Navigation Links */}
            <div className="footer-col">
              <h4 className="footer-heading">Festival Discovery</h4>
              <ul className="footer-nav-list">
                <li>
                  <Link to="/">Campus Festivals Catalog</Link>
                </li>
                <li>
                  <a href="#next-on-campus">Next on Campus</a>
                </li>
                <li>
                  <a href="#upcoming-events">Upcoming Event Lineup</a>
                </li>
                <li>
                  <a href="#venues-directions">Campus Venues &amp; Directions</a>
                </li>
              </ul>
            </div>

            {/* Column 3: Operations & Roles */}
            <div className="footer-col">
              <h4 className="footer-heading">Operations Portals</h4>
              <ul className="footer-nav-list">
                <li>
                  <Link to="/login">Organizer Event Desk</Link>
                </li>
                <li>
                  <Link to="/login">Administrator Oversight Console</Link>
                </li>
                <li>
                  <Link to="/register">Register Coordinator Account</Link>
                </li>
                <li>
                  <span className="footer-static-note">
                    Official portal for university event scheduling and venue approvals.
                  </span>
                </li>
              </ul>
            </div>

            {/* Column 4: Crowd Monitoring Notice */}
            <div className="footer-col">
              <h4 className="footer-heading">Crowd Safety Telemetry</h4>
              <div className="footer-crowd-notice-card">
                <div className="fcn-header">
                  <span className="fcn-badge">Status: In Development</span>
                </div>
                <p className="fcn-text">
                  Automated computer-vision crowd density monitoring is currently pending camera model implementation.
                  Live headcount telemetry will be activated across campus venues once computer-vision models are deployed.
                </p>
              </div>
            </div>
          </div>

          {/* Footer Bottom Bar */}
          <div className="footer-bottom-bar">
            <span className="fbb-copy">
              &copy; {CURRENT_YEAR} College Event Management System. All rights reserved.
            </span>
            <div className="fbb-meta">
              <span>Campus Event Operations</span>
              <span>&bull;</span>
              <span>Institutional Portal v2.5</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
