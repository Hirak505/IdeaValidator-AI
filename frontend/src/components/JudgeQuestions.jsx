import { useState } from 'react'

export default function JudgeQuestions({ questions, attackMode }) {
  const [expanded, setExpanded] = useState(null)

  return (
    <div className="rounded-2xl border border-slate-800 bg-surface-900 p-6 animate-slide-up">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h3 className="text-base font-semibold text-white">Judge Questions</h3>
          <p className="text-xs text-slate-500 mt-0.5">
            {attackMode
              ? 'Adversarial questions — be ready to defend every decision'
              : 'Questions you should be prepared to answer'}
          </p>
        </div>
        {attackMode && (
          <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-rose-500/10 border border-rose-500/25">
            <span className="text-xs">⚡</span>
            <span className="text-xs font-semibold text-rose-300">Attack Mode</span>
          </div>
        )}
      </div>

      <div className="space-y-2">
        {questions?.map((q, i) => (
          <div
            key={i}
            onClick={() => setExpanded(expanded === i ? null : i)}
            className={`
              cursor-pointer rounded-xl border p-4 transition-all duration-200
              ${attackMode
                ? 'border-rose-800/40 hover:border-rose-500/40 hover:bg-rose-500/5'
                : 'border-slate-800 hover:border-brand-500/30 hover:bg-brand-500/5'
              }
              ${expanded === i ? (attackMode ? 'border-rose-500/40 bg-rose-500/5' : 'border-brand-500/30 bg-brand-500/5') : ''}
            `}
          >
            <div className="flex items-start gap-3">
              <span className={`
                flex-shrink-0 w-6 h-6 rounded-md flex items-center justify-center text-xs font-bold mt-0.5
                ${attackMode ? 'bg-rose-500/15 text-rose-300' : 'bg-brand-500/15 text-brand-300'}
              `}>
                Q{i + 1}
              </span>
              <p className={`text-sm leading-relaxed flex-1 ${attackMode ? 'text-rose-100/90' : 'text-slate-200'}`}>
                {q}
              </p>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4 pt-4 border-t border-slate-800">
        <p className="text-xs text-slate-600 text-center">
          Practice your answers to these before presenting to the panel
        </p>
      </div>
    </div>
  )
}
