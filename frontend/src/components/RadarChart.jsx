export default function RadarChart({ scores }) {
  const { innovation = 0, technical = 0, business = 0, presentation = 0 } = scores || {}

  const labels = [
    { label: 'Innovation', code: 'INNV', value: innovation, angle: -90, color: 'var(--border-active)' },
    { label: 'Technical', code: 'TECH', value: technical, angle: 0, color: 'var(--evidence-conn)' },
    { label: 'Business', code: 'BIZM', value: business, angle: 90, color: 'var(--tech-annotation)' },
    { label: 'Presentation', code: 'PRES', value: presentation, angle: 180, color: 'var(--status-positive)' },
  ]

  const cx = 130
  const cy = 130
  const r = 85

  const toXY = (angle, radius) => {
    const rad = (angle * Math.PI) / 180
    return {
      x: cx + radius * Math.cos(rad),
      y: cy + radius * Math.sin(rad),
    }
  }

  // Grid levels (2.5, 5.0, 7.5, 10.0)
  const gridLevels = [2.5, 5, 7.5, 10]

  // Data polygon path
  const dataPoints = labels.map(({ value, angle }) => {
    const scaled = (Math.max(0, Math.min(10, value)) / 10) * r
    return toXY(angle - 90, scaled)
  })
  const polygonPath =
    dataPoints.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ') + ' Z'

  // Axes lines and labels
  const axes = labels.map(({ angle, label, code, value, color }) => {
    const end = toXY(angle - 90, r)
    const labelPos = toXY(angle - 90, r + 26)
    return { end, labelPos, label, code, value, color }
  })

  return (
    <div className="bp-panel p-6 animate-slide-up relative flex flex-col justify-between">
      <div className="corner-marks" />

      {/* Header */}
      <div className="flex items-center justify-between pb-3 mb-2 border-b border-theme-border">
        <div>
          <span className="font-mono text-micro text-theme-text-muted tracking-widest uppercase">
            GEOMETRIC PROFILE // RADAR
          </span>
          <h3 className="text-sm font-semibold text-theme-text mt-0.5 tracking-tight">
            Specialist Vector Polygon
          </h3>
        </div>
        <span className="font-mono text-micro text-theme-text-secondary uppercase px-2 py-0.5 rounded bg-theme-chip border border-theme-border">
          4-AXIS MATRIX
        </span>
      </div>

      {/* SVG Canvas */}
      <div className="flex justify-center items-center py-2">
        <svg width="270" height="270" viewBox="0 0 260 260" className="overflow-visible select-none">
          {/* Blueprint radial rings */}
          {gridLevels.map((level) => {
            const pts = labels.map(({ angle }) => toXY(angle - 90, (level / 10) * r))
            const path =
              pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ') + ' Z'
            return (
              <g key={level}>
                <path
                  d={path}
                  fill="none"
                  stroke="var(--border-color)"
                  strokeWidth="1"
                  strokeDasharray={level === 10 ? 'none' : '3 3'}
                />
                {level === 10 && (
                  <text
                    x={cx + 3}
                    y={cy - (level / 10) * r + 10}
                    className="text-[8px] font-mono fill-theme-text-muted"
                  >
                    10.0
                  </text>
                )}
              </g>
            )
          })}

          {/* Crosshair & center mark */}
          <line
            x1={cx - r - 8}
            y1={cy}
            x2={cx + r + 8}
            y2={cy}
            stroke="var(--border-color)"
            strokeWidth="1"
          />
          <line
            x1={cx}
            y1={cy - r - 8}
            x2={cx}
            y2={cy + r + 8}
            stroke="var(--border-color)"
            strokeWidth="1"
          />
          <circle cx={cx} cy={cy} r="2.5" fill="var(--evidence-conn)" opacity="0.8" />

          {/* Axis lines to points */}
          {axes.map(({ end }, i) => (
            <line
              key={i}
              x1={cx}
              y1={cy}
              x2={end.x.toFixed(1)}
              y2={end.y.toFixed(1)}
              stroke="var(--border-color)"
              strokeWidth="1"
            />
          ))}

          {/* Polygon area fill & stroke with evidence glow */}
          <defs>
            <linearGradient id="radarGradient" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="var(--evidence-conn)" stopOpacity="0.35" />
              <stop offset="100%" stopColor="var(--border-active)" stopOpacity="0.15" />
            </linearGradient>
            <filter id="radarGlow" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="2.5" result="blur" />
              <feComposite in="SourceGraphic" in2="blur" operator="over" />
            </filter>
          </defs>

          <path
            d={polygonPath}
            fill="url(#radarGradient)"
            stroke="var(--evidence-conn)"
            strokeWidth="2"
            filter="url(#radarGlow)"
            className="transition-all duration-700 ease-out"
          />

          {/* Vertex Pins & Scores */}
          {dataPoints.map((p, i) => (
            <g key={i}>
              <circle
                cx={p.x.toFixed(1)}
                cy={p.y.toFixed(1)}
                r="4"
                fill="var(--bg-panel)"
                stroke={labels[i].color}
                strokeWidth="2"
              />
            </g>
          ))}

          {/* Axis Labels & Values */}
          {axes.map(({ labelPos, code, value, color }, i) => {
            const isTop = i === 0
            const isRight = i === 1
            const isBottom = i === 2
            const isLeft = i === 3

            let anchor = 'middle'
            if (isRight) anchor = 'start'
            if (isLeft) anchor = 'end'

            let dy = 4
            if (isTop) dy = -4
            if (isBottom) dy = 12

            return (
              <g key={i}>
                <text
                  x={labelPos.x.toFixed(1)}
                  y={(labelPos.y + dy).toFixed(1)}
                  textAnchor={anchor}
                  className="font-mono text-[10px] font-bold tracking-wider"
                  fill={color}
                >
                  {code} {Number(value).toFixed(1)}
                </text>
              </g>
            )
          })}
        </svg>
      </div>

      {/* Legend matrix footer */}
      <div className="grid grid-cols-2 gap-2 pt-3 border-t border-theme-border font-mono text-micro">
        {labels.map((item, i) => (
          <div key={i} className="flex items-center justify-between px-2 py-1 rounded bg-theme-panel-subtle border border-theme-border">
            <span className="text-theme-text-muted">{item.code}</span>
            <span className="font-bold text-theme-text">{item.value.toFixed(1)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
