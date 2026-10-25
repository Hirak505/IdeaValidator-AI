export default function DifferentiationCard({ data }) {
  if (!data) return null

  const hasStrengths = data.differentiation_strengths?.length > 0 && data.differentiation_strengths[0] !== 'Not determined'
  const hasGaps = data.differentiation_gaps?.length > 0 && data.differentiation_gaps[0] !== 'Not determined'
  const hasClaims = data.unsupported_claims?.length > 0

  return (
    <div className="bp-panel p-6 animate-slide-up relative">
      <div className="corner-marks" />

      {/* Header */}
      <div className="flex items-center justify-between pb-3.5 mb-4 border-b border-theme-border">
        <div>
          <span className="font-mono text-micro text-theme-text-muted tracking-widest uppercase">MARKET // POSITIONING</span>
          <h3 className="text-sm font-semibold text-theme-text mt-0.5 tracking-tight">Differentiation & Moat Analysis</h3>
        </div>
        {data.solution_category && data.solution_category !== 'Not determined' && (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-micro font-mono font-medium border border-theme-evidence/30 bg-theme-evidence/10 text-theme-evidence">
            <span className="w-1.5 h-1.5 rounded-full bg-theme-evidence" />
            {data.solution_category}
          </span>
        )}
      </div>

      {/* Claimed Differentiators Vector Tags */}
      {data.claimed_differentiators?.length > 0 && data.claimed_differentiators[0] !== 'Not identified' && (
        <div className="mb-5 p-3 rounded-xl bg-theme-panel-subtle border border-theme-border">
          <span className="text-micro font-mono uppercase text-theme-text-muted tracking-wider block mb-2">
            CLAIMED COMPETITIVE VECTORS
          </span>
          <div className="flex flex-wrap gap-1.5">
            {data.claimed_differentiators.map((d, i) => (
              <span key={i} className="px-2.5 py-1 rounded-md bg-theme-chip border border-theme-border text-xs font-mono text-theme-text">
                {d}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="space-y-4">
        {/* Validated / Supported Moats */}
        {hasStrengths && (
          <div>
            <div className="flex items-center gap-1.5 text-micro font-mono uppercase tracking-wider text-theme-positive mb-2">
              <span className="w-4 h-4 rounded bg-theme-positive/15 border border-theme-positive/30 font-bold flex items-center justify-center text-[10px]">✓</span>
              <span>Validated Differentiators</span>
            </div>
            <ul className="space-y-1.5 pl-1">
              {data.differentiation_strengths.map((s, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-theme-text leading-normal">
                  <span className="text-theme-positive font-mono mt-0.5 flex-shrink-0 text-micro">▶</span>
                  <span className="flex-1">{s}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Defensibility Gaps */}
        {hasGaps && (
          <div>
            <div className="flex items-center gap-1.5 text-micro font-mono uppercase tracking-wider text-theme-warning mb-2">
              <span className="w-4 h-4 rounded bg-theme-warning/15 border border-theme-warning/30 font-bold flex items-center justify-center text-[10px]">!</span>
              <span>Defensibility Gaps & Vulnerabilities</span>
            </div>
            <ul className="space-y-1.5 pl-1">
              {data.differentiation_gaps.map((g, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-theme-text-secondary leading-normal">
                  <span className="text-theme-warning font-mono mt-0.5 flex-shrink-0 text-micro">▶</span>
                  <span className="flex-1">{g}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Unsupported Claims */}
        {hasClaims && (
          <div>
            <div className="flex items-center gap-1.5 text-micro font-mono uppercase tracking-wider text-theme-error mb-2">
              <span className="w-4 h-4 rounded bg-theme-error/15 border border-theme-error/30 font-bold flex items-center justify-center text-[10px]">✕</span>
              <span>Unsubstantiated or High-Risk Claims</span>
            </div>
            <ul className="space-y-1.5 pl-1">
              {data.unsupported_claims.map((c, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-theme-error leading-normal">
                  <span className="text-theme-error font-mono mt-0.5 flex-shrink-0 text-micro">▶</span>
                  <span className="flex-1">{c}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}
