import React, { useState, useEffect } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import Navbar from '../components/Navbar'
import OverallScore from '../components/OverallScore'
import RadarChart from '../components/RadarChart'
import ConsensusCard from '../components/ConsensusCard'
import DifferentiationCard from '../components/DifferentiationCard'
import JudgeQuestions from '../components/JudgeQuestions'
import ScoreCard from '../components/ScoreCard'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function markdownList(items) {
  return (items || []).map((item) => `- ${item}`).join('\n') || '- None provided'
}

function buildMarkdownReport(results, attackMode, title) {
  const chief = results.chief_judge || {}
  const consensus = results.consensus || {}
  const diff = chief.differentiation || {}
  const judgeLabels = {
    innovation: 'Innovation & Novelty Specialist',
    technical: 'Technical Architecture Specialist',
    business: 'Business Viability Specialist',
    presentation: 'Presentation & Pitch Specialist',
  }

  const specialistReports = Object.entries(judgeLabels)
    .map(([type, label]) => {
      const report = results[type] || {}
      const confLine = report.confidence != null ? ` | **Confidence:** ${report.confidence}%` : ''
      const evidLine = report.evidence_quality != null ? ` | **Evidence Quality:** ${report.evidence_quality}%` : ''

      let findingsSection = ''
      if (report.key_findings?.length > 0) {
        const findingLines = report.key_findings
          .map(
            (f) =>
              `- **[${(f.evidence_type || 'N/A').toUpperCase()}]** ${f.finding}\n  Evidence: ${f.evidence || 'Not directly verified'}${f.source && f.source !== 'N/A' ? ` (Source: ${f.source})` : ''}`
          )
          .join('\n')
        findingsSection = `\n\n### Key Findings\n${findingLines}`
      }

      return `## ${label}\n\n**Score:** ${report.score ?? 'N/A'}/10${confLine}${evidLine}\n\n**Comments:** ${report.comments || 'None provided'}\n\n### Strengths\n${markdownList(report.strengths)}\n\n### Weaknesses\n${markdownList(report.weaknesses)}${findingsSection}`
    })
    .join('\n\n')

  let consensusSection = ''
  if (consensus.mean != null) {
    consensusSection = `\n## Judge Consensus & Dispersion\n\n**Agreement Level:** ${consensus.agreement_level || 'N/A'}\n**Score Spread:** ${consensus.spread} points (${consensus.min} – ${consensus.max})\n**Most Aligned Dimension:** ${judgeLabels[consensus.most_aligned] || consensus.most_aligned}\n**Largest Disagreement Dimension:** ${judgeLabels[consensus.largest_disagreement] || consensus.largest_disagreement}\n`
  }

  let diffSection = ''
  if (diff.solution_category && diff.solution_category !== 'Not determined') {
    diffSection = `\n## Competitive Differentiation & Moat Analysis\n\n**Category:** ${diff.solution_category}\n`
    if (diff.differentiation_strengths?.[0] !== 'Not determined') diffSection += `\n**Validated Differentiators:**\n${markdownList(diff.differentiation_strengths)}\n`
    if (diff.differentiation_gaps?.[0] !== 'Not determined') diffSection += `\n**Defensibility Gaps:**\n${markdownList(diff.differentiation_gaps)}\n`
    if (diff.unsupported_claims?.length > 0) diffSection += `\n**Unsupported Claims:**\n${markdownList(diff.unsupported_claims)}\n`
    if (diff.limitation_note) diffSection += `\n*${diff.limitation_note}*\n`
  }

  let roadmapSection = ''
  if (chief.prioritized_roadmap?.length > 0) {
    const rows = chief.prioritized_roadmap
      .map(
        (r) =>
          `| ${r.priority} | ${r.title} | ${r.reason || '—'} | ${r.impact} | ${r.effort} |`
      )
      .join('\n')
    roadmapSection = `\n## Prioritized Remediation Roadmap\n\n| Priority | Action | Reason | Impact | Effort |\n|----------|--------|--------|--------|--------|\n${rows}\n`
  } else {
    const items = (chief.improvement_roadmap || []).map((step, index) => `${index + 1}. ${step}`).join('\n')
    roadmapSection = `\n### Improvement Roadmap\n${items || '1. None provided'}\n`
  }

  const confEvid = []
  if (chief.confidence != null) confEvid.push(`**Confidence:** ${chief.confidence}%`)
  if (chief.evidence_quality != null) confEvid.push(`**Evidence Quality:** ${chief.evidence_quality}%`)
  const confEvidLine = confEvid.length > 0 ? confEvid.join(' | ') + '\n' : ''

  return `# IdeaValidator AI // Technical Evaluation Memorandum: ${title || 'Saved Evaluation'}\n\nGenerated: ${new Date().toISOString()}\nExecution Mode: ${attackMode ? 'Adversarial Stress Test (Attack Mode)' : 'Standard Multi-Agent Panel'}\n\n## Executive Verdict\n\n**Overall Index:** ${chief.overall_score ?? 'N/A'}/10.0\n${confEvidLine}\n${chief.final_verdict || 'None provided'}\n\n### Top Strengths\n${markdownList(chief.top_strengths)}\n\n### Critical Deficits\n${markdownList(chief.top_improvements)}\n${roadmapSection}${consensusSection}${diffSection}\n## Defense Questions For The Team\n\n${markdownList(chief.judge_questions)}\n\n${specialistReports}\n`
}

export default function EvaluationDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { authFetch } = useAuth()

  const [evaluation, setEvaluation] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    let mounted = true
    const fetchDetail = async () => {
      try {
        setLoading(true)
        const res = await authFetch(`${API_URL}/evaluations/${id}`)
        if (res.ok) {
          const data = await res.json()
          if (mounted) setEvaluation(data)
        } else if (res.status === 404) {
          if (mounted) setError('Evaluation record not found or inaccessible.')
        } else {
          if (mounted) setError(`Failed to load evaluation (Status ${res.status}).`)
        }
      } catch (err) {
        if (mounted) setError(err.message)
      } finally {
        if (mounted) setLoading(false)
      }
    }

    fetchDetail()
    return () => {
      mounted = false
    }
  }, [id, authFetch])

  const handleDelete = async () => {
    if (!window.confirm('Are you sure you want to delete this evaluation permanently?')) {
      return
    }

    setDeleting(true)
    try {
      const res = await authFetch(`${API_URL}/evaluations/${id}`, {
        method: 'DELETE',
      })
      if (res.ok) {
        navigate('/history', { replace: true })
      } else {
        alert('Failed to delete evaluation.')
      }
    } catch (err) {
      alert(`Delete error: ${err.message}`)
    } finally {
      setDeleting(false)
    }
  }

  const handleDownloadReport = () => {
    if (!evaluation?.results) return
    const report = new Blob(
      [buildMarkdownReport(evaluation.results, evaluation.attack_mode, evaluation.title)],
      { type: 'text/markdown;charset=utf-8' }
    )
    const url = URL.createObjectURL(report)
    const link = document.createElement('a')
    link.href = url
    link.download = `${(evaluation.title || 'evaluation').replace(/[^a-z0-9]/gi, '_')}-Memorandum.md`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-theme-bg bp-grid text-theme-text flex flex-col justify-between">
        <Navbar />
        <div className="flex-1 flex items-center justify-center">
          <div className="bp-panel p-8 rounded-xl border border-theme-border flex flex-col items-center gap-3">
            <div className="w-8 h-8 rounded-full border-2 border-theme-evidence border-t-transparent animate-spin" />
            <p className="font-mono text-xs text-theme-text-secondary uppercase">
              Loading Saved Dossier...
            </p>
          </div>
        </div>
      </div>
    )
  }

  if (error || !evaluation) {
    return (
      <div className="min-h-screen bg-theme-bg bp-grid text-theme-text flex flex-col justify-between">
        <Navbar />
        <div className="flex-1 max-w-xl w-full mx-auto px-4 py-16 flex flex-col items-center justify-center">
          <div className="bp-panel p-8 rounded-xl border border-theme-border text-center w-full">
            <div className="w-12 h-12 rounded-full bg-theme-error/15 text-theme-error flex items-center justify-center font-mono text-lg font-bold mx-auto mb-3">
              !
            </div>
            <h2 className="text-lg font-bold text-theme-text mb-1">Dossier Unavailable</h2>
            <p className="font-mono text-xs text-theme-text-secondary mb-6">
              {error || 'This evaluation record could not be found or you do not have permission to view it.'}
            </p>
            <Link
              to="/history"
              className="px-4 py-2 rounded-lg bg-theme-evidence text-white dark:text-ink-950 font-mono text-xs font-bold"
            >
              ← Return to Archive
            </Link>
          </div>
        </div>
      </div>
    )
  }

  const results = evaluation.results || {}
  const attackMode = Boolean(evaluation.attack_mode)

  return (
    <div className="min-h-screen bg-theme-bg bp-grid text-theme-text flex flex-col transition-colors duration-200">
      <Navbar />

      {/* Dossier Header Bar */}
      <header className="border-b border-theme-border bg-theme-panel/90 backdrop-blur-md sticky top-[57px] z-10 transition-colors duration-200">
        <div className="max-w-6xl mx-auto px-4 py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <Link
              to="/history"
              className="px-2.5 py-1 rounded border border-theme-border bg-theme-panel-subtle hover:border-theme-border-active font-mono text-micro text-theme-text-secondary hover:text-theme-text transition-colors"
            >
              ← ARCHIVE
            </Link>
            <div className="truncate">
              <span className="font-bold text-sm tracking-tight text-theme-text block truncate">
                {evaluation.title}
              </span>
              <span className="font-mono text-[10px] text-theme-text-muted">
                SAVED {new Date(evaluation.created_at).toLocaleString()} • ID: {evaluation.id.slice(0, 8)}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              onClick={handleDownloadReport}
              type="button"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-theme-border bg-theme-panel-subtle hover:border-theme-border-active text-xs font-mono text-theme-text-secondary hover:text-theme-text transition-colors"
            >
              <span>EXPORT .MD</span>
            </button>

            <button
              onClick={handleDelete}
              disabled={deleting}
              type="button"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-theme-border bg-theme-panel-subtle hover:bg-theme-error/10 hover:border-theme-error hover:text-theme-error text-xs font-mono text-theme-text-muted transition-colors"
            >
              <span>{deleting ? 'DELETING...' : 'DELETE'}</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Dashboard Container */}
      <main className="flex-1 max-w-6xl w-full mx-auto px-4 py-8 space-y-6">
        {/* Executive Overall Score */}
        <section id="executive-verdict">
          <OverallScore data={results.chief_judge} attackMode={attackMode} />
        </section>

        {/* Research Assisted Banner */}
        {evaluation.research_assisted && (
          <div className="flex items-center justify-between p-3 rounded-xl bg-theme-evidence/10 border border-theme-evidence/30 text-xs font-mono">
            <div className="flex items-center gap-2 text-theme-evidence">
              <span>🔍</span>
              <span>AGENT37 MARKET RECON BOUND TO DELIBERATION DATASET</span>
            </div>
            <span className="text-theme-text-muted text-micro">GROUNDED COMPETITOR SENSING</span>
          </div>
        )}

        {/* Radar Chart + Consensus Analysis Matrix */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <RadarChart
            scores={{
              innovation: results.innovation?.score,
              technical: results.technical?.score,
              business: results.business?.score,
              presentation: results.presentation?.score,
            }}
          />
          <ConsensusCard consensus={results.consensus} />
        </div>

        {/* Differentiation & Moat + Judge Interrogation Questions */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <DifferentiationCard data={results.chief_judge?.differentiation} />
          <JudgeQuestions
            questions={results.chief_judge?.judge_questions}
            attackMode={attackMode}
          />
        </div>

        {/* Specialist Detailed Audit Cards */}
        <section className="space-y-4 pt-4">
          <div className="flex items-center justify-between pb-2 border-b border-theme-border">
            <span className="section-label">SPECIALIST PANELS // GRANULAR AUDIT REPORTS</span>
            <span className="font-mono text-micro text-theme-text-muted">4 INDEPENDENT AGENTS</span>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {['innovation', 'technical', 'business', 'presentation'].map((type) => (
              <ScoreCard key={type} type={type} data={results[type]} />
            ))}
          </div>
        </section>
      </main>

      <footer className="border-t border-theme-border py-6 px-4 bg-theme-panel">
        <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4 font-mono text-micro text-theme-text-muted">
          <span>IDEAVALIDATOR AI // HISTORICAL AUDIT DOSSIER</span>
          <span>AUTONOMOUS MULTI-AGENT GROUNDING ENGINE</span>
        </div>
      </footer>
    </div>
  )
}
