import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { registerUser } from '../services/api';

/**
 * Register Page Component
 * Connects directly to Flask /api/auth/register endpoint.
 * Uses exact fields expected by backend: name, email, password, role, management_code.
 * On success, redirects to /login with confirmation message.
 */
export default function Register() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [role, setRole] = useState('organizer');
  const [administratorCode, setAdministratorCode] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMessage('');

    const cleanName = name.trim();
    const cleanEmail = email.trim();

    if (!cleanName || !cleanEmail || !password) {
      setErrorMessage('Please fill in all required fields.');
      return;
    }

    if (password.length < 6) {
      setErrorMessage('Password must be at least 6 characters long.');
      return;
    }

    if (password !== confirmPassword) {
      setErrorMessage('Passwords do not match. Please re-enter.');
      return;
    }

    if ((role === 'administrator' || role === 'management') && !administratorCode.trim()) {
      setErrorMessage('Administrator authorization code is required for administrative accounts.');
      return;
    }

    setIsSubmitting(true);

    try {
      const response = await registerUser({
        name: cleanName,
        email: cleanEmail,
        password,
        role,
        managementCode: administratorCode,
      });

      if (response.ok) {
        // Backend returns 201: account created, prompt user to log in
        navigate('/login', {
          replace: true,
          state: {
            successMessage: 'Account created successfully! Please sign in with your credentials.',
          },
        });
      } else {
        setErrorMessage(response.error || 'Registration failed. Please check the entered information.');
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
                <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                <circle cx="8.5" cy="7" r="4" />
                <line x1="20" y1="8" x2="20" y2="14" />
                <line x1="23" y1="11" x2="17" y2="11" />
              </svg>
            </div>
            <h1 className="auth-title">Create Account</h1>
            <p className="auth-subtitle">
              Register for access to college event coordination, venue booking, or administrative safety oversight.
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

          {/* Registration Form */}
          <form onSubmit={handleSubmit} className="auth-form" noValidate>
            <div className="form-group">
              <label htmlFor="reg-name" className="form-label">
                Full Name
              </label>
              <input
                id="reg-name"
                type="text"
                className="form-input"
                placeholder="e.g. Dr. Jane Doe / John Smith"
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={isSubmitting}
                required
                autoComplete="name"
                autoFocus
              />
            </div>

            <div className="form-group">
              <label htmlFor="reg-email" className="form-label">
                College Email Address
              </label>
              <input
                id="reg-email"
                type="email"
                className="form-input"
                placeholder="name@college.edu"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={isSubmitting}
                required
                autoComplete="email"
              />
            </div>

            <div className="form-group">
              <label htmlFor="reg-role" className="form-label">
                Account Role
              </label>
              <select
                id="reg-role"
                className="form-select"
                value={role}
                onChange={(e) => setRole(e.target.value)}
                disabled={isSubmitting}
              >
                <option value="organizer">Organizer (Host Events &amp; Coordinate Venues)</option>
                <option value="administrator">Administrator (Approve Proposals &amp; Oversee Safety)</option>
              </select>
              <span className="form-hint">
                Choose between Organizer or Administrator portal access. All campus visitors can browse active fests and event schedules freely on the home page.
              </span>
            </div>

            {/* Conditionally Revealed Administrator Code */}
            {(role === 'administrator' || role === 'management') && (
              <div className="form-group management-code-group administrator-code-group">
                <label htmlFor="reg-mgmt-code" className="form-label">
                  Administrator Authorization Code
                </label>
                <input
                  id="reg-mgmt-code"
                  type="password"
                  className="form-input"
                  placeholder="Enter administrative authorization key"
                  value={administratorCode}
                  onChange={(e) => setAdministratorCode(e.target.value)}
                  disabled={isSubmitting}
                  required
                  autoComplete="off"
                />
                <span className="form-hint role-hint-alert">
                  Administrator accounts require authorization to prevent privilege escalation.
                </span>
              </div>
            )}

            <div className="form-row-2col">
              <div className="form-group">
                <label htmlFor="reg-password" className="form-label">
                  Password
                </label>
                <div className="password-input-wrap">
                  <input
                    id="reg-password"
                    type={showPassword ? 'text' : 'password'}
                    className="form-input password-input"
                    placeholder="Min 6 characters"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    disabled={isSubmitting}
                    required
                    autoComplete="new-password"
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

              <div className="form-group">
                <label htmlFor="reg-confirm-password" className="form-label">
                  Confirm Password
                </label>
                <input
                  id="reg-confirm-password"
                  type={showPassword ? 'text' : 'password'}
                  className="form-input"
                  placeholder="Repeat password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  disabled={isSubmitting}
                  required
                  autoComplete="new-password"
                />
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
                  <span>Creating Account...</span>
                </>
              ) : (
                <span>Create Account</span>
              )}
            </button>
          </form>

          <div className="auth-footer">
            <p className="auth-redirect-text">
              Already have an institutional account?{' '}
              <Link to="/login" className="auth-link">
                Sign in here
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
