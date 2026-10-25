import { useState, useEffect } from 'react'

const judges = [
  {
    code: 'SPEC // INNV-01',
    name: 'Innovation & Novelty Specialist',
    desc: 'Auditing uniqueness, market whitespace, and defensibility vectors...',
    accent: 'var(--border-active)',
  },
  {
    code: 'SPEC // TECH-02',
    name: 'Technical Architecture Specialist',
    desc: 'Verifying stack feasibility, scalability limits, and execution hurdles...',
    accent: 'var(--evidence-conn)',
  },
  {
    code: 'SPEC // BIZM-03',
    name: 'Business Viability Specialist',
    desc: 'Stress-testing unit economics, TAM calculations, and monetization paths...',
    accent: 'var(--tech-annotation)',
  },
  {
    code: 'SPEC // PRES-04',
    name: 'Presentation & Narrative Specialist',
    desc: 'Analyzing pitch fidelity, customer value clarity, and messaging coherence...',
    accent: 'var(--status-positive)',
  },
  {
    code: 'EXEC // CHIEF-05',
    name: 'Chief Arbitrator (Consensus Engine)',
    desc: 'Awaiting individual specialist telemetry to reconcile consensus and calculate variance...',
    accent: 'var(--border-active)',
  },
]

export default function LoadingScreen({ attackMode, stage }) {
  const [elapsedSeconds, setElapsedSeconds] = useState(0)

  useEffect(() => {
    const startedAt = Date.now()
    const intervalId = setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000))
    }, 200)
    return () => clearInterval(intervalId)
  }, [])

  const progressPercent = Math.min(95, Math.round((elapsedSeconds / 35) * 95))

  return (
    <div className="min-h-screen bg-theme-bg bp-grid flex items-center justify-center p-6 relative">
      <div className="max-w-xl w-full animate-fade-in relative z-10">
        {/* Terminal Header Card */}
        <div className="bp-panel p-6 mb-6">
          <div className="corner-marks" />

          <div className="flex items-center justify-between pb-3 mb-4 border-b border-theme-border font-mono text-micro">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-theme-evidence animate-ping" />
              <span className="text-theme-text-secondary">TELEMETRY // PIPELINE ACTIVE</span>
            </div>
            <span className="text-theme-text-muted">T+{elapsedSeconds}S ELAPSED</span>
          </div>

          <div className="text-left mb-4">
            <div className="flex items-center gap-2 mb-1.5">
              <span className="font-mono text-micro px-2 py-0.5 rounded bg-theme-evidence/10 border border-theme-evidence/25 text-theme-evidence uppercase font-bold">
                {attackMode ? 'MODE: ADVERSARIAL STRESS-TEST' : 'MODE: STANDARD MULTI-AGENT EVALUATION'}
              </span>
              {stage && (
                <span className="font-mono text-micro px-2 py-0.5 rounded bg-theme-chip border border-theme-border text-theme-text-secondary">
                  STAGE: {stage}
                </span>
              )}
            </div>
            <h2 className="text-xl font-bold tracking-tight text-theme-text">
              Multi-Agent Specialist Panel Deliberating
            </h2>
            <p className="text-xs text-theme-text-secondary font-mono mt-1">
              Executing parallel asynchronous evaluation pipelines and grounding against domain benchmarks.
            </p>
          </div>

          {/* Progress Bar & Telemetry readout */}
          <div className="p-3 rounded-lg bg-theme-panel-subtle border border-theme-border">
            <div className="flex justify-between items-center text-micro font-mono text-theme-text-secondary mb-1.5">
              <span>SYNTHESIS PROGRESS</span>
              <span className="text-theme-evidence font-bold">{progressPercent}%</span>
            </div>
            <div className="h-2 w-full bg-theme-chip rounded-full overflow-hidden p-0.5 border border-theme-border">
              <div
                className="h-full bg-gradient-to-r from-theme-evidence to-theme-positive rounded-full transition-all duration-300 score-bar-fill"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          </div>
        </div>

        {/* Live Specialist Status Stack */}
        <div className="space-y-2.5">
          {judges.map((judge, i) => {
            const isChief = i === judges.length - 1
            const isChiefStage = stage ? stage.toLowerCase().includes('chief') : elapsedSeconds > 25
            const isActive = isChief ? isChiefStage : !isChiefStage
            const isDone = !isChief && isChiefStage

            return (
              <div
                key={judge.code}
                className={`p-3.5 rounded-xl border transition-all duration-300 relative ${
                  isActive
                    ? 'bg-theme-panel border-theme-border-active shadow-sm'
                    : isDone
                    ? 'bg-theme-positive/5 border-theme-positive/30'
                    : 'bg-theme-panel-subtle border-theme-border opacity-70'
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-start gap-3">
                    <span
                      className="w-2 h-2 rounded-full mt-1.5 flex-shrink-0"
                      style={{
                        backgroundColor: isDone ? 'var(--status-positive)' : isActive ? judge.accent : 'var(--text-muted)',
                      }}
                    />
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-micro text-theme-text-muted">{judge.code}</span>
                        <h4 className="text-xs font-semibold text-theme-text">{judge.name}</h4>
                      </div>
                      <p className="text-[11px] text-theme-text-secondary mt-0.5 leading-snug">{judge.desc}</p>
                    </div>
                  </div>

                  <div className="flex-shrink-0">
                    {isDone ? (
                      <span className="font-mono text-micro px-2 py-0.5 rounded bg-theme-positive/15 border border-theme-positive/30 text-theme-positive font-bold">
                        COMPLETED
                      </span>
                    ) : isActive ? (
                      <span className="font-mono text-micro px-2 py-0.5 rounded bg-theme-evidence/15 border border-theme-evidence/30 text-theme-evidence font-bold flex items-center gap-1.5">
                        <span className="w-1.5 h-1.5 rounded-full bg-theme-evidence animate-ping" />
                        PROCESSING
                      </span>
                    ) : (
                      <span className="font-mono text-micro px-2 py-0.5 rounded bg-theme-chip border border-theme-border text-theme-text-muted">
                        QUEUED
                      </span>
                    )}
                  </div>
                </div>
              </div>
            )
          })}
        </div>

        {/* Studio footer telemetry */}
        <div className="mt-4 text-center">
          <p className="font-mono text-micro text-theme-text-muted uppercase tracking-widest">
            ENGINEERING WORKBENCH // AUTONOMOUS ARBITRATION PROTOCOL
          </p>
        </div>
      </div>
    </div>
  )
}
