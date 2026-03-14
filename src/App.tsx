import { useEffect, useMemo, useState } from 'react'
import { AnalyticsSection } from './sections/AnalyticsSection'
import { EditSheetPreview } from './sections/EditSheetPreview'
import { EmptyState } from './sections/EmptyState'
import { HeroCard } from './sections/HeroCard'
import { TransactionsSection } from './sections/TransactionsSection'
import { StatusBadge } from './sections/StatusBadge'
import { StatusBanner } from './sections/StatusBanner'
import { PeriodTabs } from './components/PeriodTabs'
import { removeTransaction, updateTransaction } from './lib/api'
import type { EditableTransaction, Period, Transaction } from './lib/types'
import { initTelegramWebApp } from './lib/telegram'
import { useDashboard } from './useDashboard'

export default function App() {
  const [period, setPeriod] = useState<Period>('month')
  const [tg, setTg] = useState(() => initTelegramWebApp())
  const dashboard = useDashboard(period)
  const [selectedTransaction, setSelectedTransaction] = useState<Transaction | null>(null)
  const [transactionsState, setTransactionsState] = useState<Transaction[]>([])
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setTg(initTelegramWebApp())
  }, [])

  useEffect(() => {
    setTransactionsState(dashboard.transactions)
  }, [dashboard.transactions])

  const title = useMemo(() => {
    switch (period) {
      case 'today': return 'Сегодня'
      case 'week': return 'Неделя'
      case 'month': return 'Месяц'
      default: return 'Всё время'
    }
  }, [period])

  const saveTransaction = async (draft: EditableTransaction) => {
    setSaving(true)
    const usedApi = await updateTransaction(draft)

    setTransactionsState((prev) =>
      prev.map((item) =>
        item.id === draft.id
          ? { ...item, title: draft.title, category: draft.category, amount: Number(draft.amount || 0) }
          : item,
      ),
    )

    if (usedApi) dashboard.refresh()
    setSelectedTransaction(null)
    setSaving(false)
  }

  const deleteTransaction = async (id: string) => {
    setSaving(true)
    const usedApi = await removeTransaction(id)
    setTransactionsState((prev) => prev.filter((item) => item.id !== id))
    if (usedApi) dashboard.refresh()
    setSelectedTransaction(null)
    setSaving(false)
  }

  return (
    <main className="app-shell">
      <div className="app-backdrop" />
      <div className="app-content">
        <header className="app-header">
          <div>
            <div className="app-header__kicker">Казначей</div>
            <p>Финансовая летопись · {title}</p>
          </div>
          <StatusBadge source={dashboard.source} isTelegram={tg.isTelegram} />
        </header>

        <HeroCard balance={dashboard.summary.balance} income={dashboard.summary.income} expense={dashboard.summary.expense} />
        <StatusBanner loading={dashboard.loading} source={dashboard.source} />
        <PeriodTabs value={period} onChange={setPeriod} />
        {dashboard.chart.length ? <AnalyticsSection data={dashboard.chart} /> : <EmptyState title="Нет данных для сводки" description="Когда появятся записи, здесь будет видна структура расходов." />}
        {transactionsState.length ? (
          <TransactionsSection items={transactionsState} onSelect={setSelectedTransaction} />
        ) : (
          <EmptyState title="Записей пока нет" description="Добавь расход или доход через Telegram, и они появятся здесь." />
        )}
        <EditSheetPreview
          item={selectedTransaction}
          onClose={() => setSelectedTransaction(null)}
          onSave={saveTransaction}
          onDelete={deleteTransaction}
          saving={saving}
        />
      </div>
    </main>
  )
}
