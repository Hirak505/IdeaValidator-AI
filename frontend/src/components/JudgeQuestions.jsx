import { useState } from 'react'

export default function JudgeQuestions({ questions, attackMode }) {
  const [expanded, setExpanded] = useState(null)

  return (
    <div className="bp-panel p-6 animate-slide-up relative">
      <div className="corner-marks" />

      {/* Header */}
      <div className="flex items-center justify-between pb-4 mb-4 border-b border-theme-border">
        <div>
          <span className="font-mono text-micro text-theme-text-muted tracking-widest uppercase">
            PANEL INQUIRY // DEFENSE DRILL
          </span>
          <h3 className="text-base font-semibold text-theme-text mt-0.5 tracking-tight">
            Anticipated Judge Questions
          </h3>
          <p className="text-micro text-theme-text-secondary font-mono mt-0.5 uppercase tracking-wider">
            {attackMode
              ? 'Adversarial cross-examination questions'
              : 'Key technical and commercial inquiries'}
          </p>
        </div>

        {attackMode ? (
          <div className="flex items-center gap-2 px-3 py-1 rounded bg-theme-error/10 border border-theme-error/30">
            <span className="w-2 h-2 rounded-full bg-theme-error animate-pulse" />
            <span className="text-micro font-mono font-bold text-theme-error uppercase tracking-wider">
              Attack Mode Active
            </span>
          </div>
        ) : (
          <div className="flex items-center gap-2 px-2.5 py-1 rounded bg-theme-chip border border-theme-border">
            <span className="font-mono text-micro text-theme-text-secondary uppercase">
              {questions?.length || 0} INQUIRIES
            </span>
          </div>
        )}
      </div>

      {/* Questions Stack */}
      <div className="space-y-2.5">
        {questions?.map((q, i) => {
          const isExp = expanded === i
          return (
            <div
              key={i}
              onClick={() => setExpanded(isExp ? null : i)}
              className={`cursor-pointer rounded-xl border p-4 transition-all duration-200 ${
                attackMode
                  ? 'border-theme-error/20 hover:border-theme-error/40 hover:bg-theme-error/5'
                  : 'border-theme-border hover:border-theme-border-active hover:bg-theme-panel-subtle'
              } ${
                isExp
                  ? attackMode
                    ? 'border-theme-error/40 bg-theme-error/5 shadow-sm'
                    : 'border-theme-border-active bg-theme-panel-subtle shadow-sm'
                  : 'bg-theme-panel'
              }`}
            >
              <div className="flex items-start gap-3">
                <span
                  className={`flex-shrink-0 font-mono text-micro font-bold px-2 py-1 rounded mt-0.5 border ${
                    attackMode
                      ? 'bg-theme-error/15 border-theme-error/30 text-theme-error'
                      : 'bg-theme-evidence/10 border-theme-evidence/25 text-theme-evidence'
                  }`}
                >
                  Q-{String(i + 1).padStart(2, '0')}
                </span>
                <div className="flex-1 min-w-0">
                  <p
                    className={`text-sm leading-relaxed ${
                      attackMode ? 'text-theme-error font-medium' : 'text-theme-text'
                    }`}
                  >
                    {q}
                  </p>
                  {isExp && (
                    <div className="mt-3 pt-3 border-t border-theme-border flex items-center justify-between text-micro font-mono text-theme-text-muted">
                      <span>RECOMMENDED DEFENSE STRATEGY</span>
                      <span className="text-theme-evidence font-bold">PREPARE EMPIRICAL BENCHMARKS</span>
                    </div>
                  )}
                </div>
                <span className="font-mono text-micro text-theme-text-muted mt-1">
                  {isExp ? '[-]' : '[+]'}
                </span>
              </div>
            </div>
          )
        })}
      </div>

      <div className="mt-4 pt-3.5 border-t border-theme-border flex items-center justify-between text-micro font-mono text-theme-text-muted">
        <span>PRE-PANEL REHEARSAL CHECKLIST</span>
        <span className="text-theme-text-secondary">CLICK ITEM TO REVEAL STRATEGY TAGS</span>
      </div>
    </div>
  )
}
