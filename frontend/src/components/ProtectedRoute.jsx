import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import Loading from './Loading';

/**
 * Reusable Protected Route Component
 * - Displays loading indicator while checking authentication session.
 * - Redirects unauthenticated users to /login preserving the intended destination.
 * - Enforces role-based access if allowedRoles are specified.
 * - Redirects users with mismatched roles to their authorized dashboard.
 */
export default function ProtectedRoute({ children, allowedRoles }) {
  const { user, loading, isAuthenticated } = useAuth();
  const location = useLocation();

  if (loading) {
    return <Loading fullScreen message="Verifying session authorization..." />;
  }

  if (!isAuthenticated || !user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // If role restriction is specified, verify user's backend-assigned role
  if (allowedRoles && allowedRoles.length > 0) {
    const userRole = user.role?.toLowerCase();
    const effectiveRoles = allowedRoles.flatMap((r) => {
      const lower = r.toLowerCase();
      if (lower === 'administrator' || lower === 'management') return ['administrator', 'management'];
      return [lower];
    });
    const hasPermission = effectiveRoles.includes(userRole);

    if (!hasPermission) {
      // Redirect to the user's appropriate portal route
      const roleRedirectMap = {
        organizer: '/organizer',
        administrator: '/administrator',
        management: '/administrator',
      };

      const fallbackRoute = roleRedirectMap[userRole] || '/';
      return <Navigate to={fallbackRoute} replace />;
    }
  }

  return children;
}
