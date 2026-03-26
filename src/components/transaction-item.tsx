import { ChevronRight } from 'lucide-react'
import type { Transaction } from '@/lib/schemas'
import { formatAmountSigned, formatDate } from '@/lib/format'
import { getCategoryLabel } from '@/lib/categories'

const CATEGORY_EMOJI: Record<string, string> = {
  food: '🍽',
  transport: '🚌',
  housing: '🏠',
  health: '💊',
  beauty: '✨',
  entertainment: '🎬',
  subscriptions: '📱',
  shopping: '🛍',
  home: '🪴',
  telecom: '📡',
  work: '💼',
  education: '📚',
  gifts: '🎁',
  fees: '💳',
  other: '•',
  salary: '💰',
  freelance: '🖥',
  bonus: '🏆',
  transfer: '↔',
  refund: '↩',
  other_income: '💵',
}

interface TransactionItemProps {
  transaction: Transaction
  onClick?: () => void
}

export function TransactionItem({ transaction: tx, onClick }: TransactionItemProps) {
  const isIncome = tx.type === 'income'
  const emoji = CATEGORY_EMOJI[tx.category] ?? '•'

  return (
    <button className="tx-row w-full text-left" onClick={onClick}>
      {/* Icon */}
      <div className={`tx-icon ${isIncome ? 'tx-icon--income' : 'tx-icon--expense'}`}>{emoji}</div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <p
          className="font-display font-semibold truncate leading-snug"
          style={{ fontSize: 15, color: '#1a1208' }}
        >
          {tx.description ?? getCategoryLabel(tx.category)}
        </p>
        <p className="text-xs truncate mt-0.5" style={{ color: 'rgba(26,18,8,0.45)' }}>
          {getCategoryLabel(tx.category)} · {formatDate(tx.created_at)}
        </p>
      </div>

      {/* Amount */}
      <div className="flex items-center gap-0.5 shrink-0">
        <span
          className="amount font-display font-semibold tabular-nums"
          style={{
            fontSize: 15,
            color: isIncome ? 'var(--color-income)' : 'var(--color-expense)',
          }}
        >
          {formatAmountSigned(tx.amount, tx.type)}
        </span>
        <ChevronRight className="w-3.5 h-3.5 ml-0.5" style={{ color: 'rgba(26,18,8,0.25)' }} />
      </div>
    </button>
  )
}
