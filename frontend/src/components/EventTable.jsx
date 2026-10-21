import React from 'react';
import StatusBadge from './StatusBadge';
import { getEventHappeningInfo } from '../utils/eventStatus';

/**
 * Helper to format ISO date string (YYYY-MM-DD) into readable institutional format.
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
 * Helper to format 24h time strings (HH:MM:SS or HH:MM) into a clean range.
 */
function formatTimeRange(startStr, endStr) {
  if (!startStr) return 'Schedule pending';
  const cleanStart = startStr.substring(0, 5);
  if (!endStr) return cleanStart;
  const cleanEnd = endStr.substring(0, 5);
  return `${cleanStart} – ${cleanEnd}`;
}

/**
 * Reusable Event Table Component
 * Displays organizer events with status badges, venue info, and action triggers.
 */
export default function EventTable({
  events = [],
  onCreateEvent,
  onUploadImage,
  showUploadAction = true,
  emptyMessage = 'No events found.',
  emptyActionLabel = 'Create your first event',
}) {
  if (!events || events.length === 0) {
    return (
      <div className="table-empty-state">
        <div className="empty-state-icon" aria-hidden="true">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
            <line x1="16" y1="2" x2="16" y2="6" />
            <line x1="8" y1="2" x2="8" y2="6" />
            <line x1="3" y1="10" x2="21" y2="10" />
          </svg>
        </div>
        <h4 className="empty-state-title">No events yet</h4>
        <p className="empty-state-desc">{emptyMessage}</p>
        {onCreateEvent && (
          <button
            type="button"
            className="btn btn-primary btn-sm empty-state-btn"
            onClick={onCreateEvent}
          >
            + {emptyActionLabel}
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="table-responsive-wrapper">
      <table className="institutional-table" aria-label="Organizer Events List">
        <thead>
          <tr>
            <th scope="col">Event Details</th>
            <th scope="col">Fest / Category</th>
            <th scope="col">Date</th>
            <th scope="col">Time</th>
            <th scope="col">Venue</th>
            <th scope="col">Status</th>
            {showUploadAction && <th scope="col" style={{ textAlign: 'right' }}>Actions</th>}
          </tr>
        </thead>
        <tbody>
          {events.map((ev) => {
            const displayDate = ev.status === 'approved' && ev.approved_date
              ? ev.approved_date
              : ev.requested_date;

            const startTime = ev.status === 'approved' && ev.approved_start_time
              ? ev.approved_start_time
              : ev.requested_start_time;

            const endTime = ev.status === 'approved' && ev.approved_end_time
              ? ev.approved_end_time
              : ev.requested_end_time;

            const venueName = ev.venue_name || 'Venue to be assigned';
            const venueLocation = ev.venue_location ? `(${ev.venue_location})` : '';

            return (
              <tr key={ev.id}>
                {/* Event Name & Description preview */}
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
                    {ev.status === 'rejected' && ev.rejection_reason && (
                      <span className="table-rejection-note">
                        Reason: {ev.rejection_reason}
                      </span>
                    )}
                  </div>
                </td>

                {/* Fest & Category */}
                <td>
                  <div className="table-meta-stack">
                    <span className="table-fest-tag">{ev.series_name || 'Independent Event'}</span>
                    <span className="table-category-label">{ev.category || 'General'}</span>
                  </div>
                </td>

                {/* Date */}
                <td>
                  <span className="table-date-text">{formatDate(displayDate)}</span>
                </td>

                {/* Time */}
                <td>
                  <span className="table-time-text">{formatTimeRange(startTime, endTime)}</span>
                </td>

                {/* Venue */}
                <td>
                  <div className="table-venue-stack">
                    <span className="table-venue-name">{venueName}</span>
                    {venueLocation && <span className="table-venue-sub">{venueLocation}</span>}
                  </div>
                </td>

                {/* Status Badge */}
                <td>
                  <StatusBadge status={ev.status} />
                </td>

                {/* Actions */}
                {showUploadAction && (
                  <td style={{ textAlign: 'right' }}>
                    {ev.status === 'approved' && onUploadImage ? (
                      (() => {
                        const happeningInfo = getEventHappeningInfo(ev);
                        if (happeningInfo.isHappening) {
                          return (
                            <button
                              type="button"
                              className="btn btn-primary btn-sm btn-upload-live"
                              onClick={() => onUploadImage(ev)}
                              title="Upload crowd monitoring photograph (Event is happening now)"
                              data-testid={`upload-photo-btn-${ev.id}`}
                            >
                              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                                <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                                <circle cx="8.5" cy="8.5" r="1.5" />
                                <polyline points="21 15 16 10 5 21" />
                              </svg>
                              <span>Photo Upload</span>
                            </button>
                          );
                        }
                        return (
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm btn-upload-blocked"
                            disabled
                            aria-disabled="true"
                            title={`Photo upload blocked: ${happeningInfo.reason}`}
                            data-testid={`upload-blocked-btn-${ev.id}`}
                          >
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                              <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                              <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                            </svg>
                            <span>Upload Blocked</span>
                          </button>
                        );
                      })()
                    ) : (
                      <span className="table-action-muted">—</span>
                    )}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
