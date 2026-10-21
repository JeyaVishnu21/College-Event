import React from 'react';

/**
 * Reusable Loading Spinner Component
 * Displays a clean, institutional spinner with an optional status label.
 */
export default function Loading({ message = 'Loading...', fullScreen = false }) {
  const content = (
    <div className="loading-container" role="status" aria-live="polite">
      <div className="loading-spinner" aria-hidden="true" />
      {message && <p className="loading-text">{message}</p>}
      <span className="sr-only">{message}</span>
    </div>
  );

  if (fullScreen) {
    return <div className="loading-fullscreen-overlay">{content}</div>;
  }

  return content;
}
