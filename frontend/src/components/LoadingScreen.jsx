import { useState, useEffect } from 'react'

const judges = [
  { name: 'Innovation Judge', emoji: '💡', desc: 'Evaluating originality & creativity...' },
  { name: 'Technical Judge', emoji: '⚙️', desc: 'Assessing architecture & feasibility...' },
  { name: 'Business Judge', emoji: '📊', desc: 'Analyzing market fit & monetization...' },
  { name: 'Presentation Judge', emoji: '🎤', desc: 'Reviewing clarity & communication...' },
  { name: 'Chief Judge', emoji: '⚖️', desc: 'Will synthesize the verdict after specialist reports are ready.' },
]

export default function LoadingScreen({ attackMode }) {
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const progressPercent = Math.min(90, Math.round((elapsedSeconds / 40) * 90))

  useEffect(() => {
    const startedAt = Date.now()
    const intervalId = setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000))
    }, 250)
    return () => clearInterval(intervalId)
  }, [])

  return (
    <div className="min-h-screen bg-surface-950 bg-grid flex items-center justify-center p-6">
      <div className="max-w-lg w-full animate-fade-in">
        {/* Header */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-brand-500/10 border border-brand-500/20 mb-4">
            <span className="inline-block w-2 h-2 rounded-full bg-brand-400 animate-pulse" />
            <span className="text-xs font-medium text-brand-300">
              {attackMode ? 'Attack Mode Active' : 'Judges Deliberating'}
            </span>
          </div>
          <h2 className="text-2xl font-bold text-white mb-2">Evaluating your project</h2>
          <p className="text-slate-400 text-sm">Four specialist judges are reviewing your project in parallel</p>
        </div>

        {/* Judge list */}
        <div className="space-y-3">
          {judges.map((judge, i) => {
            const isChief = i === judges.length - 1
            const isActive = !isChief
            return (
              <div
                key={judge.name}
                className={`
                  relative rounded-xl border p-4 flex items-center gap-4 transition-all duration-500
                  ${isActive
                    ? 'border-brand-500/50 bg-brand-500/8 shadow-lg shadow-brand-500/10'
                    : 'border-slate-800/60 bg-surface-900/40 opacity-70'
                  }
                `}
              >
                {/* Shimmer on active */}
                {isActive && (
                  <div className="absolute inset-0 rounded-xl overflow-hidden">
                    <div className="shimmer absolute inset-0" />
                  </div>
                )}

                <div className={`relative flex-shrink-0 w-10 h-10 rounded-lg flex items-center justify-center text-xl
                  ${isActive ? 'bg-brand-500/20' : 'bg-surface-700'}
                `}>
                  {judge.emoji}
                </div>

                <div className="relative flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <p className={`text-sm font-semibold ${isActive ? 'text-white' : 'text-slate-400'}`}>
                      {judge.name}
                    </p>
                    {isActive && (
                      <span className="text-xs text-brand-300 font-mono animate-pulse">analyzing...</span>
                    )}
                    {isChief && (
                      <span className="text-xs text-slate-500 font-mono">waiting</span>
                    )}
                  </div>
                  <p className={`text-xs mt-0.5 ${isActive ? 'text-brand-300/70' : 'text-slate-500'}`}>
                    {judge.desc}
                  </p>
                </div>
              </div>
            )
          })}
        </div>

        {/* Progress bar */}
        <div className="mt-8">
          <div className="flex justify-between text-xs text-slate-500 mb-2">
            <span>Estimated progress</span>
            <span>{progressPercent}%</span>
          </div>
          <div className="h-1.5 bg-surface-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-brand-500 to-accent-cyan rounded-full transition-all duration-700"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>

        <p className="text-center text-xs text-slate-600 mt-6">
          Waiting for the complete evaluation · {elapsedSeconds}s elapsed
        </p>
      </div>
    </div>
  )
}
