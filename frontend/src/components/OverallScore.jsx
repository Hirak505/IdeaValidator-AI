import { useEffect, useState } from 'react'

function getVerdict(score) {
  if (score >= 9.0) return { label: 'Exceptional', color: 'text-emerald-300', bg: 'bg-emerald-500/10', border: 'border-emerald-500/30' }
  if (score >= 7.5) return { label: 'Strong Entry', color: 'text-cyan-300', bg: 'bg-cyan-500/10', border: 'border-cyan-500/30' }
  if (score >= 6.0) return { label: 'Competitive', color: 'text-brand-300', bg: 'bg-brand-500/10', border: 'border-brand-500/30' }
  if (score >= 4.5) return { label: 'Needs Work', color: 'text-amber-300', bg: 'bg-amber-500/10', border: 'border-amber-500/30' }
  return { label: 'Early Stage', color: 'text-rose-300', bg: 'bg-rose-500/10', border: 'border-rose-500/30' }
}

export default function OverallScore({ data, attackMode }) {
  const [shown, setShown] = useState(0)
  const score = data?.overall_score ?? 0
  const verdict = getVerdict(score)

  useEffect(() => {
    const timer = setTimeout(() => setShown(score), 400)
    return () => clearTimeout(timer)
  }, [score])

  return (
    <div className="rounded-2xl border border-brand-500/30 bg-gradient-to-br from-surface-800 to-surface-900 p-8 relative overflow-hidden animate-slide-up">
      {/* Background glow */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-64 h-32 bg-brand-500/15 blur-3xl rounded-full pointer-events-none" />

      <div className="relative">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-6 mb-8">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs font-medium text-slate-500 uppercase tracking-widest">Chief Judge</span>
              {attackMode && (
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-500/15 border border-rose-500/30 text-rose-300 uppercase tracking-wide">
                  ⚡ Attack Mode
                </span>
              )}
            </div>
            <h2 className="text-2xl font-bold text-white">Final Verdict</h2>
          </div>

          {/* Score display */}
          <div className="flex items-end gap-3">
            <div className="text-6xl font-bold text-gradient tabular-nums">{shown.toFixed(1)}</div>
            <div className="pb-2">
              <p className="text-slate-500 text-sm font-mono">/10</p>
              <span className={`inline-block mt-1 px-2 py-0.5 rounded-md text-xs font-semibold ${verdict.bg} ${verdict.border} border ${verdict.color}`}>
                {verdict.label}
              </span>
            </div>
          </div>
        </div>

        {/* Score bar */}
        <div className="mb-4">
          <div className="h-2 bg-surface-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-brand-500 to-accent-cyan rounded-full score-bar-fill"
              style={{ width: `${(shown / 10) * 100}%` }}
            />
          </div>
        </div>

        {/* Confidence & Evidence Quality */}
        {(data?.confidence != null || data?.evidence_quality != null) && (
          <div className="flex gap-4 mb-6">
            {data?.confidence != null && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-500">Confidence</span>
                <span className={`text-sm font-semibold ${
                  data.confidence >= 70 ? 'text-emerald-300' :
                  data.confidence >= 40 ? 'text-amber-300' : 'text-rose-300'
                }`}>{data.confidence}%</span>
              </div>
            )}
            {data?.evidence_quality != null && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-500">Evidence Quality</span>
                <span className={`text-sm font-semibold ${
                  data.evidence_quality >= 70 ? 'text-emerald-300' :
                  data.evidence_quality >= 40 ? 'text-amber-300' : 'text-rose-300'
                }`}>{data.evidence_quality}%</span>
              </div>
            )}
          </div>
        )}

        {/* Final verdict text */}
        <blockquote className="text-slate-300 text-sm leading-relaxed mb-8 pl-4 border-l-2 border-brand-500/50 italic">
          "{data?.final_verdict}"
        </blockquote>

        {/* Three columns */}
        <div className="grid sm:grid-cols-3 gap-6">
          {/* Top strengths */}
          <div>
            <p className="text-xs font-medium text-emerald-400 uppercase tracking-widest mb-3">Top Strengths</p>
            <ul className="space-y-2">
              {data?.top_strengths?.map((s, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-slate-300">
                  <span className="text-emerald-400 font-bold mt-0.5 flex-shrink-0">+</span>
                  {s}
                </li>
              ))}
            </ul>
          </div>

          {/* Top improvements */}
          <div>
            <p className="text-xs font-medium text-rose-400 uppercase tracking-widest mb-3">Key Gaps</p>
            <ul className="space-y-2">
              {data?.top_improvements?.map((s, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-slate-300">
                  <span className="text-rose-400 font-bold mt-0.5 flex-shrink-0">–</span>
                  {s}
                </li>
              ))}
            </ul>
          </div>

          {/* Prioritized Roadmap */}
          <div>
            <p className="text-xs font-medium text-amber-400 uppercase tracking-widest mb-3">Roadmap</p>
            <ol className="space-y-2.5">
              {(data?.prioritized_roadmap || data?.improvement_roadmap?.map(s => ({ priority: 'P1', title: s, reason: '', impact: 'Medium', effort: 'Medium' })) || []).map((item, i) => {
                const isStructured = typeof item === 'object' && item.priority
                if (!isStructured) return (
                  <li key={i} className="flex items-start gap-2 text-sm text-slate-300">
                    <span className="flex-shrink-0 w-4 h-4 rounded-full bg-amber-500/20 border border-amber-500/30 text-amber-400 flex items-center justify-center text-[10px] font-bold mt-0.5">{i + 1}</span>
                    {String(item)}
                  </li>
                )
                return (
                  <li key={i} className="text-sm text-slate-300">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${
                        item.priority === 'P0' ? 'bg-rose-500/20 text-rose-300 border-rose-500/30' :
                        item.priority === 'P1' ? 'bg-amber-500/20 text-amber-300 border-amber-500/30' :
                        'bg-slate-500/20 text-slate-400 border-slate-600/30'
                      }`}>{item.priority}</span>
                      <span className="font-medium text-white text-xs leading-snug">{item.title}</span>
                    </div>
                    {item.reason && (
                      <p className="text-[11px] text-slate-500 ml-9 leading-relaxed">{item.reason}</p>
                    )}
                    <div className="flex gap-1.5 ml-9 mt-1">
                      <span className="text-[9px] px-1.5 py-0.5 rounded bg-surface-700 text-slate-400">↑ {item.impact}</span>
                      <span className="text-[9px] px-1.5 py-0.5 rounded bg-surface-700 text-slate-400">→ {item.effort}</span>
                    </div>
                  </li>
                )
              })}
            </ol>
          </div>
        </div>
      </div>
    </div>
  )
}
