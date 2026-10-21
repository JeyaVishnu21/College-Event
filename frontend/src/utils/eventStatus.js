/**
 * Event Happening & Timing Status Utility
 * 
 * Provides unified helper functions to check whether an event is actively happening,
 * ensuring organizers are only permitted to upload crowd surveillance photographs
 * during ongoing events according to management's final approved schedule.
 */

let serverClockOffsetMs = 0;
let serverTzOffsetMinutes = null;

/**
 * Synchronizes the client clock with the backend server's timestamp and timezone.
 * @param {string|null|undefined} serverNowIso 
 * @param {string|null|undefined} tzOffsetStr 
 */
export function syncServerTime(serverNowIso, tzOffsetStr) {
  if (serverNowIso) {
    try {
      const parsed = new Date(serverNowIso);
      if (!isNaN(parsed.getTime())) {
        serverClockOffsetMs = parsed.getTime() - Date.now();
      }
      const rawOffset = tzOffsetStr || (serverNowIso.match(/([+-]\d{2}:?\d{2})$/) || [])[1];
      if (rawOffset) {
        const clean = rawOffset.replace(':', '');
        const sign = clean[0] === '-' ? -1 : 1;
        const hours = parseInt(clean.substring(1, 3), 10);
        const mins = parseInt(clean.substring(3, 5), 10);
        if (!isNaN(hours) && !isNaN(mins)) {
          serverTzOffsetMinutes = sign * (hours * 60 + mins);
        }
      }
    } catch {
      // Fallback to local system time
    }
  }
}

/**
 * Gets the current Date object in the server's timezone.
 * @param {Date|null|undefined} referenceDate 
 * @returns {Date}
 */
export function getCurrentServerDate(referenceDate) {
  const base = referenceDate instanceof Date ? referenceDate : new Date(Date.now() + serverClockOffsetMs);
  if (serverTzOffsetMinutes !== null) {
    const utcMs = base.getTime() + (base.getTimezoneOffset() * 60000);
    return new Date(utcMs + (serverTzOffsetMinutes * 60000));
  }
  return base;
}

/**
 * Parses time string (HH:MM:SS or HH:MM) into seconds since midnight.
 * @param {string|null|undefined} tStr 
 * @returns {number|null}
 */
export function parseTimeToSeconds(tStr) {
  if (!tStr) return null;
  const str = String(tStr).trim();
  const parts = str.split(':');
  if (parts.length >= 2) {
    const hours = parseInt(parts[0], 10);
    const minutes = parseInt(parts[1], 10);
    const seconds = parts.length > 2 ? parseInt(parts[2], 10) : 0;
    if (!isNaN(hours) && !isNaN(minutes) && !isNaN(seconds)) {
      return hours * 3600 + minutes * 60 + seconds;
    }
  }
  return null;
}

/**
 * Normalizes date value to YYYY-MM-DD string.
 * @param {string|Date|null|undefined} dateVal 
 * @returns {string}
 */
export function normalizeDateStr(dateVal) {
  if (!dateVal) return '';
  if (typeof dateVal === 'string') {
    return dateVal.split('T')[0];
  }
  if (dateVal instanceof Date && !isNaN(dateVal.getTime())) {
    const y = dateVal.getFullYear();
    const m = String(dateVal.getMonth() + 1).padStart(2, '0');
    const d = String(dateVal.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
  }
  return '';
}

/**
 * Evaluates whether an event is currently happening.
 * Returns an object with isHappening boolean and descriptive feedback.
 * 
 * Strict Requirements:
 * 1. Event status must be 'approved'.
 * 2. Uses management's final approved schedule (approved_date, approved_start_time, approved_end_time).
 *    Never uses requested schedule for happening checks.
 * 3. Event final scheduled date is today (server date).
 * 4. Current server time satisfies start_time <= current_time < end_time.
 * 5. Blocks before start time, at or after end time, on other dates, and for missing/invalid schedules.
 * 
 * @param {Object} event 
 * @param {Date|null|undefined} referenceDate Optional date for deterministic testing
 * @returns {{
 *   isHappening: boolean,
 *   reason: string,
 *   badgeText: string,
 *   badgeClass: string
 * }}
 */
export function getEventHappeningInfo(event, referenceDate = null) {
  if (!event) {
    return {
      isHappening: false,
      reason: 'No event details available.',
      badgeText: 'Inactive',
      badgeClass: 'badge-muted',
    };
  }

  // 1. Status Check: Must be approved (or explicitly ongoing)
  const rawStatus = (event.status || '').toLowerCase();
  if (rawStatus !== 'approved' && rawStatus !== 'ongoing') {
    const statusLabel = event.status
      ? event.status.charAt(0).toUpperCase() + event.status.slice(1)
      : 'Not Approved';
    return {
      isHappening: false,
      reason: `Photo upload is blocked: event status is '${statusLabel.toLowerCase()}'. Photos can only be uploaded for approved events.`,
      badgeText: statusLabel,
      badgeClass: 'badge-muted',
    };
  }

  // 2. Final Schedule Validation: Management allocated approved_date, approved_start_time, approved_end_time
  const dateVal = event.approved_date;
  const startTimeVal = event.approved_start_time;
  const endTimeVal = event.approved_end_time;

  if (!dateVal || !startTimeVal || !endTimeVal) {
    return {
      isHappening: false,
      reason: 'Photo upload is blocked: event does not have a confirmed management-approved schedule.',
      badgeText: 'Schedule Pending',
      badgeClass: 'badge-muted',
    };
  }

  const evDateStr = normalizeDateStr(dateVal);
  if (!evDateStr) {
    return {
      isHappening: false,
      reason: 'Photo upload is blocked: invalid approved event date.',
      badgeText: 'Date Invalid',
      badgeClass: 'badge-muted',
    };
  }

  const startSec = parseTimeToSeconds(startTimeVal);
  const endSec = parseTimeToSeconds(endTimeVal);

  if (startSec === null || endSec === null) {
    return {
      isHappening: false,
      reason: 'Photo upload is blocked: invalid approved schedule times.',
      badgeText: 'Time Invalid',
      badgeClass: 'badge-muted',
    };
  }

  if (startSec >= endSec) {
    return {
      isHappening: false,
      reason: 'Photo upload is blocked: approved start time must precede end time.',
      badgeText: 'Schedule Invalid',
      badgeClass: 'badge-muted',
    };
  }

  // 3. Server-Consistent Date & Time Check
  const now = getCurrentServerDate(referenceDate);
  const nowY = now.getFullYear();
  const nowM = String(now.getMonth() + 1).padStart(2, '0');
  const nowD = String(now.getDate()).padStart(2, '0');
  const todayStr = `${nowY}-${nowM}-${nowD}`;
  const nowSeconds = now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds();

  // Past event
  if (evDateStr < todayStr) {
    return {
      isHappening: false,
      reason: `Photo upload is blocked: event concluded on ${evDateStr}.`,
      badgeText: 'Concluded',
      badgeClass: 'badge-concluded',
    };
  }

  // Future event
  if (evDateStr > todayStr) {
    return {
      isHappening: false,
      reason: `Photo upload is blocked: event is scheduled for ${evDateStr}. Uploads open on the event date.`,
      badgeText: 'Upcoming',
      badgeClass: 'badge-upcoming',
    };
  }

  // Event is today! Check times: start_time <= current_time < end_time
  if (nowSeconds < startSec) {
    const startStr = String(startTimeVal).substring(0, 5);
    return {
      isHappening: false,
      reason: `Photo upload is blocked: event starts today at ${startStr}. Uploads open when the event starts.`,
      badgeText: `Starts ${startStr}`,
      badgeClass: 'badge-upcoming',
    };
  }

  if (nowSeconds >= endSec) {
    const endStr = String(endTimeVal).substring(0, 5);
    return {
      isHappening: false,
      reason: `Photo upload is blocked: event concluded today at ${endStr}.`,
      badgeText: 'Concluded',
      badgeClass: 'badge-concluded',
    };
  }

  return {
    isHappening: true,
    reason: 'Event is currently happening live! Photo upload is active.',
    badgeText: 'Happening Now',
    badgeClass: 'badge-happening-live',
  };
}

/**
 * Boolean helper to check if an event is currently happening.
 * @param {Object} event 
 * @param {Date|null|undefined} referenceDate
 * @returns {boolean}
 */
export function isEventHappening(event, referenceDate = null) {
  return getEventHappeningInfo(event, referenceDate).isHappening;
}
