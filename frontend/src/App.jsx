import { useState } from 'react'
import UploadZone from './components/UploadZone'
import LoadingScreen from './components/LoadingScreen'
import ScoreCard from './components/ScoreCard'
import OverallScore from './components/OverallScore'
import JudgeQuestions from './components/JudgeQuestions'
import RadarChart from './components/RadarChart'

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
  const judgeLabels = {
    innovation: 'Innovation',
    technical: 'Technical',
    business: 'Business',
    presentation: 'Presentation',
  }

  const specialistReports = Object.entries(judgeLabels).map(([type, label]) => {
    const report = results[type] || {}
    return `## ${label} Judge

**Score:** ${report.score ?? 'N/A'}/10

**Comments:** ${report.comments || 'None provided'}

### Strengths
${markdownList(report.strengths)}

### Weaknesses
${markdownList(report.weaknesses)}`
  }).join('\n\n')

  return `# IdeaValidator AI Report

Generated: ${new Date().toISOString().slice(0, 10)}
Judge Attack Mode: ${attackMode ? 'Enabled' : 'Disabled'}

## Final Verdict

**Overall Score:** ${chief.overall_score ?? 'N/A'}/10

${chief.final_verdict || 'None provided'}

### Top Strengths
${markdownList(chief.top_strengths)}

### Key Improvements
${markdownList(chief.top_improvements)}

### Improvement Roadmap
${(chief.improvement_roadmap || []).map((step, index) => `${index + 1}. ${step}`).join('\n') || '1. None provided'}

## Questions For The Team

${markdownList(chief.judge_questions)}

${specialistReports}
`
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

export default function App() {
  const [pitchDeck, setPitchDeck] = useState(null)
  const [readme, setReadme] = useState(null)
  const [attackMode, setAttackMode] = useState(false)
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState(null)
  const [error, setError] = useState(null)

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

          {/* Radar + Questions */}
          <div className="grid sm:grid-cols-2 gap-4 mb-6">
            <RadarChart scores={{
              innovation: results.innovation?.score,
              technical: results.technical?.score,
              business: results.business?.score,
              presentation: results.presentation?.score,
            }} />
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
              IdeaValidator AI · Evaluation powered by Gemini 1.5 Flash
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
                accept=".pdf,.pptx,.ppt"
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
                accept=".md,.txt"
                hint="Markdown file from your GitHub repo"
                file={readme}
                onFile={setReadme}
                icon={<MarkdownIcon />}
              />
            </div>

            {/* Attack Mode Toggle */}
            <div className="mb-6">
              <Toggle
                enabled={attackMode}
                onToggle={() => setAttackMode(a => !a)}
                label="Judge Attack Mode"
                sublabel="Generate adversarial, high-pressure questions from the panel"
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
              Evaluate Project
            </button>

            {!canEvaluate && (
              <p className="text-center text-xs text-slate-600 mt-3">
                Upload at least one file to begin
              </p>
            )}
          </div>

          {/* Feature pills */}
          <div className="flex flex-wrap justify-center gap-2 mt-6">
            {['5 AI Judges', 'Parallel Evaluation', 'Radar Analysis', 'Instant Verdict', 'No Sign-up'].map(f => (
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
