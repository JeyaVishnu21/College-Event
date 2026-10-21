import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  getOrganizerDashboard,
  createEvent,
  getVenues,
  getEventSeries,
  getEventImages,
  uploadEventImage,
  analyzeImage,
  getBackendAssetUrl,
  getUnreadAlertsCount,
} from '../services/api';

import Loading from '../components/Loading';
import StatCard from '../components/StatCard';
import EventTable from '../components/EventTable';
import StatusBadge from '../components/StatusBadge';
import CrowdReportsView from '../components/CrowdReportsView';
import CrowdAlertsView from '../components/CrowdAlertsView';
import { getEventHappeningInfo, isEventHappening, syncServerTime } from '../utils/eventStatus';

export default function OrganizerDashboard() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  // Active Tab: synced with URL and left flyout navigation drawer (resolves 'schedule' into 'my-events')
  const currentTabFromUrl = searchParams.get('tab') || 'dashboard';
  const resolvedTab = currentTabFromUrl === 'schedule' ? 'my-events' : currentTabFromUrl;
  const [activeTab, setActiveTab] = useState(resolvedTab);
  const [eventViewMode, setEventViewMode] = useState(currentTabFromUrl === 'schedule' ? 'schedule' : 'catalog');
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [unreadAlertsCount, setUnreadAlertsCount] = useState(0);

  // Initial fetch for unread alerts count
  useEffect(() => {
    getUnreadAlertsCount().then((res) => {
      if (res.ok && typeof res.data?.unread_count === 'number') {
        setUnreadAlertsCount(res.data.unread_count);
      }
    }).catch(() => {});
  }, []);

  // Sync tab with URL search parameter
  useEffect(() => {
    const tabFromUrl = searchParams.get('tab');
    if (tabFromUrl) {
      if (tabFromUrl === 'schedule') {
        setActiveTab('my-events');
        setEventViewMode('schedule');
      } else if (tabFromUrl !== activeTab) {
        setActiveTab(tabFromUrl);
      }
    }
  }, [searchParams]);

  // Sync tab with left flyout sidebar selection
  useEffect(() => {
    const handlePortalTabSelect = (e) => {
      if (e.detail?.tab) {
        if (e.detail.tab === 'schedule') {
          setActiveTab('my-events');
          setEventViewMode('schedule');
        } else {
          setActiveTab(e.detail.tab);
        }
      }
    };
    window.addEventListener('portal-tab-select', handlePortalTabSelect);
    return () => window.removeEventListener('portal-tab-select', handlePortalTabSelect);
  }, []);

  // Real backend data states
  const [dashboardData, setDashboardData] = useState(null);
  const [venues, setVenues] = useState([]);
  const [eventSeries, setEventSeries] = useState([]);
  const [statusFilter, setStatusFilter] = useState('all');

  // Loading & Error states
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState('');
  const [actionSuccess, setActionSuccess] = useState('');

  // Create Event Form state
  const [formSubmitting, setFormSubmitting] = useState(false);
  const [formError, setFormError] = useState('');
  const [formData, setFormData] = useState({
    event_name: '',
    description: '',
    requested_date: '',
    requested_start_time: '09:00',
    requested_end_time: '17:00',
    category: 'General',
    venue_id: '',
    series_id: '',
  });

  // Photo Upload Modal / State
  const [selectedUploadEvent, setSelectedUploadEvent] = useState(null);
  const [uploadFile, setUploadFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const [eventPhotos, setEventPhotos] = useState([]);
  const [loadingPhotos, setLoadingPhotos] = useState(false);

  // Crowd Analysis States
  const [analyzingImageIds, setAnalyzingImageIds] = useState({});
  const [analysisErrors, setAnalysisErrors] = useState({});
  const [historyPhotos, setHistoryPhotos] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [historyError, setHistoryError] = useState('');
  const [historyFetched, setHistoryFetched] = useState(false);

  // References for request coordination and safe unmount
  const historyReqIdRef = useRef(0);
  const dashboardDataRef = useRef(dashboardData);
  dashboardDataRef.current = dashboardData;

  // Cleanup on unmount to cancel any pending async history operations
  useEffect(() => {
    return () => {
      historyReqIdRef.current++;
    };
  }, []);


  // Fetch all organizer dashboard data from real backend
  const loadDashboard = useCallback(async () => {
    setLoading(true);
    setErrorMessage('');
    try {
      const [dashRes, venueRes, seriesRes] = await Promise.all([
        getOrganizerDashboard(),
        getVenues(),
        getEventSeries(),
      ]);

      if (dashRes.ok && dashRes.data) {
        if (dashRes.data.server_now) {
          syncServerTime(dashRes.data.server_now, dashRes.data.timezone_offset);
        }
        setDashboardData(dashRes.data);
      } else {
        setErrorMessage(dashRes.error || 'Failed to load organizer dashboard data.');
      }

      if (venueRes.ok && venueRes.data?.venues) {
        setVenues(venueRes.data.venues);
      }

      if (seriesRes.ok && seriesRes.data?.series) {
        setEventSeries(seriesRes.data.series);
      }
    } catch {
      setErrorMessage('Unable to connect to server. Please verify backend is running.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  // Handle Logout
  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  // Switch tabs & close mobile drawer
  const handleTabChange = (tabId, viewMode = null) => {
    const target = tabId === 'schedule' ? 'my-events' : tabId;
    setActiveTab(target);
    if (tabId === 'schedule' || viewMode === 'schedule') {
      setEventViewMode('schedule');
    } else if (viewMode === 'catalog') {
      setEventViewMode('catalog');
    }
    setSearchParams({ tab: target });
    setMobileSidebarOpen(false);
    setFormError('');
    setActionSuccess('');
  };

  // Form field changes
  const handleFormChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  // Handle Event Creation submission to real Flask endpoint
  const handleCreateSubmit = async (e) => {
    e.preventDefault();
    setFormError('');
    setActionSuccess('');

    if (!formData.event_name.trim()) {
      setFormError('Event title is required.');
      return;
    }

    if (!formData.requested_date) {
      setFormError('Preferred date is required.');
      return;
    }

    if (!formData.series_id) {
      setFormError('Please select an active Fest.');
      return;
    }

    if (formData.requested_start_time >= formData.requested_end_time) {
      setFormError('Event start time must precede end time.');
      return;
    }

    setFormSubmitting(true);

    try {
      const payload = {
        event_name: formData.event_name.trim(),
        description: formData.description.trim(),
        requested_date: formData.requested_date,
        requested_start_time: formData.requested_start_time.length === 5 ? `${formData.requested_start_time}:00` : formData.requested_start_time,
        requested_end_time: formData.requested_end_time.length === 5 ? `${formData.requested_end_time}:00` : formData.requested_end_time,
        category: formData.category,
        venue_id: formData.venue_id ? parseInt(formData.venue_id, 10) : null,
        series_id: parseInt(formData.series_id, 10),
      };

      const res = await createEvent(payload);

      if (res.ok) {
        setActionSuccess(`Event proposal "${formData.event_name}" submitted successfully for administrator review.`);
        setFormData({
          event_name: '',
          description: '',
          requested_date: '',
          requested_start_time: '09:00',
          requested_end_time: '17:00',
          category: 'General',
          venue_id: '',
          series_id: '',
        });
        // Refresh dashboard data
        await loadDashboard();
        // Switch to My Events tab
        setActiveTab('my-events');
      } else {
        setFormError(res.error || 'Failed to submit event proposal.');
      }
    } catch {
      setFormError('Server error while submitting proposal.');
    } finally {
      setFormSubmitting(false);
    }
  };

  // Open photo upload modal for an approved event
  const handleOpenUpload = async (event) => {
    setSelectedUploadEvent(event);
    setUploadFile(null);
    setUploadError('');
    setLoadingPhotos(true);

    try {
      const res = await getEventImages(event.id);
      if (res.ok && res.data?.images) {
        setEventPhotos(res.data.images);
      } else {
        setEventPhotos([]);
      }
    } catch {
      setEventPhotos([]);
    } finally {
      setLoadingPhotos(false);
    }
  };

  // Handle Photo Upload submission
  const handleUploadSubmit = async (e) => {
    e.preventDefault();
    if (!selectedUploadEvent) return;

    // Block photo upload when the event is not actively happening
    const timing = getEventHappeningInfo(selectedUploadEvent);
    if (!timing.isHappening) {
      setUploadError(`Photo upload is blocked: ${timing.reason}`);
      return;
    }

    if (!uploadFile) {
      setUploadError('Please select a photograph (.jpg, .jpeg, .png).');
      return;
    }

    setUploading(true);
    setUploadError('');

    try {
      const res = await uploadEventImage(selectedUploadEvent.id, uploadFile);
      if (res.ok) {
        const newImgId = res.data?.image?.id;
        if (newImgId) {
          try {
            await analyzeImage(newImgId);
          } catch {
            // Handled gracefully; photoRes will reflect latest status
          }
        }
        setActionSuccess('Event photograph uploaded and analyzed successfully.');
        setUploadFile(null);
        // Refresh photos for this event
        const photoRes = await getEventImages(selectedUploadEvent.id);
        if (photoRes.ok && photoRes.data?.images) {
          setEventPhotos(photoRes.data.images);
        }
      } else {
        setUploadError(res.error || 'Failed to upload photograph.');
      }
    } catch {
      setUploadError('Network error while uploading photograph.');
    } finally {
      setUploading(false);
    }
  };

  // Events list derived from real backend data (memoized to avoid unneeded re-evaluations)
  const allEvents = useMemo(() => dashboardData?.events || [], [dashboardData?.events]);
  const upcomingEvents = useMemo(() => dashboardData?.upcoming_events || [], [dashboardData?.upcoming_events]);
  const stats = useMemo(() => dashboardData?.stats || {
    total_events: 0,
    pending_events: 0,
    approved_events: 0,
    rejected_events: 0,
    upcoming_events: 0,
  }, [dashboardData?.stats]);

  // Filtered events for "My Events" tab
  const filteredEvents = useMemo(() => {
    return allEvents.filter((ev) => {
      if (statusFilter === 'all') return true;
      return (ev.status || '').toLowerCase() === statusFilter.toLowerCase();
    });
  }, [allEvents, statusFilter]);

  // Approved events for schedule and crowd monitoring tabs
  const approvedEvents = useMemo(() => {
    return allEvents.filter((ev) => (ev.status || '').toLowerCase() === 'approved');
  }, [allEvents]);

  // Events that can have surveillance photographs (approved or completed)
  const analysisEvents = useMemo(() => {
    return allEvents.filter((ev) => {
      const st = (ev.status || '').toLowerCase();
      return st === 'approved' || st === 'completed';
    });
  }, [allEvents]);

  // Stable string signature of event IDs so effect dependencies only change when events genuinely change
  const analysisEventsKey = useMemo(() => {
    return analysisEvents.map((ev) => `${ev.id}:${ev.status}`).join('|');
  }, [analysisEvents]);

  const analysisEventsRef = useRef(analysisEvents);
  analysisEventsRef.current = analysisEvents;
  const historyPhotosRef = useRef(historyPhotos);
  historyPhotosRef.current = historyPhotos;

  // Trigger CSRNet crowd density estimation on an uploaded photo
  const handleAnalyzePhoto = async (photo) => {
    const imageId = photo.id;
    if (!imageId || analyzingImageIds[imageId]) return;

    setAnalyzingImageIds((prev) => ({ ...prev, [imageId]: true }));
    setAnalysisErrors((prev) => ({ ...prev, [imageId]: '' }));

    try {
      const res = await analyzeImage(imageId);
      if (res.ok && res.data?.analysis) {
        const count = res.data.analysis.predicted_count;
        setActionSuccess(`Crowd analysis complete: Estimated ${count} people.`);
        // Update local photo state immediately for reactive UI
        setEventPhotos((prev) =>
          prev.map((p) =>
            p.id === imageId
              ? {
                  ...p,
                  predicted_count: count,
                  processing_status: 'completed',
                  analysis_timestamp: res.data.analysis.analysis_timestamp,
                }
              : p
          )
        );
      } else {
        setAnalysisErrors((prev) => ({
          ...prev,
          [imageId]: res.error || 'Failed to complete crowd analysis.',
        }));
      }
    } catch {
      setAnalysisErrors((prev) => ({
        ...prev,
        [imageId]: 'Network error while requesting analysis.',
      }));
    } finally {
      setAnalyzingImageIds((prev) => ({ ...prev, [imageId]: false }));
    }
  };

  // Load historical analyzed images across organizer's approved/completed events
  const loadAnalysisHistory = useCallback(async (isManualRetry = false) => {
    const eventsToFetch = analysisEventsRef.current;

    // If dashboard is still loading or organizer has no eligible events
    if (!eventsToFetch.length) {
      if (!dashboardDataRef.current) {
        // Dashboard data hasn't loaded yet; wait for dashboard data
        return;
      }
      setHistoryPhotos([]);
      setLoadingHistory(false);
      setHistoryError('');
      setHistoryFetched(true);
      return;
    }

    const reqId = ++historyReqIdRef.current;

    // Only show full loading spinner if we don't have photos yet or if it's a manual retry
    if (historyPhotosRef.current.length === 0 || isManualRetry) {
      setLoadingHistory(true);
    }
    setHistoryError('');

    try {
      let anySuccess = false;
      let firstErrorMessage = '';

      const results = await Promise.all(
        eventsToFetch.map(async (ev) => {
          try {
            const res = await getEventImages(ev.id);
            if (res.ok && res.data?.images) {
              anySuccess = true;
              return res.data.images.map((img) => ({
                ...img,
                event_name: ev.event_name,
                venue_name: ev.venue_name,
              }));
            }
            if (!res.ok) {
              if (!firstErrorMessage) {
                firstErrorMessage = res.error || `Failed to fetch images for event #${ev.id}`;
              }
            }
            return [];
          } catch (fetchErr) {
            if (!firstErrorMessage) {
              firstErrorMessage = fetchErr.message || 'Network request failed';
            }
            return [];
          }
        })
      );

      // If a newer request was dispatched or component unmounted, drop this result
      if (reqId !== historyReqIdRef.current) {
        return;
      }

      // If all event requests failed and none succeeded, report error
      if (!anySuccess && firstErrorMessage && eventsToFetch.length > 0) {
        setHistoryError(firstErrorMessage || 'Unable to load surveillance analysis history. Please check your connection and retry.');
        return;
      }

      const allImgs = results.flat();
      // Filter for analyzed photos (predicted_count is present)
      const analyzed = allImgs.filter(
        (img) => img.predicted_count !== null && img.predicted_count !== undefined
      );

      // Sort by newest analysis / upload first
      analyzed.sort((a, b) => {
        const timeA = new Date(a.analysis_timestamp || a.uploaded_at || 0).getTime();
        const timeB = new Date(b.analysis_timestamp || b.uploaded_at || 0).getTime();
        return timeB - timeA;
      });

      setHistoryPhotos(analyzed);
      setHistoryError('');
    } catch (err) {
      if (reqId !== historyReqIdRef.current) return;
      setHistoryError(err.message || 'An error occurred while loading crowd surveillance history.');
    } finally {
      if (reqId === historyReqIdRef.current) {
        setLoadingHistory(false);
        setHistoryFetched(true);
      }
    }
  }, []);

  useEffect(() => {
    if (activeTab === 'analysis-history') {
      loadAnalysisHistory();
    }
  }, [activeTab, analysisEventsKey, loadAnalysisHistory]);


  // Page titles by tab
  const tabTitles = {
    dashboard: {
      title: 'Organizer Dashboard',
      subtitle: 'Real-time overview of your submitted events, review statuses, and confirmed venue allocations.',
    },
    create: {
      title: 'Submit Event Proposal',
      subtitle: 'Create a new event request with scheduling and venue preferences for administrative review.',
    },
    'my-events': {
      title: 'My Events & Schedule',
      subtitle: 'Complete catalog of your event proposals, approval tracking, and chronological campus venue schedule.',
    },
    'venue-requests': {
      title: 'Venue Requests & Decisions',
      subtitle: 'Track venue allocation decisions, administrative approvals, and rejection feedback.',
    },
    schedule: {
      title: 'My Events & Schedule',
      subtitle: 'Chronological agenda of approved university events scheduled across campus venues.',
    },
    'crowd-monitoring': {
      title: 'Crowd Monitoring Console',
      subtitle: 'Upload event surveillance photographs and inspect computer vision crowd analysis logs.',
    },
    'crowd-alerts': {
      title: 'Crowd Safety Alerts',
      subtitle: 'Real-time safety threshold notifications and venue capacity monitoring alerts.',
    },
    'analysis-history': {
      title: 'Crowd Analysis History',
      subtitle: 'Historical crowd headcount estimates and photographic analysis records for your events.',
    },
    'crowd-reports': {
      title: 'Crowd Occupancy & Peak Reports',
      subtitle: 'Formal event attendance summaries, peak headcount metrics, and downloadable audit reports.',
    },
  };

  const currentTabInfo = tabTitles[activeTab] || tabTitles.dashboard;

  if (loading && !dashboardData) {
    return <Loading fullScreen message="Loading organizer workspace from database..." />;
  }

  return (
    <div className="organizer-portal-layout">
      {/* Mobile Drawer Backdrop */}
      {mobileSidebarOpen && (
        <div
          className="portal-mobile-backdrop"
          onClick={() => setMobileSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Persistent Left Sidebar */}
      <aside className={`portal-sidebar ${mobileSidebarOpen ? 'portal-sidebar-open' : ''}`}>
        <div className="portal-sidebar-header">
          <div className="portal-sidebar-brand">
            <div className="portal-brand-emblem" aria-hidden="true">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 20V10" />
                <path d="M12 20V4" />
                <path d="M6 20v-6" />
              </svg>
            </div>
            <div className="portal-brand-text">
              <span className="portal-brand-name">Organizer Portal</span>
              <span className="portal-brand-dept">Campus Event Operations</span>
            </div>
          </div>
          <button
            type="button"
            className="portal-sidebar-close"
            onClick={() => setMobileSidebarOpen(false)}
            aria-label="Close menu"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* 8 Sidebar Navigation Items */}
        <nav className="portal-sidebar-nav" aria-label="Organizer Navigation">
          <span className="portal-nav-heading">Workspace</span>

          {/* 1. Dashboard */}
          <button
            type="button"
            className={`portal-nav-btn ${activeTab === 'dashboard' ? 'active' : ''}`}
            onClick={() => handleTabChange('dashboard')}
          >
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="3" width="7" height="7" />
              <rect x="14" y="3" width="7" height="7" />
              <rect x="14" y="14" width="7" height="7" />
              <rect x="3" y="14" width="7" height="7" />
            </svg>
            <span>Dashboard</span>
          </button>

          {/* 2. Create Event */}
          <button
            type="button"
            className={`portal-nav-btn ${activeTab === 'create' ? 'active' : ''}`}
            onClick={() => handleTabChange('create')}
          >
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            <span>Create Event</span>
          </button>

          {/* 3. My Events & Schedule */}
          <button
            type="button"
            className={`portal-nav-btn ${activeTab === 'my-events' ? 'active' : ''}`}
            onClick={() => handleTabChange('my-events')}
          >
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
              <polyline points="10 9 9 9 8 9" />
            </svg>
            <span>My Events &amp; Schedule</span>
            {stats.total_events > 0 && (
              <span className="portal-nav-count">{stats.total_events}</span>
            )}
          </button>

          {/* 4. Venue Requests */}
          <button
            type="button"
            className={`portal-nav-btn ${activeTab === 'venue-requests' ? 'active' : ''}`}
            onClick={() => handleTabChange('venue-requests')}
          >
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 21h18" />
              <path d="M5 21V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16" />
              <path d="M9 9h1" />
              <path d="M9 13h1" />
              <path d="M14 9h1" />
              <path d="M14 13h1" />
            </svg>
            <span>Venue Requests</span>
            {stats.pending_events > 0 && (
              <span className="portal-nav-count portal-count-warning">{stats.pending_events}</span>
            )}
          </button>

          <span className="portal-nav-heading" style={{ marginTop: '1.25rem' }}>
            Safety &amp; Monitoring
          </span>

          {/* 6. Crowd Monitoring */}
          <button
            type="button"
            className={`portal-nav-btn ${activeTab === 'crowd-monitoring' ? 'active' : ''}`}
            onClick={() => handleTabChange('crowd-monitoring')}
          >
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
              <circle cx="9" cy="7" r="4" />
              <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
              <path d="M16 3.13a4 4 0 0 1 0 7.75" />
            </svg>
            <span>Crowd Monitoring</span>
          </button>

          {/* 7. Crowd Alerts */}
          <button
            type="button"
            className={`portal-nav-btn ${activeTab === 'crowd-alerts' ? 'active' : ''}`}
            onClick={() => handleTabChange('crowd-alerts')}
          >
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
              <line x1="12" y1="9" x2="12" y2="13" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
            <span>Crowd Alerts</span>
            {unreadAlertsCount > 0 && (
              <span className="badge badge-danger" style={{ marginLeft: '0.4rem', fontSize: '0.7rem', padding: '0.1rem 0.45rem', borderRadius: '9999px' }}>
                {unreadAlertsCount}
              </span>
            )}
          </button>

          {/* 8. Analysis History */}
          <button
            type="button"
            className={`portal-nav-btn ${activeTab === 'analysis-history' ? 'active' : ''}`}
            onClick={() => handleTabChange('analysis-history')}
          >
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
            <span>Analysis History</span>
          </button>

          {/* 9. Crowd Reports */}
          <button
            type="button"
            className={`portal-nav-btn ${activeTab === 'crowd-reports' ? 'active' : ''}`}
            onClick={() => handleTabChange('crowd-reports')}
          >
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="20" x2="18" y2="10" />
              <line x1="12" y1="20" x2="12" y2="4" />
              <line x1="6" y1="20" x2="6" y2="14" />
            </svg>
            <span>Crowd Reports</span>
          </button>
        </nav>

        {/* Sidebar Footer with Organizer Profile & Sign Out */}
        <div className="portal-sidebar-footer">
          <div className="portal-user-summary">
            <span className="portal-user-name">{user?.name || 'Organizer'}</span>
            <span className="portal-user-role">Verified Organizer</span>
            <span className="portal-user-email">{user?.email}</span>
          </div>
          <button
            type="button"
            className="portal-signout-btn"
            onClick={handleLogout}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <polyline points="16 17 21 12 16 7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </svg>
            <span>Sign Out</span>
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="portal-main-area">
        {/* Mobile Topbar with drawer toggle */}
        <div className="portal-mobile-bar">
          <button
            type="button"
            className="portal-mobile-btn"
            onClick={() => setMobileSidebarOpen(true)}
            aria-label="Open sidebar menu"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="3" y1="12" x2="21" y2="12" />
              <line x1="3" y1="6" x2="21" y2="6" />
              <line x1="3" y1="18" x2="21" y2="18" />
            </svg>
          </button>
          <span className="portal-mobile-title">{currentTabInfo.title}</span>
        </div>

        {/* Top Header */}
        <header className="portal-top-header">
          <div className="portal-header-left">
            <h1 className="portal-header-title">{currentTabInfo.title}</h1>
            <p className="portal-header-desc">{currentTabInfo.subtitle}</p>
          </div>

          <div className="portal-header-right">
            {/* Real Notification / Safety Indicator */}
            <div className="portal-safety-indicator" title="Crowd threshold monitoring active across venues">
              <span className="safety-dot" aria-hidden="true" />
              <span className="safety-text">Monitoring Active</span>
            </div>

            {/* Quick Action Buttons */}
            <div className="portal-header-actions">
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={loadDashboard}
                disabled={loading}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67" />
                </svg>
                <span>Refresh</span>
              </button>

              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={() => handleTabChange('create')}
              >
                + Create Event
              </button>
            </div>
          </div>
        </header>

        {/* Status Feedback Banners */}
        {actionSuccess && (
          <div className="portal-alert portal-alert-success" role="status">
            <span>{actionSuccess}</span>
            <button
              type="button"
              className="portal-alert-close"
              onClick={() => setActionSuccess('')}
              aria-label="Dismiss message"
            >
              &times;
            </button>
          </div>
        )}

        {errorMessage && (
          <div className="portal-alert portal-alert-error" role="alert">
            <span>{errorMessage}</span>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={loadDashboard}
              style={{ marginLeft: 'auto' }}
            >
              Retry
            </button>
          </div>
        )}

        {/* Tab Content Panes */}
        <div className="portal-tab-content">
          {/* ============================================================ */}
          {/* TAB 1: DASHBOARD OVERVIEW */}
          {/* ============================================================ */}
          {activeTab === 'dashboard' && (
            <div className="tab-pane">
              {/* Summary Section: Real Database Metrics */}
              <div className="stats-grid">
                <StatCard
                  title="Total Events"
                  value={stats.total_events}
                  subtitle="Lifetime proposals submitted"
                  variant="default"
                  onClick={() => {
                    setStatusFilter('all');
                    handleTabChange('my-events');
                  }}
                  icon={
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                      <line x1="16" y1="2" x2="16" y2="6" />
                      <line x1="8" y1="2" x2="8" y2="6" />
                      <line x1="3" y1="10" x2="21" y2="10" />
                    </svg>
                  }
                />

                <StatCard
                  title="Pending Events"
                  value={stats.pending_events}
                  subtitle="Awaiting administrator review"
                  variant="warning"
                  onClick={() => {
                    setStatusFilter('pending');
                    handleTabChange('my-events');
                  }}
                  icon={
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <circle cx="12" cy="12" r="10" />
                      <polyline points="12 6 12 12 16 14" />
                    </svg>
                  }
                />

                <StatCard
                  title="Approved Events"
                  value={stats.approved_events}
                  subtitle="Venues allocated &amp; confirmed"
                  variant="success"
                  onClick={() => {
                    setStatusFilter('approved');
                    handleTabChange('my-events');
                  }}
                  icon={
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                      <polyline points="22 4 12 14.01 9 11.01" />
                    </svg>
                  }
                />

                <StatCard
                  title="Rejected Requests"
                  value={stats.rejected_events}
                  subtitle="Proposals declined"
                  variant="danger"
                  onClick={() => {
                    setStatusFilter('rejected');
                    handleTabChange('my-events');
                  }}
                  icon={
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <circle cx="12" cy="12" r="10" />
                      <line x1="15" y1="9" x2="9" y2="15" />
                      <line x1="9" y1="9" x2="15" y2="15" />
                    </svg>
                  }
                />

                <StatCard
                  title="Upcoming Scheduled"
                  value={stats.upcoming_events}
                  subtitle="Confirmed for future dates"
                  variant="primary"
                  onClick={() => handleTabChange('schedule')}
                  icon={
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
                    </svg>
                  }
                />
              </div>

              {/* Upcoming Events Section: Real Data */}
              <section className="portal-section-card">
                <div className="section-card-header">
                  <div className="header-title-stack">
                    <h2 className="section-card-title">Upcoming Approved Events</h2>
                    <span className="section-card-subtitle">
                      Your approved events scheduled on the campus calendar
                    </span>
                  </div>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => handleTabChange('schedule')}
                  >
                    View Schedule &rarr;
                  </button>
                </div>

                {upcomingEvents.length === 0 ? (
                  <div className="section-empty-block">
                    <p>No upcoming approved events scheduled right now.</p>
                  </div>
                ) : (
                  <div className="upcoming-events-grid">
                    {upcomingEvents.map((ev) => {
                      const timingInfo = getEventHappeningInfo(ev);
                      const isHappening = timingInfo.isHappening;
                      return (
                        <div key={ev.id} className="upcoming-event-item">
                          <div className="upcoming-item-header">
                            <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                              <StatusBadge status="approved" />
                              {isHappening ? (
                                <span className="monitoring-live-badge">● Live</span>
                              ) : null}
                            </div>
                            <span className="upcoming-item-date">{ev.approved_date || ev.requested_date}</span>
                          </div>
                          <h3 className="upcoming-item-title">{ev.event_name}</h3>
                          <div className="upcoming-item-meta">
                            <span>Venue: {ev.venue_name || 'Main Campus'}</span>
                            <span>Time: {ev.approved_start_time || ev.requested_start_time} - {ev.approved_end_time || ev.requested_end_time}</span>
                          </div>
                          <div className="upcoming-item-actions">
                            {isHappening ? (
                              <button
                                type="button"
                                className="btn btn-primary btn-sm btn-upload-live"
                                onClick={() => handleOpenUpload(ev)}
                                title="Upload crowd monitoring photograph"
                              >
                                Upload Photo
                              </button>
                            ) : (
                              <button
                                type="button"
                                className="btn btn-secondary btn-sm btn-upload-blocked"
                                disabled
                                aria-disabled="true"
                                title={`Photo upload blocked: ${timingInfo.reason}`}
                              >
                                Upload Blocked
                              </button>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </section>

              {/* Recent Events Table Preview */}
              <section className="portal-section-card">
                <div className="section-card-header">
                  <div className="header-title-stack">
                    <h2 className="section-card-title">Recent Event Proposals</h2>
                    <span className="section-card-subtitle">
                      Latest submissions and review status
                    </span>
                  </div>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => handleTabChange('my-events')}
                  >
                    View All ({allEvents.length}) &rarr;
                  </button>
                </div>

                <EventTable
                  events={allEvents.slice(0, 5)}
                  onCreateEvent={() => handleTabChange('create')}
                  onUploadImage={handleOpenUpload}
                  emptyMessage="Submit your first proposal to initiate the campus venue allocation workflow."
                />
              </section>
            </div>
          )}

          {/* ============================================================ */}
          {/* TAB 2: CREATE EVENT PROPOSAL FORM */}
          {/* ============================================================ */}
          {activeTab === 'create' && (
            <div className="tab-pane">
              <div className="form-card-container">
                <div className="form-card">
                  <div className="form-card-header">
                    <h2 className="form-card-title">New Event Proposal</h2>
                    <p className="form-card-desc">
                      Fill out event details and select a preferred campus venue. College administration will inspect
                      schedules for conflicts and assign confirmed time slots.
                    </p>
                  </div>

                  {formError && (
                    <div className="portal-alert portal-alert-error" role="alert">
                      <span>{formError}</span>
                    </div>
                  )}

                  <form onSubmit={handleCreateSubmit} className="portal-form" noValidate>
                    {/* Fest Selection (Strictly required by backend) */}
                    <div className="form-group">
                      <label htmlFor="form-series" className="form-label">
                        Fest *
                      </label>
                      <select
                        id="form-series"
                        name="series_id"
                        className="form-select"
                        value={formData.series_id}
                        onChange={handleFormChange}
                        required
                        disabled={formSubmitting}
                      >
                        <option value="">-- Select an active Fest * --</option>
                        {eventSeries.map((s) => (
                          <option key={s.id} value={s.id}>
                            {s.name} ({s.start_date} to {s.end_date})
                          </option>
                        ))}
                      </select>
                      <span className="form-hint">
                        All events must be associated with a registered campus program or fest.
                      </span>
                    </div>

                    {/* Event Title */}
                    <div className="form-group">
                      <label htmlFor="form-name" className="form-label">
                        Event Title *
                      </label>
                      <input
                        id="form-name"
                        type="text"
                        name="event_name"
                        className="form-input"
                        placeholder="e.g. Annual Technical Hackathon 2026"
                        value={formData.event_name}
                        onChange={handleFormChange}
                        required
                        maxLength={150}
                        disabled={formSubmitting}
                      />
                    </div>

                    {/* Category & Preferred Venue */}
                    <div className="form-row-2col">
                      <div className="form-group">
                        <label htmlFor="form-category" className="form-label">
                          Category
                        </label>
                        <select
                          id="form-category"
                          name="category"
                          className="form-select"
                          value={formData.category}
                          onChange={handleFormChange}
                          disabled={formSubmitting}
                        >
                          <option value="General">General</option>
                          <option value="Technical">Technical</option>
                          <option value="Cultural">Cultural</option>
                          <option value="Sports">Sports</option>
                          <option value="Workshops">Workshops</option>
                          <option value="Competitions">Competitions</option>
                        </select>
                      </div>

                      <div className="form-group">
                        <label htmlFor="form-venue" className="form-label">
                          Preferred Campus Venue
                        </label>
                        <select
                          id="form-venue"
                          name="venue_id"
                          className="form-select"
                          value={formData.venue_id}
                          onChange={handleFormChange}
                          disabled={formSubmitting}
                        >
                          <option value="">-- No preference (Administrator will allocate) --</option>
                          {venues.map((v) => (
                            <option key={v.id} value={v.id}>
                              {v.name} (Cap: {v.capacity} - {v.location})
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>

                    {/* Description */}
                    <div className="form-group">
                      <label htmlFor="form-desc" className="form-label">
                        Description &amp; Expected Attendance
                      </label>
                      <textarea
                        id="form-desc"
                        name="description"
                        rows={4}
                        className="form-input form-textarea"
                        placeholder="Detail the planned agenda, target audience, setup requirements, and estimated turnout."
                        value={formData.description}
                        onChange={handleFormChange}
                        disabled={formSubmitting}
                      />
                    </div>

                    {/* Date and Times */}
                    <div className="form-row-3col">
                      <div className="form-group">
                        <label htmlFor="form-date" className="form-label">
                          Preferred Date *
                        </label>
                        <input
                          id="form-date"
                          type="date"
                          name="requested_date"
                          className="form-input"
                          value={formData.requested_date}
                          onChange={handleFormChange}
                          required
                          disabled={formSubmitting}
                        />
                      </div>

                      <div className="form-group">
                        <label htmlFor="form-start" className="form-label">
                          Start Time *
                        </label>
                        <input
                          id="form-start"
                          type="time"
                          name="requested_start_time"
                          className="form-input"
                          value={formData.requested_start_time}
                          onChange={handleFormChange}
                          required
                          disabled={formSubmitting}
                        />
                      </div>

                      <div className="form-group">
                        <label htmlFor="form-end" className="form-label">
                          End Time *
                        </label>
                        <input
                          id="form-end"
                          type="time"
                          name="requested_end_time"
                          className="form-input"
                          value={formData.requested_end_time}
                          onChange={handleFormChange}
                          required
                          disabled={formSubmitting}
                        />
                      </div>
                    </div>

                    {/* Submit Button */}
                    <div className="form-action-footer">
                      <button
                        type="button"
                        className="btn btn-secondary"
                        onClick={() => handleTabChange('dashboard')}
                        disabled={formSubmitting}
                      >
                        Cancel
                      </button>

                      <button
                        type="submit"
                        className="btn btn-primary"
                        disabled={formSubmitting}
                      >
                        {formSubmitting ? (
                          <>
                            <span className="spinner-sm" aria-hidden="true" />
                            <span>Submitting Proposal...</span>
                          </>
                        ) : (
                          <span>Submit Event Proposal</span>
                        )}
                      </button>
                    </div>
                  </form>
                </div>
              </div>
            </div>
          )}

          {/* ============================================================ */}
          {/* TAB 3: MY EVENTS & SCHEDULE (COMBINED) */}
          {/* ============================================================ */}
          {activeTab === 'my-events' && (
            <div className="tab-pane">
              <section className="portal-section-card">
                <div className="section-card-header" style={{ flexWrap: 'wrap', gap: '1rem', alignItems: 'flex-start' }}>
                  <div className="header-title-stack">
                    <h2 className="section-card-title">
                      {eventViewMode === 'schedule' ? 'Confirmed Event Schedule' : 'My Events Catalog'}
                    </h2>
                    <span className="section-card-subtitle">
                      {eventViewMode === 'schedule'
                        ? 'Chronological agenda of approved university events across campus auditoriums and venues'
                        : 'Review all submitted proposals, track approval decisions, and inspect venue allocations'}
                    </span>
                  </div>

                  {/* Unified Segmented View Switcher */}
                  <div className="combined-view-toggle">
                    <button
                      type="button"
                      className={`btn btn-sm ${eventViewMode === 'catalog' ? 'btn-primary' : 'btn-secondary'}`}
                      onClick={() => setEventViewMode('catalog')}
                    >
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                        <polyline points="14 2 14 8 20 8" />
                      </svg>
                      <span>Events Catalog ({allEvents.length})</span>
                    </button>
                    <button
                      type="button"
                      className={`btn btn-sm ${eventViewMode === 'schedule' ? 'btn-primary' : 'btn-secondary'}`}
                      onClick={() => setEventViewMode('schedule')}
                    >
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                        <line x1="16" y1="2" x2="16" y2="6" />
                        <line x1="8" y1="2" x2="8" y2="6" />
                        <line x1="3" y1="10" x2="21" y2="10" />
                      </svg>
                      <span>Event Schedule ({approvedEvents.length})</span>
                    </button>
                  </div>
                </div>

                {/* SUB-VIEW A: EVENTS CATALOG */}
                {eventViewMode === 'catalog' && (
                  <>
                    <div style={{ marginBottom: '1.25rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
                      {/* Filter Pills */}
                      <div className="filter-pill-group">
                        <button
                          type="button"
                          className={`filter-pill ${statusFilter === 'all' ? 'active' : ''}`}
                          onClick={() => setStatusFilter('all')}
                        >
                          All ({allEvents.length})
                        </button>
                        <button
                          type="button"
                          className={`filter-pill ${statusFilter === 'approved' ? 'active' : ''}`}
                          onClick={() => setStatusFilter('approved')}
                        >
                          Approved ({stats.approved_events})
                        </button>
                        <button
                          type="button"
                          className={`filter-pill ${statusFilter === 'pending' ? 'active' : ''}`}
                          onClick={() => setStatusFilter('pending')}
                        >
                          Pending ({stats.pending_events})
                        </button>
                        <button
                          type="button"
                          className={`filter-pill ${statusFilter === 'rejected' ? 'active' : ''}`}
                          onClick={() => setStatusFilter('rejected')}
                        >
                          Rejected ({stats.rejected_events})
                        </button>
                      </div>

                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        onClick={() => setEventViewMode('schedule')}
                        style={{ fontSize: '0.8125rem' }}
                      >
                        Switch to Timeline View &rarr;
                      </button>
                    </div>

                    <EventTable
                      events={filteredEvents}
                      onCreateEvent={() => handleTabChange('create')}
                      onUploadImage={handleOpenUpload}
                      emptyMessage={`No ${statusFilter === 'all' ? '' : statusFilter} events found for your account.`}
                    />
                  </>
                )}

                {/* SUB-VIEW B: CONFIRMED EVENT SCHEDULE */}
                {eventViewMode === 'schedule' && (
                  <>
                    <div style={{ marginBottom: '1.25rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
                      <span style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                        Showing confirmed calendar timeline for <strong>{approvedEvents.length}</strong> approved event(s)
                      </span>
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        onClick={() => setEventViewMode('catalog')}
                        style={{ fontSize: '0.8125rem' }}
                      >
                        &larr; Switch to Catalog View
                      </button>
                    </div>

                    {approvedEvents.length === 0 ? (
                      <div className="section-empty-block">
                        <p>No approved events scheduled currently. Propose an event to begin.</p>
                        <button
                          type="button"
                          className="btn btn-primary btn-sm"
                          onClick={() => handleTabChange('create')}
                          style={{ marginTop: '0.75rem' }}
                        >
                          + Propose Event
                        </button>
                      </div>
                    ) : (
                      <div className="schedule-timeline">
                        {approvedEvents.map((ev) => (
                          <div key={ev.id} className="timeline-item">
                            <div className="timeline-date-marker">
                              <span className="marker-date">{ev.approved_date || ev.requested_date}</span>
                              <span className="marker-time">{ev.approved_start_time || ev.requested_start_time}</span>
                            </div>
                            <div className="timeline-content-card">
                              <div className="timeline-content-header">
                                <h3 className="timeline-event-name">{ev.event_name}</h3>
                                <StatusBadge status="approved" />
                              </div>
                              <p className="timeline-event-venue">
                                Venue: <strong>{ev.venue_name || 'Main Campus'}</strong> ({ev.venue_location})
                              </p>
                              <p className="timeline-event-fest">
                                Program: {ev.series_name || 'General Fest'} &bull; Category: {ev.category}
                              </p>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </section>
            </div>
          )}

          {/* ============================================================ */}
          {/* TAB 4: VENUE REQUESTS */}
          {/* ============================================================ */}
          {activeTab === 'venue-requests' && (
            <div className="tab-pane">
              <section className="portal-section-card">
                <div className="section-card-header">
                  <div className="header-title-stack">
                    <h2 className="section-card-title">Venue Allocation Overview</h2>
                    <span className="section-card-subtitle">
                      Review administrative status of campus auditorium and venue requests
                    </span>
                  </div>
                </div>

                <EventTable
                  events={allEvents}
                  onCreateEvent={() => handleTabChange('create')}
                  onUploadImage={handleOpenUpload}
                  showUploadAction={false}
                  emptyMessage="No venue requests currently recorded."
                />
              </section>
            </div>
          )}

          {/* ============================================================ */}
          {/* TAB 6: CROWD MONITORING CONSOLE */}
          {/* ============================================================ */}
          {activeTab === 'crowd-monitoring' && (
            <div className="tab-pane">
              <section className="portal-section-card">
                <div className="section-card-header">
                  <div className="header-title-stack">
                    <h2 className="section-card-title">Crowd Photographic Surveillance</h2>
                    <span className="section-card-subtitle">
                      Select an approved event to upload location photographs for computer-vision headcount estimation
                    </span>
                  </div>
                </div>

                {approvedEvents.length === 0 ? (
                  <div className="section-empty-block">
                    <p>Crowd monitoring photographs can only be uploaded for approved events.</p>
                  </div>
                ) : (
                  <div className="monitoring-events-list">
                    {approvedEvents.map((ev) => {
                      const timingInfo = getEventHappeningInfo(ev);
                      const isHappening = timingInfo.isHappening;
                      return (
                        <div key={ev.id} className="monitoring-card">
                          <div className="monitoring-card-info">
                            <div className="monitoring-card-tag-row" style={{ display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '6px' }}>
                              <span className="monitoring-card-tag">Approved Venue</span>
                              {isHappening ? (
                                <span className="monitoring-live-badge">● Happening Now</span>
                              ) : (
                                <span className="monitoring-not-happening-badge">Not Happening</span>
                              )}
                            </div>
                            <h3 className="monitoring-card-title">{ev.event_name}</h3>
                            <div className="monitoring-card-meta">
                              <span>{ev.venue_name || 'Campus Venue'} ({ev.venue_location})</span>
                              <span>Date: {ev.approved_date || ev.requested_date}</span>
                              <span>Time: {ev.approved_start_time || ev.requested_start_time} - {ev.approved_end_time || ev.requested_end_time}</span>
                            </div>
                          </div>
                          {isHappening ? (
                            <button
                              type="button"
                              className="btn btn-primary btn-sm btn-upload-live"
                              onClick={() => handleOpenUpload(ev)}
                            >
                              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                                <circle cx="8.5" cy="8.5" r="1.5" />
                                <polyline points="21 15 16 10 5 21" />
                              </svg>
                              <span>Upload & Manage Photos</span>
                            </button>
                          ) : (
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              onClick={() => handleOpenUpload(ev)}
                              title={timingInfo.reason}
                            >
                              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                                <circle cx="8.5" cy="8.5" r="1.5" />
                                <polyline points="21 15 16 10 5 21" />
                              </svg>
                              <span>View Photos (Upload Blocked)</span>
                            </button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </section>
            </div>
          )}

          {/* ============================================================ */}
          {/* TAB 7: CROWD ALERTS */}
          {/* ============================================================ */}
          {activeTab === 'crowd-alerts' && (
            <CrowdAlertsView role="organizer" onUnreadCountChange={setUnreadAlertsCount} />
          )}

          {/* ============================================================ */}
          {/* TAB 8: ANALYSIS HISTORY */}
          {/* ============================================================ */}
          {activeTab === 'analysis-history' && (
            <div className="tab-pane">
              <section className="portal-section-card">
                <div className="section-card-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.75rem' }}>
                  <div className="header-title-stack">
                    <h2 className="section-card-title">Surveillance Analysis Log</h2>
                    <span className="section-card-subtitle">
                      Historical computer-vision density estimations and processed photographic logs
                    </span>
                  </div>
                  <div className="header-actions">
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => loadAnalysisHistory(true)}
                      disabled={loadingHistory}
                      title="Refresh surveillance analysis history"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: '0.35rem' }}>
                        <path d="M23 4v6h-6" />
                        <path d="M1 20v-6h6" />
                        <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
                      </svg>
                      {loadingHistory ? 'Refreshing...' : 'Refresh'}
                    </button>
                  </div>
                </div>

                {historyError && (
                  <div className="portal-alert portal-alert-error" role="alert" style={{ margin: '1rem 0', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <span>{historyError}</span>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => loadAnalysisHistory(true)}
                      style={{ marginLeft: 'auto' }}
                    >
                      Retry
                    </button>
                  </div>
                )}

                {loadingHistory && historyPhotos.length === 0 ? (
                  <Loading message="Loading crowd surveillance history..." />
                ) : !loadingHistory && historyPhotos.length === 0 && !historyError ? (
                  <div className="section-empty-block">
                    <p>No crowd photographs analyzed yet. Navigate to Crowd Surveillance to upload and analyze event images.</p>
                  </div>
                ) : historyPhotos.length > 0 ? (
                  <div className="modal-photos-grid" style={{ padding: '1rem 0' }}>
                    {historyPhotos.map((photo) => (
                      <div key={photo.id} className="photo-card">
                        <img
                          src={getBackendAssetUrl(photo.image_url)}
                          alt="Surveillance analysis"
                          className="photo-thumbnail"
                          onError={(e) => {
                            e.target.style.display = 'none';
                          }}
                        />
                        <div className="photo-card-info">
                          <strong style={{ color: 'var(--text-primary)', fontSize: '0.78rem' }}>
                            {photo.event_name}
                          </strong>
                          {photo.venue_name && (
                            <span style={{ color: 'var(--text-muted)' }}>{photo.venue_name}</span>
                          )}
                          <div className="photo-count-badge" style={{ marginTop: '0.25rem' }}>
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                              <circle cx="9" cy="7" r="4" />
                              <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                              <path d="M16 3.13a4 4 0 0 1 0 7.75" />
                            </svg>
                            <span>{photo.predicted_count} people</span>
                          </div>
                          <span className="photo-date">
                            {photo.analysis_timestamp ? `Analyzed: ${photo.analysis_timestamp.substring(0, 10)}` : `Uploaded: ${photo.uploaded_at?.substring(0, 10)}`}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : null}
              </section>
            </div>
          )}

          {/* ============================================================ */}
          {/* TAB 9: CROWD REPORTS */}
          {/* ============================================================ */}
          {activeTab === 'crowd-reports' && (
            <CrowdReportsView role="organizer" />
          )}

        </div>
      </div>

      {/* ============================================================ */}
      {/* PHOTO UPLOAD & INSPECTION MODAL */}
      {/* ============================================================ */}
      {selectedUploadEvent && (() => {
        const modalTiming = getEventHappeningInfo(selectedUploadEvent);
        const canUpload = modalTiming.isHappening;

        return (
          <div className="modal-backdrop" onClick={() => setSelectedUploadEvent(null)} aria-hidden="true">
            <div className="modal-window" onClick={(e) => e.stopPropagation()} role="dialog" aria-labelledby="modal-title">
              <div className="modal-header">
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                    <span className="modal-tag">Photo Surveillance</span>
                    {canUpload ? (
                      <span className="monitoring-live-badge">● Happening Now</span>
                    ) : (
                      <span className="monitoring-not-happening-badge">Event Not Happening</span>
                    )}
                  </div>
                  <h3 id="modal-title" className="modal-title">{selectedUploadEvent.event_name}</h3>
                  <span className="modal-subtitle">
                    Venue: {selectedUploadEvent.venue_name || 'Main Campus'} &bull; Schedule: {selectedUploadEvent.approved_date || selectedUploadEvent.requested_date} ({selectedUploadEvent.approved_start_time || selectedUploadEvent.requested_start_time} - {selectedUploadEvent.approved_end_time || selectedUploadEvent.requested_end_time})
                  </span>
                </div>
                <button
                  type="button"
                  className="modal-close-btn"
                  onClick={() => setSelectedUploadEvent(null)}
                  aria-label="Close dialog"
                >
                  &times;
                </button>
              </div>

              <div className="modal-body">
                {/* Upload Form or Blocked Notice */}
                {canUpload ? (
                  <form onSubmit={handleUploadSubmit} className="modal-upload-form">
                    <div className="upload-live-notice">
                      <span className="live-dot-pulse" aria-hidden="true" />
                      <span>Event is actively happening now. Photographs can be uploaded for crowd headcount analysis.</span>
                    </div>
                    <label htmlFor="photo-file" className="form-label" style={{ marginTop: '0.75rem' }}>
                      Select Event Location Photograph (.jpg, .jpeg, .png)
                    </label>
                    <input
                      id="photo-file"
                      type="file"
                      accept="image/jpeg,image/png,image/jpg"
                      onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                      className="form-input"
                      disabled={uploading}
                    />
                    <span className="form-hint">Maximum upload limit: 10 MB per image.</span>

                    {uploadError && (
                      <div className="portal-alert portal-alert-error" style={{ marginTop: '0.75rem' }}>
                        <span>{uploadError}</span>
                      </div>
                    )}

                    <div className="modal-upload-actions">
                      <button
                        type="submit"
                        className="btn btn-primary btn-sm"
                        disabled={uploading || !uploadFile}
                      >
                        {uploading ? (
                          <>
                            <span className="spinner-sm" aria-hidden="true" />
                            <span>Uploading...</span>
                          </>
                        ) : (
                          <span>Upload Photograph</span>
                        )}
                      </button>
                    </div>
                  </form>
                ) : (
                  <div className="modal-upload-blocked-box">
                    <div className="upload-lock-card">
                      <div className="upload-lock-icon">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                          <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                          <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                        </svg>
                      </div>
                      <div className="upload-lock-content">
                        <h4 className="upload-lock-title">Photo Upload Option Blocked</h4>
                        <p className="upload-lock-desc">
                          Photo upload is disabled because this event is not actively happening. Organizers are only permitted to upload location photographs during the actual event hours.
                        </p>
                        <div className="upload-lock-detail">
                          <span className="lock-detail-label">Status:</span> {modalTiming.reason}
                        </div>
                      </div>
                    </div>
                  </div>
                )}

              {/* Existing Uploaded Photos */}
              <div className="modal-photos-section">
                <h4 className="modal-photos-title">Uploaded Surveillance Photos</h4>
                {loadingPhotos ? (
                  <Loading message="Loading photographs..." />
                ) : eventPhotos.length === 0 ? (
                  <p className="modal-photos-empty">No photographs uploaded for this event yet.</p>
                ) : (
                  <div className="modal-photos-grid">
                    {eventPhotos.map((photo) => {
                      const isAnalyzing = Boolean(analyzingImageIds[photo.id]);
                      const hasCount = photo.predicted_count !== null && photo.predicted_count !== undefined;
                      const errorMsg = analysisErrors[photo.id];

                      return (
                        <div key={photo.id} className="photo-card">
                          <img
                            src={getBackendAssetUrl(photo.image_url)}
                            alt="Event surveillance"
                            className="photo-thumbnail"
                            onError={(e) => {
                              e.target.style.display = 'none';
                            }}
                          />
                          <div className="photo-card-info">
                            <span className="photo-status">
                              Status: {isAnalyzing ? 'Analyzing...' : photo.processing_status}
                            </span>
                            {hasCount && (
                              <div className="photo-count-badge">
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                                  <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                                  <circle cx="9" cy="7" r="4" />
                                  <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                                  <path d="M16 3.13a4 4 0 0 1 0 7.75" />
                                </svg>
                                <span>{photo.predicted_count} people</span>
                              </div>
                            )}
                            <span className="photo-date">{photo.uploaded_at?.substring(0, 10)}</span>

                            {errorMsg && (
                              <div className="photo-error-banner" role="alert">
                                <span>{errorMsg}</span>
                              </div>
                            )}

                            {/* Analyze Crowd Button - Only for unanalyzed photos (re-analyze button removed) */}
                            {!hasCount && photo.processing_status !== 'completed' && (
                              <div className="photo-actions">
                                <button
                                  type="button"
                                  className="photo-analyze-btn"
                                  onClick={() => handleAnalyzePhoto(photo)}
                                  disabled={isAnalyzing}
                                  title="Analyze crowd headcount using CSRNet"
                                >
                                  {isAnalyzing ? (
                                    <>
                                      <span className="spinner-sm" aria-hidden="true" style={{ width: 11, height: 11, borderWidth: 2 }} />
                                      <span>Estimating...</span>
                                    </>
                                  ) : (
                                    <>
                                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                        <circle cx="12" cy="12" r="10" />
                                        <line x1="12" y1="8" x2="12" y2="12" />
                                        <line x1="12" y1="16" x2="12.01" y2="16" />
                                      </svg>
                                      <span>Analyze Crowd</span>
                                    </>
                                  )}
                                </button>
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>

                )}
              </div>
            </div>
          </div>
        </div>
      );
    })()}
    </div>
  );
}
