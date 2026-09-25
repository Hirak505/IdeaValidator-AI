export default function RadarChart({ scores }) {
  const { innovation = 0, technical = 0, business = 0, presentation = 0 } = scores

  const labels = [
    { label: 'Innovation', value: innovation, angle: -90 },
    { label: 'Technical', value: technical, angle: 0 },
    { label: 'Business', value: business, angle: 90 },
    { label: 'Presentation', value: presentation, angle: 180 },
  ]

  const cx = 110, cy = 110, r = 80

  const toXY = (angle, radius) => {
    const rad = (angle * Math.PI) / 180
    return {
      x: cx + radius * Math.cos(rad),
      y: cy + radius * Math.sin(rad),
    }
  }

  // Grid circles
  const gridLevels = [2, 4, 6, 8, 10]

  // Data polygon
  const dataPoints = labels.map(({ value, angle }) => {
    const scaled = (value / 10) * r
    return toXY(angle - 90, scaled)
  })
  const polygonPath = dataPoints.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ') + ' Z'

  // Axis lines and label positions
  const axes = labels.map(({ angle, label, value }) => {
    const end = toXY(angle - 90, r)
    const labelPos = toXY(angle - 90, r + 22)
    return { end, labelPos, label, value }
  })

  return (
    <div className="rounded-2xl border border-slate-800 bg-surface-900 p-5 animate-slide-up">
      <p className="text-xs font-medium text-slate-500 uppercase tracking-widest mb-4">Score Radar</p>
      <div className="flex justify-center">
        <svg width="220" height="220" viewBox="0 0 220 220" className="overflow-visible">
          {/* Grid rings */}
          {gridLevels.map((level) => {
            const pts = labels.map(({ angle }) => toXY(angle - 90, (level / 10) * r))
            const path = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ') + ' Z'
            return (
              <path key={level} d={path} fill="none" stroke="#1e2a40" strokeWidth="1" />
            )
          })}

          {/* Axis lines */}
          {axes.map(({ end, label }, i) => (
            <line key={i} x1={cx} y1={cy} x2={end.x.toFixed(1)} y2={end.y.toFixed(1)}
              stroke="#1e2a40" strokeWidth="1" />
          ))}

          {/* Data polygon fill */}
          <path d={polygonPath} fill="rgba(99,114,245,0.15)" stroke="rgba(99,114,245,0.7)" strokeWidth="1.5" />

          {/* Data points */}
          {dataPoints.map((p, i) => (
            <circle key={i} cx={p.x.toFixed(1)} cy={p.y.toFixed(1)} r="4"
              fill="#6272f5" stroke="#080b14" strokeWidth="2" />
          ))}

          {/* Labels */}
          {axes.map(({ labelPos, label, value }, i) => (
            <g key={i}>
              <text
                x={labelPos.x.toFixed(1)}
                y={(labelPos.y - 6).toFixed(1)}
                textAnchor="middle"
                fontSize="9"
                fill="#94a3b8"
                fontFamily="Inter, sans-serif"
                fontWeight="500"
                className="uppercase tracking-widest"
              >
                {label}
              </text>
              <text
                x={labelPos.x.toFixed(1)}
                y={(labelPos.y + 7).toFixed(1)}
                textAnchor="middle"
                fontSize="12"
                fill="#e2e8f0"
                fontFamily="Inter, sans-serif"
                fontWeight="700"
              >
                {value}
              </text>
            </g>
          ))}

          {/* Center dot */}
          <circle cx={cx} cy={cy} r="3" fill="#243050" stroke="#6272f5" strokeWidth="1.5" />
        </svg>
      </div>
    </div>
  )
}
