import React, { useState, useEffect } from 'react';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { getUnreadAlertsCount } from '../services/api';

/**
 * Auto-Hiding Left Navigation Sidebar Component
 * -------------------------------------------------------------
 * Dynamically role & dashboard aware:
 * 1. On /organizer:
 *    - Moving cursor to left reveals the Organizer Portal Navigation (all 8 workspace & safety tabs).
 *    - Clicking any tab switches the organizer dashboard tab.
 * 2. On /management:
 *    - Moving cursor to left reveals the Management Console Navigation (all 9 oversight & telemetry tabs).
 *    - Clicking any tab switches the management dashboard tab.
 * 3. On Public pages (/, /fest/:id, /event/:id, /login, /register):
 *    - Moving cursor to left reveals the Campus Event Portal discovery navigation.
 * 4. Auto-hides on mouseLeave so the dashboard or page occupies 100% full screen width!
 */
export default function Sidebar() {
  const { user, logout } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // Detect which dashboard the user is currently viewing
  const isOrganizer = location.pathname.startsWith('/organizer');
  const isAdministrator = location.pathname.startsWith('/administrator') || location.pathname.startsWith('/management');
  const isManagement = isAdministrator;
  const currentTab = searchParams.get('tab') || 'dashboard';
  const [unreadAlertCount, setUnreadAlertCount] = useState(0);

  // Poll/fetch unread alert count for badge indicator
  useEffect(() => {
    if (user) {
      getUnreadAlertsCount().then((res) => {
        if (res.ok && typeof res.data?.unread_count === 'number') {
          setUnreadAlertCount(res.data.unread_count);
        }
      }).catch(() => {});
    }
  }, [user, location.pathname, currentTab]);

  // Auto-close on route change
  useEffect(() => {
    setIsOpen(false);
  }, [location.pathname]);

  const isActive = (path) => location.pathname === path;

  const handleLogout = async () => {
    setIsOpen(false);
    await logout();
    navigate('/login');
  };

  // Switch tabs inside Organizer or Management Dashboard
  const handleTabSelect = (tabId) => {
    navigate(`${location.pathname}?tab=${tabId}`);
    window.dispatchEvent(new CustomEvent('portal-tab-select', { detail: { tab: tabId } }));
    setIsOpen(false);
  };

  const handleAnchorClick = (e, targetId) => {
    setIsOpen(false);
    if (location.pathname === '/') {
      e.preventDefault();
      const el = document.getElementById(targetId);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth' });
      }
    }
  };

  return (
    <>
      {/* 1. Left Edge Hover Sensor Zone (detects mouse hovering near the left border) */}
      <div
        className="sidebar-edge-sensor"
        onMouseEnter={() => setIsOpen(true)}
        aria-hidden="true"
      />

      {/* 2. Floating Minimal Menu Trigger Button on Top-Left */}
      <button
        type="button"
        className={`sidebar-floating-toggle ${isOpen ? 'toggle-active' : ''} ${
          isOrganizer ? 'toggle-organizer' : isManagement ? 'toggle-management' : ''
        }`}
        onClick={() => setIsOpen(!isOpen)}
        onMouseEnter={() => setIsOpen(true)}
        aria-label="Toggle Navigation"
        title="Hover or click to open Navigation"
      >
        <div className="sft-icon" aria-hidden="true">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="3" y1="12" x2="21" y2="12" />
            <line x1="3" y1="6" x2="21" y2="6" />
            <line x1="3" y1="18" x2="21" y2="18" />
          </svg>
        </div>
        <span className="sft-label">
          {isOrganizer ? 'Organizer Menu' : isAdministrator ? 'Administrator Menu' : 'Menu'}
        </span>
      </button>

      {/* 3. Backdrop for Mobile Devices */}
      {isOpen && (
        <div
          className="sidebar-backdrop"
          onClick={() => setIsOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* 4. Left Sidebar Drawer (Slides in on hover; auto-hides on mouseLeave) */}
      <aside
        className={`left-flyout-sidebar ${isOpen ? 'sidebar-visible' : ''} ${
          isOrganizer ? 'sidebar-theme-organizer' : isAdministrator ? 'sidebar-theme-administrator sidebar-theme-management' : ''
        }`}
        onMouseEnter={() => setIsOpen(true)}
        onMouseLeave={() => setIsOpen(false)}
        aria-label="Portal Navigation Drawer"
      >
        {/* ============================================================== */}
        {/* CASE A: ORGANIZER DASHBOARD NAVIGATION DRAWER                   */}
        {/* ============================================================== */}
        {isOrganizer && (
          <>
            <div className="flyout-header">
              <div className="flyout-brand">
                <div className="flyout-brand-emblem emblem-organizer" aria-hidden="true">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M18 20V10" />
                    <path d="M12 20V4" />
                    <path d="M6 20v-6" />
                  </svg>
                </div>
                <div className="flyout-brand-text">
                  <span className="flyout-brand-title">Organizer Portal</span>
                  <span className="flyout-brand-sub">Campus Event Operations Desk</span>
                </div>
              </div>
              <button
                type="button"
                className="flyout-close-btn"
                onClick={() => setIsOpen(false)}
                aria-label="Close navigation"
              >
                &times;
              </button>
            </div>

            <nav className="flyout-nav-body">
              <span className="flyout-section-heading">WORKSPACE</span>

              <button
                type="button"
                className={`flyout-nav-tab-btn ${currentTab === 'dashboard' ? 'active' : ''}`}
                onClick={() => handleTabSelect('dashboard')}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="3" y="3" width="7" height="7" />
                  <rect x="14" y="3" width="7" height="7" />
                  <rect x="14" y="14" width="7" height="7" />
                  <rect x="3" y="14" width="7" height="7" />
                </svg>
                <span>Dashboard Overview</span>
              </button>

              <button
                type="button"
                className={`flyout-nav-tab-btn ${currentTab === 'create' ? 'active' : ''}`}
                onClick={() => handleTabSelect('create')}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="12" y1="5" x2="12" y2="19" />
                  <line x1="5" y1="12" x2="19" y2="12" />
                </svg>
                <span>Create Event</span>
              </button>

              <button
                type="button"
                className={`flyout-nav-tab-btn ${currentTab === 'my-events' || currentTab === 'schedule' ? 'active' : ''}`}
                onClick={() => handleTabSelect('my-events')}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="16" y1="13" x2="8" y2="13" />
                  <line x1="16" y1="17" x2="8" y2="17" />
                  <polyline points="10 9 9 9 8 9" />
                </svg>
                <span>My Events &amp; Schedule</span>
              </button>

              <button
                type="button"
                className={`flyout-nav-tab-btn ${currentTab === 'venue-requests' ? 'active' : ''}`}
                onClick={() => handleTabSelect('venue-requests')}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M3 21h18" />
                  <path d="M5 21V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16" />
                  <path d="M9 9h1" />
                  <path d="M9 13h1" />
                  <path d="M14 9h1" />
                  <path d="M14 13h1" />
                </svg>
                <span>Venue Requests</span>
              </button>

              <span className="flyout-section-heading" style={{ marginTop: '1.15rem' }}>
                SAFETY &amp; SURVEILLANCE
              </span>

              <button
                type="button"
                className={`flyout-nav-tab-btn ${currentTab === 'crowd-monitoring' ? 'active' : ''}`}
                onClick={() => handleTabSelect('crowd-monitoring')}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                  <circle cx="9" cy="7" r="4" />
                  <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                  <path d="M16 3.13a4 4 0 0 1 0 7.75" />
                </svg>
                <span>Crowd Monitoring</span>
              </button>

              <button
                type="button"
                className={`flyout-nav-tab-btn ${currentTab === 'crowd-alerts' ? 'active' : ''}`}
                onClick={() => handleTabSelect('crowd-alerts')}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                  <line x1="12" y1="9" x2="12" y2="13" />
                  <line x1="12" y1="17" x2="12.01" y2="17" />
                </svg>
                <span>Crowd Alerts</span>
                {unreadAlertCount > 0 && (
                  <span className="badge badge-danger" style={{ marginLeft: 'auto', fontSize: '0.7rem', padding: '0.1rem 0.45rem', borderRadius: '9999px' }}>
                    {unreadAlertCount}
                  </span>
                )}
              </button>

              <button
                type="button"
                className={`flyout-nav-tab-btn ${currentTab === 'analysis-history' ? 'active' : ''}`}
                onClick={() => handleTabSelect('analysis-history')}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="10" />
                  <polyline points="12 6 12 12 16 14" />
                </svg>
                <span>Analysis History</span>
              </button>

              <button
                type="button"
                className={`flyout-nav-tab-btn ${currentTab === 'crowd-reports' ? 'active' : ''}`}
                onClick={() => handleTabSelect('crowd-reports')}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="18" y1="20" x2="18" y2="10" />
                  <line x1="12" y1="20" x2="12" y2="4" />
                  <line x1="6" y1="20" x2="6" y2="14" />
                </svg>
                <span>Analytics &amp; Peak Reports</span>
              </button>

              <span className="flyout-section-heading" style={{ marginTop: '1.15rem' }}>
                CAMPUS PORTAL
              </span>

              <Link
                to="/"
                className="flyout-nav-link"
                onClick={() => setIsOpen(false)}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="19" y1="12" x2="5" y2="12" />
                  <polyline points="12 19 5 12 12 5" />
                </svg>
                <span>Campus Pulse Home</span>
              </Link>
            </nav>

            <div className="flyout-bottom-action">
              <div className="flyout-user-box">
                <div className="fub-info">
                  <span className="fub-name">{user?.name || 'Organizer'}</span>
                  <span className="fub-role-tag role-organizer">Organizer</span>
                </div>
                <button
                  type="button"
                  className="fub-logout-btn"
                  onClick={handleLogout}
                >
                  Sign Out
                </button>
              </div>
            </div>
          </>
        )}

        {/* ============================================================== */}
        {/* CASE B: ADMINISTRATOR DASHBOARD NAVIGATION DRAWER             */}
        {/* ============================================================== */}
        {isAdministrator && (
          <>
            <div className="flyout-header">
              <div className="flyout-brand">
                <div className="flyout-brand-emblem emblem-administrator emblem-management" aria-hidden="true">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="3" y="3" width="18" height="18" rx="2" />
                    <line x1="3" y1="9" x2="21" y2="9" />
                    <line x1="9" y1="21" x2="9" y2="9" />
                  </svg>
                </div>
                <div className="flyout-brand-text">
                  <span className="flyout-brand-title">Administrator Console</span>
                  <span className="flyout-brand-sub">Executive Oversight &amp; Governance</span>
                </div>
              </div>
              <button
                type="button"
                className="flyout-close-btn"
                onClick={() => setIsOpen(false)}
                aria-label="Close navigation"
              >
                &times;
              </button>
            </div>

            <nav className="flyout-nav-body">
              <span className="flyout-section-heading">OPERATIONAL OVERSIGHT</span>

              <button
                type="button"
                className={`flyout-nav-tab-btn ${currentTab === 'dashboard' ? 'active' : ''}`}
                onClick={() => handleTabSelect('dashboard')}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="3" y="3" width="7" height="7" />
                  <rect x="14" y="3" width="7" height="7" />
                  <rect x="14" y="14" width="7" height="7" />
                  <rect x="3" y="14" width="7" height="7" />
                </svg>
                <span>Console Overview</span>
              </button>

              <button
                type="button"
                className={`flyout-nav-tab-btn ${currentTab === 'event-requests' ? 'active' : ''}`}
                onClick={() => handleTabSelect('event-requests')}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="9 11 12 14 22 4" />
                  <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
                </svg>
                <span>Event Proposals &amp; Review</span>
              </button>

              <button
                type="button"
                className={`flyout-nav-tab-btn ${currentTab === 'all-events' ? 'active' : ''}`}
                onClick={() => handleTabSelect('all-events')}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="8" y1="6" x2="21" y2="6" />
                  <line x1="8" y1="12" x2="21" y2="12" />
                  <line x1="8" y1="18" x2="21" y2="18" />
                  <line x1="3" y1="6" x2="3.01" y2="6" />
                  <line x1="3" y1="12" x2="3.01" y2="12" />
                  <line x1="3" y1="18" x2="3.01" y2="18" />
                </svg>
                <span>Events Registry</span>
              </button>

              <button
                type="button"
                className={`flyout-nav-tab-btn ${currentTab === 'venues' ? 'active' : ''}`}
                onClick={() => handleTabSelect('venues')}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M3 21h18" />
                  <path d="M5 21V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16" />
                  <path d="M9 9h1" />
                  <path d="M9 13h1" />
                  <path d="M14 9h1" />
                  <path d="M14 13h1" />
                </svg>
                <span>Campus Venues</span>
              </button>

              <span className="flyout-section-heading" style={{ marginTop: '1.15rem' }}>
                SAFETY &amp; TELEMETRY
              </span>

              <button
                type="button"
                className={`flyout-nav-tab-btn ${currentTab === 'crowd-monitoring' ? 'active' : ''}`}
                onClick={() => handleTabSelect('crowd-monitoring')}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                  <circle cx="9" cy="7" r="4" />
                  <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                  <path d="M16 3.13a4 4 0 0 1 0 7.75" />
                </svg>
                <span>Crowd Density Console</span>
              </button>

              <button
                type="button"
                className={`flyout-nav-tab-btn ${currentTab === 'crowd-alerts' ? 'active' : ''}`}
                onClick={() => handleTabSelect('crowd-alerts')}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                  <line x1="12" y1="9" x2="12" y2="13" />
                  <line x1="12" y1="17" x2="12.01" y2="17" />
                </svg>
                <span>Threshold Alerts</span>
                {unreadAlertCount > 0 && (
                  <span className="badge badge-danger" style={{ marginLeft: 'auto', fontSize: '0.7rem', padding: '0.1rem 0.45rem', borderRadius: '9999px' }}>
                    {unreadAlertCount}
                  </span>
                )}
              </button>

              <button
                type="button"
                className={`flyout-nav-tab-btn ${currentTab === 'crowd-reports' ? 'active' : ''}`}
                onClick={() => handleTabSelect('crowd-reports')}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="18" y1="20" x2="18" y2="10" />
                  <line x1="12" y1="20" x2="12" y2="4" />
                  <line x1="6" y1="20" x2="6" y2="14" />
                </svg>
                <span>Analytics &amp; Peak Reports</span>
              </button>

              <button
                type="button"
                className={`flyout-nav-tab-btn ${currentTab === 'event-history' ? 'active' : ''}`}
                onClick={() => handleTabSelect('event-history')}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="21 8 21 21 3 21 3 8" />
                  <rect x="1" y="3" width="22" height="5" />
                  <line x1="10" y1="12" x2="14" y2="12" />
                </svg>
                <span>Completed Events History</span>
              </button>

              <span className="flyout-section-heading" style={{ marginTop: '1.15rem' }}>
                CAMPUS PORTAL
              </span>

              <Link
                to="/"
                className="flyout-nav-link"
                onClick={() => setIsOpen(false)}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="19" y1="12" x2="5" y2="12" />
                  <polyline points="12 19 5 12 12 5" />
                </svg>
                <span>Campus Pulse Home</span>
              </Link>
            </nav>

            <div className="flyout-bottom-action">
              <div className="flyout-user-box">
                <div className="fub-info">
                  <span className="fub-name">{user?.name || 'Administrator'}</span>
                  <span className="fub-role-tag role-administrator role-management">Administrator</span>
                </div>
                <button
                  type="button"
                  className="fub-logout-btn"
                  onClick={handleLogout}
                >
                  Sign Out
                </button>
              </div>
            </div>
          </>
        )}

        {/* ============================================================== */}
        {/* CASE C: PUBLIC CAMPUS PORTAL LANDING PAGE NAVIGATION           */}
        {/* ============================================================== */}
        {!isOrganizer && !isManagement && (
          <>
            <div className="flyout-header">
              <Link to="/" className="flyout-brand" onClick={() => setIsOpen(false)}>
                <div className="flyout-brand-emblem" aria-hidden="true">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                    <line x1="16" y1="2" x2="16" y2="6" />
                    <line x1="8" y1="2" x2="8" y2="6" />
                    <line x1="3" y1="10" x2="21" y2="10" />
                  </svg>
                </div>
                <div className="flyout-brand-text">
                  <span className="flyout-brand-title">College Event Portal</span>
                  <span className="flyout-brand-sub">Campus Event Discovery &amp; Crowd Monitoring</span>
                </div>
              </Link>
              <button
                type="button"
                className="flyout-close-btn"
                onClick={() => setIsOpen(false)}
                aria-label="Close navigation"
              >
                &times;
              </button>
            </div>

            <nav className="flyout-nav-body">
              <span className="flyout-section-heading">NAVIGATION</span>

              <Link
                to="/"
                className={`flyout-nav-link ${isActive('/') ? 'active' : ''}`}
                onClick={() => setIsOpen(false)}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
                  <polyline points="9 22 9 12 15 12 15 22" />
                </svg>
                <span>Campus Pulse</span>
              </Link>

              <a
                href="/#available-fests"
                className="flyout-nav-link"
                onClick={(e) => handleAnchorClick(e, 'available-fests')}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
                </svg>
                <span>Festivals</span>
              </a>

              <a
                href="/#next-on-campus"
                className="flyout-nav-link"
                onClick={(e) => handleAnchorClick(e, 'next-on-campus')}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" />
                  <polyline points="12 6 12 12 16 14" />
                </svg>
                <span>Next on Campus</span>
              </a>

              <a
                href="/#upcoming-events"
                className="flyout-nav-link"
                onClick={(e) => handleAnchorClick(e, 'upcoming-events')}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                  <line x1="16" y1="2" x2="16" y2="6" />
                  <line x1="8" y1="2" x2="8" y2="6" />
                  <line x1="3" y1="10" x2="21" y2="10" />
                </svg>
                <span>Events Directory</span>
              </a>

              <a
                href="/#venues-directions"
                className="flyout-nav-link"
                onClick={(e) => handleAnchorClick(e, 'venues-directions')}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                  <circle cx="12" cy="10" r="3" />
                </svg>
                <span>Venues &amp; Directions</span>
              </a>

              {user && (
                <>
                  <span className="flyout-section-heading" style={{ marginTop: '1.25rem' }}>OPERATIONS</span>
                  <Link
                    to={user.role === 'administrator' || user.role === 'management' ? '/administrator' : '/organizer'}
                    className="flyout-nav-link"
                    onClick={() => setIsOpen(false)}
                  >
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="3" y="3" width="7" height="9" />
                      <rect x="14" y="3" width="7" height="5" />
                      <rect x="14" y="12" width="7" height="9" />
                      <rect x="3" y="16" width="7" height="5" />
                    </svg>
                    <span>{user.role === 'administrator' || user.role === 'management' ? 'Administrator Console' : 'Organizer Portal'}</span>
                  </Link>
                </>
              )}
            </nav>

            <div className="flyout-bottom-action">
              {!user ? (
                <div className="flyout-guest-box">
                  <Link
                    to="/login"
                    className="flyout-btn-signin"
                    onClick={() => setIsOpen(false)}
                  >
                    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="5" y1="12" x2="19" y2="12" />
                      <polyline points="12 5 19 12 12 19" />
                    </svg>
                    <span>Sign In</span>
                  </Link>
                  <Link
                    to="/register"
                    className="flyout-register-link"
                    onClick={() => setIsOpen(false)}
                  >
                    Register Coordinator Account
                  </Link>
                </div>
              ) : (
                <div className="flyout-user-box">
                  <div className="fub-info">
                    <span className="fub-name">{user.name}</span>
                    <span className={`fub-role-tag role-${user.role?.toLowerCase()}`}>
                      {user.role}
                    </span>
                  </div>
                  <button
                    type="button"
                    className="fub-logout-btn"
                    onClick={handleLogout}
                  >
                    Sign Out
                  </button>
                </div>
              )}
            </div>
          </>
        )}
      </aside>
    </>
  );
}
