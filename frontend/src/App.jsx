import { useState, useRef } from 'react'
import { Routes, Route, Navigate, Link } from 'react-router-dom'
import UploadZone from './components/UploadZone'
import LoadingScreen from './components/LoadingScreen'
import ScoreCard from './components/ScoreCard'
import OverallScore from './components/OverallScore'
import JudgeQuestions from './components/JudgeQuestions'
import RadarChart from './components/RadarChart'
import ConsensusCard from './components/ConsensusCard'
import DifferentiationCard from './components/DifferentiationCard'
import ThemeToggle from './components/ThemeToggle'
import Navbar from './components/Navbar'
import SaveEvaluationButton from './components/SaveEvaluationButton'
import ProtectedRoute from './components/ProtectedRoute'
import LoginPage from './pages/LoginPage'
import SignupPage from './pages/SignupPage'
import DashboardPage from './pages/DashboardPage'
import HistoryPage from './pages/HistoryPage'
import EvaluationDetailPage from './pages/EvaluationDetailPage'
import { useAuth } from './context/AuthContext'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// Technical Blueprint Icons
const PresentationIcon = () => (
  <svg className="w-5 h-5 text-theme-evidence" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
      d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
  </svg>
)

const MarkdownIcon = () => (
  <svg className="w-5 h-5 text-brand-500 dark:text-brand-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
      d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
  </svg>
)

const BoltIcon = () => (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5}
      d="M13 10V3L4 14h7v7l9-11h-7z" />
  </svg>
)

const ArrowLeftIcon = () => (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
  </svg>
)

const DownloadIcon = () => (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v12m0 0l-4-4m4 4l4-4M5 21h14" />
  </svg>
)

const ResearchIcon = () => (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
      d="M21 21l-4.35-4.35M11 19a8 8 0 100-16 8 8 0 000 16z" />
  </svg>
)

const CopyIcon = () => (
  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
      d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
  </svg>
)

const CheckIcon = () => (
  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
  </svg>
)

function markdownList(items) {
  return (items || []).map(item => `- ${item}`).join('\n') || '- None provided'
}

function buildMarkdownReport(results, attackMode) {
  const chief = results.chief_judge || {}
  const consensus = results.consensus || {}
  const diff = chief.differentiation || {}
  const judgeLabels = {
    innovation: 'Innovation & Novelty Specialist',
    technical: 'Technical Architecture Specialist',
    business: 'Business Viability Specialist',
    presentation: 'Presentation & Pitch Specialist',
  }

  const specialistReports = Object.entries(judgeLabels).map(([type, label]) => {
    const report = results[type] || {}
    const confLine = report.confidence != null ? ` | **Confidence:** ${report.confidence}%` : ''
    const evidLine = report.evidence_quality != null ? ` | **Evidence Quality:** ${report.evidence_quality}%` : ''

    let findingsSection = ''
    if (report.key_findings?.length > 0) {
      const findingLines = report.key_findings.map(f =>
        `- **[${(f.evidence_type || 'N/A').toUpperCase()}]** ${f.finding}\n  Evidence: ${f.evidence || 'Not directly verified'}${f.source && f.source !== 'N/A' ? ` (Source: ${f.source})` : ''}`
      ).join('\n')
      findingsSection = `\n\n### Key Findings\n${findingLines}`
    }

    return `## ${label}\n\n**Score:** ${report.score ?? 'N/A'}/10${confLine}${evidLine}\n\n**Comments:** ${report.comments || 'None provided'}\n\n### Strengths\n${markdownList(report.strengths)}\n\n### Weaknesses\n${markdownList(report.weaknesses)}${findingsSection}`
  }).join('\n\n')

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
    const rows = chief.prioritized_roadmap.map(r =>
      `| ${r.priority} | ${r.title} | ${r.reason || '—'} | ${r.impact} | ${r.effort} |`
    ).join('\n')
    roadmapSection = `\n## Prioritized Remediation Roadmap\n\n| Priority | Action | Reason | Impact | Effort |\n|----------|--------|--------|--------|--------|\n${rows}\n`
  } else {
    const items = (chief.improvement_roadmap || []).map((step, index) => `${index + 1}. ${step}`).join('\n')
    roadmapSection = `\n### Improvement Roadmap\n${items || '1. None provided'}\n`
  }

  const confEvid = []
  if (chief.confidence != null) confEvid.push(`**Confidence:** ${chief.confidence}%`)
  if (chief.evidence_quality != null) confEvid.push(`**Evidence Quality:** ${chief.evidence_quality}%`)
  const confEvidLine = confEvid.length > 0 ? confEvid.join(' | ') + '\n' : ''

  return `# IdeaValidator AI // Technical Evaluation Memorandum\n\nGenerated: ${new Date().toISOString()}\nExecution Mode: ${attackMode ? 'Adversarial Stress Test (Attack Mode)' : 'Standard Multi-Agent Panel'}\n\n## Executive Verdict\n\n**Overall Index:** ${chief.overall_score ?? 'N/A'}/10.0\n${confEvidLine}\n${chief.final_verdict || 'None provided'}\n\n### Top Strengths\n${markdownList(chief.top_strengths)}\n\n### Critical Deficits\n${markdownList(chief.top_improvements)}\n${roadmapSection}${consensusSection}${diffSection}\n## Defense Questions For The Team\n\n${markdownList(chief.judge_questions)}\n\n${specialistReports}\n`
}

function Toggle({ enabled, onToggle, label, sublabel }) {
  return (
    <div
      onClick={onToggle}
      className={`group relative flex items-center justify-between p-4 rounded-xl border cursor-pointer transition-all duration-200 select-none ${
        enabled
          ? 'border-theme-error/40 bg-theme-error/10 shadow-sm'
          : 'border-theme-border bg-theme-panel hover:border-theme-border-active hover:bg-theme-panel-subtle'
      }`}
    >
      <div className="flex-1 pr-4">
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${enabled ? 'bg-theme-error animate-ping' : 'bg-theme-text-muted'}`} />
          <p className={`text-xs font-mono font-bold uppercase tracking-wider ${enabled ? 'text-theme-error' : 'text-theme-text'}`}>
            {label}
          </p>
        </div>
        <p className="text-micro text-theme-text-secondary font-mono mt-1 pl-4">
          {sublabel}
        </p>
      </div>
      <div className={`relative w-11 h-6 rounded-full transition-all duration-300 flex-shrink-0 p-0.5 border ${
        enabled ? 'bg-theme-error/30 border-theme-error' : 'bg-theme-chip border-theme-border'
      }`}>
        <div className={`w-4.5 h-4.5 rounded-full transition-all duration-300 shadow-sm ${
          enabled ? 'translate-x-5 bg-theme-error' : 'translate-x-0 bg-theme-text-muted'
        }`} />
      </div>
    </div>
  )
}

function ErrorBanner({ message, onDismiss }) {
  const isDailyQuota = typeof message === 'string' && (
    message.toLowerCase().includes('daily') && (message.toLowerCase().includes('quota') || message.toLowerCase().includes('limit'))
  )
  const isRateLimit = typeof message === 'string' && (
    !isDailyQuota && (message.toLowerCase().includes('rate limit') || message.toLowerCase().includes('rpm'))
  )

  return (
    <div className={`flex items-start gap-3 p-4 rounded-xl animate-slide-up border ${
      isDailyQuota
        ? 'bg-amber-500/10 border-amber-500/30'
        : 'bg-theme-error/10 border-theme-error/30'
    }`}>
      <span className={`font-mono font-bold text-sm mt-0.5 ${
        isDailyQuota ? 'text-amber-500' : 'text-theme-error'
      }`}>
        {isDailyQuota ? '[QUOTA]' : isRateLimit ? '[RPM]' : '[ERR]'}
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1 flex-wrap">
          <p className={`text-xs font-mono font-bold uppercase tracking-wider ${
            isDailyQuota ? 'text-amber-500' : 'text-theme-error'
          }`}>
            {isDailyQuota
              ? 'Daily API Quota Exhausted'
              : isRateLimit
              ? 'Temporary Rate Limit Reached'
              : 'Evaluation Protocol Halted'}
          </p>
          {isDailyQuota && (
            <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-amber-500/20 text-amber-600 dark:text-amber-400 font-semibold uppercase">
              Daily Limit
            </span>
          )}
        </div>
        <p className="text-xs text-theme-text font-mono leading-relaxed">{message}</p>
        {isDailyQuota && (
          <p className="text-[11px] font-mono text-theme-text-secondary mt-2 bg-theme-panel/60 p-2 rounded border border-theme-border">
            💡 <strong className="text-theme-text">Tip:</strong> Change <code className="text-theme-evidence font-bold">GEMINI_MODEL</code> in <code className="text-theme-evidence">backend/.env</code> (e.g. <code className="text-theme-evidence">gemini-1.5-flash</code>, <code className="text-theme-evidence">gemini-2.0-flash</code>, or <code className="text-theme-evidence">gemini-2.5-flash</code>) to resume without waiting for daily reset.
          </p>
        )}
      </div>
      <button onClick={onDismiss} type="button" className="text-theme-text-muted hover:text-theme-text font-mono text-xs p-1">
        ✕
      </button>
    </div>
  )
}

// Deep Market Reconnaissance Component
function MythosSection({ pitchDeck, readme, onResearchReady }) {
  const [step, setStep] = useState('idle')
  const [requestId, setRequestId] = useState(null)
  const [authToken, setAuthToken] = useState(null)
  const [researchPrompt, setResearchPrompt] = useState('')
  const [statusMessage, setStatusMessage] = useState('')
  const [jsonInput, setJsonInput] = useState('')
  const [copied, setCopied] = useState(false)
  const [importError, setImportError] = useState(null)
  const [competitorCount, setCompetitorCount] = useState(0)

  const canGenerate = pitchDeck || readme

  const handleAutomate = async () => {
    setStep('automating')
    setImportError(null)
    setStatusMessage('Initiating automated research pipeline via Agent37 Mythos...')
    const formData = new FormData()
    if (pitchDeck) formData.append('pitch_deck', pitchDeck)
    if (readme) formData.append('readme', readme)

    try {
      const res = await fetch(`${API_URL}/research/auto`, { method: 'POST', body: formData })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Failed to start automated research.')

      const rid = data.request_id
      setRequestId(rid)
      if (data.research_prompt) setResearchPrompt(data.research_prompt)

      let attempts = 0
      const pollInterval = setInterval(async () => {
        attempts++
        if (attempts > 5) {
          setStatusMessage('Synthesizing competitor evidence and market whitespace...')
        }
        try {
          const statusRes = await fetch(`${API_URL}/research/status/${rid}`)
          if (!statusRes.ok) {
            clearInterval(pollInterval)
            throw new Error('Failed to check research status.')
          }
          const statusData = await statusRes.json()

          if (statusData.status === 'completed') {
            clearInterval(pollInterval)
            setCompetitorCount(statusData.competitor_count || 0)
            setStep('done')
            onResearchReady(rid)
          } else if (statusData.status === 'failed') {
            clearInterval(pollInterval)
            setImportError(statusData.error || 'Automated research encountered an error.')
            if (statusData.research_prompt) setResearchPrompt(statusData.research_prompt)
            setStep('prompt')
          }
        } catch (pollErr) {
          clearInterval(pollInterval)
          setImportError(pollErr.message)
          setStep('prompt')
        }
      }, 2000)
    } catch (err) {
      setImportError(err.message)
      setStep('error')
    }
  }

  const handleGenerate = async () => {
    setStep('generating')
    setImportError(null)
    const formData = new FormData()
    if (pitchDeck) formData.append('pitch_deck', pitchDeck)
    if (readme) formData.append('readme', readme)
    try {
      const res = await fetch(`${API_URL}/research/request`, { method: 'POST', body: formData })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Failed to generate prompt specification.')
      setRequestId(data.request_id)
      setAuthToken(data.auth_token)
      setResearchPrompt(data.research_prompt)
      setStep('prompt')
    } catch (err) {
      setImportError(err.message)
      setStep('error')
    }
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(researchPrompt)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleImport = async () => {
    setImportError(null)
    setStep('importing')
    try {
      let parsed
      try {
        parsed = JSON.parse(jsonInput)
      } catch (e) {
        throw new Error('Invalid JSON format. Check brackets and quotes.')
      }

      const res = await fetch(`${API_URL}/research/callback`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
        },
        body: JSON.stringify(parsed),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Validation error while ingesting research dataset.')

      setCompetitorCount(data.competitor_count || 0)
      setStep('done')
      onResearchReady(requestId)
    } catch (err) {
      setImportError(err.message)
      setStep('prompt')
    }
  }

  if (step === 'done') {
    return (
      <div className="flex items-center justify-between p-4 rounded-xl border border-theme-positive/40 bg-theme-positive/10">
        <div className="flex items-center gap-2 text-theme-positive">
          <span className="font-mono text-sm font-bold">[RECON VERIFIED]</span>
          <span className="font-mono text-xs">
            Grounding active: {competitorCount} competitor entities ingested into synthesis buffer.
          </span>
        </div>
        <button
          onClick={() => {
            setStep('idle')
            setRequestId(null)
            onResearchReady(null)
          }}
          type="button"
          className="text-micro font-mono text-theme-positive hover:underline ml-4"
        >
          Detach
        </button>
      </div>
    )
  }

  if (step === 'idle' || step === 'error') {
    return (
      <div className="space-y-2">
        <div className="flex gap-2">
          <button
            onClick={handleAutomate}
            disabled={!canGenerate}
            type="button"
            id="mythos-automate-btn"
            className={`flex-1 flex items-center justify-center gap-2 py-3 px-4 rounded-xl border text-xs font-mono font-bold uppercase tracking-wider transition-all duration-200 ${
              canGenerate
                ? 'border-theme-evidence/40 bg-theme-evidence/10 text-theme-evidence hover:bg-theme-evidence/20 shadow-sm cursor-pointer'
                : 'border-theme-border bg-theme-panel text-theme-text-muted cursor-not-allowed opacity-60'
            }`}
          >
            <ResearchIcon />
            <span>Agent37 Deep Market Recon (Automated)</span>
          </button>
          <button
            onClick={handleGenerate}
            disabled={!canGenerate}
            type="button"
            id="mythos-manual-btn"
            title="Manual Prompt Specification Workflow"
            className={`px-3 py-3 rounded-xl border text-xs font-mono font-bold uppercase tracking-wider transition-all ${
              canGenerate
                ? 'border-theme-border bg-theme-panel hover:bg-theme-panel-subtle text-theme-text-secondary hover:text-theme-text cursor-pointer'
                : 'border-theme-border bg-theme-panel text-theme-text-muted cursor-not-allowed opacity-60'
            }`}
          >
            Manual
          </button>
        </div>
        {step === 'error' && importError && (
          <p className="text-micro font-mono text-theme-error pl-1">[ERR] {importError}</p>
        )}
      </div>
    )
  }

  if (step === 'automating') {
    return (
      <div className="p-4 rounded-xl border border-theme-border bg-theme-panel animate-pulse space-y-2">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-theme-evidence animate-ping" />
          <p className="text-xs font-mono font-bold uppercase tracking-wider text-theme-evidence">
            Agent37 Deep Market Recon Active
          </p>
        </div>
        <p className="text-micro text-theme-text-secondary font-mono pl-4">
          {statusMessage}
        </p>
      </div>
    )
  }

  if (step === 'generating') {
    return (
      <div className="p-4 rounded-xl border border-theme-border bg-theme-panel animate-pulse">
        <p className="text-xs font-mono text-theme-text-secondary uppercase">
          Synthesizing Research Prompt Specification...
        </p>
      </div>
    )
  }

  return (
    <div className="bp-panel p-4 rounded-xl border border-theme-border space-y-3">
      <div className="flex items-center justify-between pb-2 border-b border-theme-border">
        <span className="section-label">AGENT37 GROUNDING PROTOCOL</span>
        <span className="font-mono text-micro text-theme-text-muted">REQ ID: {requestId?.slice(0, 8)}...</span>
      </div>

      {importError && (
        <div className="p-2 rounded bg-theme-error/10 text-theme-error font-mono text-micro">
          [ERR] {importError}
        </div>
      )}

      <div>
        <label className="block text-micro font-mono uppercase text-theme-text-secondary mb-1">
          Market Intelligence Extraction Prompt
        </label>
        <div className="relative">
          <textarea
            readOnly
            value={researchPrompt}
            className="w-full h-24 bg-theme-panel border border-theme-border rounded-lg p-2.5 text-micro text-theme-text font-mono resize-none focus:outline-none"
          />
        </div>
        <button
          onClick={handleCopy}
          type="button"
          className="mt-1 flex items-center gap-1.5 text-micro font-mono text-theme-evidence hover:underline"
        >
          {copied ? <CheckIcon /> : <CopyIcon />}
          <span>{copied ? 'Copied Specification' : 'Copy Prompt Specification'}</span>
        </button>
      </div>

      <div>
        <label className="block text-micro font-mono uppercase text-theme-text-secondary mb-1">
          Ingest Mythos Schema Response (JSON)
        </label>
        <textarea
          id="mythos-json-input"
          className="w-full h-24 bg-theme-panel border border-theme-border rounded-lg p-2.5 text-micro text-theme-text font-mono resize-none focus:outline-none focus:border-theme-border-active"
          placeholder='{"schema_version": "1.0", "request_id": "...", "competitors": [...]}'
          value={jsonInput}
          onChange={(e) => setJsonInput(e.target.value)}
        />
      </div>

      <div className="flex gap-2">
        <button
          onClick={handleImport}
          disabled={!jsonInput.trim() || step === 'importing'}
          type="button"
          id="mythos-import-btn"
          className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-xs font-mono font-bold uppercase tracking-wider transition-all ${
            jsonInput.trim() && step !== 'importing'
              ? 'bg-theme-evidence text-white dark:text-ink-950 hover:opacity-90 shadow-sm'
              : 'bg-theme-chip text-theme-text-muted cursor-not-allowed border border-theme-border'
          }`}
        >
          {step === 'importing' ? 'Ingesting Schema Data...' : 'Import Recon Data'}
        </button>
        <button
          onClick={handleAutomate}
          disabled={!canGenerate}
          type="button"
          title="Retry automated recon"
          className="px-3 py-2 rounded-lg text-xs font-mono bg-theme-chip hover:bg-theme-panel text-theme-text border border-theme-border"
        >
          ↺ Retry Auto
        </button>
      </div>
    </div>
  )
}

// Studio Component (Intake + Live Session Results View)
function Studio() {
  const [pitchDeck, setPitchDeck] = useState(null)
  const [readme, setReadme] = useState(null)
  const [attackMode, setAttackMode] = useState(false)
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState(null)
  const [error, setError] = useState(null)
  const [evalStage, setEvalStage] = useState(null)
  const [researchRequestId, setResearchRequestId] = useState(null)

  const isSubmittingRef = useRef(false)
  const canEvaluate = pitchDeck || readme

  const handleEvaluate = async () => {
    if (!canEvaluate || loading || isSubmittingRef.current) return
    isSubmittingRef.current = true
    setError(null)
    setLoading(true)
    setResults(null)
    setEvalStage('Specialist Judges')

    const formData = new FormData()
    if (pitchDeck) formData.append('pitch_deck', pitchDeck)
    if (readme) formData.append('readme', readme)
    formData.append('attack_mode', String(attackMode))
    if (researchRequestId) formData.append('research_request_id', researchRequestId)

    try {
      const asyncRes = await fetch(`${API_URL}/evaluate/async`, {
        method: 'POST',
        body: formData,
      })

      if (asyncRes.status === 202) {
        const asyncData = await asyncRes.json()
        const jobId = asyncData.job_id
        if (!jobId) throw new Error(asyncData.detail || 'Failed to initialize evaluation job.')
        if (asyncData.stage) setEvalStage(asyncData.stage)

        await new Promise((resolve, reject) => {
          const pollInterval = setInterval(async () => {
            try {
              const statusRes = await fetch(`${API_URL}/evaluate/status/${jobId}`)
              if (!statusRes.ok) {
                clearInterval(pollInterval)
                let errMsg = `Status check failed (${statusRes.status})`
                try {
                  const errPayload = await statusRes.json()
                  if (errPayload && (errPayload.detail || errPayload.error)) {
                    errMsg = errPayload.detail || errPayload.error
                  }
                } catch (_) {}
                reject(new Error(errMsg))
                return
              }
              const statusData = await statusRes.json()
              if (statusData.stage) setEvalStage(statusData.stage)

              if (statusData.status === 'completed') {
                clearInterval(pollInterval)
                setResults(statusData.results)
                resolve()
              } else if (statusData.status === 'failed') {
                clearInterval(pollInterval)
                reject(new Error(statusData.detail || statusData.error || 'Evaluation failed.'))
              }
            } catch (pollErr) {
              clearInterval(pollInterval)
              reject(pollErr)
            }
          }, 1500)
        })
      } else if (asyncRes.status === 409) {
        const conflictData = await asyncRes.json().catch(() => ({}))
        throw new Error(conflictData.detail || 'An evaluation is already running.')
      } else if (asyncRes.status === 404) {
        const res = await fetch(`${API_URL}/evaluate`, { method: 'POST', body: formData })
        const data = await res.json()
        if (!res.ok) throw new Error(data.detail || `Server error (${res.status})`)
        setResults(data)
      } else {
        const errData = await asyncRes.json().catch(() => ({}))
        throw new Error(errData.detail || `Evaluation request failed (${asyncRes.status})`)
      }
    } catch (err) {
      if (err.name === 'TypeError' && err.message.includes('fetch')) {
        setError('Cannot connect to backend service at http://localhost:8000')
      } else {
        setError(err.message || 'An unexpected evaluation error occurred.')
      }
    } finally {
      isSubmittingRef.current = false
      setLoading(false)
      setEvalStage(null)
    }
  }

  const handleReset = () => {
    setResults(null)
    setError(null)
    setPitchDeck(null)
    setReadme(null)
    setAttackMode(false)
    setResearchRequestId(null)
    setEvalStage(null)
  }

  const handleDownloadReport = () => {
    const report = new Blob([buildMarkdownReport(results, attackMode)], {
      type: 'text/markdown;charset=utf-8',
    })
    const url = URL.createObjectURL(report)
    const link = document.createElement('a')
    link.href = url
    link.download = `IdeaValidator-AI-Memorandum-${new Date().toISOString().slice(0, 10)}.md`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

  if (loading) return <LoadingScreen attackMode={attackMode} stage={evalStage} />

  // Evaluation Results Dashboard View
  if (results) {
    return (
      <div className="min-h-screen bg-theme-bg bp-grid text-theme-text flex flex-col transition-colors duration-200">
        {/* Top Navigation & Telemetry Bar */}
        <header className="border-b border-theme-border bg-theme-panel/90 backdrop-blur-md sticky top-0 z-30 transition-colors duration-200">
          <div className="max-w-6xl mx-auto px-4 py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="w-7 h-7 rounded bg-theme-evidence/15 border border-theme-evidence/30 flex items-center justify-center font-mono font-bold text-xs text-theme-evidence">
                ⚖
              </div>
              <div className="flex items-baseline gap-2">
                <span className="font-bold text-sm tracking-tight text-theme-text">
                  IDEAVALIDATOR
                </span>
                <span className="font-mono text-micro text-theme-text-muted uppercase">
                  // ARBITRATION DOSSIER
                </span>
              </div>
            </div>

            <div className="flex items-center gap-2.5 flex-wrap">
              {/* Save Evaluation Button (Hybrid: Auth prompt or Direct Save) */}
              <SaveEvaluationButton
                results={results}
                attackMode={attackMode}
                pitchDeck={pitchDeck}
                readme={readme}
                researchAssisted={Boolean(researchRequestId)}
              />

              <button
                onClick={handleDownloadReport}
                type="button"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-theme-border bg-theme-panel-subtle hover:border-theme-border-active text-xs font-mono text-theme-text-secondary hover:text-theme-text transition-colors"
              >
                <DownloadIcon />
                <span>EXPORT .MD</span>
              </button>

              <button
                onClick={handleReset}
                type="button"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-theme-border bg-theme-panel-subtle hover:border-theme-border-active text-xs font-mono text-theme-evidence transition-colors"
              >
                <ArrowLeftIcon />
                <span>NEW EVALUATION</span>
              </button>

              <ThemeToggle />
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
          {results.research_assisted && (
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

        {/* Studio Footer */}
        <footer className="border-t border-theme-border py-6 px-4 bg-theme-panel">
          <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4 font-mono text-micro text-theme-text-muted">
            <span>IDEAVALIDATOR AI // ENGINEERING STUDIO v2.4</span>
            <span>AUTONOMOUS MULTI-AGENT GROUNDING ENGINE</span>
          </div>
        </footer>
      </div>
    )
  }

  // Intake Workbench Landing View
  return (
    <div className="min-h-screen bg-theme-bg bp-grid text-theme-text flex flex-col justify-between transition-colors duration-200">
      {/* Shared Navigation Bar with Auth Links */}
      <Navbar />

      {/* Main Intake Section */}
      <main className="flex-1 max-w-4xl w-full mx-auto px-4 py-12 flex flex-col items-center justify-center">
        <div className="w-full max-w-2xl animate-fade-in">
          {/* Header Title & Swiss Typography */}
          <div className="text-center mb-8">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-theme-chip border border-theme-border font-mono text-micro text-theme-evidence mb-4">
              <span>● MULTI-AGENT ASYNCHRONOUS EVALUATION</span>
            </div>
            <h1 className="text-3xl sm:text-4xl font-extrabold text-theme-text tracking-tight leading-tight mb-3">
              Stress-test your startup before <br />
              <span className="text-gradient">the investment panel does.</span>
            </h1>
            <p className="text-theme-text-secondary text-sm max-w-lg mx-auto font-sans leading-relaxed">
              Upload your pitch deck or technical specification. Four specialist AI judges evaluate your thesis independently before a Chief Justice synthesizes the executive verdict.
            </p>
          </div>

          {/* Workbench Panel */}
          <div className="bp-panel p-6 sm:p-8 rounded-2xl border border-theme-border space-y-6 relative">
            <div className="corner-marks" />
            <div className="top-highlight" />

            {/* Error Banner */}
            {error && (
              <ErrorBanner
                message={error}
                onDismiss={() => setError(null)}
              />
            )}

            {/* Ingestion Channels */}
            <div>
              <div className="flex items-center justify-between pb-2 border-b border-theme-border mb-4">
                <span className="section-label">INGESTION CHANNELS // PRIMARY SOURCES</span>
                <span className="font-mono text-micro text-theme-text-muted">MIN 1 REQUIRED</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <UploadZone
                  label="PITCH DECK"
                  accept=".pdf"
                  file={pitchDeck}
                  onFileSelect={setPitchDeck}
                  onFile={setPitchDeck}
                  hint="Slide deck, executive memo, or one-pager"
                  badgeText="PDF · MAX 20MB"
                  icon={<PresentationIcon />}
                  id="pitch-deck"
                />
                <UploadZone
                  label="TECHNICAL README"
                  accept=".md,.txt"
                  file={readme}
                  onFileSelect={setReadme}
                  onFile={setReadme}
                  hint="Architecture doc, system design, or spec"
                  badgeText="MD / TXT · MAX 5MB"
                  icon={<MarkdownIcon />}
                  id="readme"
                />
              </div>
            </div>

            {/* Deep Market Reconnaissance (Mythos) */}
            <div>
              <div className="flex items-center justify-between pb-2 border-b border-theme-border mb-3">
                <span className="section-label">EXTERNAL GROUNDING ENGINE</span>
                <span className="font-mono text-micro text-theme-text-muted">OPTIONAL RECON</span>
              </div>
              <MythosSection
                pitchDeck={pitchDeck}
                readme={readme}
                onResearchReady={(id) => setResearchRequestId(id)}
              />
            </div>

            {/* Execution Parameter Configuration */}
            <div>
              <div className="flex items-center justify-between pb-2 border-b border-theme-border mb-3">
                <span className="section-label">DELIBERATION PROTOCOL</span>
                <span className="font-mono text-micro text-theme-text-muted">PARAM CFG</span>
              </div>
              <Toggle
                enabled={attackMode}
                onToggle={() => setAttackMode(!attackMode)}
                label="Adversarial Attack Mode"
                sublabel="Judges assume hostile competitor posture, actively penalize ambiguity, and simulate deep-diligence cross-examination."
              />
            </div>

            {/* Execution Trigger */}
            <div className="pt-2">
              <button
                onClick={handleEvaluate}
                disabled={!canEvaluate || loading}
                type="button"
                id="evaluate-btn"
                className={`w-full py-4 rounded-xl font-mono font-bold text-xs uppercase tracking-widest transition-all duration-200 flex items-center justify-center gap-2.5 relative overflow-hidden group select-none ${
                  canEvaluate && !loading
                    ? attackMode
                      ? 'bg-theme-error text-white hover:opacity-90 shadow-md hover:shadow-lg active:scale-[0.99] cursor-pointer'
                      : 'bg-theme-evidence text-white dark:text-ink-950 hover:opacity-90 shadow-md hover:shadow-lg active:scale-[0.99] cursor-pointer'
                    : 'bg-theme-chip text-theme-text-muted cursor-not-allowed border border-theme-border opacity-50'
                }`}
              >
                <BoltIcon />
                <span>
                  {canEvaluate
                    ? attackMode
                      ? 'Launch Adversarial Stress-Test Protocol →'
                      : 'Initiate Multi-Agent Arbitration →'
                    : 'Attach Pitch Deck or README to Begin'}
                </span>
              </button>
            </div>
          </div>

          {/* System Spec Badges */}
          <div className="mt-8 flex flex-wrap justify-center gap-2 text-micro font-mono text-theme-text-secondary">
            {[
              '4 SPECIALIST AGENTS',
              'CHIEF JUSTICE SYNTHESIS',
              'BAYESIAN CONSENSUS SYNTHESIS',
              'EMPIRICAL EVIDENCE AUDIT',
              'DIFFERENTIATION MOAT MAPPING',
            ].map((badge) => (
              <span
                key={badge}
                className="px-2.5 py-1 rounded bg-theme-panel border border-theme-border shadow-xs"
              >
                {badge}
              </span>
            ))}
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-theme-border py-4 px-4 text-center bg-theme-panel">
        <p className="font-mono text-micro text-theme-text-muted">
          IDEAVALIDATOR AI // EPHEMERAL PIPELINE · ALL ARTIFACTS PARSED IN-MEMORY
        </p>
      </footer>
    </div>
  )
}

// Router Root
export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Studio />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<SignupPage />} />
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <DashboardPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/history"
        element={
          <ProtectedRoute>
            <HistoryPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/history/:id"
        element={
          <ProtectedRoute>
            <EvaluationDetailPage />
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
