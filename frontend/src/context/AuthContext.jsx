import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { loginUser, logoutUser, getCurrentUser } from '../services/api';

const AuthContext = createContext(null);

/**
 * Authentication Provider Component
 * Maintains the session-authenticated user state across the React application.
 * Automatically verifies session on initial mount and preserves the Flask session cookie.
 */
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  /**
   * Refreshes the current user from the Flask backend session endpoint (/api/auth/me).
   */
  const refreshUser = useCallback(async () => {
    try {
      const response = await getCurrentUser();
      if (response.ok && response.authenticated && response.user) {
        setUser(response.user);
        return { success: true, user: response.user };
      } else {
        setUser(null);
        return { success: false, user: null };
      }
    } catch {
      setUser(null);
      return { success: false, user: null };
    }
  }, []);

  // Check server-side session on initial mount
  useEffect(() => {
    let isMounted = true;

    async function initializeSession() {
      try {
        const response = await getCurrentUser();
        if (isMounted) {
          if (response.ok && response.authenticated && response.user) {
            setUser(response.user);
          } else {
            setUser(null);
          }
        }
      } catch {
        if (isMounted) {
          setUser(null);
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    }

    initializeSession();

    return () => {
      isMounted = false;
    };
  }, []);

  /**
   * Logs in with email and password, establishing server-side session.
   * On success, updates user state and returns { success: true, user }.
   * On failure, returns { success: false, error }.
   * Passwords are NEVER stored in React state or localStorage.
   */
  const login = async (email, password) => {
    const response = await loginUser(email, password);

    if (response.ok && response.data?.user) {
      const authenticatedUser = response.data.user;
      setUser(authenticatedUser);
      return {
        success: true,
        user: authenticatedUser,
        message: response.data.message || 'Login successful.',
      };
    }

    return {
      success: false,
      user: null,
      error: response.error || 'Invalid email or password.',
    };
  };

  /**
   * Logs out from the Flask backend, terminating the session.
   * Clears the React authenticated user state.
   */
  const logout = async () => {
    try {
      await logoutUser();
    } catch {
      // Even if network fails, ensure client state is cleared
    } finally {
      setUser(null);
    }
  };

  const value = {
    user,
    loading,
    isAuthenticated: Boolean(user),
    login,
    logout,
    refreshUser,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

/**
 * Custom hook to access authentication context.
 */
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

export default AuthContext;
