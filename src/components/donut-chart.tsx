import { formatAmount } from '@/lib/format'

interface Slice {
  label: string
  value: number
  color: string
}

interface DonutChartProps {
  data: Slice[]
  size?: number
  thickness?: number
}

export function DonutChart({ data, size = 172, thickness = 36 }: DonutChartProps) {
  const total = data.reduce((sum, s) => sum + s.value, 0)
  if (total === 0) return null

  let cumulative = 0
  const stops = data.map((slice, i) => {
    const pct = (slice.value / total) * 100
    const gap = i === 0 ? 0 : 0.4
    const start = cumulative + gap
    cumulative += pct
    return `${slice.color} ${start.toFixed(2)}% ${cumulative.toFixed(2)}%`
  })

  const gradient = `conic-gradient(from -90deg, ${stops.join(', ')})`
  const innerSize = size - thickness * 2

  return (
    <div className="flex justify-center">
      <div
        className="relative rounded-full"
        style={{ width: size, height: size, background: gradient }}
      >
        {/* Inner hole */}
        <div
          className="donut-center absolute rounded-full flex flex-col items-center justify-center text-center"
          style={{ width: innerSize, height: innerSize, top: thickness, left: thickness }}
        >
          {/* Gold accent dot */}
          <span
            className="block rounded-full mb-1.5"
            style={{ width: 5, height: 5, background: 'var(--color-gold)' }}
          />
          <span
            style={{
              fontSize: 10,
              color: 'rgba(26,18,8,0.45)',
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              lineHeight: 1,
              marginBottom: 4,
            }}
          >
            Расходы
          </span>
          <span
            className="amount font-display font-semibold"
            style={{ fontSize: 14, color: '#1a1208', letterSpacing: '-0.02em' }}
          >
            {formatAmount(total)} ₽
          </span>
        </div>
      </div>
    </div>
  )
}
