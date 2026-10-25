import React, { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import Navbar from '../components/Navbar'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function DashboardPage() {
  const { user, authFetch } = useAuth()
  const [evaluations, setEvaluations] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let mounted = true
    const fetchHistory = async () => {
      try {
        const res = await authFetch(`${API_URL}/evaluations?limit=20`)
        if (res.ok) {
          const data = await res.json()
          const items = Array.isArray(data) ? data : (data.evaluations || [])
          if (mounted) setEvaluations(items)
        } else {
          if (mounted) setError('Failed to retrieve evaluation telemetry.')
        }
      } catch (err) {
        if (mounted) setError(err.message)
      } finally {
        if (mounted) setLoading(false)
      }
    }
    fetchHistory()
    return () => {
      mounted = false
    }
  }, [authFetch])

  const totalEvals = evaluations.length
  const avgScore = totalEvals > 0
    ? (
        evaluations.reduce((acc, curr) => acc + (curr.overall_score || 0), 0) /
        totalEvals
      ).toFixed(1)
    : 'N/A'
  const attackModeCount = evaluations.filter((e) => e.attack_mode).length

  return (
    <div className="min-h-screen bg-theme-bg bp-grid text-theme-text flex flex-col justify-between transition-colors duration-200">
      <Navbar />

      <main className="flex-1 max-w-6xl w-full mx-auto px-4 py-8 space-y-6">
        {/* Welcome Section */}
        <div className="bp-panel p-6 rounded-xl border border-theme-border relative">
          <div className="corner-marks" />
          <div className="top-highlight" />

          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="w-2 h-2 rounded-full bg-theme-positive animate-ping" />
                <span className="font-mono text-micro text-theme-evidence uppercase tracking-wider">
                  FOUNDER PROFILE TELEMETRY
                </span>
              </div>
              <h1 className="text-2xl font-bold tracking-tight text-theme-text">
                Welcome, {user?.display_name || user?.email?.split('@')[0]}
              </h1>
              <p className="font-mono text-micro text-theme-text-secondary mt-1">
                Logged in as <span className="text-theme-text font-semibold">{user?.email}</span> • Member since{' '}
                {user?.created_at ? new Date(user.created_at).toLocaleDateString() : 'N/A'}
              </p>
            </div>

            <div className="flex items-center gap-3">
              <Link
                to="/"
                className="px-4 py-2 rounded-lg bg-theme-evidence text-white dark:text-ink-950 font-mono text-xs font-bold uppercase tracking-wider hover:opacity-90 shadow-sm transition-opacity"
              >
                + Run New Evaluation
              </Link>
              <Link
                to="/history"
                className="px-4 py-2 rounded-lg border border-theme-border bg-theme-panel-subtle hover:border-theme-border-active font-mono text-xs text-theme-text-secondary hover:text-theme-text transition-colors"
              >
                View All History →
              </Link>
            </div>
          </div>
        </div>

        {/* Telemetry Metrics */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="bp-panel p-5 rounded-xl border border-theme-border">
            <span className="section-label">TOTAL VALIDATIONS SAVED</span>
            <div className="mt-3 flex items-baseline gap-2">
              <span className="text-3xl font-extrabold font-mono text-theme-text">
                {loading ? '...' : totalEvals}
              </span>
              <span className="text-micro font-mono text-theme-text-muted">/ 100 maximum</span>
            </div>
            <p className="font-mono text-micro text-theme-text-secondary mt-1">
              Persistent multi-agent dossiers stored in database
            </p>
          </div>

          <div className="bp-panel p-5 rounded-xl border border-theme-border">
            <span className="section-label">AVERAGE COMPOSITE SCORE</span>
            <div className="mt-3 flex items-baseline gap-2">
              <span className="text-3xl font-extrabold font-mono text-theme-evidence">
                {loading ? '...' : avgScore}
              </span>
              <span className="text-micro font-mono text-theme-text-muted">/ 10.0 scale</span>
            </div>
            <p className="font-mono text-micro text-theme-text-secondary mt-1">
              Calculated across all stored evaluations
            </p>
          </div>

          <div className="bp-panel p-5 rounded-xl border border-theme-border">
            <span className="section-label">STRESS TEST AUDITS</span>
            <div className="mt-3 flex items-baseline gap-2">
              <span className="text-3xl font-extrabold font-mono text-theme-error">
                {loading ? '...' : attackModeCount}
              </span>
              <span className="text-micro font-mono text-theme-text-muted">
                adversarial runs ({totalEvals > 0 ? Math.round((attackModeCount / totalEvals) * 100) : 0}%)
              </span>
            </div>
            <p className="font-mono text-micro text-theme-text-secondary mt-1">
              Evaluations executed under high-scrutiny attack mode
            </p>
          </div>
        </div>

        {/* Recent Evaluations Preview */}
        <div className="bp-panel p-6 rounded-xl border border-theme-border">
          <div className="flex items-center justify-between pb-3 border-b border-theme-border mb-4">
            <span className="section-label">RECENT SAVED DOSSIERS</span>
            <Link
              to="/history"
              className="font-mono text-micro text-theme-evidence hover:underline"
            >
              Browse Complete Archive ({totalEvals}) →
            </Link>
          </div>

          {loading ? (
            <div className="py-8 text-center font-mono text-xs text-theme-text-secondary">
              Querying encrypted evaluation database...
            </div>
          ) : error ? (
            <div className="p-4 rounded bg-theme-error/10 text-theme-error font-mono text-xs">
              [ERR] {error}
            </div>
          ) : evaluations.length === 0 ? (
            <div className="py-12 text-center flex flex-col items-center">
              <div className="w-10 h-10 rounded-full bg-theme-chip flex items-center justify-center font-mono text-theme-text-muted text-sm mb-3">
                📭
              </div>
              <p className="font-mono text-xs font-semibold text-theme-text">No Saved Dossiers Found</p>
              <p className="font-mono text-micro text-theme-text-secondary mt-1 max-w-sm">
                Run an evaluation in the studio, then click "Save Dossier" to store and track your startup's progression over time.
              </p>
              <Link
                to="/"
                className="mt-4 px-3.5 py-1.5 rounded-lg bg-theme-evidence text-white dark:text-ink-950 font-mono text-xs font-bold hover:opacity-90 transition-opacity"
              >
                Go to Evaluation Studio
              </Link>
            </div>
          ) : (
            <div className="space-y-3">
              {evaluations.slice(0, 5).map((item) => (
                <div
                  key={item.id}
                  className="p-4 rounded-lg border border-theme-border bg-theme-panel-subtle hover:border-theme-border-active transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-mono text-xs font-bold text-theme-text truncate">
                        {item.title}
                      </span>
                      {item.attack_mode ? (
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-theme-error/20 text-theme-error font-semibold">
                          ATTACK MODE
                        </span>
                      ) : (
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-theme-evidence/15 text-theme-evidence font-semibold">
                          STANDARD
                        </span>
                      )}
                      {item.research_assisted && (
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-theme-warning/20 text-theme-warning font-semibold">
                          RECON
                        </span>
                      )}
                    </div>
                    <p className="font-mono text-micro text-theme-text-secondary">
                      Saved {new Date(item.created_at).toLocaleString()}
                    </p>
                  </div>

                  <div className="flex items-center gap-4 flex-shrink-0">
                    <div className="text-right">
                      <span className="font-mono text-xs font-bold text-theme-evidence">
                        {item.overall_score != null ? `${item.overall_score}/10` : 'N/A'}
                      </span>
                      <span className="block font-mono text-[10px] text-theme-text-muted">
                        INDEX
                      </span>
                    </div>

                    <Link
                      to={`/history/${item.id}`}
                      className="px-3 py-1.5 rounded border border-theme-border bg-theme-panel hover:border-theme-border-active font-mono text-xs text-theme-text-secondary hover:text-theme-text transition-colors"
                    >
                      Inspect →
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>

      <footer className="border-t border-theme-border py-4 px-4 bg-theme-panel">
        <div className="max-w-6xl mx-auto flex items-center justify-between font-mono text-micro text-theme-text-muted">
          <span>IDEAVALIDATOR AI // SECURE FOUNDER TELEMETRY</span>
          <span>HYBRID ACCESS ARCHITECTURE ACTIVE</span>
        </div>
      </footer>
    </div>
  )
}
