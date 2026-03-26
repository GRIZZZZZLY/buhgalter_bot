import { useState } from 'react'
import { useNavigate } from 'react-router'
import { Plus, PiggyBank } from 'lucide-react'
import { motion } from 'motion/react'
import { useSummary } from '@/hooks/use-summary'
import { useTransactions } from '@/hooks/use-transactions'
import { HeroCard } from '@/components/hero-card'
import { DonutChart } from '@/components/donut-chart'
import { TransactionItem } from '@/components/transaction-item'
import { SkeletonCard } from '@/components/skeleton-card'
import { formatAmount } from '@/lib/format'
import { getCategoryLabel, CATEGORY_COLORS } from '@/lib/categories'
import type { Period } from '@/lib/schemas'

const PERIODS: { value: Period; label: string }[] = [
  { value: 'today', label: 'Сегодня' },
  { value: 'week', label: 'Неделя' },
  { value: 'month', label: 'Месяц' },
  { value: 'all', label: 'Всё' },
]

const listVariants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.04, delayChildren: 0.06 } },
}
const rowVariants = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: { type: 'spring', damping: 24, stiffness: 260 } },
}

export function DashboardPage() {
  const navigate = useNavigate()
  const [period, setPeriod] = useState<Period>('month')

  const {
    data: summary,
    isLoading: summaryLoading,
    isError: summaryError,
    error: summaryErr,
  } = useSummary(period)

  const {
    data: txPages,
    isLoading: txLoading,
    fetchNextPage,
    hasNextPage,
  } = useTransactions(period)

  const transactions = txPages?.pages.flatMap((p) => p.items) ?? []

  const chartData = (summary?.top_expense_categories ?? []).map((cat, i) => ({
    label: getCategoryLabel(cat.category),
    value: Number(cat.amount),
    color: CATEGORY_COLORS[i % CATEGORY_COLORS.length] ?? '#2f62b8',
  }))

  const totalExpense = chartData.reduce((s, c) => s + c.value, 0)

  return (
    <div className="page-content flex flex-col gap-4 pb-28">
      {/* ── Period tabs ─────────────────────────────────────────────── */}
      <div className="px-4 pt-4">
        <div className="period-tabs-wrap">
          {PERIODS.map((p) => (
            <button
              key={p.value}
              onClick={() => setPeriod(p.value)}
              className={`period-tab ${period === p.value ? 'is-active' : ''}`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── Hero card ────────────────────────────────────────────────── */}
      {summaryLoading ? (
        <div className="mx-4">
          <SkeletonCard className="h-52" />
        </div>
      ) : (
        <>
          <HeroCard
            balance={Number(summary?.balance ?? 0)}
            income={Number(summary?.income_total ?? 0)}
            expense={Number(summary?.expense_total ?? 0)}
            period={period}
          />
          {summaryError && (
            <div className="mx-4 error-banner">
              {summaryErr instanceof Error && summaryErr.message.includes('401')
                ? '⚠️ Нет доступа к данным. Укажи VITE_DEV_USER_ID или открой через Telegram.'
                : '⚠️ Не удалось загрузить данные'}
            </div>
          )}
        </>
      )}

      {/* ── Expense breakdown ────────────────────────────────────────── */}
      {chartData.length > 0 && (
        <motion.div
          className="mx-4 surface-card surface-card--accented"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1, type: 'spring', damping: 24, stiffness: 220 }}
        >
          <div className="px-5 pt-5 pb-2">
            <span className="section-kicker">Аналитика</span>
            <h2
              className="font-display font-semibold mt-0.5 mb-4"
              style={{ fontSize: 18, color: '#1a1208' }}
            >
              Структура расходов
            </h2>
          </div>

          <div className="px-5 pb-2">
            <DonutChart data={chartData} />
          </div>

          {/* Legend */}
          <div className="px-3 pb-4 mt-2">
            {chartData.map((cat, i) => {
              const pct = totalExpense > 0 ? Math.round((cat.value / totalExpense) * 100) : 0
              return (
                <div key={cat.label} className="legend-row">
                  {/* Rank */}
                  <span
                    className="amount font-display w-5 text-right shrink-0"
                    style={{ fontSize: 11, color: 'var(--color-gold)', fontWeight: 700 }}
                  >
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  {/* Color dot */}
                  <span
                    className="w-2 h-2 rounded-full shrink-0"
                    style={{ backgroundColor: cat.color }}
                  />
                  {/* Name */}
                  <span className="flex-1 text-sm truncate" style={{ color: '#1a1208' }}>
                    {cat.label}
                  </span>
                  {/* Amount */}
                  <span
                    className="amount font-display font-semibold tabular-nums shrink-0"
                    style={{ fontSize: 14, color: '#1a1208' }}
                  >
                    {formatAmount(cat.value)} ₽
                  </span>
                  {/* Pct */}
                  <span
                    className="w-8 text-right shrink-0"
                    style={{ fontSize: 12, color: 'rgba(26,18,8,0.40)' }}
                  >
                    {pct}%
                  </span>
                </div>
              )
            })}
          </div>
        </motion.div>
      )}

      {/* ── Transactions ─────────────────────────────────────────────── */}
      <div className="mx-4">
        {/* Section header */}
        <div className="flex items-center justify-between mb-3 px-1">
          <div>
            <span className="section-kicker">Записи</span>
            <h2
              className="font-display font-semibold mt-0.5"
              style={{ fontSize: 18, color: '#1a1208' }}
            >
              Операции
            </h2>
          </div>
          <button className="btn-ghost" onClick={() => void navigate('/budgets')}>
            <PiggyBank className="w-3.5 h-3.5" />
            Бюджеты
          </button>
        </div>

        {txLoading ? (
          <div className="flex flex-col gap-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <SkeletonCard key={i} className="h-16" />
            ))}
          </div>
        ) : transactions.length === 0 ? (
          <div className="empty-state">
            <p className="text-3xl mb-3">📒</p>
            <p
              className="font-display font-semibold mb-1"
              style={{ fontSize: 16, color: '#1a1208' }}
            >
              Записей пока нет
            </p>
            <p style={{ fontSize: 13, color: 'rgba(26,18,8,0.45)' }}>
              Добавь расход или доход через Telegram или кнопку ниже
            </p>
          </div>
        ) : (
          <motion.div variants={listVariants} initial="hidden" animate="show">
            <div className="surface-card overflow-hidden">
              {transactions.map((tx) => (
                <motion.div key={tx.id} variants={rowVariants}>
                  <TransactionItem
                    transaction={tx}
                    onClick={() => void navigate(`/transaction/${tx.id}`)}
                  />
                </motion.div>
              ))}
            </div>

            {hasNextPage && (
              <button
                className="mt-3 w-full py-3 text-sm font-medium"
                style={{ color: 'rgba(26,18,8,0.40)' }}
                onClick={() => void fetchNextPage()}
              >
                Загрузить ещё
              </button>
            )}
          </motion.div>
        )}
      </div>

      {/* ── FAB ──────────────────────────────────────────────────────── */}
      <motion.button
        className="fab"
        whileTap={{ scale: 0.9 }}
        whileHover={{ scale: 1.06 }}
        onClick={() => void navigate('/add')}
        aria-label="Добавить операцию"
      >
        <Plus className="w-6 h-6" />
      </motion.button>
    </div>
  )
}
