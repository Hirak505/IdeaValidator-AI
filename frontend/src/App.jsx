import { useState } from 'react'
import UploadZone from './components/UploadZone'
import LoadingScreen from './components/LoadingScreen'
import ScoreCard from './components/ScoreCard'
import OverallScore from './components/OverallScore'
import JudgeQuestions from './components/JudgeQuestions'
import RadarChart from './components/RadarChart'
import ConsensusCard from './components/ConsensusCard'
import DifferentiationCard from './components/DifferentiationCard'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// Icons
const PresentationIcon = () => (
  <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
      d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
  </svg>
)

const MarkdownIcon = () => (
  <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
      d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
  </svg>
)

const BoltIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
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

function markdownList(items) {
  return (items || []).map(item => `- ${item}`).join('\n') || '- None provided'
}

function buildMarkdownReport(results, attackMode) {
  const chief = results.chief_judge || {}
  const consensus = results.consensus || {}
  const diff = chief.differentiation || {}
  const judgeLabels = {
    innovation: 'Innovation',
    technical: 'Technical',
    business: 'Business',
    presentation: 'Presentation',
  }

  // Build specialist reports with evidence
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

    return `## ${label} Judge\n\n**Score:** ${report.score ?? 'N/A'}/10${confLine}${evidLine}\n\n**Comments:** ${report.comments || 'None provided'}\n\n### Strengths\n${markdownList(report.strengths)}\n\n### Weaknesses\n${markdownList(report.weaknesses)}${findingsSection}`
  }).join('\n\n')

  // Build consensus section
  let consensusSection = ''
  if (consensus.mean != null) {
    consensusSection = `\n## Judge Consensus\n\n**Agreement Level:** ${consensus.agreement_level || 'N/A'}\n**Score Spread:** ${consensus.spread} points (${consensus.min} – ${consensus.max})\n**Most Aligned:** ${judgeLabels[consensus.most_aligned] || consensus.most_aligned}\n**Largest Disagreement:** ${judgeLabels[consensus.largest_disagreement] || consensus.largest_disagreement}\n`
  }

  // Build differentiation section
  let diffSection = ''
  if (diff.solution_category && diff.solution_category !== 'Not determined') {
    diffSection = `\n## Differentiation Analysis\n\n**Category:** ${diff.solution_category}\n`
    if (diff.differentiation_strengths?.[0] !== 'Not determined') diffSection += `\n**Strengths:**\n${markdownList(diff.differentiation_strengths)}\n`
    if (diff.differentiation_gaps?.[0] !== 'Not determined') diffSection += `\n**Gaps:**\n${markdownList(diff.differentiation_gaps)}\n`
    if (diff.unsupported_claims?.length > 0) diffSection += `\n**Unsupported Claims:**\n${markdownList(diff.unsupported_claims)}\n`
    if (diff.limitation_note) diffSection += `\n*${diff.limitation_note}*\n`
  }

  // Build prioritized roadmap
  let roadmapSection = ''
  if (chief.prioritized_roadmap?.length > 0) {
    const rows = chief.prioritized_roadmap.map(r =>
      `| ${r.priority} | ${r.title} | ${r.reason || '—'} | ${r.impact} | ${r.effort} |`
    ).join('\n')
    roadmapSection = `\n## Prioritized Roadmap\n\n| Priority | Action | Reason | Impact | Effort |\n|----------|--------|--------|--------|--------|\n${rows}\n`
  } else {
    const items = (chief.improvement_roadmap || []).map((step, index) => `${index + 1}. ${step}`).join('\n')
    roadmapSection = `\n### Improvement Roadmap\n${items || '1. None provided'}\n`
  }

  // Confidence line
  const confEvid = []
  if (chief.confidence != null) confEvid.push(`**Confidence:** ${chief.confidence}%`)
  if (chief.evidence_quality != null) confEvid.push(`**Evidence Quality:** ${chief.evidence_quality}%`)
  const confEvidLine = confEvid.length > 0 ? confEvid.join(' | ') + '\n' : ''

  return `# IdeaValidator AI Report\n\nGenerated: ${new Date().toISOString().slice(0, 10)}\nJudge Attack Mode: ${attackMode ? 'Enabled' : 'Disabled'}\n\n## Final Verdict\n\n**Overall Score:** ${chief.overall_score ?? 'N/A'}/10\n${confEvidLine}\n${chief.final_verdict || 'None provided'}\n\n### Top Strengths\n${markdownList(chief.top_strengths)}\n\n### Key Improvements\n${markdownList(chief.top_improvements)}\n${roadmapSection}${consensusSection}${diffSection}\n## Questions For The Team\n\n${markdownList(chief.judge_questions)}\n\n${specialistReports}\n`
}

function Toggle({ enabled, onToggle, label, sublabel }) {
  return (
    <div
      className={`
        group relative flex items-center gap-4 p-4 rounded-xl border cursor-pointer transition-all duration-200
        ${enabled
          ? 'border-rose-500/40 bg-rose-500/8 shadow-lg shadow-rose-500/10'
          : 'border-slate-700/60 hover:border-slate-600'
        }
      `}
      onClick={onToggle}
    >
      <div className="flex-1">
        <div className="flex items-center gap-2">
          <span className="text-base">{enabled ? '⚡' : '🎯'}</span>
          <p className={`text-sm font-semibold transition-colors ${enabled ? 'text-rose-200' : 'text-slate-300'}`}>
            {label}
          </p>
        </div>
        <p className="text-xs text-slate-500 mt-0.5 ml-6">{sublabel}</p>
      </div>
      <div className={`
        relative w-11 h-6 rounded-full transition-all duration-300 flex-shrink-0
        ${enabled ? 'bg-rose-500' : 'bg-slate-700'}
      `}>
        <div className={`
          absolute top-1 w-4 h-4 bg-white rounded-full shadow transition-all duration-300
          ${enabled ? 'left-6' : 'left-1'}
        `} />
      </div>
    </div>
  )
}

function ErrorBanner({ message, onDismiss }) {
  return (
    <div className="flex items-start gap-3 p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 animate-slide-up">
      <span className="text-rose-400 text-lg flex-shrink-0">✕</span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-rose-300 mb-0.5">Evaluation failed</p>
        <p className="text-sm text-rose-300/70 leading-relaxed">{message}</p>
      </div>
      <button onClick={onDismiss} className="text-rose-400/50 hover:text-rose-400 flex-shrink-0">
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  )
}

// ---- Mythos Research Icons ----
const ResearchIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
      d="M21 21l-4.35-4.35M11 19a8 8 0 100-16 8 8 0 000 16z" />
  </svg>
)

const CopyIcon = () => (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
      d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
  </svg>
)

const CheckIcon = () => (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
  </svg>
)

// ---- MythosSection component ----
function MythosSection({ pitchDeck, readme, onResearchReady }) {
  const [step, setStep] = useState('idle') // idle | generating | prompt | importing | done | error
  const [requestId, setRequestId] = useState(null)
  const [authToken, setAuthToken] = useState(null)  // kept in memory only, never logged
  const [researchPrompt, setResearchPrompt] = useState('')
  const [jsonInput, setJsonInput] = useState('')
  const [copied, setCopied] = useState(false)
  const [importError, setImportError] = useState(null)
  const [competitorCount, setCompetitorCount] = useState(0)

  const canGenerate = pitchDeck || readme

  const handleGenerate = async () => {
    setStep('generating')
    setImportError(null)
    const formData = new FormData()
    if (pitchDeck) formData.append('pitch_deck', pitchDeck)
    if (readme) formData.append('readme', readme)
    try {
      const res = await fetch(`${API_URL}/research/request`, { method: 'POST', body: formData })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Failed to create research request.')
      setRequestId(data.request_id)
      setAuthToken(data.auth_token)   // held in component state, never surfaced in the prompt
      setResearchPrompt(data.research_prompt)
      setStep('prompt')
    } catch (err) {
      setImportError(err.message)
      setStep('error')
    }
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(researchPrompt).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  const handleImport = async () => {
    setImportError(null)
    setStep('importing')
    try {
      const formData = new FormData()
      formData.append('request_id', requestId)
      formData.append('research_json', jsonInput.trim())
      const res = await fetch(`${API_URL}/research/import`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${authToken}` },
        body: formData,
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Import failed.')
      setCompetitorCount(data.competitor_count || 0)
      setStep('done')
      onResearchReady(requestId)
    } catch (err) {
      setImportError(err.message)
      setStep('prompt')
    }
  }

  if (step === 'idle' || step === 'error') {
    return (
      <div className="rounded-xl border border-slate-700/60 bg-surface-900/60 p-4">
        <div className="flex items-center gap-3 mb-3">
          <span className="text-lg">🔍</span>
          <div>
            <p className="text-sm font-semibold text-slate-200">Market Research with Mythos</p>
            <p className="text-xs text-slate-500 mt-0.5">Use Agent37 Mythos to research competitors and enrich your evaluation.</p>
          </div>
        </div>
        {step === 'error' && importError && (
          <p className="text-xs text-rose-400 mb-3">{importError}</p>
        )}
        <button
          onClick={handleGenerate}
          disabled={!canGenerate}
          id="mythos-generate-btn"
          className={`w-full flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-medium transition-colors
            ${canGenerate
              ? 'bg-indigo-600/30 border border-indigo-500/50 text-indigo-300 hover:bg-indigo-500/30 hover:border-indigo-400/60'
              : 'bg-slate-800 border border-slate-700 text-slate-600 cursor-not-allowed'}`}
        >
          <ResearchIcon />
          Generate Mythos Research Prompt
        </button>
        {!canGenerate && <p className="text-center text-xs text-slate-600 mt-2">Upload a file first to generate a research prompt.</p>}
      </div>
    )
  }

  if (step === 'generating') {
    return (
      <div className="rounded-xl border border-slate-700/60 bg-surface-900/60 p-4 flex items-center gap-3">
        <div className="w-4 h-4 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
        <p className="text-sm text-slate-400">Generating research prompt…</p>
      </div>
    )
  }

  if (step === 'done') {
    return (
      <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-emerald-400"><CheckIcon /></span>
          <p className="text-sm font-semibold text-emerald-300">Research imported — {competitorCount} competitor{competitorCount !== 1 ? 's' : ''} loaded</p>
        </div>
        <p className="text-xs text-slate-500">Your next evaluation will include this market research context.</p>
      </div>
    )
  }

  // step === 'prompt' | 'importing'
  return (
    <div className="rounded-xl border border-indigo-500/30 bg-surface-900/60 p-4 space-y-4">
      <div className="flex items-center gap-2">
        <span className="text-lg">🔍</span>
        <p className="text-sm font-semibold text-indigo-200">Mythos Research Prompt</p>
      </div>

      <div className="relative">
        <pre className="text-xs text-slate-400 bg-surface-950 rounded-lg p-3 overflow-auto max-h-40 whitespace-pre-wrap border border-slate-800">
          {researchPrompt}
        </pre>
        <button
          onClick={handleCopy}
          id="mythos-copy-btn"
          className="absolute top-2 right-2 flex items-center gap-1 px-2 py-1 rounded-md text-xs bg-slate-800 border border-slate-700 text-slate-400 hover:text-white hover:border-slate-500 transition-colors"
        >
          {copied ? <><CheckIcon /> Copied!</> : <><CopyIcon /> Copy</>}
        </button>
      </div>

      <p className="text-xs text-slate-500">
        📋 Copy the prompt above → paste into <strong className="text-slate-300">Agent37 Mythos</strong> → paste the returned JSON below.
      </p>

      <div>
        <label className="block text-xs font-medium text-slate-400 mb-1.5">Paste Mythos JSON Response</label>
        <textarea
          id="mythos-json-input"
          className="w-full h-32 bg-surface-950 border border-slate-700 rounded-lg p-3 text-xs text-slate-300 font-mono resize-none focus:outline-none focus:border-indigo-500/60 transition-colors"
          placeholder='{"schema_version": "1.0", "request_id": "...", ...}'
          value={jsonInput}
          onChange={e => setJsonInput(e.target.value)}
        />
      </div>

      {importError && (
        <p className="text-xs text-rose-400">{importError}</p>
      )}

      <button
        onClick={handleImport}
        disabled={!jsonInput.trim() || step === 'importing'}
        id="mythos-import-btn"
        className={`w-full flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-medium transition-colors
          ${jsonInput.trim() && step !== 'importing'
            ? 'bg-indigo-600 hover:bg-indigo-500 text-white'
            : 'bg-slate-800 text-slate-600 cursor-not-allowed'}`}
      >
        {step === 'importing'
          ? <><div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" /> Importing…</>
          : 'Import Research'
        }
      </button>
    </div>
  )
}

// ---- CompetitorCard component ----
function CompetitorCard({ competitor }) {
  return (
    <div className="rounded-lg border border-indigo-500/20 bg-indigo-500/5 p-3">
      <p className="text-sm font-semibold text-indigo-200 mb-1">{competitor.name}</p>
      <p className="text-xs text-slate-400 mb-2">{competitor.description}</p>
      {competitor.differentiation && (
        <p className="text-xs text-slate-500 italic mb-2">vs. your idea: {competitor.differentiation}</p>
      )}
      {competitor.source_urls?.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-1">
          {competitor.source_urls.map((url, i) => (
            <a
              key={i}
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-indigo-400 hover:text-indigo-300 underline underline-offset-2 transition-colors"
            >
              Source {i + 1}
            </a>
          ))}
        </div>
      )}
    </div>
  )
}

export default function App() {
  const [pitchDeck, setPitchDeck] = useState(null)
  const [readme, setReadme] = useState(null)
  const [attackMode, setAttackMode] = useState(false)
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState(null)
  const [error, setError] = useState(null)
  // Mythos research state
  const [researchRequestId, setResearchRequestId] = useState(null)

  const canEvaluate = pitchDeck || readme

  const handleEvaluate = async () => {
    if (!canEvaluate) return
    setError(null)
    setLoading(true)
    setResults(null)

    const formData = new FormData()
    if (pitchDeck) formData.append('pitch_deck', pitchDeck)
    if (readme) formData.append('readme', readme)
    formData.append('attack_mode', String(attackMode))
    if (researchRequestId) formData.append('research_request_id', researchRequestId)

    try {
      const res = await fetch(`${API_URL}/evaluate`, {
        method: 'POST',
        body: formData,
      })

      const data = await res.json()

      if (!res.ok) {
        throw new Error(data.detail || `Server error (${res.status})`)
      }

      setResults(data)
    } catch (err) {
      if (err.name === 'TypeError' && err.message.includes('fetch')) {
        setError('Cannot connect to the backend. Make sure it is running on http://localhost:8000')
      } else {
        setError(err.message || 'An unexpected error occurred.')
      }
    } finally {
      setLoading(false)
    }
  }

  const handleReset = () => {
    setResults(null)
    setError(null)
    setPitchDeck(null)
    setReadme(null)
    setAttackMode(false)
    setResearchRequestId(null)
  }

  const handleDownloadReport = () => {
    const report = new Blob([buildMarkdownReport(results, attackMode)], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(report)
    const link = document.createElement('a')
    link.href = url
    link.download = 'ideavalidator-ai-report.md'
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

  if (loading) return <LoadingScreen attackMode={attackMode} />

  if (results) {
    return (
      <div className="min-h-screen bg-surface-950 bg-grid">
        <div className="max-w-5xl mx-auto px-4 py-8">
          {/* Results Header */}
          <div className="flex items-center justify-between mb-8 animate-fade-in">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <div className="w-2 h-2 rounded-full bg-emerald-400" />
                <span className="text-xs font-medium text-emerald-400 uppercase tracking-widest">Evaluation Complete</span>
              </div>
              <h1 className="text-2xl font-bold text-white">
                <span className="text-gradient">IdeaValidator AI</span> — Results
              </h1>
            </div>
            <button
              onClick={handleReset}
              className="flex items-center gap-2 px-4 py-2 rounded-lg border border-slate-700 text-slate-400 hover:text-white hover:border-slate-500 transition-colors text-sm"
            >
              <ArrowLeftIcon />
              Evaluate another
            </button>
          </div>

          {/* Overall Score */}
          <div className="mb-6">
            <OverallScore data={results.chief_judge} attackMode={attackMode} />
          </div>

          {/* Research-assisted badge */}
          {results.research_assisted && (
            <div className="mb-4 flex items-center gap-2 px-3 py-2 rounded-lg bg-indigo-500/10 border border-indigo-500/25 w-fit">
              <span className="text-xs">🔍</span>
              <span className="text-xs font-medium text-indigo-300">Evaluation includes Mythos market research</span>
            </div>
          )}

          {/* Competitor Cards (if research assisted) */}
          {results.research_assisted && results.chief_judge?.differentiation && (
            <div className="mb-6">
              <p className="text-xs font-medium text-slate-500 uppercase tracking-widest mb-3">External Market Research</p>
              <div className="grid sm:grid-cols-2 gap-3">
                {/* We surface competitor context from the differentiation block */}
                <div className="rounded-lg border border-indigo-500/20 bg-indigo-500/5 p-3 text-xs text-slate-400 italic">
                  Competitor research was used by Mythos and assessed by the Innovation and Business judges.
                  Sources are preserved in their source_urls fields per the v1.0 research schema.
                </div>
              </div>
            </div>
          )}

          {/* Radar + Consensus */}
          <div className="grid sm:grid-cols-2 gap-4 mb-6">
            <RadarChart scores={{
              innovation: results.innovation?.score,
              technical: results.technical?.score,
              business: results.business?.score,
              presentation: results.presentation?.score,
            }} />
            <ConsensusCard consensus={results.consensus} />
          </div>

          {/* Differentiation + Questions */}
          <div className="grid sm:grid-cols-2 gap-4 mb-6">
            <DifferentiationCard data={results.chief_judge?.differentiation} />
            <JudgeQuestions
              questions={results.chief_judge?.judge_questions}
              attackMode={attackMode}
            />
          </div>

          {/* Individual Judge Cards */}
          <div className="mb-4">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-widest mb-4">Judge Reports</p>
            <div className="grid sm:grid-cols-2 gap-4">
              {['innovation', 'technical', 'business', 'presentation'].map(type => (
                <ScoreCard key={type} type={type} data={results[type]} />
              ))}
            </div>
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between gap-4 mt-8 pb-8">
            <button
              onClick={handleDownloadReport}
              className="flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-700 text-slate-400 hover:text-white hover:border-brand-500/60 transition-colors text-sm"
            >
              <DownloadIcon />
              Download Markdown
            </button>
            <p className="text-right text-xs text-slate-700">
              IdeaValidator AI · Evidence-grounded evaluation powered by Gemini
            </p>
          </div>
        </div>
      </div>
    )
  }

  // Landing page
  return (
    <div className="min-h-screen bg-surface-950 bg-grid flex flex-col">
      {/* Nav */}
      <nav className="border-b border-slate-800/60 px-4 py-4">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-brand-500 to-accent-cyan flex items-center justify-center text-sm">
              ⚖️
            </div>
            <span className="font-semibold text-white text-sm tracking-tight">IdeaValidator AI</span>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-slate-500">
            <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            Powered by Gemini
          </div>
        </div>
      </nav>

      {/* Hero */}
      <div className="flex-1 flex flex-col items-center justify-center px-4 py-12">
        <div className="max-w-2xl w-full animate-fade-in">
          {/* Badge */}
          <div className="flex justify-center mb-6">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-brand-500/10 border border-brand-500/20">
              <span className="text-xs">🏆</span>
              <span className="text-xs font-medium text-brand-300">AI-Powered Hackathon Evaluation</span>
            </div>
          </div>

          {/* Headline */}
          <h1 className="text-4xl sm:text-5xl font-bold text-white text-center leading-tight mb-4">
            Get judged before<br />
            <span className="text-gradient">the judges judge you.</span>
          </h1>
          <p className="text-center text-slate-400 text-lg mb-10 max-w-lg mx-auto">
            Upload your pitch deck and README. Five specialized AI judges independently evaluate your project and deliver a panel verdict.
          </p>

          {/* Card */}
          <div className="rounded-2xl border border-slate-800/80 bg-surface-900/80 backdrop-blur-sm p-6 shadow-2xl">
            {/* Error */}
            {error && (
              <div className="mb-5">
                <ErrorBanner message={error} onDismiss={() => setError(null)} />
              </div>
            )}

            {/* Upload zones */}
            <div className="space-y-4 mb-6">
              <UploadZone
                label="Pitch Deck"
                accept=".pdf,.pptx"
                hint="PDF or PPTX — up to 20MB"
                file={pitchDeck}
                onFile={setPitchDeck}
                icon={<PresentationIcon />}
              />
              <div className="flex items-center gap-3">
                <div className="flex-1 h-px bg-slate-800" />
                <span className="text-xs text-slate-600 font-medium">or</span>
                <div className="flex-1 h-px bg-slate-800" />
              </div>
              <UploadZone
                label="README.md"
                accept=".md"
                hint="Markdown file from your GitHub repo"
                file={readme}
                onFile={setReadme}
                icon={<MarkdownIcon />}
              />
            </div>

            {/* Attack Mode Toggle */}
            <div className="mb-4">
              <Toggle
                enabled={attackMode}
                onToggle={() => setAttackMode(a => !a)}
                label="Judge Attack Mode"
                sublabel="Generate adversarial, high-pressure questions from the panel"
              />
            </div>

            {/* Mythos Research Section */}
            <div className="mb-4">
              <MythosSection
                pitchDeck={pitchDeck}
                readme={readme}
                onResearchReady={(rid) => setResearchRequestId(rid)}
              />
            </div>

            {/* Evaluate Button */}
            <button
              onClick={handleEvaluate}
              disabled={!canEvaluate}
              className={`
                w-full flex items-center justify-center gap-2.5 py-3.5 rounded-xl font-semibold text-sm transition-all duration-200
                ${canEvaluate
                  ? 'bg-gradient-to-r from-brand-600 to-brand-500 hover:from-brand-500 hover:to-brand-400 text-white shadow-lg shadow-brand-500/25 hover:shadow-brand-500/40 hover:-translate-y-0.5'
                  : 'bg-surface-700 text-slate-600 cursor-not-allowed'
                }
              `}
            >
              <BoltIcon />
              {researchRequestId ? 'Evaluate with Research' : 'Evaluate Project'}
            </button>

            {!canEvaluate && (
              <p className="text-center text-xs text-slate-600 mt-3">
                Upload at least one file to begin
              </p>
            )}
          </div>

          {/* Feature pills */}
          <div className="flex flex-wrap justify-center gap-2 mt-6">
            {['5 AI Judges', 'Parallel Evaluation', 'Radar Analysis', 'Mythos Research', 'No Sign-up'].map(f => (
              <span key={f} className="px-3 py-1 rounded-full text-xs text-slate-500 border border-slate-800 bg-surface-900">
                {f}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="border-t border-slate-800/60 py-4 text-center">
        <p className="text-xs text-slate-700">
          IdeaValidator AI · Files are deleted immediately after evaluation
        </p>
      </div>
    </div>
  )
}
