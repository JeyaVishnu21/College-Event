import React from 'react';

/**
 * Reusable Status Badge Component
 * Renders restrained, accessible institutional status badges.
 * Supports: pending, approved, rejected, completed, ongoing.
 */
export default function StatusBadge({ status }) {
  const normalized = (status || 'pending').toLowerCase();

  const statusConfig = {
    pending: {
      label: 'Pending Review',
      className: 'badge-pending',
    },
    approved: {
      label: 'Approved',
      className: 'badge-approved',
    },
    rejected: {
      label: 'Rejected',
      className: 'badge-rejected',
    },
    completed: {
      label: 'Completed',
      className: 'badge-completed',
    },
    ongoing: {
      label: 'Ongoing',
      className: 'badge-ongoing',
    },
    upcoming: {
      label: 'Upcoming',
      className: 'badge-upcoming',
    },
  };

  const current = statusConfig[normalized] || {
    label: status || 'Unknown',
    className: 'badge-default',
  };

  return (
    <span className={`status-badge ${current.className}`}>
      <span className="status-badge-dot" aria-hidden="true" />
      <span>{current.label}</span>
    </span>
  );
}
