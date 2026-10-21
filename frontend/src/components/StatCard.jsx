import React from 'react';

/**
 * Reusable Metric/Stat Card Component
 * Displays institutional KPIs with clean numbers, labels, contextual subtext,
 * and restrained status accents.
 */
export default function StatCard({
  title,
  value,
  subtitle,
  icon,
  variant = 'default',
  onClick,
}) {
  const isClickable = Boolean(onClick);

  return (
    <div
      className={`stat-card stat-card-${variant} ${isClickable ? 'stat-card-clickable' : ''}`}
      onClick={onClick}
      role={isClickable ? 'button' : undefined}
      tabIndex={isClickable ? 0 : undefined}
      onKeyDown={
        isClickable
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onClick();
              }
            }
          : undefined
      }
    >
      <div className="stat-card-header">
        <span className="stat-card-title">{title}</span>
        {icon && <div className="stat-card-icon" aria-hidden="true">{icon}</div>}
      </div>
      <div className="stat-card-body">
        <span className="stat-card-value">
          {value !== undefined && value !== null ? value : '—'}
        </span>
        {subtitle && <span className="stat-card-subtitle">{subtitle}</span>}
      </div>
    </div>
  );
}
