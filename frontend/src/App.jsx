import React, { useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import Sidebar from './components/Sidebar';
import Home from './pages/Home';
import Login from './pages/Login';
import Register from './pages/Register';
import FestDetails from './pages/FestDetails';
import EventDetails from './pages/EventDetails';
import OrganizerDashboard from './pages/OrganizerDashboard';
import AdministratorDashboard from './pages/AdministratorDashboard';

/**
 * Main Application Component
 * Sets up AuthProvider, React Router, role-based ProtectedRoute guards,
 * and persistent institutional layout navigation.
 */
export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <div className="app-layout full-width-layout">
          {/* Left-Side Auto-Hiding Portal Navigation */}
          <Sidebar />

          {/* Main Full-Width Route Content */}
          <main className="main-content full-screen-content">
            <Routes>
              {/* Public Discovery Routes */}
              <Route path="/" element={<Home />} />
              <Route path="/fest/:id" element={<FestDetails />} />
              <Route path="/series/:id" element={<FestDetails />} />
              <Route path="/event/:id" element={<EventDetails />} />
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />

              {/* Role-Protected Routes (Organizer & Administrator Only) */}
              <Route path="/student" element={<Navigate to="/" replace />} />
              <Route
                path="/organizer"
                element={
                  <ProtectedRoute allowedRoles={['organizer']}>
                    <OrganizerDashboard />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/administrator"
                element={
                  <ProtectedRoute allowedRoles={['administrator', 'management']}>
                    <AdministratorDashboard />
                  </ProtectedRoute>
                }
              />
              <Route path="/management" element={<Navigate to="/administrator" replace />} />

              {/* Fallback */}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </AuthProvider>
  );
}
