/**
 * College Event Management & Crowd Monitoring System
 * Centralized API Service Module
 *
 * Backend URL is defined here and used across all API communications.
 * Uses session-based authentication via credentials: "include".
 * Hostname is matched to window.location (localhost vs 127.0.0.1) to avoid cookie drops.
 */

const API_HOST = typeof window !== 'undefined' && window.location.hostname === '127.0.0.1' 
  ? '127.0.0.1' 
  : 'localhost';

export const API_BASE_URL = import.meta.env?.VITE_API_URL || `http://${API_HOST}:5000/api`;

export function getBackendAssetUrl(path) {
  if (!path) return '';
  if (path.startsWith('http://') || path.startsWith('https://')) return path;
  return `http://${API_HOST}:5000${path.startsWith('/') ? '' : '/'}${path}`;
}

/**
 * Generic request helper with credentials: 'include' and standardized error parsing.
 * Shields frontend users from raw backend stack traces or internal errors.
 * Automatically accommodates FormData uploads without forcing application/json.
 */
async function request(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint}`;
  const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData;

  const defaultHeaders = isFormData
    ? { Accept: 'application/json' }
    : { 'Content-Type': 'application/json', Accept: 'application/json' };

  const config = {
    headers: {
      ...defaultHeaders,
      ...(options.headers || {}),
    },
    credentials: 'include',
    ...options,
  };

  try {
    const response = await fetch(url, config);
    let data = null;

    try {
      data = await response.json();
    } catch {
      data = null;
    }

    if (!response.ok) {
      // Map HTTP status codes to user-friendly error messages
      let message = 'An unexpected error occurred. Please try again.';

      if (response.status === 401) {
        message = data?.message || 'Authentication required. Please sign in.';
      } else if (response.status === 403) {
        message = data?.message || 'Access denied. You do not have permission to perform this action.';
      } else if (response.status === 404) {
        message = data?.message || 'The requested resource was not found.';
      } else if (response.status === 409) {
        message = data?.message || 'Conflict detected. Please check your submission.';
      } else if (response.status === 400) {
        message = data?.message || 'Invalid information provided. Please verify the entered fields.';
      } else if (response.status >= 500) {
        message = 'Server encountered an issue. Please try again later.';
      }

      return {
        ok: false,
        status: response.status,
        data,
        error: message,
      };
    }

    return {
      ok: true,
      status: response.status,
      data,
      error: null,
    };
  } catch (networkError) {
    return {
      ok: false,
      status: 0,
      data: null,
      error: 'Unable to connect to server. Please check your network connection or verify that the backend is running.',
    };
  }
}

// ==========================================================================
// AUTHENTICATION APIs
// ==========================================================================

export async function loginUser(email, password) {
  if (!email || !password) {
    return {
      ok: false,
      status: 400,
      data: null,
      error: 'Email and password are required.',
    };
  }

  return await request('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email: email.trim().toLowerCase(), password }),
  });
}

export async function registerUser({ name, email, password, role = 'organizer', managementCode = '' }) {
  if (!name || !email || !password) {
    return {
      ok: false,
      status: 400,
      data: null,
      error: 'Full name, email address, and password are required.',
    };
  }

  if (password.length < 6) {
    return {
      ok: false,
      status: 400,
      data: null,
      error: 'Password must be at least 6 characters long.',
    };
  }

  const payload = {
    name: name.trim(),
    email: email.trim().toLowerCase(),
    password,
    role: role.toLowerCase(),
  };

  if (role.toLowerCase() === 'management' || role.toLowerCase() === 'administrator') {
    payload.administrator_code = (managementCode || '').trim();
    payload.management_code = (managementCode || '').trim();
  }

  return await request('/auth/register', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function logoutUser() {
  return await request('/auth/logout', {
    method: 'POST',
  });
}

export async function getCurrentUser() {
  const result = await request('/auth/me', {
    method: 'GET',
  });

  if (result.ok && result.data?.authenticated) {
    return {
      ok: true,
      authenticated: true,
      user: result.data.user,
      error: null,
    };
  }

  return {
    ok: false,
    authenticated: false,
    user: null,
    error: result.error || 'Authentication required.',
  };
}

// ==========================================================================
// ORGANIZER DASHBOARD & EVENTS APIs
// ==========================================================================

/**
 * Fetches real-time dashboard data for the authenticated organizer.
 * Returns: { stats, events, upcoming_events }
 */
export async function getOrganizerDashboard() {
  return await request('/organizer/dashboard', {
    method: 'GET',
  });
}

/**
 * Fetches all events created by the authenticated organizer.
 * Returns: { events: [...] }
 */
export async function getOrganizerEvents() {
  return await request('/events', {
    method: 'GET',
  });
}

/**
 * Submits a new event request on behalf of the authenticated organizer.
 * Expected payload:
 * {
 *   event_name: string,
 *   description: string,
 *   requested_date: 'YYYY-MM-DD',
 *   requested_start_time: 'HH:MM:SS',
 *   requested_end_time: 'HH:MM:SS',
 *   category: string,
 *   venue_id: number | null,
 *   series_id: number
 * }
 */
export async function createEvent(eventData) {
  return await request('/events', {
    method: 'POST',
    body: JSON.stringify(eventData),
  });
}

/**
 * Retrieves all campus venues for dropdown selection and availability tracking.
 */
export async function getVenues() {
  return await request('/venues', {
    method: 'GET',
  });
}

/**
 * Retrieves all registered campus fests.
 */
export async function getFests() {
  return await request('/public/fests', {
    method: 'GET',
  });
}

export const getEventSeries = getFests;

/**
 * Retrieves all uploaded crowd photographs for a specific approved event.
 */
export async function getEventImages(eventId) {
  return await request(`/events/${eventId}/images`, {
    method: 'GET',
  });
}

/**
 * Uploads a crowd surveillance photograph for an approved event.
 */
export async function uploadEventImage(eventId, file) {
  const formData = new FormData();
  formData.append('image', file);

  return await request(`/events/${eventId}/images`, {
    method: 'POST',
    body: formData,
  });
}

/**
 * Triggers CSRNet crowd analysis on an uploaded event image by database image ID.
 */
export async function analyzeImage(imageId) {
  return await request(`/images/${imageId}/analyze`, {
    method: 'POST',
  });
}

/**
 * Retrieves existing crowd analysis results for a specific image by image ID.
 */
export async function getImageAnalysis(imageId) {
  return await request(`/images/${imageId}/analysis`, {
    method: 'GET',
  });
}


/**
 * Health check endpoint for system readiness verification.
 */
export async function checkBackendHealth() {
  return await request('/health', {
    method: 'GET',
  });
}

// ==========================================================================
// ADMINISTRATOR PORTAL APIs
// ==========================================================================

/**
 * Fetches real-time system-wide statistics and summary records for College Administrator.
 * Returns: { stats: {...}, pending_requests: [...], upcoming_events: [...], venues: [...] }
 */
export async function getAdministratorDashboard() {
  return await request('/administrator/dashboard', {
    method: 'GET',
  });
}

export const getManagementDashboard = getAdministratorDashboard;

/**
 * Fetches all events across all organizers for administrative oversight.
 * Returns: { events: [...] }
 */
export async function getAdministratorEvents() {
  return await request('/administrator/events', {
    method: 'GET',
  });
}

export const getManagementEvents = getAdministratorEvents;

/**
 * Fetches all pending event requests awaiting administrator review and allocation.
 * Returns: { events: [...] }
 */
export async function getAdministratorPendingEvents() {
  return await request('/administrator/events/pending', {
    method: 'GET',
  });
}

export const getManagementPendingEvents = getAdministratorPendingEvents;

/**
 * Fetches complete event record for administrator inspection.
 */
export async function getAdministratorEvent(eventId) {
  return await request(`/administrator/events/${eventId}`, {
    method: 'GET',
  });
}

export const getManagementEvent = getAdministratorEvent;

/**
 * Updates event status (e.g. approve or reject).
 * When rejecting, an optional rejection_reason string may be provided.
 */
export async function updateEventStatus(eventId, status, rejectionReason = '') {
  return await request(`/administrator/events/${eventId}/status`, {
    method: 'PATCH',
    body: JSON.stringify({
      status,
      rejection_reason: rejectionReason,
    }),
  });
}

/**
 * Allocates final venue and schedule for an event with backend conflict checking.
 * Payload: { venue_id, approved_date, approved_start_time, approved_end_time, expected_participants }
 */
export async function allocateEventSchedule(eventId, { venue_id, approved_date, approved_start_time, approved_end_time, expected_participants }) {
  const body = {
    venue_id: parseInt(venue_id, 10),
    approved_date,
    approved_start_time,
    approved_end_time,
  };
  if (expected_participants !== undefined && expected_participants !== null && expected_participants !== '') {
    body.expected_participants = parseInt(expected_participants, 10);
  }
  return await request(`/administrator/events/${eventId}/allocation`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

/**
 * Creates a new campus venue.
 * Payload: { name, location, capacity, status }
 */
export async function createVenue({ name, location, capacity, status = 'available' }) {
  return await request('/venues', {
    method: 'POST',
    body: JSON.stringify({
      name: name.trim(),
      location: location.trim(),
      capacity: parseInt(capacity, 10) || 0,
      status: status.toLowerCase(),
    }),
  });
}

/**
 * Updates details and status of an existing venue.
 */
export async function updateVenue(venueId, { name, location, capacity, status }) {
  return await request(`/venues/${venueId}`, {
    method: 'PUT',
    body: JSON.stringify({
      name: name.trim(),
      location: location.trim(),
      capacity: parseInt(capacity, 10) || 0,
      status: status.toLowerCase(),
    }),
  });
}

/**
 * Toggles venue availability status ('available' | 'unavailable').
 */
export async function updateVenueStatus(venueId, status) {
  return await request(`/venues/${venueId}/status`, {
    method: 'PATCH',
    body: JSON.stringify({
      status: status.toLowerCase(),
    }),
  });
}

/**
 * Deletes a venue if no events are associated with it.
 */
export async function deleteVenue(venueId) {
  return await request(`/venues/${venueId}`, {
    method: 'DELETE',
  });
}

/**
 * Fetches administrator list of campus fests.
 */
export async function getAdministratorFests() {
  return await request('/administrator/fests', {
    method: 'GET',
  });
}

export const getManagementEventSeries = getAdministratorFests;

/**
 * Creates a new campus fest.
 */
export async function createFest({ name, description, start_date, end_date }) {
  return await request('/administrator/fests', {
    method: 'POST',
    body: JSON.stringify({
      name: name?.trim(),
      description: description?.trim() || null,
      start_date: start_date?.trim() || null,
      end_date: end_date?.trim() || null,
    }),
  });
}

/**
 * Safely removes a fest record.
 * Supports optional reassign_to ID to safely migrate associated events.
 */
export async function deleteFest(festId, { reassign_to = null } = {}) {
  const options = {
    method: 'DELETE',
  };
  if (reassign_to) {
    options.body = JSON.stringify({ reassign_to: parseInt(reassign_to, 10) });
  }
  return await request(`/administrator/fests/${festId}`, options);
}

/**
 * Fetches approved events belonging to a specific fest.
 */
export async function getFestApprovedEvents(festId) {
  return await request(`/administrator/fests/${festId}/approved-events`, {
    method: 'GET',
  });
}

/**
 * Fetches approved events that currently have no fest assigned.
 */
export async function getUnassignedApprovedEvents() {
  return await request('/administrator/events/unassigned-approved', {
    method: 'GET',
  });
}

/**
 * Assigns or reassigns an event to a fest.
 */
export async function assignEventToFest(eventId, seriesId) {
  return await request(`/administrator/events/${eventId}/assign-fest`, {
    method: 'PATCH',
    body: JSON.stringify({ series_id: seriesId ? parseInt(seriesId, 10) : null }),
  });
}

// ==========================================================================
// STUDENT & PUBLIC EVENT DISCOVERY APIs
// ==========================================================================

/**
 * Fetches approved public campus events with optional filtering.
 * Filter options: { search, category, status, year, month, series_id, limit }
 */
export async function getPublicEvents(filters = {}) {
  const params = new URLSearchParams();
  if (filters.search && filters.search.trim()) {
    params.append('search', filters.search.trim());
  }
  if (filters.category && filters.category !== 'all') {
    params.append('category', filters.category);
  }
  if (filters.status && filters.status !== 'all') {
    params.append('status', filters.status.toLowerCase());
  }
  if (filters.year) {
    params.append('year', filters.year);
  }
  if (filters.month) {
    params.append('month', filters.month);
  }
  if (filters.series_id) {
    params.append('series_id', filters.series_id);
  }
  if (filters.limit) {
    params.append('limit', filters.limit);
  }

  const queryString = params.toString();
  const endpoint = queryString ? `/public/events?${queryString}` : '/public/events';
  return await request(endpoint, {
    method: 'GET',
  });
}

/**
 * Fetches single approved event details with real crowd analysis info.
 */
export async function getPublicEventDetail(eventId) {
  return await request(`/public/events/${eventId}`, {
    method: 'GET',
  });
}

/**
 * Fetches distinct categories and active years for filtering.
 */
export async function getPublicCategories() {
  return await request('/public/categories', {
    method: 'GET',
  });
}

/**
 * Fetches single fest with associated events.
 */
export async function getPublicFestDetail(seriesId) {
  return await request(`/public/fests/${seriesId}`, {
    method: 'GET',
  });
}

export const getPublicSeriesDetail = getPublicFestDetail;

/**
 * Fetches all campus venues with directions and location guide.
 */
export async function getPublicVenues() {
  return await request('/public/venues', {
    method: 'GET',
  });
}

// ==========================================================================
// CROWD REPORTS & AUDIT APIs
// ==========================================================================

/**
 * Fetches all events accessible to the user for crowd report generation.
 */
export async function getReportEvents() {
  return await request('/reports/events', {
    method: 'GET',
  });
}

/**
 * Fetches comprehensive crowd analysis report for a specific event.
 */
export async function getEventReport(eventId) {
  return await request(`/reports/events/${eventId}`, {
    method: 'GET',
  });
}

/**
 * Downloads official PDF crowd report for a specific event.
 */
export async function downloadEventReportPdf(eventId, eventName = '') {
  const url = `${API_BASE_URL}/reports/events/${eventId}/pdf`;
  try {
    const response = await fetch(url, {
      method: 'GET',
      credentials: 'include',
    });

    if (!response.ok) {
      let errorMsg = 'Failed to download PDF report.';
      try {
        const errorData = await response.json();
        if (errorData?.message) errorMsg = errorData.message;
      } catch {
        // response was not JSON
      }
      return { ok: false, error: errorMsg };
    }

    const blob = await response.blob();
    const downloadUrl = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = downloadUrl;
    const sanitizedName = (eventName || `event_${eventId}`).replace(/[^a-zA-Z0-9_-]/g, '_');
    link.download = `crowd_report_${sanitizedName}.pdf`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(downloadUrl);
    return { ok: true };
  } catch {
    return {
      ok: false,
      error: 'Network connection issue while downloading report PDF.',
    };
  }
}

// ==========================================================================
// REAL-TIME CROWD SAFETY ALERTS APIs
// ==========================================================================

/**
 * Fetches real-time crowd safety threshold alerts.
 * Optional params: { unread_only: boolean, event_id: number, scope: 'user'|'all' }
 */
export async function getAlerts(params = {}) {
  const query = new URLSearchParams();
  if (params.unread_only) query.append('unread_only', 'true');
  if (params.event_id) query.append('event_id', String(params.event_id));
  if (params.scope) query.append('scope', params.scope);
  const qs = query.toString() ? `?${query.toString()}` : '';
  return await request(`/alerts${qs}`, {
    method: 'GET',
  });
}

/**
 * Fetches count of unread crowd safety alerts for badge counters.
 */
export async function getUnreadAlertsCount() {
  return await request('/alerts/unread-count', {
    method: 'GET',
  });
}

/**
 * Acknowledges and marks an individual alert as read.
 */
export async function markAlertRead(alertId) {
  return await request(`/alerts/${alertId}/read`, {
    method: 'PATCH',
  });
}

/**
 * Marks all unread alerts as read for the current user.
 */
export async function markAllAlertsRead() {
  return await request('/alerts/mark-all-read', {
    method: 'POST',
  });
}

