import React from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import ThemeToggle from './ThemeToggle'

export default function Navbar() {
  const { user, logout, isAuthenticated } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  const isActive = (path) => location.pathname === path

  return (
    <header className="border-b border-theme-border bg-theme-panel/80 backdrop-blur-md sticky top-0 z-20 transition-colors duration-200">
      <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-3 group">
          <div className="w-7 h-7 rounded bg-theme-evidence/15 border border-theme-evidence/30 flex items-center justify-center font-mono font-bold text-xs text-theme-evidence group-hover:border-theme-border-active transition-colors">
            ⚖
          </div>
          <div>
            <span className="font-bold text-sm tracking-tight text-theme-text block leading-tight">
              IdeaValidator AI
            </span>
            <span className="font-mono text-[10px] text-theme-text-muted tracking-wider">
              ENGINEERING VALIDATION STUDIO
            </span>
          </div>
        </Link>

        <div className="flex items-center gap-2 sm:gap-4 font-mono text-micro">
          <Link
            to="/"
            className={`px-2.5 py-1.5 rounded-lg border transition-colors ${
              isActive('/')
                ? 'bg-theme-panel text-theme-evidence border-theme-border font-semibold shadow-xs'
                : 'text-theme-text-secondary hover:text-theme-text border-transparent hover:border-theme-border'
            }`}
          >
            STUDIO
          </Link>

          {isAuthenticated ? (
            <>
              <Link
                to="/dashboard"
                className={`px-2.5 py-1.5 rounded-lg border transition-colors ${
                  isActive('/dashboard')
                    ? 'bg-theme-panel text-theme-evidence border-theme-border font-semibold shadow-xs'
                    : 'text-theme-text-secondary hover:text-theme-text border-transparent hover:border-theme-border'
                }`}
              >
                DASHBOARD
              </Link>

              <Link
                to="/history"
                className={`px-2.5 py-1.5 rounded-lg border transition-colors ${
                  isActive('/history')
                    ? 'bg-theme-panel text-theme-evidence border-theme-border font-semibold shadow-xs'
                    : 'text-theme-text-secondary hover:text-theme-text border-transparent hover:border-theme-border'
                }`}
              >
                SAVED DOSSIERS
              </Link>

              <span className="hidden md:inline-flex items-center gap-1.5 px-2 py-1 rounded bg-theme-chip text-theme-text-secondary border border-theme-border text-micro">
                <span className="w-1.5 h-1.5 rounded-full bg-theme-positive" />
                <span className="max-w-[120px] truncate">{user?.display_name || user?.email}</span>
              </span>

              <button
                onClick={handleLogout}
                type="button"
                className="px-2.5 py-1.5 rounded-lg border border-theme-border bg-theme-panel-subtle hover:border-theme-border-active text-theme-text-secondary hover:text-theme-error transition-colors"
                title="Sign out of your session"
              >
                LOGOUT
              </button>
            </>
          ) : (
            <>
              <Link
                to="/login"
                className="px-2.5 py-1.5 rounded-lg border border-theme-border bg-theme-panel-subtle hover:border-theme-border-active text-theme-text-secondary hover:text-theme-text transition-colors"
              >
                SIGN IN
              </Link>
              <Link
                to="/signup"
                className="px-2.5 py-1.5 rounded-lg bg-theme-evidence text-white dark:text-ink-950 font-semibold hover:opacity-90 transition-opacity"
              >
                REGISTER
              </Link>
            </>
          )}

          <ThemeToggle />
        </div>
      </div>
    </header>
  )
}
