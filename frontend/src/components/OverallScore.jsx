import { useEffect, useState } from 'react'

function getVerdict(score) {
  if (score >= 9.0)
    return {
      grade: 'TIER-1 // EXCEPTIONAL',
      label: 'Exceptional Prospect',
      color: 'text-theme-positive',
      bg: 'bg-theme-positive/10',
      border: 'border-theme-positive/30',
      fill: 'var(--status-positive)',
    }
  if (score >= 7.5)
    return {
      grade: 'TIER-2 // STRONG',
      label: 'Strong Entry',
      color: 'text-theme-evidence',
      bg: 'bg-theme-evidence/10',
      border: 'border-theme-evidence/30',
      fill: 'var(--evidence-conn)',
    }
  if (score >= 6.0)
    return {
      grade: 'TIER-3 // COMPETITIVE',
      label: 'Competitive Viable',
      color: 'text-brand-500 dark:text-brand-300',
      bg: 'bg-brand-500/10',
      border: 'border-brand-500/30',
      fill: '#4a72e0',
    }
  if (score >= 4.5)
    return {
      grade: 'TIER-4 // REMEDIATION',
      label: 'Needs Architecture Work',
      color: 'text-theme-warning',
      bg: 'bg-theme-warning/10',
      border: 'border-theme-warning/30',
      fill: 'var(--status-warning)',
    }
  return {
    grade: 'TIER-5 // UNVALIDATED',
    label: 'Early / High Risk',
    color: 'text-theme-error',
    bg: 'bg-theme-error/10',
    border: 'border-theme-error/30',
    fill: 'var(--status-error)',
  }
}

export default function OverallScore({ data, attackMode }) {
  const [shown, setShown] = useState(0)
  const score = data?.overall_score ?? 0
  const verdict = getVerdict(score)

  useEffect(() => {
    const timer = setTimeout(() => setShown(score), 300)
    return () => clearTimeout(timer)
  }, [score])

  return (
    <div className="bp-panel p-8 relative overflow-hidden animate-slide-up">
      <div className="corner-marks" />

      {/* Blueprint Ambient Top Flare */}
      <div className="absolute top-0 left-1/4 -translate-x-1/2 w-96 h-32 bg-theme-evidence/10 blur-3xl rounded-full pointer-events-none" />

      {/* Header section */}
      <div className="relative flex flex-col md:flex-row md:items-start md:justify-between gap-6 pb-6 mb-6 border-b border-theme-border">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <span className="font-mono text-micro text-theme-text-muted tracking-widest uppercase">
              CHIEF ARBITRATION // CONSOLIDATED VERDICT
            </span>
            {attackMode && (
              <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-theme-error/15 border border-theme-error/30 text-theme-error uppercase">
                <span className="w-1.5 h-1.5 rounded-full bg-theme-error animate-ping" />
                Adversarial Attack Mode
              </span>
            )}
          </div>
          <h2 className="text-2xl font-bold tracking-tight text-theme-text">
            Executive Synthesis & Evaluation Index
          </h2>
          <p className="text-xs text-theme-text-secondary font-mono mt-1">
            CONSOLIDATED CROSS-DISCIPLINARY BENCHMARK
          </p>
        </div>

        {/* Big Swiss Tabular Score Readout */}
        <div className="flex items-end gap-4 p-4 rounded-xl bg-theme-panel-subtle border border-theme-border flex-shrink-0">
          <div>
            <span className="text-micro font-mono uppercase text-theme-text-muted block mb-0.5">
              COMPOSITE INDEX
            </span>
            <div className="flex items-baseline gap-2">
              <span className="font-mono text-5xl font-bold tracking-tight text-theme-text tabular-nums">
                {shown.toFixed(1)}
              </span>
              <span className="font-mono text-sm text-theme-text-muted">/ 10.0</span>
            </div>
          </div>

          <div className="flex flex-col items-end pb-1 border-l border-theme-border pl-4">
            <span
              className={`inline-block px-2.5 py-1 rounded text-micro font-mono font-bold tracking-wider border ${verdict.bg} ${verdict.border} ${verdict.color}`}
            >
              {verdict.grade}
            </span>
            <span className="text-micro text-theme-text-secondary mt-1 font-mono">{verdict.label}</span>
          </div>
        </div>
      </div>

      {/* Calibrated Meter Bar */}
      <div className="mb-6 p-4 rounded-xl bg-theme-panel-subtle border border-theme-border">
        <div className="flex justify-between items-center text-micro font-mono text-theme-text-secondary mb-2">
          <span>PRECISION BENCHMARK METER</span>
          <span className="font-bold text-theme-text">{Math.round((shown / 10) * 100)}% COMPLIANCE INDEX</span>
        </div>
        <div className="h-2.5 w-full bg-theme-chip rounded-full overflow-hidden p-0.5 border border-theme-border">
          <div
            className="h-full rounded-full transition-all duration-1000 ease-out score-bar-fill"
            style={{
              width: `${Math.min(100, Math.max(0, (shown / 10) * 100))}%`,
              background: `linear-gradient(90deg, var(--border-active) 0%, ${verdict.fill} 100%)`,
            }}
          />
        </div>
        <div className="flex justify-between text-[9px] font-mono text-theme-text-muted mt-1.5 px-0.5">
          <span>0.0 UNVIABLE</span>
          <span>5.0 AVERAGE THRESHOLD</span>
          <span>7.5 INVESTMENT GRADE</span>
          <span>10.0 BEST IN CLASS</span>
        </div>
      </div>

      {/* Telemetry chips: Confidence & Evidence Quality */}
      {(data?.confidence != null || data?.evidence_quality != null) && (
        <div className="flex flex-wrap gap-4 mb-6">
          {data?.confidence != null && (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-theme-panel-subtle border border-theme-border font-mono text-xs">
              <span className="text-theme-text-muted uppercase text-micro">CONFIDENCE LEVEL:</span>
              <span
                className={`font-bold ${
                  data.confidence >= 70
                    ? 'text-theme-positive'
                    : data.confidence >= 40
                    ? 'text-theme-warning'
                    : 'text-theme-error'
                }`}
              >
                {data.confidence}%
              </span>
            </div>
          )}
          {data?.evidence_quality != null && (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-theme-panel-subtle border border-theme-border font-mono text-xs">
              <span className="text-theme-text-muted uppercase text-micro">EMPIRICAL EVIDENCE QUALITY:</span>
              <span
                className={`font-bold ${
                  data.evidence_quality >= 70
                    ? 'text-theme-positive'
                    : data.evidence_quality >= 40
                    ? 'text-theme-warning'
                    : 'text-theme-error'
                }`}
              >
                {data.evidence_quality}%
              </span>
            </div>
          )}
        </div>
      )}

      {/* Swiss Editorial Quote / Chief Verdict */}
      {data?.final_verdict && (
        <div className="relative pl-5 py-3 mb-8 border-l-2 border-theme-evidence bg-theme-panel-subtle rounded-r-xl pr-4">
          <span className="font-mono text-micro text-theme-evidence uppercase tracking-widest block mb-1">
            SYNTHESIS MEMORANDUM
          </span>
          <p className="text-sm font-sans text-theme-text leading-relaxed italic">
            "{data?.final_verdict}"
          </p>
        </div>
      )}

      {/* 3-Column Engineering Matrix */}
      <div className="grid md:grid-cols-3 gap-6 pt-4 border-t border-theme-border">
        {/* Top Strengths */}
        <div className="p-4 rounded-xl bg-theme-panel-subtle border border-theme-border">
          <div className="flex items-center gap-1.5 text-micro font-mono uppercase tracking-wider text-theme-positive mb-3">
            <span className="w-4 h-4 rounded bg-theme-positive/15 border border-theme-positive/30 font-bold flex items-center justify-center text-[10px]">
              +
            </span>
            <span>Key Competitive Strengths</span>
          </div>
          <ul className="space-y-2">
            {data?.top_strengths?.map((s, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-theme-text leading-normal">
                <span className="text-theme-positive font-mono mt-0.5 flex-shrink-0 text-micro">▶</span>
                <span className="flex-1">{s}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Top Gaps */}
        <div className="p-4 rounded-xl bg-theme-panel-subtle border border-theme-border">
          <div className="flex items-center gap-1.5 text-micro font-mono uppercase tracking-wider text-theme-error mb-3">
            <span className="w-4 h-4 rounded bg-theme-error/15 border border-theme-error/30 font-bold flex items-center justify-center text-[10px]">
              -
            </span>
            <span>Critical Deficits & Gaps</span>
          </div>
          <ul className="space-y-2">
            {data?.top_improvements?.map((s, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-theme-text-secondary leading-normal">
                <span className="text-theme-error font-mono mt-0.5 flex-shrink-0 text-micro">▶</span>
                <span className="flex-1">{s}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Prioritized Roadmap */}
        <div className="p-4 rounded-xl bg-theme-panel-subtle border border-theme-border">
          <div className="flex items-center gap-1.5 text-micro font-mono uppercase tracking-wider text-theme-warning mb-3">
            <span className="w-4 h-4 rounded bg-theme-warning/15 border border-theme-warning/30 font-bold flex items-center justify-center text-[10px]">
              !
            </span>
            <span>Sequenced Remediation Roadmap</span>
          </div>
          <div className="space-y-2.5">
            {(
              data?.prioritized_roadmap ||
              data?.improvement_roadmap?.map((s) => ({
                priority: 'P1',
                title: s,
                reason: '',
                impact: 'Medium',
                effort: 'Medium',
              })) ||
              []
            ).map((item, i) => {
              const isStructured = typeof item === 'object' && item.priority
              if (!isStructured)
                return (
                  <div key={i} className="flex items-start gap-2 text-xs text-theme-text">
                    <span className="font-mono text-micro text-theme-warning font-bold">[{i + 1}]</span>
                    <span>{String(item)}</span>
                  </div>
                )

              return (
                <div key={i} className="p-2.5 rounded-lg bg-theme-panel border border-theme-border text-xs">
                  <div className="flex items-center gap-2 mb-1">
                    <span
                      className={`font-mono text-[9px] font-bold px-1.5 py-0.5 rounded border ${
                        item.priority === 'P0'
                          ? 'bg-theme-error/15 text-theme-error border-theme-error/30'
                          : item.priority === 'P1'
                          ? 'bg-theme-warning/15 text-theme-warning border-theme-warning/30'
                          : 'bg-theme-chip text-theme-text-secondary border-theme-border'
                      }`}
                    >
                      {item.priority}
                    </span>
                    <span className="font-semibold text-theme-text text-xs truncate flex-1">
                      {item.title}
                    </span>
                  </div>
                  {item.reason && (
                    <p className="text-[11px] text-theme-text-secondary font-sans leading-relaxed mb-1.5">
                      {item.reason}
                    </p>
                  )}
                  <div className="flex gap-2 text-[9px] font-mono text-theme-text-muted">
                    <span>IMP: <strong className="text-theme-text">{item.impact}</strong></span>
                    <span>•</span>
                    <span>EFFORT: <strong className="text-theme-text">{item.effort}</strong></span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
