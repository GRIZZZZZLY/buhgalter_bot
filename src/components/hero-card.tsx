import { motion } from 'motion/react'
import { formatAmount } from '@/lib/format'
import type { Period } from '@/lib/schemas'

const PERIOD_LABELS: Record<Period, string> = {
  today: 'Сегодня',
  week: 'Неделя',
  month: 'Месяц',
  all: 'Всё время',
}

interface HeroCardProps {
  balance: number
  income: number
  expense: number
  period: Period
}

export function HeroCard({ balance, income, expense, period }: HeroCardProps) {
  const isNegative = balance < 0

  return (
    <motion.div
      className="hero-card mx-4"
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', damping: 22, stiffness: 200 }}
    >
      <div className="px-5 pt-5 pb-5">
        {/* Header row */}
        <div className="flex items-center justify-between mb-4">
          <div>
            <span className="section-kicker">Казначей</span>
            <p
              className="font-display mt-0.5 leading-none"
              style={{ fontSize: 11, color: 'rgba(26,18,8,0.40)', letterSpacing: '0.06em' }}
            >
              {PERIOD_LABELS[period]}
            </p>
          </div>
          {/* Decorative crest */}
          <div
            className="w-9 h-9 rounded-full flex items-center justify-center text-base"
            style={{
              background: 'rgba(255,255,255,0.60)',
              border: '1px solid rgba(184,134,11,0.20)',
              color: 'var(--color-gold)',
              boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.80)',
            }}
          >
            ✦
          </div>
        </div>

        {/* Balance */}
        <div className="mb-1">
          <p
            style={{
              fontSize: 11,
              color: 'rgba(26,18,8,0.45)',
              letterSpacing: '0.06em',
              textTransform: 'uppercase',
            }}
          >
            Остаток
          </p>
        </div>
        <p
          className="amount font-display leading-none mb-1"
          style={{
            fontSize: 'clamp(40px, 11vw, 54px)',
            fontWeight: 700,
            color: isNegative ? 'var(--color-expense)' : '#1a1208',
            letterSpacing: '-0.03em',
          }}
        >
          {isNegative ? '−' : ''}
          {formatAmount(Math.abs(balance))} ₽
        </p>

        {/* Ornamental divider */}
        <div className="ornament-dots my-4" />

        {/* Metrics */}
        <div className="grid grid-cols-2 gap-3">
          <div className="hero-metric">
            <p
              style={{
                fontSize: 11,
                color: 'rgba(26,18,8,0.45)',
                marginBottom: 4,
                letterSpacing: '0.04em',
                textTransform: 'uppercase',
              }}
            >
              Доходы
            </p>
            <p
              className="amount font-display font-semibold leading-tight"
              style={{ fontSize: 17, color: 'var(--color-income)' }}
            >
              +{formatAmount(income)} ₽
            </p>
          </div>
          <div className="hero-metric">
            <p
              style={{
                fontSize: 11,
                color: 'rgba(26,18,8,0.45)',
                marginBottom: 4,
                letterSpacing: '0.04em',
                textTransform: 'uppercase',
              }}
            >
              Расходы
            </p>
            <p
              className="amount font-display font-semibold leading-tight"
              style={{ fontSize: 17, color: 'var(--color-expense)' }}
            >
              −{formatAmount(expense)} ₽
            </p>
          </div>
        </div>
      </div>
    </motion.div>
  )
}
