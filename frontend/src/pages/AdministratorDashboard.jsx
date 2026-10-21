import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  getAdministratorDashboard,
  getAdministratorEvents,
  allocateEventSchedule,
  updateEventStatus,
  createVenue,
  updateVenue,
  updateVenueStatus,
  deleteVenue,
  getEventImages,
  getBackendAssetUrl,
  getAdministratorFests,
  createFest,
  deleteFest,
  getFestApprovedEvents,
  getUnassignedApprovedEvents,
  assignEventToFest,
  getUnreadAlertsCount,
} from '../services/api';
import Loading from '../components/Loading';
import StatCard from '../components/StatCard';
import StatusBadge from '../components/StatusBadge';
import CrowdReportsView from '../components/CrowdReportsView';
import CrowdAlertsView from '../components/CrowdAlertsView';

/**
 * Format ISO date string (YYYY-MM-DD) into readable institutional format.
 */
function formatDate(dateStr) {
  if (!dateStr) return 'TBD';
  try {
    const parts = dateStr.split('-');
    if (parts.length === 3) {
      const year = parseInt(parts[0], 10);
      const month = parseInt(parts[1], 10) - 1;
      const day = parseInt(parts[2], 10);
      const d = new Date(year, month, day);
      return d.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      });
    }
    return dateStr;
  } catch {
    return dateStr;
  }
}

/**
 * Format time range into clean HH:MM - HH:MM display.
 */
function formatTimeRange(startStr, endStr) {
  if (!startStr) return 'Pending schedule';
  const cleanStart = startStr.substring(0, 5);
  if (!endStr) return cleanStart;
  const cleanEnd = endStr.substring(0, 5);
  return `${cleanStart} – ${cleanEnd}`;
}

export default function AdministratorDashboard() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  // Active Tab synced with URL and left flyout sidebar (resolve 'schedule' to 'all-events')
  const currentTabFromUrl = searchParams.get('tab') || 'dashboard';
  const resolvedTab = currentTabFromUrl === 'schedule' ? 'all-events' : currentTabFromUrl;
  const [activeTab, setActiveTab] = useState(resolvedTab);
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
      const target = tabFromUrl === 'schedule' ? 'all-events' : tabFromUrl;
      if (target !== activeTab) {
        setActiveTab(target);
      }
    }
  }, [searchParams]);

  // Sync tab with left flyout sidebar selection
  useEffect(() => {
    const handlePortalTabSelect = (e) => {
      if (e.detail?.tab) {
        const target = e.detail.tab === 'schedule' ? 'all-events' : e.detail.tab;
        setActiveTab(target);
      }
    };
    window.addEventListener('portal-tab-select', handlePortalTabSelect);
    return () => window.removeEventListener('portal-tab-select', handlePortalTabSelect);
  }, []);

  // Real backend data states
  const [dashboardData, setDashboardData] = useState(null);
  const [allEvents, setAllEvents] = useState([]);
  const [eventSearch, setEventSearch] = useState('');
  const [eventFilter, setEventFilter] = useState('all');

  // Fest Registry states
  const [festsList, setFestsList] = useState([]);
  const [festsLoading, setFestsLoading] = useState(false);
  const [selectedFest, setSelectedFest] = useState(null);
  const [selectedFestEvents, setSelectedFestEvents] = useState([]);
  const [selectedFestEventsLoading, setSelectedFestEventsLoading] = useState(false);
  const [unassignedEvents, setUnassignedEvents] = useState([]);

  // Add Fest Modal state
  const [addFestModalOpen, setAddFestModalOpen] = useState(false);
  const [festFormData, setFestFormData] = useState({
    name: '',
    description: '',
    start_date: '',
    end_date: '',
  });
  const [festSubmitting, setFestSubmitting] = useState(false);
  const [festFormError, setFestFormError] = useState('');

  // Delete Fest Modal state
  const [deleteFestModal, setDeleteFestModal] = useState(null);
  const [deleteTargetReassignId, setDeleteTargetReassignId] = useState('');
  const [deleteFestSubmitting, setDeleteFestSubmitting] = useState(false);
  const [deleteFestError, setDeleteFestError] = useState('');

  // Assign Unassigned Event Modal state
  const [assignModalEvent, setAssignModalEvent] = useState(null);
  const [assignFestTargetId, setAssignFestTargetId] = useState('');
  const [assignSubmitting, setAssignSubmitting] = useState(false);
  const [assignError, setAssignError] = useState('');

  // Loading & Error states
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState('');
  const [actionSuccess, setActionSuccess] = useState('');

  // Modals state
  // 1. Allocation / Schedule Modal
  const [allocationModalEvent, setAllocationModalEvent] = useState(null);
  const [allocationForm, setAllocationForm] = useState({
    venue_id: '',
    approved_date: '',
    approved_start_time: '09:00',
    approved_end_time: '17:00',
    expected_participants: '',
  });
  const [allocationSubmitting, setAllocationSubmitting] = useState(false);
  const [allocationError, setAllocationError] = useState('');

  // 2. Rejection Modal
  const [rejectModalEvent, setRejectModalEvent] = useState(null);
  const [rejectionReason, setRejectionReason] = useState('');
  const [rejectionSubmitting, setRejectionSubmitting] = useState(false);
  const [rejectionError, setRejectionError] = useState('');

  // 3. Venue Create / Edit Modal
  const [venueModalOpen, setVenueModalOpen] = useState(false);
  const [editingVenue, setEditingVenue] = useState(null);
  const [venueFormData, setVenueFormData] = useState({
    name: '',
    location: '',
    capacity: '',
    status: 'available',
  });
  const [venueSubmitting, setVenueSubmitting] = useState(false);
  const [venueError, setVenueError] = useState('');

  // 4. Photo Inspection Modal
  const [inspectEvent, setInspectEvent] = useState(null);
  const [inspectPhotos, setInspectPhotos] = useState([]);
  const [inspectLoading, setInspectLoading] = useState(false);

  // Fetch all administrator dashboard data from real backend
  const loadDashboard = useCallback(async () => {
    setLoading(true);
    setErrorMessage('');
    try {
      const [dashRes, eventsRes, festsRes, unassignedRes] = await Promise.all([
        getAdministratorDashboard(),
        getAdministratorEvents(),
        getAdministratorFests(),
        getUnassignedApprovedEvents(),
      ]);

      if (dashRes.ok && dashRes.data) {
        setDashboardData(dashRes.data);
      } else {
        setErrorMessage(dashRes.error || 'Failed to load administrator dashboard data.');
      }

      if (eventsRes.ok && eventsRes.data?.events) {
        setAllEvents(eventsRes.data.events);
      }

      if (festsRes.ok && festsRes.data) {
        setFestsList(festsRes.data.fests || festsRes.data.series || []);
      }

      if (unassignedRes.ok && unassignedRes.data) {
        setUnassignedEvents(unassignedRes.data.events || []);
      }
    } catch {
      setErrorMessage('Unable to connect to server. Please verify backend is running.');
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchSelectedFestEvents = useCallback(async (festId) => {
    if (!festId) return;
    setSelectedFestEventsLoading(true);
    try {
      const res = await getFestApprovedEvents(festId);
      if (res.ok && res.data) {
        setSelectedFestEvents(res.data.events || []);
        if (res.data.fest) {
          setSelectedFest((prev) => (prev ? { ...prev, ...res.data.fest } : res.data.fest));
        }
      }
    } catch {
      // Handled in view
    } finally {
      setSelectedFestEventsLoading(false);
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
  const handleTabChange = (tabId) => {
    const target = tabId === 'schedule' ? 'all-events' : tabId;
    setActiveTab(target);
    setSearchParams({ tab: target });
    setMobileSidebarOpen(false);
    setErrorMessage('');
    setActionSuccess('');
  };

  // -------------------------------------------------------------
  // ALLOCATION / APPROVAL HANDLERS
  // -------------------------------------------------------------
  const handleOpenAllocation = (event) => {
    setAllocationModalEvent(event);
    setAllocationError('');
    setAllocationForm({
      venue_id: event.venue_id ? String(event.venue_id) : '',
      approved_date: event.approved_date || event.requested_date || '',
      approved_start_time: event.approved_start_time
        ? event.approved_start_time.substring(0, 5)
        : event.requested_start_time
        ? event.requested_start_time.substring(0, 5)
        : '09:00',
      approved_end_time: event.approved_end_time
        ? event.approved_end_time.substring(0, 5)
        : event.requested_end_time
        ? event.requested_end_time.substring(0, 5)
        : '17:00',
      expected_participants: event.expected_participants != null ? String(event.expected_participants) : '',
    });
  };

  const handleAllocationSubmit = async (e) => {
    e.preventDefault();
    if (!allocationForm.venue_id) {
      setAllocationError('Please select a campus venue.');
      return;
    }
    if (!allocationForm.approved_date) {
      setAllocationError('Approved date is required.');
      return;
    }
    if (allocationForm.approved_start_time >= allocationForm.approved_end_time) {
      setAllocationError('Start time must precede end time.');
      return;
    }

    const venuesList = dashboardData?.venues || [];
    const selectedVenue = venuesList.find(v => v.id === parseInt(allocationForm.venue_id, 10));
    if (selectedVenue && selectedVenue.status !== 'available') {
      setAllocationError(`Cannot allocate venue "${selectedVenue.name}": it is currently marked as unavailable.`);
      return;
    }

    let parsedExp = null;
    if (allocationForm.expected_participants && allocationForm.expected_participants.trim() !== '') {
      parsedExp = parseInt(allocationForm.expected_participants.trim(), 10);
      if (isNaN(parsedExp) || parsedExp < 0) {
        setAllocationError('Expected participants must be a non-negative number.');
        return;
      }
      if (selectedVenue && selectedVenue.capacity > 0 && parsedExp > selectedVenue.capacity) {
        setAllocationError(`Venue "${selectedVenue.name}" capacity (${selectedVenue.capacity}) is insufficient for expected attendance (${parsedExp}).`);
        return;
      }
    }

    setAllocationSubmitting(true);
    setAllocationError('');

    try {
      const payload = {
        venue_id: parseInt(allocationForm.venue_id, 10),
        approved_date: allocationForm.approved_date,
        approved_start_time:
          allocationForm.approved_start_time.length === 5
            ? `${allocationForm.approved_start_time}:00`
            : allocationForm.approved_start_time,
        approved_end_time:
          allocationForm.approved_end_time.length === 5
            ? `${allocationForm.approved_end_time}:00`
            : allocationForm.approved_end_time,
      };
      if (parsedExp !== null) {
        payload.expected_participants = parsedExp;
      }

      const res = await allocateEventSchedule(allocationModalEvent.id, payload);

      if (res.ok) {
        setActionSuccess(`Schedule and venue saved for "${allocationModalEvent.event_name}".`);
        setAllocationModalEvent(null);
        await loadDashboard();
        if (selectedFest) {
          await fetchSelectedFestEvents(selectedFest.id);
        }
      } else {
        setAllocationError(res.error || res.data?.message || 'Failed to allocate schedule.');
      }
    } catch {
      setAllocationError('Network error while allocating event schedule.');
    } finally {
      setAllocationSubmitting(false);
    }
  };

  // -------------------------------------------------------------
  // FEST REGISTRY HANDLERS
  // -------------------------------------------------------------
  const handleSelectFest = (fest) => {
    setSelectedFest(fest);
    setErrorMessage('');
    setActionSuccess('');
    fetchSelectedFestEvents(fest.id);
  };

  const handleBackToFestRegistry = () => {
    setSelectedFest(null);
    setSelectedFestEvents([]);
    loadDashboard();
  };

  const handleOpenAddFest = () => {
    setFestFormData({
      name: '',
      description: '',
      start_date: '',
      end_date: '',
    });
    setFestFormError('');
    setAddFestModalOpen(true);
  };

  const handleAddFestSubmit = async (e) => {
    e.preventDefault();
    const festName = festFormData.name.trim();
    if (!festName) {
      setFestFormError('Fest name is required.');
      return;
    }

    // Duplicate check client-side
    const duplicate = festsList.some(
      (f) => f.name.trim().toLowerCase() === festName.toLowerCase()
    );
    if (duplicate) {
      setFestFormError(`A fest named "${festName}" already exists.`);
      return;
    }

    if (festFormData.start_date && festFormData.end_date) {
      if (festFormData.end_date < festFormData.start_date) {
        setFestFormError('End date must not precede start date.');
        return;
      }
    }

    setFestSubmitting(true);
    setFestFormError('');

    try {
      const res = await createFest(festFormData);
      if (res.ok) {
        setActionSuccess(`Fest "${festName}" registered successfully.`);
        setAddFestModalOpen(false);
        await loadDashboard();
      } else {
        setFestFormError(res.error || res.data?.message || 'Failed to create fest.');
      }
    } catch {
      setFestFormError('Network error while creating fest.');
    } finally {
      setFestSubmitting(false);
    }
  };

  const handleOpenDeleteFest = (fest) => {
    setDeleteFestModal(fest);
    // Find candidate fests for reassignment
    const candidates = festsList.filter(f => f.id !== fest.id);
    setDeleteTargetReassignId(candidates[0]?.id ? String(candidates[0].id) : '');
    setDeleteFestError('');
  };

  const handleDeleteFestSubmit = async (e) => {
    e.preventDefault();
    if (!deleteFestModal) return;

    const eventCount = deleteFestModal.event_count || deleteFestModal.approved_event_count || 0;
    if (eventCount > 0 && !deleteTargetReassignId) {
      setDeleteFestError('Please choose a fest to reassign existing events to before removing.');
      return;
    }

    setDeleteFestSubmitting(true);
    setDeleteFestError('');

    try {
      const res = await deleteFest(deleteFestModal.id, {
        reassign_to: deleteTargetReassignId || null,
      });

      if (res.ok) {
        setActionSuccess(`Fest "${deleteFestModal.name}" removed successfully.`);
        if (selectedFest && selectedFest.id === deleteFestModal.id) {
          setSelectedFest(null);
        }
        setDeleteFestModal(null);
        await loadDashboard();
      } else {
        setDeleteFestError(res.error || res.data?.message || 'Failed to delete fest.');
      }
    } catch {
      setDeleteFestError('Network error while removing fest.');
    } finally {
      setDeleteFestSubmitting(false);
    }
  };

  const handleOpenAssignEvent = (event) => {
    setAssignModalEvent(event);
    setAssignFestTargetId(festsList[0]?.id ? String(festsList[0].id) : '');
    setAssignError('');
  };

  const handleAssignEventSubmit = async (e) => {
    e.preventDefault();
    if (!assignModalEvent || !assignFestTargetId) {
      setAssignError('Please select a target college fest.');
      return;
    }

    setAssignSubmitting(true);
    setAssignError('');

    try {
      const res = await assignEventToFest(assignModalEvent.id, assignFestTargetId);
      if (res.ok) {
        const targetFest = festsList.find(f => f.id === parseInt(assignFestTargetId, 10));
        setActionSuccess(`Event "${assignModalEvent.event_name}" assigned to "${targetFest?.name || 'fest'}".`);
        setAssignModalEvent(null);
        await loadDashboard();
        if (selectedFest) {
          await fetchSelectedFestEvents(selectedFest.id);
        }
      } else {
        setAssignError(res.error || res.data?.message || 'Failed to assign event to fest.');
      }
    } catch {
      setAssignError('Network error while assigning event.');
    } finally {
      setAssignSubmitting(false);
    }
  };

  const handleDirectAssignToFest = async (eventId, targetFestId) => {
    try {
      const res = await assignEventToFest(eventId, targetFestId);
      if (res.ok) {
        setActionSuccess(`Event assigned to fest successfully.`);
        await loadDashboard();
        if (selectedFest) {
          await fetchSelectedFestEvents(selectedFest.id);
        }
      } else {
        setErrorMessage(res.error || 'Failed to assign event.');
      }
    } catch {
      setErrorMessage('Network error while assigning event.');
    }
  };

  // -------------------------------------------------------------
  // REJECTION HANDLERS
  // -------------------------------------------------------------
  const handleOpenReject = (event) => {
    setRejectModalEvent(event);
    setRejectionReason('');
    setRejectionError('');
  };

  const handleRejectSubmit = async (e) => {
    e.preventDefault();
    setRejectionSubmitting(true);
    setRejectionError('');

    try {
      const res = await updateEventStatus(
        rejectModalEvent.id,
        'rejected',
        rejectionReason.trim() || 'Declined during administrative review.'
      );

      if (res.ok) {
        setActionSuccess(`Event "${rejectModalEvent.event_name}" has been marked as rejected.`);
        setRejectModalEvent(null);
        await loadDashboard();
      } else {
        setRejectionError(res.error || res.data?.message || 'Failed to reject event.');
      }
    } catch {
      setRejectionError('Network error while updating event status.');
    } finally {
      setRejectionSubmitting(false);
    }
  };

  // -------------------------------------------------------------
  // VENUE CRUD HANDLERS
  // -------------------------------------------------------------
  const handleOpenAddVenue = () => {
    setEditingVenue(null);
    setVenueFormData({
      name: '',
      location: '',
      capacity: '500',
      status: 'available',
    });
    setVenueError('');
    setVenueModalOpen(true);
  };

  const handleOpenEditVenue = (venue) => {
    setEditingVenue(venue);
    setVenueFormData({
      name: venue.name,
      location: venue.location,
      capacity: String(venue.capacity),
      status: venue.status || 'available',
    });
    setVenueError('');
    setVenueModalOpen(true);
  };

  const handleVenueFormSubmit = async (e) => {
    e.preventDefault();
    if (!venueFormData.name.trim()) {
      setVenueError('Venue name is required.');
      return;
    }
    if (!venueFormData.location.trim()) {
      setVenueError('Location is required.');
      return;
    }
    const cap = parseInt(venueFormData.capacity, 10);
    if (isNaN(cap) || cap < 0) {
      setVenueError('Capacity must be a non-negative number.');
      return;
    }

    setVenueSubmitting(true);
    setVenueError('');

    try {
      let res;
      if (editingVenue) {
        res = await updateVenue(editingVenue.id, venueFormData);
      } else {
        res = await createVenue(venueFormData);
      }

      if (res.ok) {
        setActionSuccess(
          editingVenue
            ? `Venue "${venueFormData.name}" updated successfully.`
            : `New venue "${venueFormData.name}" added successfully.`
        );
        setVenueModalOpen(false);
        await loadDashboard();
      } else {
        setVenueError(res.error || res.data?.message || 'Failed to save venue.');
      }
    } catch {
      setVenueError('Network error while saving venue record.');
    } finally {
      setVenueSubmitting(false);
    }
  };

  const handleToggleVenueStatus = async (venue) => {
    const newStatus = venue.status === 'available' ? 'unavailable' : 'available';
    try {
      const res = await updateVenueStatus(venue.id, newStatus);
      if (res.ok) {
        setActionSuccess(`Venue "${venue.name}" marked as ${newStatus}.`);
        await loadDashboard();
      } else {
        setErrorMessage(res.error || 'Failed to update venue status.');
      }
    } catch {
      setErrorMessage('Network error updating venue availability.');
    }
  };

  const handleDeleteVenue = async (venue) => {
    if (!window.confirm(`Are you sure you want to delete venue "${venue.name}"?`)) {
      return;
    }

    try {
      const res = await deleteVenue(venue.id);
      if (res.ok) {
        setActionSuccess(`Venue "${venue.name}" deleted successfully.`);
        await loadDashboard();
      } else {
        setErrorMessage(res.error || res.data?.message || 'Cannot delete venue.');
      }
    } catch {
      setErrorMessage('Network error while deleting venue.');
    }
  };

  // -------------------------------------------------------------
  // PHOTO INSPECTION HANDLER
  // -------------------------------------------------------------
  const handleOpenInspectPhotos = async (event) => {
    setInspectEvent(event);
    setInspectPhotos([]);
    setInspectLoading(true);
    try {
      const res = await getEventImages(event.id);
      if (res.ok && res.data?.images) {
        setInspectPhotos(res.data.images);
      }
    } catch {
      // safe fallback
    } finally {
      setInspectLoading(false);
    }
  };

  // -------------------------------------------------------------
  // DERIVED DATA
  // -------------------------------------------------------------
  const stats = dashboardData?.stats || {
    total_events: 0,
    pending_events: 0,
    pending_requests: 0,
    approved_events: 0,
    rejected_events: 0,
    upcoming_events: 0,
    total_venues: 0,
    available_venues: 0,
    unavailable_venues: 0,
  };

  const venuesList = dashboardData?.venues || [];
  const pendingRequests = dashboardData?.pending_requests || [];
  const upcomingEvents = dashboardData?.upcoming_events || [];

  // Filtered list for "All Events" tab
  const filteredAllEvents = allEvents.filter((ev) => {
    const matchesFilter =
      eventFilter === 'all' || (ev.status || '').toLowerCase() === eventFilter.toLowerCase();

    if (!matchesFilter) return false;

    if (!eventSearch.trim()) return true;
    const q = eventSearch.toLowerCase();
    return (
      (ev.event_name || '').toLowerCase().includes(q) ||
      (ev.organizer_name || '').toLowerCase().includes(q) ||
      (ev.venue_name || '').toLowerCase().includes(q) ||
      (ev.series_name || '').toLowerCase().includes(q)
    );
  });

  // Approved events for Schedule & Crowd Monitoring
  const approvedEvents = allEvents.filter(
    (ev) => (ev.status || '').toLowerCase() === 'approved'
  );

  // Completed / Past events for History
  const pastEvents = allEvents.filter(
    (ev) => (ev.status || '').toLowerCase() === 'completed'
  );

  // Tab Title Metadata
  const tabTitles = {
    dashboard: {
      title: 'Administrator Console',
      subtitle: 'System-wide operational oversight of venue capacity, event proposals, and campus calendar allocations.',
    },
    'event-requests': {
      title: 'Event Proposals & Review',
      subtitle: 'Evaluate incoming organizer event requests, verify capacity requirements, and allocate venues.',
    },
    'all-events': {
      title: 'Event Registry',
      subtitle: 'Manage college fests, their approved events, venues, and schedules.',
    },
    venues: {
      title: 'Campus Venues',
      subtitle: 'Maintain venue specifications, seating capacities, and real-time operational availability.',
    },
    'crowd-monitoring': {
      title: 'Surveillance & Crowd Density Console',
      subtitle: 'Monitor crowd occupancy levels and inspect location surveillance photographs across active venues.',
    },
    'crowd-alerts': {
      title: 'Crowd Threshold Alerts',
      subtitle: 'Real-time automated warnings triggered when venue capacity thresholds are exceeded.',
    },
    'crowd-reports': {
      title: 'Crowd Analytics & Peak Reports',
      subtitle: 'Historical peak headcount records and venue occupancy metrics for college audit compliance.',
    },
    'event-history': {
      title: 'Completed Events History',
      subtitle: 'Historical archive of concluded campus symposiums, conferences, and student events.',
    },
  };

  const currentTabInfo = tabTitles[activeTab] || tabTitles.dashboard;

  if (loading && !dashboardData) {
    return <Loading fullScreen message="Loading administrative workspace from database..." />;
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
            <div className="portal-brand-emblem" style={{ backgroundColor: '#0284c7' }} aria-hidden="true">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2L2 7l10 5 10-5-10-5z" />
                <path d="M2 17l10 5 10-5" />
                <path d="M2 12l10 5 10-5" />
              </svg>
            </div>
            <div className="portal-brand-text">
              <span className="portal-brand-name">Administrator Portal</span>
              <span className="portal-brand-dept">College Administration</span>
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

        {/* 9 Sidebar Navigation Items */}
        <nav className="portal-sidebar-nav" aria-label="Administrator Navigation">
          <span className="portal-nav-heading">Administrative Control</span>

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

          {/* 2. Event Requests */}
          <button
            type="button"
            className={`portal-nav-btn ${activeTab === 'event-requests' ? 'active' : ''}`}
            onClick={() => handleTabChange('event-requests')}
          >
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
            </svg>
            <span>Event Requests</span>
            {stats.pending_requests > 0 && (
              <span className="portal-nav-count portal-count-warning">{stats.pending_requests}</span>
            )}
          </button>

          {/* 3. All Events */}
          <button
            type="button"
            className={`portal-nav-btn ${activeTab === 'all-events' ? 'active' : ''}`}
            onClick={() => handleTabChange('all-events')}
          >
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
              <line x1="16" y1="2" x2="16" y2="6" />
              <line x1="8" y1="2" x2="8" y2="6" />
              <line x1="3" y1="10" x2="21" y2="10" />
            </svg>
            <span>Events Registry</span>
            {festsList.length > 0 && (
              <span className="portal-nav-count">{festsList.length}</span>
            )}
          </button>

          {/* 4. Venues */}
          <button
            type="button"
            className={`portal-nav-btn ${activeTab === 'venues' ? 'active' : ''}`}
            onClick={() => handleTabChange('venues')}
          >
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 21h18" />
              <path d="M5 21V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16" />
              <path d="M9 9h1" />
              <path d="M9 13h1" />
              <path d="M14 9h1" />
              <path d="M14 13h1" />
            </svg>
            <span>Venues</span>
            <span className="portal-nav-count">{stats.total_venues}</span>
          </button>

          <span className="portal-nav-heading" style={{ marginTop: '1.25rem' }}>
            Safety &amp; Compliance
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

          {/* 8. Crowd Reports */}
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

          {/* 9. Event History */}
          <button
            type="button"
            className={`portal-nav-btn ${activeTab === 'event-history' ? 'active' : ''}`}
            onClick={() => handleTabChange('event-history')}
          >
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 3v5h5" />
              <path d="M3.05 13A9 9 0 1 0 6 5.3L3 8" />
              <path d="M12 7v5l4 2" />
            </svg>
            <span>Event History</span>
          </button>
        </nav>

        {/* Sidebar Footer */}
        <div className="portal-sidebar-footer">
          <div className="portal-user-summary">
            <span className="portal-user-name">{user?.name || 'Administrator'}</span>
            <span className="portal-user-role" style={{ color: '#38bdf8' }}>College Administration</span>
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
        {/* Mobile Topbar */}
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
                onClick={handleOpenAddVenue}
              >
                + Add Venue
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
              {/* Summary KPIs: Real Backend Aggregations */}
              <div className="stats-grid">
                <StatCard
                  title="Total Events"
                  value={stats.total_events}
                  subtitle="System proposals recorded"
                  variant="default"
                  onClick={() => {
                    setEventFilter('all');
                    handleTabChange('all-events');
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
                  title="Pending Requests"
                  value={stats.pending_requests}
                  subtitle="Awaiting schedule allocation"
                  variant="warning"
                  onClick={() => handleTabChange('event-requests')}
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
                  subtitle="Venues locked &amp; confirmed"
                  variant="success"
                  onClick={() => {
                    setEventFilter('approved');
                    handleTabChange('all-events');
                  }}
                  icon={
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                      <polyline points="22 4 12 14.01 9 11.01" />
                    </svg>
                  }
                />

                <StatCard
                  title="Rejected Proposals"
                  value={stats.rejected_events}
                  subtitle="Declined requests"
                  variant="danger"
                  onClick={() => {
                    setEventFilter('rejected');
                    handleTabChange('all-events');
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
                  title="Available Venues"
                  value={stats.available_venues}
                  subtitle={`${stats.total_venues} total campus venues`}
                  variant="primary"
                  onClick={() => handleTabChange('venues')}
                  icon={
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M3 21h18" />
                      <path d="M5 21V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16" />
                    </svg>
                  }
                />
              </div>

              {/* Pending Requests Preview Section */}
              <section className="portal-section-card">
                <div className="section-card-header">
                  <div className="header-title-stack">
                    <h2 className="section-card-title">Pending Event Proposals Awaiting Review</h2>
                    <span className="section-card-subtitle">
                      Proposals submitted by organizers requiring venue allocation and conflict verification
                    </span>
                  </div>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => handleTabChange('event-requests')}
                  >
                    View All Requests ({pendingRequests.length}) &rarr;
                  </button>
                </div>

                {pendingRequests.length === 0 ? (
                  <div className="table-empty-state">
                    <div className="empty-state-icon" aria-hidden="true">
                      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <circle cx="12" cy="12" r="10" />
                        <path d="M8 12l2 2 4-4" />
                      </svg>
                    </div>
                    <h4 className="empty-state-title">No pending event requests</h4>
                    <p className="empty-state-desc">
                      All event proposals submitted by organizers have been reviewed and allocated.
                    </p>
                  </div>
                ) : (
                  <div className="table-responsive-wrapper">
                    <table className="institutional-table" aria-label="Pending Proposals">
                      <thead>
                        <tr>
                          <th scope="col">Event Details</th>
                          <th scope="col">Organizer</th>
                          <th scope="col">Requested Date &amp; Time</th>
                          <th scope="col">Preferred Venue</th>
                          <th scope="col">Status</th>
                          <th scope="col" style={{ textAlign: 'right' }}>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {pendingRequests.slice(0, 5).map((ev) => (
                          <tr key={ev.id}>
                            <td>
                              <div className="table-event-name-block">
                                <span className="table-event-title">{ev.event_name}</span>
                                <span className="table-fest-tag">{ev.series_name || 'Independent Event'} &bull; {ev.category}</span>
                              </div>
                            </td>
                            <td>
                              <div className="table-meta-stack">
                                <span style={{ fontWeight: 600 }}>{ev.organizer_name}</span>
                                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{ev.organizer_email}</span>
                              </div>
                            </td>
                            <td>
                              <div className="table-meta-stack">
                                <span className="table-date-text">{formatDate(ev.requested_date)}</span>
                                <span className="table-time-text">{formatTimeRange(ev.requested_start_time, ev.requested_end_time)}</span>
                              </div>
                            </td>
                            <td>
                              <span className="table-venue-name">{ev.venue_name || 'No Preference'}</span>
                            </td>
                            <td>
                              <StatusBadge status="pending" />
                            </td>
                            <td style={{ textAlign: 'right' }}>
                              <div style={{ display: 'inline-flex', gap: '0.5rem' }}>
                                <button
                                  type="button"
                                  className="btn btn-primary btn-sm"
                                  onClick={() => handleOpenAllocation(ev)}
                                >
                                  Review &amp; Allocate
                                </button>
                                <button
                                  type="button"
                                  className="btn btn-secondary btn-sm"
                                  style={{ color: 'var(--danger)' }}
                                  onClick={() => handleOpenReject(ev)}
                                >
                                  Reject
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>

              {/* Upcoming Confirmed Events Preview */}
              <section className="portal-section-card">
                <div className="section-card-header">
                  <div className="header-title-stack">
                    <h2 className="section-card-title">Confirmed Campus Schedule Preview</h2>
                    <span className="section-card-subtitle">
                      Approved events scheduled on upcoming calendar dates across college venues
                    </span>
                  </div>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => handleTabChange('all-events')}
                  >
                    Open Events Registry &rarr;
                  </button>
                </div>

                {upcomingEvents.length === 0 ? (
                  <div className="section-empty-block">
                    <p>No upcoming approved events confirmed on the calendar right now.</p>
                  </div>
                ) : (
                  <div className="upcoming-events-grid">
                    {upcomingEvents.slice(0, 4).map((ev) => (
                      <div key={ev.id} className="upcoming-event-item">
                        <div className="upcoming-item-header">
                          <StatusBadge status="approved" />
                          <span className="upcoming-item-date">{ev.approved_date || ev.requested_date}</span>
                        </div>
                        <h3 className="upcoming-item-title">{ev.event_name}</h3>
                        <div className="upcoming-item-meta">
                          <span>Venue: <strong>{ev.venue_name || 'Main Campus'}</strong> ({ev.venue_location})</span>
                          <span>Time: {ev.approved_start_time || ev.requested_start_time} - {ev.approved_end_time || ev.requested_end_time}</span>
                          <span>Organizer: {ev.organizer_name}</span>
                        </div>
                        <div className="upcoming-item-actions">
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            onClick={() => handleOpenAllocation(ev)}
                          >
                            Modify Schedule
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            </div>
          )}

          {/* ============================================================ */}
          {/* TAB 2: PENDING EVENT REQUESTS */}
          {/* ============================================================ */}
          {activeTab === 'event-requests' && (
            <div className="tab-pane">
              <section className="portal-section-card">
                <div className="section-card-header">
                  <div className="header-title-stack">
                    <h2 className="section-card-title">Pending Event Requests ({pendingRequests.length})</h2>
                    <span className="section-card-subtitle">
                      Review organizer submissions, inspect requested timeframes, and perform conflict-checked allocations
                    </span>
                  </div>
                </div>

                {pendingRequests.length === 0 ? (
                  <div className="table-empty-state">
                    <div className="empty-state-icon" aria-hidden="true">
                      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                        <polyline points="22 4 12 14.01 9 11.01" />
                      </svg>
                    </div>
                    <h4 className="empty-state-title">No pending event requests</h4>
                    <p className="empty-state-desc">
                      There are currently no event requests awaiting administrative approval.
                    </p>
                  </div>
                ) : (
                  <div className="table-responsive-wrapper">
                    <table className="institutional-table" aria-label="Event Requests Table">
                      <thead>
                        <tr>
                          <th scope="col">Event Details</th>
                          <th scope="col">Organizer</th>
                          <th scope="col">Requested Date</th>
                          <th scope="col">Requested Hours</th>
                          <th scope="col">Preferred Venue</th>
                          <th scope="col">Status</th>
                          <th scope="col" style={{ textAlign: 'right' }}>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {pendingRequests.map((ev) => (
                          <tr key={ev.id}>
                            <td>
                              <div className="table-event-name-block">
                                <span className="table-event-title">{ev.event_name}</span>
                                {ev.description && (
                                  <span className="table-event-desc" title={ev.description}>
                                    {ev.description.length > 70
                                      ? `${ev.description.substring(0, 70)}...`
                                      : ev.description}
                                  </span>
                                )}
                                <span className="table-fest-tag">{ev.series_name || 'Independent Event'} &bull; {ev.category}</span>
                              </div>
                            </td>
                            <td>
                              <div className="table-meta-stack">
                                <span style={{ fontWeight: 600 }}>{ev.organizer_name}</span>
                                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{ev.organizer_email}</span>
                              </div>
                            </td>
                            <td>
                              <span className="table-date-text">{formatDate(ev.requested_date)}</span>
                            </td>
                            <td>
                              <span className="table-time-text">{formatTimeRange(ev.requested_start_time, ev.requested_end_time)}</span>
                            </td>
                            <td>
                              <span className="table-venue-name">{ev.venue_name || 'No Preference'}</span>
                            </td>
                            <td>
                              <StatusBadge status="pending" />
                            </td>
                            <td style={{ textAlign: 'right' }}>
                              <div style={{ display: 'inline-flex', gap: '0.5rem' }}>
                                <button
                                  type="button"
                                  className="btn btn-primary btn-sm"
                                  onClick={() => handleOpenAllocation(ev)}
                                >
                                  Review &amp; Allocate
                                </button>
                                <button
                                  type="button"
                                  className="btn btn-secondary btn-sm"
                                  style={{ color: 'var(--danger)' }}
                                  onClick={() => handleOpenReject(ev)}
                                >
                                  Reject
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            </div>
          )}

          {/* ============================================================ */}
          {/* TAB 3: EVENT REGISTRY (FEST REGISTRY & APPROVED EVENTS)      */}
          {/* ============================================================ */}
          {activeTab === 'all-events' && (
            <div className="tab-pane">
              {/* Unassigned Approved Events Alert Banner */}
              {unassignedEvents.length > 0 && !selectedFest && (
                <div className="fest-unassigned-banner">
                  <div className="fest-unassigned-info">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#854d0e" strokeWidth="2">
                      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                      <line x1="12" y1="9" x2="12" y2="13" />
                      <line x1="12" y1="17" x2="12.01" y2="17" />
                    </svg>
                    <div>
                      <div className="fest-unassigned-title">
                        {unassignedEvents.length} Approved Event{unassignedEvents.length > 1 ? 's' : ''} Without a College Fest
                      </div>
                      <div className="fest-unassigned-desc">
                        These approved events do not currently belong to any fest. You can safely assign them to a college fest.
                      </div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                    {unassignedEvents.map(ue => (
                      <button
                        key={ue.id}
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => handleOpenAssignEvent(ue)}
                        style={{ borderColor: '#fde047', backgroundColor: '#fef9c3', color: '#854d0e', fontWeight: 600 }}
                      >
                        Assign "{ue.event_name}" &rarr;
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* VIEW 1: DEDICATED FEST DETAILS VIEW */}
              {selectedFest ? (
                <div>
                  <div className="fest-details-banner">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <button
                        type="button"
                        className="fest-details-nav-back"
                        onClick={handleBackToFestRegistry}
                      >
                        &larr; Back to Event Registry
                      </button>
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        style={{ color: 'var(--danger)' }}
                        onClick={() => handleOpenDeleteFest(selectedFest)}
                      >
                        Remove Fest
                      </button>
                    </div>

                    <div className="fest-details-header-row">
                      <div className="fest-details-title-stack">
                        <h2>{selectedFest.name}</h2>
                        {selectedFest.description && (
                          <p>{selectedFest.description}</p>
                        )}
                      </div>
                      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                        <span className={`status-badge badge-${selectedFest.status || 'approved'}`}>
                          <span className="status-badge-dot" aria-hidden="true" />
                          <span>{selectedFest.computed_status || 'Active Fest'}</span>
                        </span>
                      </div>
                    </div>

                    <div className="fest-details-badge-strip">
                      <span>
                        <strong>Dates:</strong>{' '}
                        {selectedFest.start_date || selectedFest.end_date
                          ? `${formatDate(selectedFest.start_date)} – ${formatDate(selectedFest.end_date)}`
                          : 'Not scheduled'}
                      </span>
                      <span>&bull;</span>
                      <span>
                        <strong>Approved Events:</strong> {selectedFestEvents.length}
                      </span>
                    </div>
                  </div>

                  {/* Approved Events List for this Fest */}
                  <section className="portal-section-card">
                    <div className="section-card-header">
                      <div className="header-title-stack">
                        <h3 className="section-card-title">
                          Approved Events in {selectedFest.name} ({selectedFestEvents.length})
                        </h3>
                        <span className="section-card-subtitle">
                          Review dates, times, allocated venues, and attendance limits for approved programs under this fest
                        </span>
                      </div>
                      {unassignedEvents.length > 0 && (
                        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                          <span style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>Assign unassigned event:</span>
                          <select
                            className="form-select"
                            style={{ padding: '0.3rem 0.6rem', fontSize: '0.8125rem', maxWidth: '240px' }}
                            onChange={(e) => {
                              const evId = e.target.value;
                              if (evId) {
                                handleDirectAssignToFest(parseInt(evId, 10), selectedFest.id);
                                e.target.value = '';
                              }
                            }}
                            defaultValue=""
                          >
                            <option value="">+ Assign Event to {selectedFest.name}</option>
                            {unassignedEvents.map(ue => (
                              <option key={ue.id} value={ue.id}>{ue.event_name}</option>
                            ))}
                          </select>
                        </div>
                      )}
                    </div>

                    {selectedFestEventsLoading ? (
                      <div style={{ padding: '2.5rem', textAlign: 'center' }}>
                        <Loading message="Loading approved fest events..." />
                      </div>
                    ) : selectedFestEvents.length === 0 ? (
                      <div className="table-empty-state">
                        <h4 className="empty-state-title">No approved events for this fest</h4>
                        <p className="empty-state-desc">
                          There are currently no events approved for {selectedFest.name}. When proposals are reviewed and allocated, approved events will appear here.
                        </p>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          onClick={() => handleTabChange('event-requests')}
                        >
                          Review Event Proposals &rarr;
                        </button>
                      </div>
                    ) : (
                      <div className="table-responsive-wrapper">
                        <table className="institutional-table" aria-label={`Approved Events for ${selectedFest.name}`}>
                          <thead>
                            <tr>
                              <th scope="col">Event Details</th>
                              <th scope="col">Organizer</th>
                              <th scope="col">Event Date</th>
                              <th scope="col">Time Range</th>
                              <th scope="col">Allocated Venue</th>
                              <th scope="col">Expected Attendance</th>
                              <th scope="col">Status</th>
                              <th scope="col" style={{ textAlign: 'right' }}>Actions</th>
                            </tr>
                          </thead>
                          <tbody>
                            {selectedFestEvents.map((ev) => {
                              const displayDate = ev.approved_date || ev.requested_date;
                              const startTime = ev.approved_start_time || ev.requested_start_time;
                              const endTime = ev.approved_end_time || ev.requested_end_time;

                              return (
                                <tr key={ev.id}>
                                  <td>
                                    <div className="table-event-name-block">
                                      <span className="table-event-title">{ev.event_name}</span>
                                      <span className="table-fest-tag">{ev.category || 'General'}</span>
                                    </div>
                                  </td>
                                  <td>
                                    <div className="table-meta-stack">
                                      <span style={{ fontWeight: 600 }}>{ev.organizer_name}</span>
                                      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{ev.organizer_email}</span>
                                    </div>
                                  </td>
                                  <td>
                                    <span className="table-date-text">{formatDate(displayDate)}</span>
                                  </td>
                                  <td>
                                    <span className="table-time-text">{formatTimeRange(startTime, endTime)}</span>
                                  </td>
                                  <td>
                                    <div className="table-venue-stack">
                                      <span className="table-venue-name">{ev.venue_name || 'Venue pending'}</span>
                                      {ev.venue_location && (
                                        <span className="table-venue-sub">({ev.venue_location})</span>
                                      )}
                                    </div>
                                  </td>
                                  <td>
                                    {ev.expected_participants ? (
                                      <span style={{ fontWeight: 600 }}>{ev.expected_participants.toLocaleString()} attendees</span>
                                    ) : (
                                      <span style={{ color: 'var(--text-muted)' }}>Not specified</span>
                                    )}
                                  </td>
                                  <td>
                                    <StatusBadge status={ev.status} />
                                  </td>
                                  <td style={{ textAlign: 'right' }}>
                                    <button
                                      type="button"
                                      className="btn btn-secondary btn-sm"
                                      onClick={() => handleOpenAllocation(ev)}
                                      title="Edit schedule or change allocated venue"
                                    >
                                      Edit Schedule / Venue
                                    </button>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </section>
                </div>
              ) : (
                /* VIEW 2: MAIN FEST REGISTRY LIST/CARD VIEW */
                <section className="portal-section-card">
                  <div className="section-card-header">
                    <div className="header-title-stack">
                      <h2 className="section-card-title">Event Registry</h2>
                      <span className="section-card-subtitle">
                        Manage college fests, their approved events, venues, and schedules.
                      </span>
                    </div>

                    <button
                      type="button"
                      className="btn btn-primary btn-sm"
                      onClick={handleOpenAddFest}
                    >
                      + Add New Fest
                    </button>
                  </div>

                  {festsLoading ? (
                    <div style={{ padding: '3rem', textAlign: 'center' }}>
                      <Loading message="Loading college fests from database..." />
                    </div>
                  ) : festsList.length === 0 ? (
                    <div className="table-empty-state">
                      <h4 className="empty-state-title">No college fests registered</h4>
                      <p className="empty-state-desc">
                        Register your college's first fest to group approved events, allocate venues, and manage campus schedules.
                      </p>
                      <button
                        type="button"
                        className="btn btn-primary btn-sm"
                        onClick={handleOpenAddFest}
                      >
                        + Add New Fest
                      </button>
                    </div>
                  ) : (
                    <div className="fest-registry-grid">
                      {festsList.map((fest) => {
                        const approvedCount = fest.approved_event_count != null ? fest.approved_event_count : (fest.event_count || 0);
                        const hasDates = fest.start_date || fest.end_date;

                        return (
                          <div key={fest.id} className="fest-card">
                            <div>
                              <div className="fest-card-header">
                                <h3 className="fest-card-title">{fest.name}</h3>
                                <span className={`status-badge badge-${fest.status || 'approved'}`}>
                                  <span className="status-badge-dot" aria-hidden="true" />
                                  <span>{fest.computed_status || 'Active'}</span>
                                </span>
                              </div>
                              <p className="fest-card-desc">
                                {fest.description || 'No description provided for this college fest.'}
                              </p>
                            </div>

                            <div className="fest-meta-strip">
                              <div className="fest-meta-item">
                                <svg className="fest-meta-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                  <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                                  <polyline points="22 4 12 14.01 9 11.01" />
                                </svg>
                                <span>
                                  <strong>{approvedCount}</strong> approved event{approvedCount === 1 ? '' : 's'}
                                </span>
                              </div>
                              <div className="fest-meta-item">
                                <svg className="fest-meta-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                  <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                                  <line x1="16" y1="2" x2="16" y2="6" />
                                  <line x1="8" y1="2" x2="8" y2="6" />
                                  <line x1="3" y1="10" x2="21" y2="10" />
                                </svg>
                                <span>
                                  {hasDates
                                    ? `${formatDate(fest.start_date)} – ${formatDate(fest.end_date)}`
                                    : 'Scheduled dates pending'}
                                </span>
                              </div>
                            </div>

                            <div className="fest-card-actions">
                              <button
                                type="button"
                                className="btn btn-primary btn-sm"
                                onClick={() => handleSelectFest(fest)}
                              >
                                View Events &rarr;
                              </button>
                              <button
                                type="button"
                                className="btn btn-ghost btn-sm"
                                style={{ color: 'var(--danger)' }}
                                onClick={() => handleOpenDeleteFest(fest)}
                              >
                                Remove Fest
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </section>
              )}
            </div>
          )}

          {/* ============================================================ */}
          {/* TAB 4: VENUES ADMINISTRATION */}
          {/* ============================================================ */}
          {activeTab === 'venues' && (
            <div className="tab-pane">
              <section className="portal-section-card">
                <div className="section-card-header">
                  <div className="header-title-stack">
                    <h2 className="section-card-title">Campus Venues ({venuesList.length})</h2>
                    <span className="section-card-subtitle">
                      Maintain auditorium seating capacities, campus buildings, and operational availability
                    </span>
                  </div>
                  <button
                    type="button"
                    className="btn btn-primary btn-sm"
                    onClick={handleOpenAddVenue}
                  >
                    + Add New Venue
                  </button>
                </div>

                {venuesList.length === 0 ? (
                  <div className="table-empty-state">
                    <h4 className="empty-state-title">No venues registered</h4>
                    <p className="empty-state-desc">
                      Add your first campus venue to enable event allocations.
                    </p>
                    <button
                      type="button"
                      className="btn btn-primary btn-sm"
                      onClick={handleOpenAddVenue}
                    >
                      + Add Venue
                    </button>
                  </div>
                ) : (
                  <div className="table-responsive-wrapper">
                    <table className="institutional-table" aria-label="Campus Venues Table">
                      <thead>
                        <tr>
                          <th scope="col">Venue Name</th>
                          <th scope="col">Campus Location</th>
                          <th scope="col">Capacity</th>
                          <th scope="col">Status</th>
                          <th scope="col" style={{ textAlign: 'right' }}>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {venuesList.map((v) => (
                          <tr key={v.id}>
                            <td>
                              <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                                {v.name}
                              </span>
                            </td>
                            <td>
                              <span style={{ color: 'var(--text-secondary)' }}>{v.location}</span>
                            </td>
                            <td>
                              <span style={{ fontWeight: 600 }}>{v.capacity.toLocaleString()}</span> attendees
                            </td>
                            <td>
                              <span
                                className={`status-badge ${
                                  v.status === 'available' ? 'badge-approved' : 'badge-rejected'
                                }`}
                              >
                                <span className="status-badge-dot" aria-hidden="true" />
                                <span>{v.status === 'available' ? 'Available' : 'Unavailable'}</span>
                              </span>
                            </td>
                            <td style={{ textAlign: 'right' }}>
                              <div style={{ display: 'inline-flex', gap: '0.4rem' }}>
                                <button
                                  type="button"
                                  className="btn btn-secondary btn-sm"
                                  onClick={() => handleToggleVenueStatus(v)}
                                  title="Toggle availability status"
                                >
                                  {v.status === 'available' ? 'Mark Unavailable' : 'Mark Available'}
                                </button>
                                <button
                                  type="button"
                                  className="btn btn-secondary btn-sm"
                                  onClick={() => handleOpenEditVenue(v)}
                                >
                                  Edit
                                </button>
                                <button
                                  type="button"
                                  className="btn btn-ghost btn-sm"
                                  style={{ color: 'var(--danger)' }}
                                  onClick={() => handleDeleteVenue(v)}
                                >
                                  Delete
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
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
                    <h2 className="section-card-title">Live Venue Surveillance &amp; Crowd Headcount</h2>
                    <span className="section-card-subtitle">
                      Inspect photographic surveillance feeds and verify computer-vision crowd headcount estimations
                    </span>
                  </div>
                </div>

                {approvedEvents.length === 0 ? (
                  <div className="section-empty-block">
                    <p>No active or approved events available for crowd surveillance.</p>
                  </div>
                ) : (
                  <div className="monitoring-events-list">
                    {approvedEvents.map((ev) => (
                      <div key={ev.id} className="monitoring-card">
                        <div className="monitoring-card-info">
                          <div className="monitoring-card-tag">Venue Active for Surveillance</div>
                          <h3 className="monitoring-card-title">{ev.event_name}</h3>
                          <div className="monitoring-card-meta">
                            <span>Venue: <strong>{ev.venue_name || 'Campus Venue'}</strong> ({ev.venue_location})</span>
                            <span>Date: {ev.approved_date || ev.requested_date}</span>
                            <span>Organizer: {ev.organizer_name}</span>
                          </div>
                          <div style={{ marginTop: '0.5rem', fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
                            No crowd analysis available yet. Headcount estimation will activate once computer vision model processing runs.
                          </div>
                        </div>
                        <button
                          type="button"
                          className="btn btn-primary btn-sm"
                          onClick={() => handleOpenInspectPhotos(ev)}
                        >
                          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                            <circle cx="8.5" cy="8.5" r="1.5" />
                            <polyline points="21 15 16 10 5 21" />
                          </svg>
                          <span>Inspect Surveillance Photos</span>
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            </div>
          )}

          {/* ============================================================ */}
          {/* TAB 7: CROWD ALERTS */}
          {/* ============================================================ */}
          {activeTab === 'crowd-alerts' && (
            <CrowdAlertsView role="administrator" onUnreadCountChange={setUnreadAlertsCount} />
          )}

          {/* ============================================================ */}
          {/* TAB 8: CROWD REPORTS */}
          {/* ============================================================ */}
          {activeTab === 'crowd-reports' && (
            <CrowdReportsView role="administrator" />
          )}

          {/* ============================================================ */}
          {/* TAB 9: EVENT HISTORY */}
          {/* ============================================================ */}
          {activeTab === 'event-history' && (
            <div className="tab-pane">
              <section className="portal-section-card">
                <div className="section-card-header">
                  <div className="header-title-stack">
                    <h2 className="section-card-title">Completed Event Archive</h2>
                    <span className="section-card-subtitle">
                      Historical log of past college symposiums, hackathons, and conferences
                    </span>
                  </div>
                </div>

                {pastEvents.length === 0 ? (
                  <div className="table-empty-state">
                    <div className="empty-state-icon" aria-hidden="true">
                      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <circle cx="12" cy="12" r="10" />
                        <polyline points="12 6 12 12 14 14" />
                      </svg>
                    </div>
                    <h4 className="empty-state-title">No completed event history records found</h4>
                    <p className="empty-state-desc">
                      Events that complete their scheduled dates and times will automatically archive here for administrative audit.
                    </p>
                  </div>
                ) : (
                  <div className="table-responsive-wrapper">
                    <table className="institutional-table" aria-label="Event History Archive">
                      <thead>
                        <tr>
                          <th scope="col">Event Title</th>
                          <th scope="col">Organizer</th>
                          <th scope="col">Concluded Date</th>
                          <th scope="col">Venue</th>
                          <th scope="col">Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {pastEvents.map((ev) => (
                          <tr key={ev.id}>
                            <td>
                              <span style={{ fontWeight: 600 }}>{ev.event_name}</span>
                            </td>
                            <td>
                              <span>{ev.organizer_name}</span>
                            </td>
                            <td>
                              <span>{formatDate(ev.approved_date || ev.requested_date)}</span>
                            </td>
                            <td>
                              <span>{ev.venue_name}</span>
                            </td>
                            <td>
                              <StatusBadge status="completed" />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            </div>
          )}
        </div>
      </div>

      {/* ============================================================ */}
      {/* MODAL 1: REVIEW & SCHEDULE ALLOCATION */}
      {/* ============================================================ */}
      {allocationModalEvent && (
        <div className="modal-backdrop" onClick={() => setAllocationModalEvent(null)} aria-hidden="true">
          <div className="modal-window" onClick={(e) => e.stopPropagation()} role="dialog" aria-labelledby="alloc-title">
            <div className="modal-header">
              <div>
                <span className="modal-tag">
                  {allocationModalEvent.status === 'approved' ? 'Edit Schedule & Campus Venue' : 'Venue Allocation & Schedule'}
                </span>
                <h3 id="alloc-title" className="modal-title">{allocationModalEvent.event_name}</h3>
                <span className="modal-subtitle">
                  Organizer: <strong>{allocationModalEvent.organizer_name}</strong> ({allocationModalEvent.organizer_email})
                </span>
              </div>
              <button
                type="button"
                className="modal-close-btn"
                onClick={() => setAllocationModalEvent(null)}
                aria-label="Close dialog"
              >
                &times;
              </button>
            </div>

            <div className="modal-body">
              {allocationError && (
                <div className="portal-alert portal-alert-error">
                  <span>{allocationError}</span>
                </div>
              )}

              <form onSubmit={handleAllocationSubmit} className="portal-form">
                <div className="form-row-2col">
                  <div className="form-group">
                    <label htmlFor="alloc-venue" className="form-label">
                      Allocated Campus Venue *
                    </label>
                    <select
                      id="alloc-venue"
                      className="form-select"
                      value={allocationForm.venue_id}
                      onChange={(e) =>
                        setAllocationForm((prev) => ({ ...prev, venue_id: e.target.value }))
                      }
                      required
                      disabled={allocationSubmitting}
                    >
                      <option value="">-- Select Campus Venue * --</option>
                      {venuesList.map((v) => (
                        <option key={v.id} value={v.id} disabled={v.status !== 'available'}>
                          {v.name} (Cap: {v.capacity} - {v.location}){v.status !== 'available' ? ' [UNAVAILABLE]' : ''}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="form-group">
                    <label htmlFor="alloc-expected" className="form-label">
                      Expected Participants
                    </label>
                    <input
                      id="alloc-expected"
                      type="number"
                      min={0}
                      className="form-input"
                      placeholder="e.g. 250"
                      value={allocationForm.expected_participants}
                      onChange={(e) =>
                        setAllocationForm((prev) => ({ ...prev, expected_participants: e.target.value }))
                      }
                      disabled={allocationSubmitting}
                    />
                  </div>
                </div>

                <div className="form-row-3col">
                  <div className="form-group">
                    <label htmlFor="alloc-date" className="form-label">
                      Approved Date *
                    </label>
                    <input
                      id="alloc-date"
                      type="date"
                      className="form-input"
                      value={allocationForm.approved_date}
                      onChange={(e) =>
                        setAllocationForm((prev) => ({ ...prev, approved_date: e.target.value }))
                      }
                      required
                      disabled={allocationSubmitting}
                    />
                  </div>

                  <div className="form-group">
                    <label htmlFor="alloc-start" className="form-label">
                      Start Time *
                    </label>
                    <input
                      id="alloc-start"
                      type="time"
                      className="form-input"
                      value={allocationForm.approved_start_time}
                      onChange={(e) =>
                        setAllocationForm((prev) => ({ ...prev, approved_start_time: e.target.value }))
                      }
                      required
                      disabled={allocationSubmitting}
                    />
                  </div>

                  <div className="form-group">
                    <label htmlFor="alloc-end" className="form-label">
                      End Time *
                    </label>
                    <input
                      id="alloc-end"
                      type="time"
                      className="form-input"
                      value={allocationForm.approved_end_time}
                      onChange={(e) =>
                        setAllocationForm((prev) => ({ ...prev, approved_end_time: e.target.value }))
                      }
                      required
                      disabled={allocationSubmitting}
                    />
                  </div>
                </div>

                <div className="form-hint">
                  The backend performs real-time conflict checking against other approved events and validates venue capacity against expected attendance.
                </div>

                <div className="form-action-footer">
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => setAllocationModalEvent(null)}
                    disabled={allocationSubmitting}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={allocationSubmitting}
                  >
                    {allocationSubmitting
                      ? 'Verifying & Saving...'
                      : allocationModalEvent.status === 'approved'
                      ? 'Save Schedule & Venue'
                      : 'Confirm Allocation & Approve'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* ============================================================ */}
      {/* MODAL 2: REJECT EVENT PROPOSAL */}
      {/* ============================================================ */}
      {rejectModalEvent && (
        <div className="modal-backdrop" onClick={() => setRejectModalEvent(null)} aria-hidden="true">
          <div className="modal-window" onClick={(e) => e.stopPropagation()} role="dialog" aria-labelledby="reject-title">
            <div className="modal-header">
              <div>
                <span className="modal-tag" style={{ color: 'var(--danger)' }}>Administrative Decision</span>
                <h3 id="reject-title" className="modal-title">Decline Event Proposal</h3>
                <span className="modal-subtitle">{rejectModalEvent.event_name}</span>
              </div>
              <button
                type="button"
                className="modal-close-btn"
                onClick={() => setRejectModalEvent(null)}
                aria-label="Close dialog"
              >
                &times;
              </button>
            </div>

            <div className="modal-body">
              {rejectionError && (
                <div className="portal-alert portal-alert-error">
                  <span>{rejectionError}</span>
                </div>
              )}

              <form onSubmit={handleRejectSubmit} className="portal-form">
                <div className="form-group">
                  <label htmlFor="reject-reason" className="form-label">
                    Rejection Feedback for Organizer
                  </label>
                  <textarea
                    id="reject-reason"
                    rows={3}
                    className="form-input form-textarea"
                    placeholder="Provide specific feedback or reason for proposal decline (e.g. venue maintenance conflict, scheduling constraint)."
                    value={rejectionReason}
                    onChange={(e) => setRejectionReason(e.target.value)}
                    disabled={rejectionSubmitting}
                  />
                  <span className="form-hint">
                    This note will be communicated directly to organizer {rejectModalEvent.organizer_name}.
                  </span>
                </div>

                <div className="form-action-footer">
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => setRejectModalEvent(null)}
                    disabled={rejectionSubmitting}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn btn-secondary"
                    style={{ backgroundColor: 'var(--danger)', color: '#ffffff', borderColor: 'var(--danger)' }}
                    disabled={rejectionSubmitting}
                  >
                    {rejectionSubmitting ? 'Rejecting...' : 'Confirm Rejection'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* ============================================================ */}
      {/* MODAL 3: ADD / EDIT CAMPUS VENUE */}
      {/* ============================================================ */}
      {venueModalOpen && (
        <div className="modal-backdrop" onClick={() => setVenueModalOpen(false)} aria-hidden="true">
          <div className="modal-window" onClick={(e) => e.stopPropagation()} role="dialog" aria-labelledby="venue-mod-title">
            <div className="modal-header">
              <div>
                <span className="modal-tag">Venue Administration</span>
                <h3 id="venue-mod-title" className="modal-title">
                  {editingVenue ? `Edit Venue: ${editingVenue.name}` : 'Add New Campus Venue'}
                </h3>
              </div>
              <button
                type="button"
                className="modal-close-btn"
                onClick={() => setVenueModalOpen(false)}
                aria-label="Close dialog"
              >
                &times;
              </button>
            </div>

            <div className="modal-body">
              {venueError && (
                <div className="portal-alert portal-alert-error">
                  <span>{venueError}</span>
                </div>
              )}

              <form onSubmit={handleVenueFormSubmit} className="portal-form">
                <div className="form-group">
                  <label htmlFor="venue-name" className="form-label">
                    Venue Name *
                  </label>
                  <input
                    id="venue-name"
                    type="text"
                    className="form-input"
                    placeholder="e.g. Dr. APJ Abdul Kalam Auditorium"
                    value={venueFormData.name}
                    onChange={(e) =>
                      setVenueFormData((prev) => ({ ...prev, name: e.target.value }))
                    }
                    required
                    disabled={venueSubmitting}
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="venue-location" className="form-label">
                    Campus Location *
                  </label>
                  <input
                    id="venue-location"
                    type="text"
                    className="form-input"
                    placeholder="e.g. Academic Block 3, Ground Floor"
                    value={venueFormData.location}
                    onChange={(e) =>
                      setVenueFormData((prev) => ({ ...prev, location: e.target.value }))
                    }
                    required
                    disabled={venueSubmitting}
                  />
                </div>

                <div className="form-row-2col">
                  <div className="form-group">
                    <label htmlFor="venue-capacity" className="form-label">
                      Seating Capacity *
                    </label>
                    <input
                      id="venue-capacity"
                      type="number"
                      min={0}
                      className="form-input"
                      value={venueFormData.capacity}
                      onChange={(e) =>
                        setVenueFormData((prev) => ({ ...prev, capacity: e.target.value }))
                      }
                      required
                      disabled={venueSubmitting}
                    />
                  </div>

                  <div className="form-group">
                    <label htmlFor="venue-status" className="form-label">
                      Operational Status *
                    </label>
                    <select
                      id="venue-status"
                      className="form-select"
                      value={venueFormData.status}
                      onChange={(e) =>
                        setVenueFormData((prev) => ({ ...prev, status: e.target.value }))
                      }
                      disabled={venueSubmitting}
                    >
                      <option value="available">Available for Bookings</option>
                      <option value="unavailable">Unavailable / Maintenance</option>
                    </select>
                  </div>
                </div>

                <div className="form-action-footer">
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => setVenueModalOpen(false)}
                    disabled={venueSubmitting}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={venueSubmitting}
                  >
                    {venueSubmitting
                      ? 'Saving...'
                      : editingVenue
                      ? 'Update Venue'
                      : 'Register Venue'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* ============================================================ */}
      {/* MODAL 4: SURVEILLANCE PHOTO INSPECTION */}
      {/* ============================================================ */}
      {inspectEvent && (
        <div className="modal-backdrop" onClick={() => setInspectEvent(null)} aria-hidden="true">
          <div className="modal-window" onClick={(e) => e.stopPropagation()} role="dialog" aria-labelledby="photo-title">
            <div className="modal-header">
              <div>
                <span className="modal-tag">Surveillance Inspection</span>
                <h3 id="photo-title" className="modal-title">{inspectEvent.event_name}</h3>
                <span className="modal-subtitle">Venue: {inspectEvent.venue_name || 'Main Campus'}</span>
              </div>
              <button
                type="button"
                className="modal-close-btn"
                onClick={() => setInspectEvent(null)}
                aria-label="Close dialog"
              >
                &times;
              </button>
            </div>

            <div className="modal-body">
              <div className="modal-photos-section">
                <h4 className="modal-photos-title">Surveillance Image Logs</h4>
                {inspectLoading ? (
                  <Loading message="Fetching surveillance frames..." />
                ) : inspectPhotos.length === 0 ? (
                  <p className="modal-photos-empty">
                    No surveillance photographs have been uploaded for this event by the organizer yet.
                  </p>
                ) : (
                  <div className="modal-photos-grid">
                    {inspectPhotos.map((photo) => (
                      <div key={photo.id} className="photo-card">
                        <img
                          src={getBackendAssetUrl(photo.image_url)}
                          alt="Surveillance frame"
                          className="photo-thumbnail"
                          onError={(e) => {
                            e.target.style.display = 'none';
                          }}
                        />
                        <div className="photo-card-info">
                          <span className="photo-status">Status: {photo.processing_status}</span>
                          {photo.predicted_count !== null && photo.predicted_count !== undefined && (
                            <span className="photo-count">Estimated: {photo.predicted_count}</span>
                          )}
                          <span className="photo-date">{photo.uploaded_at?.substring(0, 10)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ============================================================ */}
      {/* MODAL 5: ADD NEW FEST */}
      {/* ============================================================ */}
      {addFestModalOpen && (
        <div className="modal-backdrop" onClick={() => setAddFestModalOpen(false)} aria-hidden="true">
          <div className="modal-window" onClick={(e) => e.stopPropagation()} role="dialog" aria-labelledby="add-fest-title">
            <div className="modal-header">
              <div>
                <span className="modal-tag">Fest Administration</span>
                <h3 id="add-fest-title" className="modal-title">Register New College Fest</h3>
                <span className="modal-subtitle">
                  Create a major symposium, cultural fest, or technical summit to organize events
                </span>
              </div>
              <button
                type="button"
                className="modal-close-btn"
                onClick={() => setAddFestModalOpen(false)}
                aria-label="Close dialog"
              >
                &times;
              </button>
            </div>

            <div className="modal-body">
              {festFormError && (
                <div className="portal-alert portal-alert-error">
                  <span>{festFormError}</span>
                </div>
              )}

              <form onSubmit={handleAddFestSubmit} className="portal-form">
                <div className="form-group">
                  <label htmlFor="fest-name" className="form-label">
                    Fest Name *
                  </label>
                  <input
                    id="fest-name"
                    type="text"
                    className="form-input"
                    placeholder="e.g. Technova, Legacy, Gyan Mitra"
                    value={festFormData.name}
                    onChange={(e) =>
                      setFestFormData((prev) => ({ ...prev, name: e.target.value }))
                    }
                    required
                    disabled={festSubmitting}
                  />
                  <span className="form-hint">
                    Enter the official name of the university symposium or college festival.
                  </span>
                </div>

                <div className="form-group">
                  <label htmlFor="fest-desc" className="form-label">
                    Description (Optional)
                  </label>
                  <textarea
                    id="fest-desc"
                    rows={3}
                    className="form-input form-textarea"
                    placeholder="e.g. Annual inter-college national level technical symposium hosted by the university."
                    value={festFormData.description}
                    onChange={(e) =>
                      setFestFormData((prev) => ({ ...prev, description: e.target.value }))
                    }
                    disabled={festSubmitting}
                  />
                </div>

                <div className="form-row-2col">
                  <div className="form-group">
                    <label htmlFor="fest-start-date" className="form-label">
                      Start Date (Optional)
                    </label>
                    <input
                      id="fest-start-date"
                      type="date"
                      className="form-input"
                      value={festFormData.start_date}
                      onChange={(e) =>
                        setFestFormData((prev) => ({ ...prev, start_date: e.target.value }))
                      }
                      disabled={festSubmitting}
                    />
                  </div>

                  <div className="form-group">
                    <label htmlFor="fest-end-date" className="form-label">
                      End Date (Optional)
                    </label>
                    <input
                      id="fest-end-date"
                      type="date"
                      className="form-input"
                      value={festFormData.end_date}
                      onChange={(e) =>
                        setFestFormData((prev) => ({ ...prev, end_date: e.target.value }))
                      }
                      disabled={festSubmitting}
                    />
                  </div>
                </div>

                <div className="form-action-footer">
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => setAddFestModalOpen(false)}
                    disabled={festSubmitting}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={festSubmitting}
                  >
                    {festSubmitting ? 'Registering Fest...' : 'Register College Fest'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* ============================================================ */}
      {/* MODAL 6: REMOVE FEST CONFIRMATION */}
      {/* ============================================================ */}
      {deleteFestModal && (
        <div className="modal-backdrop" onClick={() => setDeleteFestModal(null)} aria-hidden="true">
          <div className="modal-window" onClick={(e) => e.stopPropagation()} role="dialog" aria-labelledby="del-fest-title">
            <div className="modal-header">
              <div>
                <span className="modal-tag" style={{ color: 'var(--danger)' }}>Administrative Removal</span>
                <h3 id="del-fest-title" className="modal-title">Remove Fest: {deleteFestModal.name}</h3>
                <span className="modal-subtitle">Verify event preservation and reassignments</span>
              </div>
              <button
                type="button"
                className="modal-close-btn"
                onClick={() => setDeleteFestModal(null)}
                aria-label="Close dialog"
              >
                &times;
              </button>
            </div>

            <div className="modal-body">
              {deleteFestError && (
                <div className="portal-alert portal-alert-error">
                  <span>{deleteFestError}</span>
                </div>
              )}

              <form onSubmit={handleDeleteFestSubmit} className="portal-form">
                {(deleteFestModal.event_count || deleteFestModal.approved_event_count || 0) > 0 ? (
                  <>
                    <div className="portal-alert portal-alert-error" style={{ backgroundColor: 'rgba(239, 68, 68, 0.08)', borderColor: 'var(--danger)' }}>
                      <strong>Event Preservation Protection:</strong> This fest currently has{' '}
                      <strong>{deleteFestModal.event_count || deleteFestModal.approved_event_count}</strong> associated
                      event(s). To protect historical schedules, image analyses, and approval records, all events must be
                      reassigned to another college fest.
                    </div>

                    {festsList.filter(f => f.id !== deleteFestModal.id).length === 0 ? (
                      <p style={{ color: 'var(--danger)', fontSize: '0.875rem' }}>
                        No other fests are available to receive these events. Please create another fest first before removing this one.
                      </p>
                    ) : (
                      <div className="form-group">
                        <label htmlFor="reassign-fest-select" className="form-label">
                          Reassign Existing Events To *
                        </label>
                        <select
                          id="reassign-fest-select"
                          className="form-select"
                          value={deleteTargetReassignId}
                          onChange={(e) => setDeleteTargetReassignId(e.target.value)}
                          required
                          disabled={deleteFestSubmitting}
                        >
                          <option value="">-- Select Destination College Fest * --</option>
                          {festsList
                            .filter(f => f.id !== deleteFestModal.id)
                            .map(f => (
                              <option key={f.id} value={f.id}>
                                {f.name} ({f.approved_event_count || 0} approved events)
                              </option>
                            ))}
                        </select>
                        <span className="form-hint">
                          All approved events, schedules, venue bookings, and surveillance logs will migrate safely.
                        </span>
                      </div>
                    )}
                  </>
                ) : (
                  <p style={{ fontSize: '0.9375rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                    Are you sure you want to remove fest <strong>"{deleteFestModal.name}"</strong>? This fest has no
                    associated events and can be safely deleted.
                  </p>
                )}

                <div className="form-action-footer">
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => setDeleteFestModal(null)}
                    disabled={deleteFestSubmitting}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn btn-secondary"
                    style={{ backgroundColor: 'var(--danger)', color: '#ffffff', borderColor: 'var(--danger)' }}
                    disabled={
                      deleteFestSubmitting ||
                      ((deleteFestModal.event_count || deleteFestModal.approved_event_count || 0) > 0 &&
                        festsList.filter(f => f.id !== deleteFestModal.id).length === 0)
                    }
                  >
                    {deleteFestSubmitting ? 'Removing Fest...' : 'Confirm Remove Fest'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* ============================================================ */}
      {/* MODAL 7: ASSIGN UNASSIGNED EVENT TO FEST */}
      {/* ============================================================ */}
      {assignModalEvent && (
        <div className="modal-backdrop" onClick={() => setAssignModalEvent(null)} aria-hidden="true">
          <div className="modal-window" onClick={(e) => e.stopPropagation()} role="dialog" aria-labelledby="assign-event-title">
            <div className="modal-header">
              <div>
                <span className="modal-tag">Fest Association</span>
                <h3 id="assign-event-title" className="modal-title">Assign Event to College Fest</h3>
                <span className="modal-subtitle">{assignModalEvent.event_name}</span>
              </div>
              <button
                type="button"
                className="modal-close-btn"
                onClick={() => setAssignModalEvent(null)}
                aria-label="Close dialog"
              >
                &times;
              </button>
            </div>

            <div className="modal-body">
              {assignError && (
                <div className="portal-alert portal-alert-error">
                  <span>{assignError}</span>
                </div>
              )}

              <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', marginBottom: '1rem' }}>
                Associate approved event <strong>"{assignModalEvent.event_name}"</strong> (organized by{' '}
                {assignModalEvent.organizer_name}) with an existing college fest.
              </p>

              <form onSubmit={handleAssignEventSubmit} className="portal-form">
                <div className="form-group">
                  <label htmlFor="target-fest-assign" className="form-label">
                    Select College Fest *
                  </label>
                  <select
                    id="target-fest-assign"
                    className="form-select"
                    value={assignFestTargetId}
                    onChange={(e) => setAssignFestTargetId(e.target.value)}
                    required
                    disabled={assignSubmitting}
                  >
                    <option value="">-- Choose College Fest * --</option>
                    {festsList.map(f => (
                      <option key={f.id} value={f.id}>
                        {f.name} ({f.approved_event_count || 0} approved events)
                      </option>
                    ))}
                  </select>
                </div>

                <div className="form-action-footer">
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => setAssignModalEvent(null)}
                    disabled={assignSubmitting}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={assignSubmitting || !assignFestTargetId}
                  >
                    {assignSubmitting ? 'Assigning...' : 'Assign to Fest'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

