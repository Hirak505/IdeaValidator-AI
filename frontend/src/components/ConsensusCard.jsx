export default function ConsensusCard({ consensus }) {
  if (!consensus) return null

  const agreementStyles = {
    strong: {
      tone: 'border-theme-positive/30 bg-theme-positive/10 text-theme-positive',
      label: 'HIGH CONSENSUS',
      desc: 'Specialist panel reached strong alignment across evaluative criteria.',
      indicator: '● SYNCED',
    },
    moderate: {
      tone: 'border-theme-warning/30 bg-theme-warning/10 text-theme-warning',
      label: 'MODERATE SPREAD',
      desc: 'Variance detected between specialist perspectives.',
      indicator: '◑ PARTIAL VARIANCE',
    },
    weak: {
      tone: 'border-theme-error/30 bg-theme-error/10 text-theme-error',
      label: 'SIGNIFICANT DIVERGENCE',
      desc: 'Strong disagreement between judges requiring manual reconciliation.',
      indicator: '○ DIVERGENT',
    },
  }

  const style = agreementStyles[consensus.agreement_level] || agreementStyles.moderate

  const labelMap = {
    innovation: 'Innovation & Novelty',
    technical: 'Technical Architecture',
    business: 'Business Viability',
    presentation: 'Presentation & Comms',
  }

  const colorMap = {
    innovation: 'bg-brand-500',
    technical: 'bg-theme-evidence',
    business: 'bg-theme-annotation',
    presentation: 'bg-theme-positive',
  }

  return (
    <div className="bp-panel p-6 animate-slide-up relative">
      <div className="corner-marks" />

      {/* Header */}
      <div className="flex items-center justify-between pb-3.5 mb-4 border-b border-theme-border">
        <div>
          <span className="font-mono text-micro text-theme-text-muted tracking-widest uppercase">AUDIT // DELIBERATION</span>
          <h3 className="text-sm font-semibold text-theme-text mt-0.5 tracking-tight">Judge Panel Consensus</h3>
        </div>
        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-micro font-mono font-bold tracking-wider border ${style.tone}`}>
          <span>{style.indicator}</span>
          <span>{style.label}</span>
        </span>
      </div>

      <p className="text-xs text-theme-text-secondary leading-relaxed mb-4">
        {style.desc}
      </p>

      {/* Telemetry Matrix Grid */}
      <div className="grid grid-cols-2 gap-2.5 mb-5 p-3 rounded-xl bg-theme-panel-subtle border border-theme-border">
        <div className="p-2.5 rounded-lg bg-theme-panel border border-theme-border">
          <span className="text-micro font-mono uppercase text-theme-text-muted block mb-1">SCORE SPREAD (Δ)</span>
          <div className="flex items-baseline gap-1">
            <span className="font-mono text-xl font-bold text-theme-text">{consensus.spread}</span>
            <span className="font-mono text-micro text-theme-text-muted">PTS</span>
          </div>
        </div>

        <div className="p-2.5 rounded-lg bg-theme-panel border border-theme-border">
          <span className="text-micro font-mono uppercase text-theme-text-muted block mb-1">EVAL RANGE</span>
          <div className="font-mono text-sm font-bold text-theme-text mt-1">
            {consensus.min} <span className="text-theme-text-muted font-normal">→</span> {consensus.max}
          </div>
        </div>

        <div className="p-2.5 rounded-lg bg-theme-panel border border-theme-border">
          <span className="text-micro font-mono uppercase text-theme-positive block mb-1">MOST ALIGNED</span>
          <span className="text-xs font-semibold text-theme-text truncate block">
            {labelMap[consensus.most_aligned] || consensus.most_aligned}
          </span>
        </div>

        <div className="p-2.5 rounded-lg bg-theme-panel border border-theme-border">
          <span className="text-micro font-mono uppercase text-theme-error block mb-1">MAX DIVERGENCE</span>
          <span className="text-xs font-semibold text-theme-text truncate block">
            {labelMap[consensus.largest_disagreement] || consensus.largest_disagreement}
          </span>
        </div>
      </div>

      {/* Specialist Dispersion Bars */}
      <div className="space-y-3 pt-3 border-t border-theme-border">
        <span className="text-micro font-mono uppercase text-theme-text-muted tracking-wider block mb-2">
          INDIVIDUAL SCORE CALIBRATION
        </span>
        {Object.entries(consensus.scores || {}).map(([judgeKey, score]) => {
          const barClass = colorMap[judgeKey] || 'bg-theme-evidence'
          const numScore = Number(score) || 0
          return (
            <div key={judgeKey} className="flex items-center gap-3">
              <span className="font-mono text-micro text-theme-text-secondary w-24 truncate uppercase tracking-wider">
                {judgeKey}
              </span>
              <div className="flex-1 h-2 bg-theme-chip rounded-full overflow-hidden p-0.5 border border-theme-border">
                <div
                  className={`h-full rounded-full score-bar-fill ${barClass}`}
                  style={{ width: `${Math.min(100, Math.max(0, (numScore / 10) * 100))}%` }}
                />
              </div>
              <span className="font-mono text-xs font-bold text-theme-text w-8 text-right tabular-nums">
                {numScore.toFixed(1)}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
