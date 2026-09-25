import { useEffect, useState } from 'react'

const judgeConfig = {
  innovation: {
    label: 'Innovation',
    emoji: '💡',
    color: 'from-violet-500 to-purple-600',
    barColor: 'bg-violet-400',
    glowColor: 'shadow-violet-500/20',
    borderColor: 'border-violet-500/25',
    bgColor: 'bg-violet-500/8',
    textColor: 'text-violet-300',
  },
  technical: {
    label: 'Technical',
    emoji: '⚙️',
    color: 'from-cyan-500 to-blue-600',
    barColor: 'bg-cyan-400',
    glowColor: 'shadow-cyan-500/20',
    borderColor: 'border-cyan-500/25',
    bgColor: 'bg-cyan-500/8',
    textColor: 'text-cyan-300',
  },
  business: {
    label: 'Business',
    emoji: '📊',
    color: 'from-amber-500 to-orange-600',
    barColor: 'bg-amber-400',
    glowColor: 'shadow-amber-500/20',
    borderColor: 'border-amber-500/25',
    bgColor: 'bg-amber-500/8',
    textColor: 'text-amber-300',
  },
  presentation: {
    label: 'Presentation',
    emoji: '🎤',
    color: 'from-emerald-500 to-teal-600',
    barColor: 'bg-emerald-400',
    glowColor: 'shadow-emerald-500/20',
    borderColor: 'border-emerald-500/25',
    bgColor: 'bg-emerald-500/8',
    textColor: 'text-emerald-300',
  },
}

function ScoreRing({ score, config }) {
  const [displayed, setDisplayed] = useState(0)

  useEffect(() => {
    const timer = setTimeout(() => {
      setDisplayed(score)
    }, 300)
    return () => clearTimeout(timer)
  }, [score])

  const getScoreLabel = (s) => {
    if (s >= 9) return 'Exceptional'
    if (s >= 7) return 'Strong'
    if (s >= 5) return 'Average'
    if (s >= 3) return 'Below Average'
    return 'Poor'
  }

  return (
    <div className="flex items-center gap-4 mb-5">
      <div className={`relative flex-shrink-0 w-16 h-16 rounded-2xl ${config.bgColor} border ${config.borderColor} flex items-center justify-center`}>
        <span className="text-2xl font-bold text-white">{displayed}</span>
        <span className="absolute bottom-1 right-1.5 text-[9px] font-mono text-slate-500">/10</span>
      </div>
      <div>
        <div className="flex items-center gap-2 mb-1.5">
          <span className="text-base">{config.emoji}</span>
          <span className="text-sm font-semibold text-white">{config.label}</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-28 h-1.5 bg-surface-700 rounded-full overflow-hidden">
            <div
              className={`h-full ${config.barColor} rounded-full score-bar-fill`}
              style={{ width: `${(displayed / 10) * 100}%` }}
            />
          </div>
          <span className={`text-xs font-medium ${config.textColor}`}>{getScoreLabel(displayed)}</span>
        </div>
      </div>
    </div>
  )
}

export default function ScoreCard({ type, data }) {
  const config = judgeConfig[type]
  if (!config || !data) return null

  return (
    <div className={`rounded-2xl border ${config.borderColor} bg-surface-900 p-5 transition-all hover:shadow-lg ${config.glowColor} animate-slide-up`}>
      <ScoreRing score={data.score} config={config} />

      {/* Comment */}
      <p className="text-sm text-slate-400 leading-relaxed mb-4 border-l-2 border-slate-700 pl-3 italic">
        "{data.comments}"
      </p>

      {/* Strengths */}
      {data.strengths?.length > 0 && (
        <div className="mb-3">
          <p className="text-xs font-medium text-slate-500 uppercase tracking-widest mb-2">Strengths</p>
          <ul className="space-y-1.5">
            {data.strengths.map((s, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-slate-300">
                <span className="text-emerald-400 mt-0.5 flex-shrink-0">↑</span>
                {s}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Weaknesses */}
      {data.weaknesses?.length > 0 && (
        <div>
          <p className="text-xs font-medium text-slate-500 uppercase tracking-widest mb-2">Weaknesses</p>
          <ul className="space-y-1.5">
            {data.weaknesses.map((w, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-slate-400">
                <span className="text-rose-400 mt-0.5 flex-shrink-0">↓</span>
                {w}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
