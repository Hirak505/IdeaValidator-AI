export default function ConsensusCard({ consensus }) {
  if (!consensus) return null

  const agreementStyles = {
    strong: { bg: 'bg-emerald-500/10', border: 'border-emerald-500/30', text: 'text-emerald-300', label: 'Strong Agreement', icon: '✓' },
    moderate: { bg: 'bg-amber-500/10', border: 'border-amber-500/30', text: 'text-amber-300', label: 'Moderate Agreement', icon: '~' },
    weak: { bg: 'bg-rose-500/10', border: 'border-rose-500/30', text: 'text-rose-300', label: 'Weak Agreement', icon: '!' },
  }
  const style = agreementStyles[consensus.agreement_level] || agreementStyles.moderate

  const labelMap = {
    innovation: 'Innovation',
    technical: 'Technical',
    business: 'Business',
    presentation: 'Presentation',
  }

  const barColors = {
    innovation: 'bg-violet-400',
    technical: 'bg-cyan-400',
    business: 'bg-amber-400',
    presentation: 'bg-emerald-400',
  }

  return (
    <div className="rounded-2xl border border-slate-800 bg-surface-900 p-5 animate-slide-up">
      <p className="text-xs font-medium text-slate-500 uppercase tracking-widest mb-4">Judge Consensus</p>

      {/* Agreement badge */}
      <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg ${style.bg} ${style.border} border mb-4`}>
        <span className={`text-sm font-bold ${style.text}`}>{style.icon}</span>
        <span className={`text-sm font-semibold ${style.text}`}>{style.label}</span>
      </div>

      {/* Stats grid */}
      <div className="space-y-2.5 mb-4">
        <div className="flex justify-between items-center">
          <span className="text-xs text-slate-500">Score Spread</span>
          <span className="text-sm font-semibold text-white">{consensus.spread} point{consensus.spread !== 1 ? 's' : ''}</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-xs text-slate-500">Most Aligned</span>
          <span className="text-sm font-medium text-emerald-300">{labelMap[consensus.most_aligned] || consensus.most_aligned}</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-xs text-slate-500">Largest Disagreement</span>
          <span className="text-sm font-medium text-rose-300">{labelMap[consensus.largest_disagreement] || consensus.largest_disagreement}</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-xs text-slate-500">Score Range</span>
          <span className="text-sm font-mono text-slate-300">{consensus.min} – {consensus.max}</span>
        </div>
      </div>

      {/* Mini score bars */}
      <div className="space-y-2 pt-3 border-t border-slate-800">
        {Object.entries(consensus.scores || {}).map(([judge, score]) => (
          <div key={judge} className="flex items-center gap-2">
            <span className="text-[10px] text-slate-500 w-[70px] truncate uppercase tracking-wider">{labelMap[judge] || judge}</span>
            <div className="flex-1 h-1.5 bg-surface-700 rounded-full overflow-hidden">
              <div
                className={`h-full ${barColors[judge] || 'bg-brand-400'} rounded-full transition-all duration-700`}
                style={{ width: `${(score / 10) * 100}%` }}
              />
            </div>
            <span className="text-xs font-mono text-slate-400 w-4 text-right">{score}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
