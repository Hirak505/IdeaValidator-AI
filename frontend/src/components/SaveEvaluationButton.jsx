import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function SaveEvaluationButton({ results, attackMode, pitchDeck, readme, researchAssisted }) {
  const { isAuthenticated, authFetch } = useAuth()

  const [saving, setSaving] = useState(false)
  const [savedId, setSavedId] = useState(null)
  const [error, setError] = useState(null)
  const [isOpen, setIsOpen] = useState(false)
  const [showAuthPrompt, setShowAuthPrompt] = useState(false)

  // Default suggested title based on uploaded documents or timestamp
  const defaultTitle = pitchDeck?.name
    ? `Dossier: ${pitchDeck.name.replace(/\.[^/.]+$/, '')}`
    : readme?.name
    ? `Dossier: ${readme.name.replace(/\.[^/.]+$/, '')}`
    : `Startup Evaluation - ${new Date().toLocaleDateString()}`

  const [title, setTitle] = useState(defaultTitle)

  const handleSave = async (e) => {
    e.preventDefault()
    if (!title.trim() || saving) return

    setSaving(true)
    setError(null)

    try {
      const payload = {
        title: title.trim(),
        attack_mode: Boolean(attackMode),
        research_assisted: Boolean(researchAssisted || results?.research_assisted),
        results: results,
      }

      const res = await authFetch(`${API_URL}/evaluations/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to save evaluation.')
      }

      setSavedId(data.id)
      setIsOpen(false)
    } catch (err) {
      setError(err.message || 'Error saving dossier.')
    } finally {
      setSaving(false)
    }
  }

  if (savedId) {
    return (
      <div className="flex items-center gap-2">
        <Link
          to={`/history/${savedId}`}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-theme-positive/40 bg-theme-positive/10 text-xs font-mono text-theme-positive font-semibold hover:bg-theme-positive/20 transition-colors"
        >
          <span>✓ SAVED TO DOSSIER</span>
          <span className="text-micro font-normal underline">View →</span>
        </Link>
      </div>
    )
  }

  return (
    <div className="relative">
      <button
        onClick={() => {
          if (!isAuthenticated) {
            setShowAuthPrompt(true)
          } else {
            setIsOpen(true)
          }
        }}
        type="button"
        id="save-eval-btn"
        className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-theme-evidence bg-theme-evidence/10 hover:bg-theme-evidence/20 text-xs font-mono text-theme-evidence font-bold transition-all shadow-xs"
      >
        <span>💾</span>
        <span>SAVE DOSSIER</span>
      </button>

      {/* Auth Prompt Modal / Popover for Visitors */}
      {showAuthPrompt && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-fade-in">
          <div className="bp-panel p-6 rounded-xl border border-theme-border max-w-sm w-full relative shadow-2xl">
            <div className="corner-marks" />
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className="text-base">🔐</span>
                <h3 className="font-bold text-sm text-theme-text font-mono">
                  Founder Authentication Required
                </h3>
              </div>
              <button
                onClick={() => setShowAuthPrompt(false)}
                className="text-theme-text-muted hover:text-theme-text font-mono text-xs"
              >
                ✕
              </button>
            </div>

            <p className="font-mono text-micro text-theme-text-secondary mb-5 leading-relaxed">
              Create a free founder account or sign in to save this multi-agent arbitration report to your permanent history.
            </p>

            <div className="flex flex-col gap-2 font-mono text-xs">
              <Link
                to="/signup"
                className="w-full py-2 rounded-lg bg-theme-evidence text-white dark:text-ink-950 font-bold text-center hover:opacity-90 transition-opacity"
              >
                Create Account (Free) →
              </Link>
              <Link
                to="/login"
                className="w-full py-2 rounded-lg border border-theme-border bg-theme-panel-subtle text-theme-text font-semibold text-center hover:border-theme-border-active transition-colors"
              >
                Sign In to Existing Account
              </Link>
            </div>
          </div>
        </div>
      )}

      {/* Save Title Modal for Authenticated Users */}
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-fade-in">
          <div className="bp-panel p-6 rounded-xl border border-theme-border max-w-md w-full relative shadow-2xl">
            <div className="corner-marks" />
            <div className="flex items-start justify-between mb-4">
              <div>
                <span className="section-label">COMMIT TO DATABASE</span>
                <h3 className="font-bold text-base text-theme-text mt-1">
                  Save Evaluation Dossier
                </h3>
              </div>
              <button
                onClick={() => setIsOpen(false)}
                className="text-theme-text-muted hover:text-theme-text font-mono text-xs"
              >
                ✕
              </button>
            </div>

            {error && (
              <div className="mb-4 p-2.5 rounded bg-theme-error/10 text-theme-error font-mono text-xs">
                [ERR] {error}
              </div>
            )}

            <form onSubmit={handleSave} className="space-y-4">
              <div>
                <label className="block text-micro font-mono uppercase text-theme-text-secondary mb-1">
                  Dossier Title
                </label>
                <input
                  type="text"
                  required
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g. Acme AI Seed Pitch Audit"
                  className="w-full bg-theme-panel-subtle border border-theme-border rounded-lg px-3 py-2 text-xs text-theme-text font-mono focus:outline-none focus:border-theme-border-active"
                />
              </div>

              <div className="p-3 rounded-lg bg-theme-panel-subtle border border-theme-border font-mono text-micro text-theme-text-secondary space-y-1">
                <div className="flex justify-between">
                  <span>Execution Scrutiny:</span>
                  <span className="text-theme-text font-semibold">
                    {attackMode ? 'Adversarial Attack Mode' : 'Standard Panel'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Overall Composite:</span>
                  <span className="text-theme-evidence font-bold">
                    {results?.chief_judge?.overall_score ?? 'N/A'}/10.0
                  </span>
                </div>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsOpen(false)}
                  className="px-3 py-1.5 rounded-lg border border-theme-border font-mono text-xs text-theme-text-secondary hover:text-theme-text"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving || !title.trim()}
                  className="px-4 py-1.5 rounded-lg bg-theme-evidence text-white dark:text-ink-950 font-mono text-xs font-bold hover:opacity-90 transition-opacity disabled:opacity-50"
                >
                  {saving ? 'Saving...' : 'Confirm & Save'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
