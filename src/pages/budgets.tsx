import { motion } from 'motion/react'
import { useBudgets } from '@/hooks/use-budgets'
import { SkeletonCard } from '@/components/skeleton-card'
import { formatAmount, formatPercent } from '@/lib/format'
import { getCategoryLabel } from '@/lib/categories'
import type { BudgetItem } from '@/lib/schemas'

const rowVariants = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: { type: 'spring', damping: 24, stiffness: 260 } },
}
const listVariants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.06 } },
}

function BudgetBar({ pct }: { pct: number }) {
  const capped = Math.min(pct, 100)
  const cls =
    pct > 100
      ? 'budget-bar-fill--danger'
      : pct > 75
        ? 'budget-bar-fill--warn'
        : 'budget-bar-fill--ok'
  return (
    <div className="budget-bar-track">
      <motion.div
        className={`budget-bar-fill ${cls}`}
        initial={{ width: 0 }}
        animate={{ width: `${capped}%` }}
        transition={{ duration: 0.6, ease: [0.22, 0.68, 0, 1.2] }}
      />
    </div>
  )
}

function BudgetRow({ budget }: { budget: BudgetItem }) {
  const statusColor =
    budget.pct > 100
      ? 'var(--color-expense)'
      : budget.pct > 75
        ? 'var(--color-gold)'
        : 'var(--color-income)'

  return (
    <div className="surface-card px-4 py-4">
      <div className="flex items-baseline justify-between mb-2.5">
        <span className="font-display font-semibold" style={{ fontSize: 15, color: '#1a1208' }}>
          {getCategoryLabel(budget.category)}
        </span>
        <span className="font-semibold" style={{ fontSize: 13, color: statusColor }}>
          {formatPercent(budget.pct)}
        </span>
      </div>
      <BudgetBar pct={budget.pct} />
      <div className="flex justify-between mt-2">
        <span className="amount font-display" style={{ fontSize: 12, color: 'rgba(26,18,8,0.45)' }}>
          {formatAmount(budget.spent)} ₽
        </span>
        <span style={{ fontSize: 12, color: 'rgba(26,18,8,0.40)' }}>
          из <span className="amount font-display">{formatAmount(budget.limit)} ₽</span>
        </span>
      </div>
    </div>
  )
}

export function BudgetsPage() {
  const { data, isLoading } = useBudgets()

  return (
    <div className="page-content flex flex-col gap-4 px-4 pt-4 pb-24">
      {/* Header */}
      <div>
        <span className="section-kicker">Казначей</span>
        <h1
          className="font-display font-semibold mt-0.5"
          style={{ fontSize: 22, color: '#1a1208' }}
        >
          Бюджеты
        </h1>
      </div>

      {isLoading ? (
        <div className="flex flex-col gap-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <SkeletonCard key={i} className="h-24" />
          ))}
        </div>
      ) : !data || data.items.length === 0 ? (
        <div className="empty-state">
          <p className="text-3xl mb-3">🏦</p>
          <p className="font-display font-semibold mb-1" style={{ fontSize: 16, color: '#1a1208' }}>
            Бюджеты не установлены
          </p>
          <p style={{ fontSize: 13, color: 'rgba(26,18,8,0.45)' }}>
            Задай через бота:{' '}
            <code className="font-display" style={{ color: '#1a1208' }}>
              /budget еда 15000
            </code>
          </p>
        </div>
      ) : (
        <>
          {/* Overall budget */}
          {data.total_budget !== null && (
            <div className="surface-card surface-card--accented px-4 py-4">
              <div className="flex items-baseline justify-between mb-2.5">
                <span
                  className="font-display font-semibold"
                  style={{ fontSize: 15, color: '#1a1208' }}
                >
                  Общий бюджет
                </span>
                <span style={{ fontSize: 12, color: 'rgba(26,18,8,0.45)' }}>
                  <span className="amount font-display">{formatAmount(data.total_spent)}</span>
                  {' / '}
                  <span className="amount font-display">{formatAmount(data.total_budget)} ₽</span>
                </span>
              </div>
              <BudgetBar pct={data.total_pct ?? 0} />
            </div>
          )}

          {/* Ornamental divider */}
          <div className="ornament-dots mx-2" />

          {/* Category budgets */}
          <motion.div
            variants={listVariants}
            initial="hidden"
            animate="show"
            className="flex flex-col gap-3"
          >
            {data.items.map((budget) => (
              <motion.div key={budget.category} variants={rowVariants}>
                <BudgetRow budget={budget} />
              </motion.div>
            ))}
          </motion.div>
        </>
      )}
    </div>
  )
}
