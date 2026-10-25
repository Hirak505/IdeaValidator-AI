import { useEffect, useState } from 'react'

const judgeConfig = {
  innovation: {
    code: 'SPEC // INNV-01',
    label: 'Innovation & Novelty',
    role: 'Originality & Market Disruption',
    accent: '#4a72e0',
    accentDark: '#8bb4ff',
    border: 'border-brand-400/30',
  },
  technical: {
    code: 'SPEC // TECH-02',
    label: 'Technical Architecture',
    role: 'Feasibility, Stack & Scaling',
    accent: '#087E8B',
    accentDark: '#38d9f5',
    border: 'border-accent-cyan/30',
  },
  business: {
    code: 'SPEC // BIZM-03',
    label: 'Business Viability',
    role: 'Unit Economics & Market Fit',
    accent: '#B77900',
    accentDark: '#f59e0b',
    border: 'border-accent-amber/30',
  },
  presentation: {
    code: 'SPEC // PRES-04',
    label: 'Presentation & Comms',
    role: 'Pitch Clarity & Narrative',
    accent: '#16835D',
    accentDark: '#34d399',
    border: 'border-accent-emerald/30',
  },
}

const evidenceTypeBadge = {
  documented_fact: { code: 'DOCF', label: 'Documented Fact', cls: 'border-theme-positive/30 bg-theme-positive/10 text-theme-positive' },
  supported_inference: { code: 'SUP-INF', label: 'Supported Inference', cls: 'border-theme-evidence/30 bg-theme-evidence/10 text-theme-evidence' },
  not_documented: { code: 'N/D', label: 'Not Documented', cls: 'border-theme-border bg-theme-chip text-theme-text-muted' },
  requires_verification: { code: 'REQ-VER', label: 'Requires Verification', cls: 'border-theme-warning/30 bg-theme-warning/10 text-theme-warning' },
  unsupported_claim: { code: 'UNSUP-CLM', label: 'Unsupported Claim', cls: 'border-theme-error/30 bg-theme-error/10 text-theme-error' },
  not_verified: { code: 'UNVER', label: 'Unverified', cls: 'border-theme-border bg-theme-chip text-theme-text-muted' },
  project: { code: 'PROJ', label: 'Project Data', cls: 'border-theme-evidence/30 bg-theme-evidence/10 text-theme-evidence' },
  uploaded_document: { code: 'DOC-ATTACH', label: 'Uploaded Doc', cls: 'border-theme-evidence/30 bg-theme-evidence/10 text-theme-evidence' },
  inference: { code: 'INFER', label: 'Inference', cls: 'border-theme-warning/30 bg-theme-warning/10 text-theme-warning' },
  external: { code: 'EXT-REF', label: 'External Ref', cls: 'border-theme-evidence/30 bg-theme-evidence/10 text-theme-evidence' },
}

function getRatingBadge(score) {
  if (score >= 9) return { label: 'EXCEPTIONAL', tone: 'text-theme-positive border-theme-positive/30 bg-theme-positive/10' }
  if (score >= 7.5) return { label: 'STRONG', tone: 'text-theme-evidence border-theme-evidence/30 bg-theme-evidence/10' }
  if (score >= 6) return { label: 'COMPETITIVE', tone: 'text-brand-500 dark:text-brand-300 border-brand-400/30 bg-brand-400/10' }
  if (score >= 4.5) return { label: 'MODERATE', tone: 'text-theme-warning border-theme-warning/30 bg-theme-warning/10' }
  return { label: 'CRITICAL ATTN', tone: 'text-theme-error border-theme-error/30 bg-theme-error/10' }
}

export default function ScoreCard({ type, data }) {
  const [showFindings, setShowFindings] = useState(false)
  const [animatedScore, setAnimatedScore] = useState(0)
  const config = judgeConfig[type]

  useEffect(() => {
    if (data?.score != null) {
      const timer = setTimeout(() => setAnimatedScore(data.score), 250)
      return () => clearTimeout(timer)
    }
  }, [data?.score])

  if (!config || !data) return null

  const rating = getRatingBadge(data.score)
  const hasFindings = data.key_findings?.length > 0 &&
    !(data.key_findings.length === 1 && data.key_findings[0]?.evidence_type === 'not_verified' &&
      data.key_findings[0]?.finding?.startsWith('General '))

  return (
    <div className="bp-panel relative p-6 transition-all duration-300 hover:border-theme-border-active hover:-translate-y-0.5 animate-slide-up group">
      {/* Blueprint Corner Accents */}
      <div className="corner-marks" />

      {/* Header Bar: Code & Role */}
      <div className="flex items-center justify-between gap-2 pb-4 mb-4 border-b border-theme-border">
        <div>
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-theme-evidence" />
            <span className="font-mono text-micro text-theme-text-muted tracking-widest">{config.code}</span>
          </div>
          <h3 className="text-base font-semibold text-theme-text mt-0.5 tracking-tight">{config.label}</h3>
          <p className="text-micro text-theme-text-secondary tracking-wider font-mono uppercase">{config.role}</p>
        </div>

        <div className="flex flex-col items-end">
          <span className={`inline-flex items-center px-2 py-0.5 rounded text-micro font-mono font-bold tracking-wider border ${rating.tone}`}>
            {rating.label}
          </span>
          <span className="text-[11px] font-mono text-theme-text-muted mt-1">SCALE 0.0 - 10.0</span>
        </div>
      </div>

      {/* Score Readout & Precision Meter */}
      <div className="mb-6 p-4 rounded-xl bg-theme-panel-subtle border border-theme-border">
        <div className="flex items-baseline justify-between mb-3">
          <div className="flex items-baseline gap-1.5">
            <span className="font-mono text-4xl font-bold tracking-tight text-theme-text tabular-nums">
              {animatedScore.toFixed(1)}
            </span>
            <span className="font-mono text-xs text-theme-text-muted">/ 10.0</span>
          </div>

          {/* Telemetry Chips (Confidence & Evidence Quality) */}
          <div className="flex items-center gap-2">
            {data.confidence != null && (
              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-theme-chip border border-theme-border text-micro font-mono">
                <span className="text-theme-text-muted">CONF</span>
                <span className="font-bold text-theme-text">{data.confidence}%</span>
              </div>
            )}
            {data.evidence_quality != null && (
              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-theme-chip border border-theme-border text-micro font-mono">
                <span className="text-theme-text-muted">EVID</span>
                <span className="font-bold text-theme-text">{data.evidence_quality}%</span>
              </div>
            )}
          </div>
        </div>

        {/* Calibrated Meter Bar with tick marks */}
        <div className="relative pt-1 pb-2">
          <div className="h-2 w-full bg-theme-chip rounded-full overflow-hidden p-0.5 border border-theme-border">
            <div
              className="h-full rounded-full transition-all duration-1000 ease-out score-bar-fill bg-theme-evidence"
              style={{
                width: `${Math.min(100, Math.max(0, (animatedScore / 10) * 100))}%`,
              }}
            />
          </div>
          {/* Tick Marks for 2.5, 5.0, 7.5 */}
          <div className="flex justify-between text-[9px] font-mono text-theme-text-muted mt-1 px-1">
            <span>0.0</span>
            <span>2.5</span>
            <span>5.0</span>
            <span>7.5</span>
            <span>10.0</span>
          </div>
        </div>
      </div>

      {/* Editorial Comment / Synthesis Quote */}
      {data.comments && (
        <div className="mb-5 relative pl-3.5 border-l-2 border-theme-evidence/50">
          <p className="text-xs text-theme-text-secondary font-sans leading-relaxed italic">
            "{data.comments}"
          </p>
        </div>
      )}

      {/* Strengths & Weaknesses Breakdown */}
      <div className="space-y-4 mb-4">
        {data.strengths?.length > 0 && (
          <div>
            <div className="flex items-center gap-1.5 text-micro font-mono uppercase tracking-wider text-theme-positive mb-2">
              <span className="inline-block px-1 rounded bg-theme-positive/15 border border-theme-positive/30 font-bold">+</span>
              <span>Observed Strengths & Positive Vectors</span>
            </div>
            <ul className="space-y-1.5 pl-1">
              {data.strengths.map((s, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-theme-text leading-normal">
                  <span className="text-theme-positive font-mono mt-0.5 flex-shrink-0 text-micro">▶</span>
                  <span className="flex-1">{s}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {data.weaknesses?.length > 0 && (
          <div>
            <div className="flex items-center gap-1.5 text-micro font-mono uppercase tracking-wider text-theme-error mb-2">
              <span className="inline-block px-1 rounded bg-theme-error/15 border border-theme-error/30 font-bold">-</span>
              <span>Identified Vulnerabilities & Risk Vectors</span>
            </div>
            <ul className="space-y-1.5 pl-1">
              {data.weaknesses.map((w, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-theme-text-secondary leading-normal">
                  <span className="text-theme-error font-mono mt-0.5 flex-shrink-0 text-micro">▶</span>
                  <span className="flex-1">{w}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Key Findings / Empirical Evidence Drawer */}
      {hasFindings && (
        <div className="pt-3 border-t border-theme-border">
          <button
            onClick={() => setShowFindings(!showFindings)}
            type="button"
            className="flex items-center justify-between w-full py-1 text-micro font-mono uppercase tracking-wider text-theme-text-secondary hover:text-theme-evidence transition-colors"
          >
            <span className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-theme-evidence" />
              <span>Audit Trail / Grounded Evidence ({data.key_findings.length})</span>
            </span>
            <span className="font-mono text-xs">{showFindings ? '[- HIDE]' : '[+ EXPAND]'}</span>
          </button>

          {showFindings && (
            <div className="mt-3 space-y-2.5 max-h-72 overflow-y-auto pr-1 animate-fadeIn">
              {data.key_findings.map((f, i) => {
                const badge = evidenceTypeBadge[f.evidence_type] || evidenceTypeBadge.not_verified
                return (
                  <div key={i} className="p-2.5 rounded-lg bg-theme-panel-subtle border border-theme-border text-xs">
                    <div className="flex items-start gap-2 mb-1.5">
                      <span className={`inline-flex px-1.5 py-0.5 rounded text-[9px] font-mono font-bold tracking-wider border uppercase flex-shrink-0 ${badge.cls}`}>
                        {badge.code}
                      </span>
                      <p className="text-xs font-semibold text-theme-text leading-snug">{f.finding}</p>
                    </div>
                    {f.evidence && (
                      <p className="text-micro text-theme-text-secondary font-mono pl-2 border-l border-theme-border mt-1">
                        ↳ {f.evidence}
                      </p>
                    )}
                    {f.source && f.source !== 'N/A' && (
                      <p className="text-[10px] font-mono text-theme-text-muted mt-1 pl-2">
                        SOURCE_REF: <span className="text-theme-text-secondary">{f.source}</span>
                      </p>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
