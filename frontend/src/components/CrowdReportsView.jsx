import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  getReportEvents,
  getEventReport,
  downloadEventReportPdf,
} from '../services/api';

/**
 * CrowdReportsView Component
 * --------------------------
 * Renders the complete, real-time Crowd Occupancy & Peak Density Report section.
 * Displays executive summary KPIs, interactive timeline chart, chronological
 * computer vision analysis history, and safety threshold alerts directly from MySQL database records.
 * Provides instant PDF report compilation and export.
 */
export default function CrowdReportsView({ role = 'administrator' }) {
  const [events, setEvents] = useState([]);
  const [selectedEventId, setSelectedEventId] = useState('');
  const [loadingEvents, setLoadingEvents] = useState(true);
  const [loadingReport, setLoadingReport] = useState(false);
  const [reportData, setReportData] = useState(null);
  const [errorMessage, setErrorMessage] = useState('');
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const [downloadError, setDownloadError] = useState('');
  const [hoveredPoint, setHoveredPoint] = useState(null);

  // 1. Load accessible events for selector
  const fetchEvents = useCallback(async () => {
    setLoadingEvents(true);
    setErrorMessage('');
    try {
      const res = await getReportEvents();
      if (res.ok && res.data?.events) {
        const eventList = res.data.events;
        setEvents(eventList);

        // Pre-select first event with analysis data, or the very first event
        if (eventList.length > 0) {
          const withData = eventList.find((e) => (e.analyzed_images || 0) > 0);
          const initialId = withData ? withData.id : eventList[0].id;
          setSelectedEventId(String(initialId));
        } else {
          setSelectedEventId('');
        }
      } else {
        setErrorMessage(res.error || 'Failed to load events for reporting.');
      }
    } catch {
      setErrorMessage('Unable to connect to backend server to fetch report events.');
    } finally {
      setLoadingEvents(false);
    }
  }, []);

  useEffect(() => {
    fetchEvents();
  }, [fetchEvents]);

  // 2. Load detailed report whenever selectedEventId changes
  const fetchReport = useCallback(async (eventId) => {
    if (!eventId) {
      setReportData(null);
      return;
    }
    setLoadingReport(true);
    setErrorMessage('');
    setDownloadError('');
    try {
      const res = await getEventReport(eventId);
      if (res.ok && res.data?.report) {
        setReportData(res.data.report);
      } else {
        setErrorMessage(res.error || `Unable to load report for Event #${eventId}.`);
        setReportData(null);
      }
    } catch {
      setErrorMessage('Network error while retrieving crowd report data.');
      setReportData(null);
    } finally {
      setLoadingReport(false);
    }
  }, []);

  useEffect(() => {
    if (selectedEventId) {
      fetchReport(selectedEventId);
    }
  }, [selectedEventId, fetchReport]);

  // Handle Event Selector Change
  const handleEventChange = (e) => {
    const newId = e.target.value;
    setSelectedEventId(newId);
  };

  // Handle Refresh Action
  const handleRefresh = () => {
    if (selectedEventId) {
      fetchReport(selectedEventId);
    } else {
      fetchEvents();
    }
  };

  // Handle PDF Download
  const handleDownloadPdf = async () => {
    if (!selectedEventId || !reportData?.event) return;
    setDownloadingPdf(true);
    setDownloadError('');
    try {
      const res = await downloadEventReportPdf(
        selectedEventId,
        reportData.event.event_name
      );
      if (!res.ok) {
        setDownloadError(res.error || 'Failed to download official PDF report.');
      }
    } catch {
      setDownloadError('Network error while requesting PDF compilation.');
    } finally {
      setDownloadingPdf(false);
    }
  };

  // Chart coordinate calculations
  const chartData = useMemo(() => {
    const history = reportData?.history || [];
    if (history.length < 2) return null;

    const parsed = history
      .map((item, idx) => {
        let ts = item.analysis_timestamp;
        let d = new Date(ts);
        if (isNaN(d.getTime())) {
          d = new Date();
        }
        return {
          idx,
          id: item.analysis_id,
          timestamp: d,
          timeLabel: d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
          dateLabel: d.toLocaleDateString([], { month: 'short', day: 'numeric' }),
          count: item.predicted_count || 0,
          utilization: item.utilization_percent,
          level: item.crowd_level,
          model: item.model_name,
        };
      })
      .sort((a, b) => a.timestamp - b.timestamp);

    const counts = parsed.map((p) => p.count);
    const capacity = reportData?.summary?.venue_capacity || 0;
    const maxVal = Math.max(...counts, capacity > 0 ? capacity * 1.1 : 50);
    const minVal = 0;

    // SVG canvas dimensions
    const width = 760;
    const height = 240;
    const padding = { top: 30, right: 35, bottom: 45, left: 55 };
    const chartW = width - padding.left - padding.right;
    const chartH = height - padding.top - padding.bottom;

    const scaleX = (index) => padding.left + (index / (parsed.length - 1)) * chartW;
    const scaleY = (val) => padding.top + chartH - ((val - minVal) / (maxVal - minVal || 1)) * chartH;

    const points = parsed.map((p, i) => ({
      ...p,
      x: scaleX(i),
      y: scaleY(p.count),
    }));

    // SVG path string
    const pathD = points.reduce((acc, pt, i) => {
      return i === 0 ? `M ${pt.x} ${pt.y}` : `${acc} L ${pt.x} ${pt.y}`;
    }, '');

    // SVG area path (for gradient fill under curve)
    const areaD = `${pathD} L ${points[points.length - 1].x} ${padding.top + chartH} L ${points[0].x} ${padding.top + chartH} Z`;

    // Capacity reference line Y
    const capacityY = capacity > 0 ? scaleY(capacity) : null;

    // Y-Axis Ticks (4 ticks)
    const yTicks = [0, Math.round(maxVal * 0.33), Math.round(maxVal * 0.66), Math.round(maxVal)];

    return {
      width,
      height,
      padding,
      points,
      pathD,
      areaD,
      capacityY,
      capacity,
      yTicks,
      scaleY,
    };
  }, [reportData]);

  const event = reportData?.event;
  const summary = reportData?.summary;
  const history = reportData?.history || [];
  const alerts = reportData?.alerts || [];

  return (
    <div className="tab-pane crowd-reports-tab-pane">
      <section className="portal-section-card">
        {/* ============================================================ */}
        {/* 1. HEADER & ACTION BUTTONS                                   */}
        {/* ============================================================ */}
        <div className="section-card-header">
          <div className="header-title-stack">
            <h2 className="section-card-title">Crowd Occupancy &amp; Peak Density Reports</h2>
            <span className="section-card-subtitle">
              Formal campus event attendance summaries, computer vision headcounts, and peak capacity compliance logs
            </span>
          </div>

          <div className="section-header-actions" style={{ display: 'flex', gap: '0.65rem', alignItems: 'center', flexWrap: 'wrap' }}>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={handleRefresh}
              disabled={loadingEvents || loadingReport}
              title="Reload real-time telemetry from database"
            >
              <svg
                width="15"
                height="15"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                style={{
                  animation: loadingReport ? 'spin 1s linear infinite' : 'none',
                }}
              >
                <path d="M23 4v6h-6" />
                <path d="M1 20v-6h6" />
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
              </svg>
              <span>{loadingReport ? 'Refreshing...' : 'Refresh Report'}</span>
            </button>

            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={handleDownloadPdf}
              disabled={!selectedEventId || !event || downloadingPdf || loadingReport}
              title="Compile and download official institutional PDF audit report"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
              <span>{downloadingPdf ? 'Generating PDF...' : 'Download PDF Report'}</span>
            </button>
          </div>
        </div>

        {/* Download error banner */}
        {downloadError && (
          <div
            className="alert-banner alert-banner-danger"
            style={{
              padding: '0.65rem 1rem',
              backgroundColor: '#fef2f2',
              border: '1px solid #fecaca',
              borderRadius: 'var(--radius)',
              color: '#b91c1c',
              fontSize: '0.85rem',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <span>{downloadError}</span>
            <button
              type="button"
              onClick={() => setDownloadError('')}
              style={{ background: 'none', border: 'none', color: '#b91c1c', cursor: 'pointer', fontWeight: 'bold' }}
            >
              ✕
            </button>
          </div>
        )}

        {/* ============================================================ */}
        {/* 2. EVENT SELECTOR BAR                                         */}
        {/* ============================================================ */}
        <div
          className="reports-selector-card"
          style={{
            backgroundColor: '#f8fafc',
            border: '1px solid var(--border-color)',
            borderRadius: 'var(--radius)',
            padding: '1rem 1.25rem',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.5rem',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
            <label
              htmlFor="report-event-select"
              style={{
                fontSize: '0.875rem',
                fontWeight: '600',
                color: 'var(--text-primary)',
                display: 'flex',
                alignItems: 'center',
                gap: '0.4rem',
              }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: '#0284c7' }}>
                <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                <line x1="16" y1="2" x2="16" y2="6" />
                <line x1="8" y1="2" x2="8" y2="6" />
                <line x1="3" y1="10" x2="21" y2="10" />
              </svg>
              <span>Target Event for Crowd Audit Report:</span>
            </label>

            {events.length > 0 && (
              <span style={{ fontSize: '0.78125rem', color: 'var(--text-muted)' }}>
                {events.filter((e) => (e.analyzed_images || 0) > 0).length} of {events.length} events have analysis telemetry
              </span>
            )}
          </div>

          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
            <select
              id="report-event-select"
              value={selectedEventId}
              onChange={handleEventChange}
              disabled={loadingEvents || events.length === 0}
              style={{
                flex: '1 1 320px',
                padding: '0.55rem 0.85rem',
                fontSize: '0.875rem',
                border: '1px solid var(--border-color)',
                borderRadius: 'var(--radius-sm)',
                backgroundColor: '#ffffff',
                color: 'var(--text-primary)',
                fontFamily: 'inherit',
                outline: 'none',
              }}
            >
              {events.length === 0 ? (
                <option value="">{loadingEvents ? 'Loading events...' : 'No events available'}</option>
              ) : (
                events.map((ev) => {
                  const hasAnalyses = (ev.analyzed_images || 0) > 0;
                  const maxCrowdText = hasAnalyses ? `Peak: ${ev.max_crowd} persons` : 'No analyses';
                  return (
                    <option key={ev.id} value={ev.id}>
                      #{ev.id} — {ev.event_name} | {ev.venue_name || 'Unassigned Venue'} ({maxCrowdText})
                    </option>
                  );
                })
              )}
            </select>

            {event && (
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  padding: '0.3rem 0.65rem',
                  fontSize: '0.75rem',
                  fontWeight: '600',
                  borderRadius: '9999px',
                  backgroundColor: event.status === 'approved' ? '#f0fdf4' : '#fffbeb',
                  color: event.status === 'approved' ? '#16a34a' : '#b45309',
                  border: `1px solid ${event.status === 'approved' ? '#bbf7d0' : '#fde68a'}`,
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em',
                }}
              >
                ● Status: {event.status}
              </span>
            )}
          </div>
        </div>

        {/* ============================================================ */}
        {/* 3. ERROR & LOADING STATES                                     */}
        {/* ============================================================ */}
        {errorMessage && (
          <div
            className="alert-banner alert-banner-danger"
            style={{
              padding: '1rem',
              backgroundColor: '#fef2f2',
              border: '1px solid #fecaca',
              borderRadius: 'var(--radius)',
              color: '#b91c1c',
              fontSize: '0.875rem',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              <span>{errorMessage}</span>
            </div>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={handleRefresh}
              style={{ backgroundColor: '#ffffff' }}
            >
              Retry
            </button>
          </div>
        )}

        {loadingReport && (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '3rem 1.5rem',
              gap: '0.75rem',
              color: 'var(--text-muted)',
            }}
          >
            <div
              style={{
                width: '32px',
                height: '32px',
                border: '3px solid #e2e8f0',
                borderTopColor: '#0284c7',
                borderRadius: '50%',
                animation: 'spin 0.8s linear infinite',
              }}
            />
            <span style={{ fontSize: '0.875rem' }}>Querying verified crowd records from database...</span>
          </div>
        )}

        {/* Global Empty State: No events exist */}
        {!loadingEvents && events.length === 0 && !errorMessage && (
          <div className="table-empty-state">
            <div className="empty-state-icon" aria-hidden="true">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                <line x1="16" y1="2" x2="16" y2="6" />
                <line x1="8" y1="2" x2="8" y2="6" />
                <line x1="3" y1="10" x2="21" y2="10" />
              </svg>
            </div>
            <h4 className="empty-state-title">No events available for report generation</h4>
            <p className="empty-state-desc">
              Events will populate here once created by organizers and registered in the system.
            </p>
          </div>
        )}

        {/* ============================================================ */}
        {/* 4. MAIN REPORT CONTENT (WHEN REPORT LOADED)                  */}
        {/* ============================================================ */}
        {!loadingReport && reportData && event && summary && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            {/* 4A. Event Profile Header Card */}
            <div
              style={{
                backgroundColor: '#ffffff',
                border: '1px solid var(--border-color)',
                borderRadius: 'var(--radius)',
                padding: '1.25rem',
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                gap: '1rem',
                boxShadow: 'var(--shadow-sm)',
              }}
            >
              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: '600' }}>
                  Event Details
                </span>
                <div style={{ fontSize: '1.05rem', fontWeight: '700', color: 'var(--text-primary)', marginTop: '0.15rem' }}>
                  {event.event_name}
                </div>
                <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
                  ID #{event.id} {event.category ? `• ${event.category}` : ''}
                </div>
              </div>

              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: '600' }}>
                  Organizer
                </span>
                <div style={{ fontSize: '0.925rem', fontWeight: '600', color: 'var(--text-primary)', marginTop: '0.15rem' }}>
                  {event.organizer_name || 'N/A'}
                </div>
                <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
                  {event.organizer_email || ''}
                </div>
              </div>

              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: '600' }}>
                  Allocated Venue
                </span>
                <div style={{ fontSize: '0.925rem', fontWeight: '600', color: 'var(--text-primary)', marginTop: '0.15rem' }}>
                  {event.venue_name || 'Unassigned Venue'}
                </div>
                <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
                  {event.venue_location ? `${event.venue_location} • ` : ''}
                  Capacity: {summary.venue_capacity ? `${summary.venue_capacity.toLocaleString()} seats` : 'Not set'}
                </div>
              </div>

              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: '600' }}>
                  Scheduled Date &amp; Time
                </span>
                <div style={{ fontSize: '0.925rem', fontWeight: '600', color: 'var(--text-primary)', marginTop: '0.15rem' }}>
                  {event.approved_date || event.requested_date || 'Date TBD'}
                </div>
                <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
                  {event.approved_start_time || event.requested_start_time || '00:00'} -{' '}
                  {event.approved_end_time || event.requested_end_time || '00:00'}
                </div>
              </div>
            </div>

            {/* 4B. Executive KPI Metrics Grid */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))',
                gap: '0.85rem',
              }}
            >
              {/* Card 1: Analyzed Images */}
              <div
                style={{
                  backgroundColor: '#ffffff',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius)',
                  padding: '1rem',
                  boxShadow: 'var(--shadow-sm)',
                }}
              >
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: '600' }}>
                  Analyzed Photos
                </span>
                <div style={{ fontSize: '1.65rem', fontWeight: '700', color: '#0f172a', margin: '0.2rem 0' }}>
                  {summary.analyzed_images}
                </div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  of {summary.total_images} uploaded ({summary.pending_images} pending)
                </span>
              </div>

              {/* Card 2: Peak Headcount */}
              <div
                style={{
                  backgroundColor: '#ffffff',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius)',
                  padding: '1rem',
                  boxShadow: 'var(--shadow-sm)',
                }}
              >
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: '600' }}>
                  Peak Crowd Count
                </span>
                <div
                  style={{
                    fontSize: '1.65rem',
                    fontWeight: '700',
                    color: summary.max_crowd !== null ? '#0284c7' : 'var(--text-muted)',
                    margin: '0.2rem 0',
                  }}
                >
                  {summary.max_crowd !== null ? summary.max_crowd.toLocaleString() : 'N/A'}
                </div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  {summary.max_crowd !== null ? `Min: ${summary.min_crowd} • Avg: ${summary.avg_crowd}` : 'No verified headcounts'}
                </span>
              </div>

              {/* Card 3: Venue Capacity */}
              <div
                style={{
                  backgroundColor: '#ffffff',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius)',
                  padding: '1rem',
                  boxShadow: 'var(--shadow-sm)',
                }}
              >
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: '600' }}>
                  Venue Capacity
                </span>
                <div style={{ fontSize: '1.65rem', fontWeight: '700', color: '#0f172a', margin: '0.2rem 0' }}>
                  {summary.venue_capacity ? summary.venue_capacity.toLocaleString() : 'N/A'}
                </div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  Safe threshold ceiling
                </span>
              </div>

              {/* Card 4: Peak Utilization % */}
              <div
                style={{
                  backgroundColor: '#ffffff',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius)',
                  padding: '1rem',
                  boxShadow: 'var(--shadow-sm)',
                }}
              >
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: '600' }}>
                  Peak Utilization
                </span>
                <div
                  style={{
                    fontSize: '1.65rem',
                    fontWeight: '700',
                    color:
                      summary.peak_utilization_percent > 100
                        ? '#dc2626'
                        : summary.peak_utilization_percent > 85
                        ? '#d97706'
                        : summary.peak_utilization_percent !== null
                        ? '#16a34a'
                        : 'var(--text-muted)',
                    margin: '0.2rem 0',
                  }}
                >
                  {summary.peak_utilization_percent !== null ? `${summary.peak_utilization_percent}%` : 'N/A'}
                </div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  {summary.peak_utilization_percent > 100 ? 'Exceeded safe ceiling' : 'Observed capacity share'}
                </span>
              </div>

              {/* Card 5: Highest Crowd Level */}
              <div
                style={{
                  backgroundColor: '#ffffff',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius)',
                  padding: '1rem',
                  boxShadow: 'var(--shadow-sm)',
                }}
              >
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: '600' }}>
                  Highest Crowd Level
                </span>
                <div
                  style={{
                    fontSize: '1.15rem',
                    fontWeight: '700',
                    color:
                      summary.highest_crowd_level.includes('Critical')
                        ? '#dc2626'
                        : summary.highest_crowd_level.includes('High')
                        ? '#d97706'
                        : summary.highest_crowd_level.includes('Safe')
                        ? '#16a34a'
                        : 'var(--text-primary)',
                    margin: '0.45rem 0',
                  }}
                >
                  {summary.highest_crowd_level}
                </div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  Density classification
                </span>
              </div>

              {/* Card 6: Safety Alerts */}
              <div
                style={{
                  backgroundColor: '#ffffff',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius)',
                  padding: '1rem',
                  boxShadow: 'var(--shadow-sm)',
                }}
              >
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: '600' }}>
                  Safety Alerts
                </span>
                <div
                  style={{
                    fontSize: '1.65rem',
                    fontWeight: '700',
                    color: summary.alerts_count > 0 ? '#dc2626' : '#16a34a',
                    margin: '0.2rem 0',
                  }}
                >
                  {summary.alerts_count}
                </div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  {summary.alerts_count > 0 ? 'Threshold breach events' : 'Nominal safety state'}
                </span>
              </div>
            </div>

            {/* 4C. Empty State when event has NO analyses yet */}
            {!summary.has_data && (
              <div className="table-empty-state" style={{ backgroundColor: '#ffffff', padding: '2.5rem 1.5rem' }}>
                <div className="empty-state-icon" aria-hidden="true">
                  <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <line x1="18" y1="20" x2="18" y2="10" />
                    <line x1="12" y1="20" x2="12" y2="4" />
                    <line x1="6" y1="20" x2="6" y2="14" />
                  </svg>
                </div>
                <h4 className="empty-state-title">No crowd analysis results are available for this event yet.</h4>
                <p className="empty-state-desc" style={{ maxWidth: '520px' }}>
                  Surveillance photographs have either not been uploaded or have not yet completed computer vision analysis.
                  When surveillance images are processed, peak crowd counts, occupancy percentages, and chronological timeline curves will automatically display here.
                </p>
              </div>
            )}

            {/* 4D. Interactive Line Chart (When sufficient data exists) */}
            {summary.has_data && chartData && (
              <div
                style={{
                  backgroundColor: '#ffffff',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius)',
                  padding: '1.25rem',
                  boxShadow: 'var(--shadow-sm)',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                  <div>
                    <h3 style={{ fontSize: '0.95rem', fontWeight: '700', color: 'var(--text-primary)', margin: 0 }}>
                      Crowd Density Over Time
                    </h3>
                    <span style={{ fontSize: '0.78125rem', color: 'var(--text-muted)' }}>
                      Chronological headcount trends recorded across surveillance photographs
                    </span>
                  </div>

                  <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', fontSize: '0.78125rem' }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                      <span style={{ width: '12px', height: '3px', backgroundColor: '#0284c7', borderRadius: '2px' }} />
                      <span>Estimated Headcount</span>
                    </span>
                    {chartData.capacity > 0 && (
                      <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                        <span style={{ width: '12px', height: '2px', borderTop: '2px dashed #ef4444' }} />
                        <span>Venue Capacity ({chartData.capacity})</span>
                      </span>
                    )}
                  </div>
                </div>

                <div style={{ position: 'relative', width: '100%', overflowX: 'auto' }}>
                  <svg
                    viewBox={`0 0 ${chartData.width} ${chartData.height}`}
                    style={{ width: '100%', height: 'auto', minWidth: '550px', maxHeight: '250px' }}
                  >
                    <defs>
                      <linearGradient id="crowdGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.35" />
                        <stop offset="100%" stopColor="#38bdf8" stopOpacity="0.02" />
                      </linearGradient>
                    </defs>

                    {/* Horizontal Grid Lines */}
                    {chartData.yTicks.map((val) => {
                      const y = chartData.scaleY(val);
                      return (
                        <g key={val}>
                          <line
                            x1={chartData.padding.left}
                            y1={y}
                            x2={chartData.width - chartData.padding.right}
                            y2={y}
                            stroke="#e2e8f0"
                            strokeDasharray="3 3"
                            strokeWidth="1"
                          />
                          <text
                            x={chartData.padding.left - 8}
                            y={y + 4}
                            textAnchor="end"
                            fontSize="10"
                            fill="#64748b"
                            fontFamily="inherit"
                          >
                            {val}
                          </text>
                        </g>
                      );
                    })}

                    {/* Capacity Threshold Reference Line */}
                    {chartData.capacityY && (
                      <g>
                        <line
                          x1={chartData.padding.left}
                          y1={chartData.capacityY}
                          x2={chartData.width - chartData.padding.right}
                          y2={chartData.capacityY}
                          stroke="#ef4444"
                          strokeDasharray="4 4"
                          strokeWidth="1.5"
                        />
                        <text
                          x={chartData.width - chartData.padding.right}
                          y={chartData.capacityY - 4}
                          textAnchor="end"
                          fontSize="9.5"
                          fontWeight="600"
                          fill="#ef4444"
                          fontFamily="inherit"
                        >
                          Capacity Ceiling: {chartData.capacity}
                        </text>
                      </g>
                    )}

                    {/* Gradient Area under curve */}
                    <path d={chartData.areaD} fill="url(#crowdGradient)" />

                    {/* Main Trend Line */}
                    <path d={chartData.pathD} fill="none" stroke="#0284c7" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />

                    {/* Data Points */}
                    {chartData.points.map((pt, i) => (
                      <g key={pt.id || i}>
                        <circle
                          cx={pt.x}
                          cy={pt.y}
                          r={hoveredPoint?.id === pt.id ? 7 : 4.5}
                          fill="#0284c7"
                          stroke="#ffffff"
                          strokeWidth="2"
                          style={{ cursor: 'pointer', transition: 'r 0.15s ease' }}
                          onMouseEnter={() => setHoveredPoint(pt)}
                          onMouseLeave={() => setHoveredPoint(null)}
                        />
                        {/* Time labels below axis */}
                        <text
                          x={pt.x}
                          y={chartData.height - 12}
                          textAnchor="middle"
                          fontSize="10"
                          fill="#64748b"
                          fontFamily="inherit"
                        >
                          {pt.timeLabel}
                        </text>
                      </g>
                    ))}
                  </svg>

                  {/* Tooltip on Point Hover */}
                  {hoveredPoint && (
                    <div
                      style={{
                        position: 'absolute',
                        left: `${(hoveredPoint.x / chartData.width) * 100}%`,
                        top: `${(hoveredPoint.y / chartData.height) * 100}%`,
                        transform: 'translate(-50%, -120%)',
                        backgroundColor: '#0f172a',
                        color: '#f8fafc',
                        padding: '0.45rem 0.75rem',
                        borderRadius: 'var(--radius-sm)',
                        fontSize: '0.75rem',
                        boxShadow: 'var(--shadow-md)',
                        pointerEvents: 'none',
                        zIndex: 10,
                        whiteSpace: 'nowrap',
                      }}
                    >
                      <div style={{ fontWeight: '700' }}>{hoveredPoint.count.toLocaleString()} persons</div>
                      <div style={{ color: '#94a3b8' }}>
                        {hoveredPoint.timeLabel} • {hoveredPoint.level}
                        {hoveredPoint.utilization ? ` (${hoveredPoint.utilization}%)` : ''}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* 4E. Chronological Crowd Analysis History Table */}
            {history.length > 0 && (
              <div
                style={{
                  backgroundColor: '#ffffff',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius)',
                  padding: '1.25rem',
                  boxShadow: 'var(--shadow-sm)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.75rem',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <h3 style={{ fontSize: '0.95rem', fontWeight: '700', color: 'var(--text-primary)', margin: 0 }}>
                      Surveillance Headcount Chronological Log
                    </h3>
                    <span style={{ fontSize: '0.78125rem', color: 'var(--text-muted)' }}>
                      Sequential crowd-estimation records produced by the CSRNet neural model
                    </span>
                  </div>
                  <span style={{ fontSize: '0.78125rem', color: 'var(--text-muted)' }}>
                    {history.length} verified observations
                  </span>
                </div>

                <div className="table-responsive-wrapper" style={{ overflowX: 'auto' }}>
                  <table className="institutional-table" aria-label="Chronological Crowd Analysis History">
                    <thead>
                      <tr>
                        <th scope="col" style={{ width: '45px' }}>#</th>
                        <th scope="col">Analysis Timestamp</th>
                        <th scope="col">Image Record</th>
                        <th scope="col">Predicted Headcount</th>
                        <th scope="col">Capacity Utilization</th>
                        <th scope="col">Density Safety Level</th>
                        <th scope="col">Inference Model</th>
                      </tr>
                    </thead>
                    <tbody>
                      {history.map((row, idx) => {
                        const count = row.predicted_count || 0;
                        const util = row.utilization_percent;
                        const level = row.crowd_level || 'Normal';
                        const isPeak = count === summary.max_crowd;

                        return (
                          <tr
                            key={row.analysis_id || idx}
                            style={{
                              backgroundColor: isPeak ? '#f8fafc' : 'transparent',
                            }}
                          >
                            <td style={{ fontWeight: '600', color: 'var(--text-muted)' }}>{idx + 1}</td>
                            <td>
                              <div style={{ fontWeight: '600', color: 'var(--text-primary)' }}>
                                {new Date(row.analysis_timestamp).toLocaleTimeString([], {
                                  hour: '2-digit',
                                  minute: '2-digit',
                                  second: '2-digit',
                                })}
                              </div>
                              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                                {new Date(row.analysis_timestamp).toLocaleDateString([], {
                                  year: 'numeric',
                                  month: 'short',
                                  day: 'numeric',
                                })}
                              </div>
                            </td>
                            <td>
                              <span style={{ fontFamily: 'monospace', fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
                                Image #{row.image_id}
                              </span>
                            </td>
                            <td>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                                <span style={{ fontWeight: '700', fontSize: '0.925rem', color: isPeak ? '#0284c7' : 'inherit' }}>
                                  {count.toLocaleString()}
                                </span>
                                {isPeak && (
                                  <span
                                    style={{
                                      fontSize: '0.6875rem',
                                      padding: '0.15rem 0.4rem',
                                      borderRadius: '4px',
                                      backgroundColor: '#e0f2fe',
                                      color: '#0369a1',
                                      fontWeight: '700',
                                    }}
                                  >
                                    PEAK
                                  </span>
                                )}
                              </div>
                            </td>
                            <td>
                              {util !== null && util !== undefined ? (
                                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                  <div
                                    style={{
                                      width: '60px',
                                      height: '6px',
                                      backgroundColor: '#e2e8f0',
                                      borderRadius: '3px',
                                      overflow: 'hidden',
                                    }}
                                  >
                                    <div
                                      style={{
                                        width: `${Math.min(util, 100)}%`,
                                        height: '100%',
                                        backgroundColor: util > 100 ? '#ef4444' : util > 85 ? '#f59e0b' : '#10b981',
                                      }}
                                    />
                                  </div>
                                  <span style={{ fontSize: '0.8125rem', fontWeight: '600' }}>{util}%</span>
                                </div>
                              ) : (
                                <span style={{ color: 'var(--text-muted)', fontSize: '0.8125rem' }}>N/A</span>
                              )}
                            </td>
                            <td>
                              <span
                                style={{
                                  display: 'inline-block',
                                  padding: '0.2rem 0.55rem',
                                  borderRadius: '9999px',
                                  fontSize: '0.75rem',
                                  fontWeight: '600',
                                  backgroundColor: level.includes('Critical')
                                    ? '#fef2f2'
                                    : level.includes('High')
                                    ? '#fffbeb'
                                    : '#f0fdf4',
                                  color: level.includes('Critical')
                                    ? '#dc2626'
                                    : level.includes('High')
                                    ? '#b45309'
                                    : '#15803d',
                                  border: `1px solid ${
                                    level.includes('Critical')
                                      ? '#fecaca'
                                      : level.includes('High')
                                      ? '#fde68a'
                                      : '#bbf7d0'
                                  }`,
                                }}
                              >
                                {level}
                              </span>
                            </td>
                            <td>
                              <span
                                style={{
                                  fontSize: '0.75rem',
                                  fontWeight: '600',
                                  color: '#475569',
                                  backgroundColor: '#f1f5f9',
                                  padding: '0.2rem 0.5rem',
                                  borderRadius: '4px',
                                }}
                              >
                                {row.model_name || 'CSRNet'}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* 4F. Safety Alerts & Compliance Log */}
            <div
              style={{
                backgroundColor: '#ffffff',
                border: '1px solid var(--border-color)',
                borderRadius: 'var(--radius)',
                padding: '1.25rem',
                boxShadow: 'var(--shadow-sm)',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.75rem',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <h3 style={{ fontSize: '0.95rem', fontWeight: '700', color: 'var(--text-primary)', margin: 0 }}>
                    Crowd Safety Threshold Alerts
                  </h3>
                  <span style={{ fontSize: '0.78125rem', color: 'var(--text-muted)' }}>
                    Automated capacity breach notifications dispatched during event surveillance
                  </span>
                </div>
                <span style={{ fontSize: '0.78125rem', color: 'var(--text-muted)' }}>
                  {alerts.length} alerts logged
                </span>
              </div>

              {alerts.length === 0 ? (
                <div
                  style={{
                    backgroundColor: '#f8fafc',
                    border: '1px solid #e2e8f0',
                    borderRadius: 'var(--radius)',
                    padding: '1.25rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.75rem',
                    color: 'var(--text-secondary)',
                  }}
                >
                  <div
                    style={{
                      width: '32px',
                      height: '32px',
                      borderRadius: '50%',
                      backgroundColor: '#dcfce7',
                      color: '#15803d',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                    }}
                  >
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  </div>
                  <div>
                    <div style={{ fontWeight: '600', fontSize: '0.875rem' }}>No Active Safety Alerts Recorded</div>
                    <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
                      Venue occupancy remained within regulatory limits or no automated breach warnings were triggered.
                    </div>
                  </div>
                </div>
              ) : (
                <div className="table-responsive-wrapper" style={{ overflowX: 'auto' }}>
                  <table className="institutional-table" aria-label="Crowd Threshold Alerts Log">
                    <thead>
                      <tr>
                        <th scope="col" style={{ width: '45px' }}>#</th>
                        <th scope="col">Alert Timestamp</th>
                        <th scope="col">Detected Count</th>
                        <th scope="col">Threshold Ceiling</th>
                        <th scope="col">Recipient</th>
                        <th scope="col">Status</th>
                        <th scope="col">Notice Message</th>
                      </tr>
                    </thead>
                    <tbody>
                      {alerts.map((alt, aIdx) => (
                        <tr key={alt.id || aIdx}>
                          <td>{aIdx + 1}</td>
                          <td>
                            {new Date(alt.created_at).toLocaleString([], {
                              month: 'short',
                              day: 'numeric',
                              hour: '2-digit',
                              minute: '2-digit',
                            })}
                          </td>
                          <td style={{ fontWeight: '700', color: '#dc2626' }}>
                            {alt.detected_count?.toLocaleString()}
                          </td>
                          <td style={{ color: 'var(--text-muted)' }}>
                            {alt.threshold?.toLocaleString()}
                          </td>
                          <td>
                            {alt.recipient_name} ({alt.recipient_role})
                          </td>
                          <td>
                            <span
                              style={{
                                textTransform: 'uppercase',
                                fontSize: '0.6875rem',
                                fontWeight: '700',
                                padding: '0.2rem 0.5rem',
                                borderRadius: '4px',
                                backgroundColor: alt.status === 'read' ? '#f1f5f9' : '#fef2f2',
                                color: alt.status === 'read' ? '#475569' : '#dc2626',
                              }}
                            >
                              {alt.status}
                            </span>
                          </td>
                          <td>{alt.message}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
