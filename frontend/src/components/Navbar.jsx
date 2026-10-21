import React, { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

/**
 * Institutional Navigation Bar Component
 * Consumes AuthContext to show active session info, role badge,
 * dashboard link, and sign-out button.
 */
export default function Navbar({ onToggleSidebar }) {
  const { user, logout } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  const isActive = (path) => location.pathname === path;

  const handleNavClick = () => {
    setMobileMenuOpen(false);
  };

  const handleLogout = async () => {
    handleNavClick();
    await logout();
    navigate('/login');
  };

  // Determine dashboard link according to Flask backend role (Organizer & Administrator only)
  const getDashboardPath = () => {
    if (!user || !user.role) return '/';
    const role = user.role.toLowerCase();
    if (role === 'organizer') return '/organizer';
    if (role === 'administrator' || role === 'management') return '/administrator';
    return '/';
  };

  const handleAnchorClick = (e, targetId) => {
    handleNavClick();
    if (location.pathname === '/') {
      e.preventDefault();
      const el = document.getElementById(targetId);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth' });
      } else if (targetId === 'fest-explorer') {
        const festsEl = document.getElementById('available-fests');
        if (festsEl) {
          festsEl.scrollIntoView({ behavior: 'smooth' });
        }
      }
    }
  };

  return (
    <header className="institutional-navbar">
      <div className="nav-container">
        {/* Left: Mobile Toggle & Brand Emblem */}
        <div className="nav-brand-group">
          {onToggleSidebar && (
            <button
              type="button"
              className="nav-sidebar-toggle"
              onClick={onToggleSidebar}
              aria-label="Toggle Sidebar Menu"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </svg>
            </button>
          )}

          <Link to="/" className="nav-brand" onClick={handleNavClick}>
            <div className="brand-emblem" aria-hidden="true">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                <line x1="16" y1="2" x2="16" y2="6" />
                <line x1="8" y1="2" x2="8" y2="6" />
                <line x1="3" y1="10" x2="21" y2="10" />
              </svg>
            </div>
            <div className="brand-text-block">
              <span className="brand-title">Crowd Event Management System</span>
              <span className="brand-subtitle">College Event Operations &amp; Safety Portal</span>
            </div>
          </Link>
        </div>

        {/* Center/Desktop Navigation Links */}
        <nav className={`nav-menu ${mobileMenuOpen ? 'nav-menu-open' : ''}`} aria-label="Main Navigation">
          <Link
            to="/"
            className={`nav-link ${isActive('/') ? 'nav-link-active' : ''}`}
            onClick={handleNavClick}
          >
            Home
          </Link>

          <a
            href="/#available-fests"
            className="nav-link"
            onClick={(e) => handleAnchorClick(e, 'available-fests')}
          >
            Campus Fests
          </a>

          <a
            href="/#upcoming-events"
            className="nav-link"
            onClick={(e) => handleAnchorClick(e, 'upcoming-events')}
          >
            Upcoming Events
          </a>

          {/* If authenticated, provide direct link to user's dashboard in nav */}
          {user && (
            <Link
              to={getDashboardPath()}
              className={`nav-link ${isActive(getDashboardPath()) ? 'nav-link-active' : ''}`}
              onClick={handleNavClick}
            >
              Dashboard
            </Link>
          )}

          {/* Mobile-only Auth Links when not logged in */}
          {!user && (
            <div className="nav-mobile-auth">
              <Link
                to="/login"
                className={`nav-link ${isActive('/login') ? 'nav-link-active' : ''}`}
                onClick={handleNavClick}
              >
                Login
              </Link>
              <Link
                to="/register"
                className="btn btn-primary btn-sm"
                onClick={handleNavClick}
              >
                Register
              </Link>
            </div>
          )}

          {/* Mobile-only Auth info when logged in */}
          {user && (
            <div className="nav-mobile-auth">
              <span className="nav-user-label">
                {user.name} ({user.role})
              </span>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={handleLogout}
              >
                Sign Out
              </button>
            </div>
          )}
        </nav>

        {/* Right Desktop Auth Actions */}
        <div className="nav-actions">
          {user ? (
            <div className="nav-user-profile">
              <div className="user-details">
                <span className="user-name">{user.name}</span>
                <span className={`role-badge role-badge-${user.role}`}>
                  {user.role}
                </span>
              </div>
              <Link
                to={getDashboardPath()}
                className="btn btn-ghost btn-sm"
              >
                My Portal
              </Link>
              <button
                type="button"
                onClick={handleLogout}
                className="btn btn-secondary btn-sm"
              >
                Sign Out
              </button>
            </div>
          ) : (
            <div className="nav-auth-buttons">
              <Link
                to="/login"
                className={`btn btn-ghost btn-sm ${isActive('/login') ? 'btn-ghost-active' : ''}`}
              >
                Login
              </Link>
              <Link
                to="/register"
                className="btn btn-primary btn-sm"
              >
                Register
              </Link>
            </div>
          )}

          {/* Mobile Hamburger Toggle Button */}
          <button
            type="button"
            className="nav-hamburger"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            aria-expanded={mobileMenuOpen}
            aria-label="Toggle navigation menu"
          >
            {mobileMenuOpen ? (
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            ) : (
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </svg>
            )}
          </button>
        </div>
      </div>
    </header>
  );
}
