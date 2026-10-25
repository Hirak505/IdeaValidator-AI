import React, { useState } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import ThemeToggle from '../components/ThemeToggle'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from = location.state?.from?.pathname || '/dashboard'

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!email.trim() || !password) {
      setError('Please provide both email and password.')
      return
    }

    setError(null)
    setSubmitting(true)

    try {
      await login(email.trim(), password)
      navigate(from, { replace: true })
    } catch (err) {
      setError(err.message || 'Invalid email or password.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-theme-bg bp-grid text-theme-text flex flex-col justify-between transition-colors duration-200">
      {/* Top Header */}
      <header className="border-b border-theme-border bg-theme-panel/80 backdrop-blur-md sticky top-0 z-20">
        <div className="max-w-4xl mx-auto px-4 py-3.5 flex items-center justify-between">
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

          <div className="flex items-center gap-3">
            <ThemeToggle />
            <Link
              to="/"
              className="font-mono text-micro text-theme-text-secondary hover:text-theme-evidence px-3 py-1.5 rounded-lg border border-theme-border bg-theme-panel-subtle hover:border-theme-border-active transition-colors"
            >
              ← RETURN TO STUDIO
            </Link>
          </div>
        </div>
      </header>

      {/* Main Login Box */}
      <main className="flex-1 max-w-md w-full mx-auto px-4 py-12 flex flex-col items-center justify-center">
        <div className="w-full bp-panel p-8 rounded-xl border border-theme-border relative shadow-lg">
          <div className="corner-marks" />
          <div className="top-highlight" />

          <div className="mb-6 text-center">
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-theme-chip border border-theme-border font-mono text-micro text-theme-evidence mb-2">
              <span>● ACCESS CONTROL PROTOCOL</span>
            </div>
            <h1 className="text-2xl font-extrabold tracking-tight text-theme-text">
              Sign In to Your Dossier
            </h1>
            <p className="font-mono text-micro text-theme-text-secondary mt-1">
              Access your saved arbitration reports and historical telemetry
            </p>
          </div>

          {error && (
            <div className="mb-4 p-3 rounded-lg bg-theme-error/10 border border-theme-error/30 text-theme-error text-xs font-mono flex items-start gap-2">
              <span className="font-bold">[ERR]</span>
              <span className="flex-1">{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label
                htmlFor="login-email"
                className="block text-micro font-mono uppercase text-theme-text-secondary mb-1"
              >
                Account Email
              </label>
              <input
                id="login-email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="founder@venture.io"
                className="w-full bg-theme-panel-subtle border border-theme-border rounded-lg px-3.5 py-2.5 text-xs text-theme-text font-mono focus:outline-none focus:border-theme-border-active transition-colors"
              />
            </div>

            <div>
              <label
                htmlFor="login-password"
                className="block text-micro font-mono uppercase text-theme-text-secondary mb-1"
              >
                Password
              </label>
              <input
                id="login-password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                className="w-full bg-theme-panel-subtle border border-theme-border rounded-lg px-3.5 py-2.5 text-xs text-theme-text font-mono focus:outline-none focus:border-theme-border-active transition-colors"
              />
            </div>

            <button
              id="login-submit-btn"
              type="submit"
              disabled={submitting}
              className={`w-full py-2.5 rounded-lg text-xs font-mono font-bold uppercase tracking-wider transition-all flex items-center justify-center gap-2 ${
                submitting
                  ? 'bg-theme-chip text-theme-text-muted cursor-wait border border-theme-border'
                  : 'bg-theme-evidence text-white dark:text-ink-950 hover:opacity-90 shadow-sm cursor-pointer'
              }`}
            >
              {submitting ? 'Authenticating...' : 'Authenticate & Enter →'}
            </button>
          </form>

          <div className="mt-6 pt-5 border-t border-theme-border text-center">
            <p className="font-mono text-micro text-theme-text-secondary">
              Don't have an engineering account?{' '}
              <Link
                to="/signup"
                className="text-theme-evidence hover:underline font-semibold"
              >
                Register Here
              </Link>
            </p>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-theme-border py-4 px-4 bg-theme-panel">
        <div className="max-w-4xl mx-auto flex items-center justify-between font-mono text-micro text-theme-text-muted">
          <span>IDEAVALIDATOR AI // AUTHENTICATION</span>
          <span>SESSION SECURITY: HTTPONLY REFRESH + ROTATION</span>
        </div>
      </footer>
    </div>
  )
}
