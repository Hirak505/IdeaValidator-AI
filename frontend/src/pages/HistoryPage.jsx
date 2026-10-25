import React, { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import Navbar from '../components/Navbar'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function HistoryPage() {
  const { authFetch } = useAuth()
  const [evaluations, setEvaluations] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [deletingId, setDeletingId] = useState(null)

  const fetchHistory = async () => {
    try {
      setLoading(true)
      const res = await authFetch(`${API_URL}/evaluations?limit=100`)
      if (res.ok) {
        const data = await res.json()
        const items = Array.isArray(data) ? data : (data.evaluations || [])
        setEvaluations(items)
      } else {
        setError('Failed to load evaluation history.')
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchHistory()
  }, [])

  const handleDelete = async (id, title) => {
    if (!window.confirm(`Are you sure you want to delete "${title}"? This cannot be undone.`)) {
      return
    }

    setDeletingId(id)
    try {
      const res = await authFetch(`${API_URL}/evaluations/${id}`, {
        method: 'DELETE',
      })
      if (res.ok) {
        setEvaluations((prev) => prev.filter((item) => item.id !== id))
      } else {
        const data = await res.json().catch(() => ({}))
        alert(data.detail || 'Failed to delete evaluation record.')
      }
    } catch (err) {
      alert(`Delete error: ${err.message}`)
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <div className="min-h-screen bg-theme-bg bp-grid text-theme-text flex flex-col justify-between transition-colors duration-200">
      <Navbar />

      <main className="flex-1 max-w-6xl w-full mx-auto px-4 py-8 space-y-6">
        {/* Header Bar */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-theme-border">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="section-label">ARBITRATION ARCHIVE</span>
              <span className="font-mono text-micro text-theme-evidence">
                // {evaluations.length} RECORDS
              </span>
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-theme-text">
              Saved Evaluation Dossiers
            </h1>
            <p className="font-mono text-micro text-theme-text-secondary mt-1">
              Historical multi-agent validation assessments associated with your founder ID
            </p>
          </div>

          <Link
            to="/"
            className="px-4 py-2 rounded-lg bg-theme-evidence text-white dark:text-ink-950 font-mono text-xs font-bold uppercase tracking-wider hover:opacity-90 shadow-sm transition-opacity self-start sm:self-auto"
          >
            + New Evaluation
          </Link>
        </div>

        {error && (
          <div className="p-4 rounded-lg bg-theme-error/10 border border-theme-error/30 text-theme-error font-mono text-xs flex items-center gap-2">
            <span className="font-bold">[ERR]</span>
            <span>{error}</span>
          </div>
        )}

        {loading ? (
          <div className="bp-panel p-12 rounded-xl border border-theme-border text-center">
            <div className="w-8 h-8 rounded-full border-2 border-theme-evidence border-t-transparent animate-spin mx-auto mb-3" />
            <p className="font-mono text-xs text-theme-text-secondary uppercase">
              Retrieving Evaluation Records...
            </p>
          </div>
        ) : evaluations.length === 0 ? (
          <div className="bp-panel p-16 rounded-xl border border-theme-border text-center flex flex-col items-center">
            <div className="w-12 h-12 rounded-full bg-theme-chip flex items-center justify-center font-mono text-theme-text-muted text-base mb-4">
              🗄️
            </div>
            <h3 className="font-mono text-sm font-bold text-theme-text uppercase">
              Archive Directory Is Empty
            </h3>
            <p className="font-mono text-xs text-theme-text-secondary mt-1.5 max-w-md">
              You have not saved any arbitration runs yet. When reviewing evaluation results in the studio, click "Save Evaluation Dossier" to store them here.
            </p>
            <Link
              to="/"
              className="mt-6 px-4 py-2 rounded-lg bg-theme-evidence text-white dark:text-ink-950 font-mono text-xs font-bold hover:opacity-90 transition-opacity"
            >
              Launch First Assessment →
            </Link>
          </div>
        ) : (
          <div className="space-y-3">
            {evaluations.map((item) => (
              <div
                key={item.id}
                className="bp-panel p-5 rounded-xl border border-theme-border hover:border-theme-border-active transition-all flex flex-col md:flex-row md:items-center justify-between gap-4"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2.5 flex-wrap mb-1.5">
                    <span className="font-bold text-sm text-theme-text hover:text-theme-evidence transition-colors">
                      <Link to={`/history/${item.id}`}>{item.title}</Link>
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
                        RECON GROUNDED
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-4 font-mono text-micro text-theme-text-secondary">
                    <span>RECORD ID: {item.id.slice(0, 8)}...</span>
                    <span>•</span>
                    <span>{new Date(item.created_at).toLocaleString()}</span>
                  </div>
                </div>

                <div className="flex items-center gap-5 flex-shrink-0 self-end md:self-auto">
                  <div className="text-right">
                    <div className="font-mono text-base font-extrabold text-theme-evidence">
                      {item.overall_score != null ? `${item.overall_score}/10` : '—'}
                    </div>
                    <span className="font-mono text-[9px] uppercase tracking-wider text-theme-text-muted">
                      OVERALL INDEX
                    </span>
                  </div>

                  <div className="flex items-center gap-2">
                    <Link
                      to={`/history/${item.id}`}
                      className="px-3 py-1.5 rounded-lg border border-theme-border bg-theme-panel-subtle hover:border-theme-border-active font-mono text-xs text-theme-text-secondary hover:text-theme-text transition-colors"
                    >
                      Inspect Dossier
                    </Link>

                    <button
                      onClick={() => handleDelete(item.id, item.title)}
                      disabled={deletingId === item.id}
                      type="button"
                      title="Delete this record"
                      className="px-2.5 py-1.5 rounded-lg border border-theme-border bg-theme-panel-subtle hover:bg-theme-error/10 hover:border-theme-error hover:text-theme-error font-mono text-xs text-theme-text-muted transition-colors disabled:opacity-50"
                    >
                      {deletingId === item.id ? '...' : '✕'}
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>

      <footer className="border-t border-theme-border py-4 px-4 bg-theme-panel">
        <div className="max-w-6xl mx-auto flex items-center justify-between font-mono text-micro text-theme-text-muted">
          <span>IDEAVALIDATOR AI // HISTORICAL DATA REPOSITORY</span>
          <span>STRICT ROW-LEVEL TENANT ISOLATION</span>
        </div>
      </footer>
    </div>
  )
}
