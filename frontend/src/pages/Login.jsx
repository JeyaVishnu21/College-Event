import React, { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

/**
 * Login Page Component
 * Connects directly to Flask /api/auth/login endpoint.
 * Backend determines user role and navigates to the respective placeholder dashboard.
 */
export default function Login() {
  const { user, login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  const navigate = useNavigate();
  const location = useLocation();

  // Pick up any flash message passed from registration
  useEffect(() => {
    if (location.state?.successMessage) {
      setSuccessMessage(location.state.successMessage);
    }
  }, [location.state]);

  // If already authenticated, redirect to authorized dashboard
  useEffect(() => {
    if (user && user.role) {
      const role = user.role.toLowerCase();
      if (role === 'organizer') navigate('/organizer', { replace: true });
      else if (role === 'administrator' || role === 'management') navigate('/administrator', { replace: true });
      else navigate('/', { replace: true });
    }
  }, [user, navigate]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMessage('');
    setSuccessMessage('');

    const cleanEmail = email.trim();
    if (!cleanEmail || !password) {
      setErrorMessage('Please enter both your college email and password.');
      return;
    }

    setIsSubmitting(true);

    try {
      const result = await login(cleanEmail, password);

      if (result.success && result.user) {
        const returnedRole = result.user.role?.toLowerCase();

        if (returnedRole === 'organizer') {
          setSuccessMessage(`Welcome back, ${result.user.name}. Organizer portal ready.`);
          setTimeout(() => navigate('/organizer', { replace: true }), 500);
        } else if (returnedRole === 'administrator' || returnedRole === 'management') {
          setSuccessMessage(`Welcome back, ${result.user.name}. Administrator console ready.`);
          setTimeout(() => navigate('/administrator', { replace: true }), 500);
        } else {
          setErrorMessage('Account role is not authorized for portal access.');
        }
      } else {
        setErrorMessage(result.error || 'Invalid email or password.');
      }
    } catch {
      setErrorMessage('Unable to connect to server. Please verify the backend service is running.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-card-wrapper">
        <div className="auth-card">
          <div className="auth-header">
            <div className="auth-emblem" aria-hidden="true">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                <line x1="16" y1="2" x2="16" y2="6" />
                <line x1="8" y1="2" x2="8" y2="6" />
                <line x1="3" y1="10" x2="21" y2="10" />
              </svg>
            </div>
            <h1 className="auth-title">Organizer &amp; Administrator Sign In</h1>
            <p className="auth-subtitle">
              Sign in with your institutional credentials to access your operations dashboard.
            </p>
          </div>

          {/* Status Messages */}
          {errorMessage && (
            <div className="alert alert-error" role="alert">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              <span>{errorMessage}</span>
            </div>
          )}

          {successMessage && (
            <div className="alert alert-success" role="status">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                <polyline points="22 4 12 14.01 9 11.01" />
              </svg>
              <span>{successMessage}</span>
            </div>
          )}

          {/* Login Form */}
          <form onSubmit={handleSubmit} className="auth-form" noValidate>
            <div className="form-group">
              <label htmlFor="login-email" className="form-label">
                College Email Address
              </label>
              <input
                id="login-email"
                type="email"
                className="form-input"
                placeholder="name@college.edu"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={isSubmitting}
                required
                autoComplete="email"
                autoFocus
              />
            </div>

            <div className="form-group">
              <div className="form-label-row">
                <label htmlFor="login-password" className="form-label">
                  Password
                </label>
              </div>
              <div className="password-input-wrap">
                <input
                  id="login-password"
                  type={showPassword ? 'text' : 'password'}
                  className="form-input password-input"
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={isSubmitting}
                  required
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  className="password-toggle-btn"
                  onClick={() => setShowPassword(!showPassword)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  tabIndex={-1}
                >
                  {showPassword ? (
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                      <line x1="1" y1="1" x2="23" y2="23" />
                    </svg>
                  ) : (
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                      <circle cx="12" cy="12" r="3" />
                    </svg>
                  )}
                </button>
              </div>
            </div>

            <button
              type="submit"
              className="btn btn-primary btn-full btn-submit"
              disabled={isSubmitting}
            >
              {isSubmitting ? (
                <>
                  <span className="spinner-sm" aria-hidden="true" />
                  <span>Signing In...</span>
                </>
              ) : (
                <span>Sign In</span>
              )}
            </button>
          </form>

          <div className="auth-footer">
            <p className="auth-redirect-text">
              Don't have an institutional account yet?{' '}
              <Link to="/register" className="auth-link">
                Register here
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
