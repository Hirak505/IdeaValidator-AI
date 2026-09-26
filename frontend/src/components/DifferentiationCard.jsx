export default function DifferentiationCard({ data }) {
  if (!data) return null

  const hasStrengths = data.differentiation_strengths?.length > 0 && data.differentiation_strengths[0] !== 'Not determined'
  const hasGaps = data.differentiation_gaps?.length > 0 && data.differentiation_gaps[0] !== 'Not determined'
  const hasClaims = data.unsupported_claims?.length > 0

  return (
    <div className="rounded-2xl border border-slate-800 bg-surface-900 p-5 animate-slide-up">
      <p className="text-xs font-medium text-slate-500 uppercase tracking-widest mb-3">Differentiation Analysis</p>

      {/* Solution Category */}
      {data.solution_category && data.solution_category !== 'Not determined' && (
        <div className="mb-4">
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-brand-500/10 border border-brand-500/25 text-xs font-medium text-brand-300">
            {data.solution_category}
          </span>
        </div>
      )}

      {/* Claimed Differentiators */}
      {data.claimed_differentiators?.length > 0 && data.claimed_differentiators[0] !== 'Not identified' && (
        <div className="mb-3">
          <p className="text-[10px] font-medium text-slate-500 uppercase tracking-widest mb-1.5">Claimed Differentiators</p>
          <div className="flex flex-wrap gap-1.5">
            {data.claimed_differentiators.map((d, i) => (
              <span key={i} className="px-2 py-0.5 rounded-md bg-surface-800 border border-slate-700/50 text-xs text-slate-300">
                {d}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Strengths */}
      {hasStrengths && (
        <div className="mb-3">
          <p className="text-[10px] font-medium text-emerald-400 uppercase tracking-widest mb-1.5">Supported</p>
          <ul className="space-y-1">
            {data.differentiation_strengths.map((s, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-slate-300">
                <span className="text-emerald-400 mt-0.5 flex-shrink-0 text-xs">✓</span>
                {s}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Gaps */}
      {hasGaps && (
        <div className="mb-3">
          <p className="text-[10px] font-medium text-rose-400 uppercase tracking-widest mb-1.5">Gaps</p>
          <ul className="space-y-1">
            {data.differentiation_gaps.map((s, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-slate-400">
                <span className="text-rose-400 mt-0.5 flex-shrink-0 text-xs">✕</span>
                {s}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Unsupported Claims */}
      {hasClaims && (
        <div className="mb-3">
          <p className="text-[10px] font-medium text-amber-400 uppercase tracking-widest mb-1.5">Unsupported Claims</p>
          <ul className="space-y-1">
            {data.unsupported_claims.map((s, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-slate-400">
                <span className="text-amber-400 mt-0.5 flex-shrink-0 text-xs">?</span>
                {s}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Limitation note */}
      {data.limitation_note && (
        <p className="text-[10px] text-slate-600 italic mt-3 pt-2 border-t border-slate-800 leading-relaxed">
          {data.limitation_note}
        </p>
      )}
    </div>
  )
}
