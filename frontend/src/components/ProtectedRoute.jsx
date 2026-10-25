import React from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function ProtectedRoute({ children }) {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) {
    return (
      <div className="min-h-screen bg-theme-bg bp-grid flex items-center justify-center p-4">
        <div className="bp-panel p-8 rounded-xl border border-theme-border flex flex-col items-center gap-4 max-w-sm w-full text-center">
          <div className="w-8 h-8 rounded-full border-2 border-theme-evidence border-t-transparent animate-spin" />
          <p className="font-mono text-xs text-theme-text-secondary uppercase tracking-wider">
            Verifying Security Credentials...
          </p>
        </div>
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return children
}
