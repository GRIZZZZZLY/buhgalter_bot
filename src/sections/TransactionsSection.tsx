import type { Transaction } from '../lib/types'

function transactionMark(type: 'income' | 'expense') {
  return type === 'income' ? '↗' : '↘'
}

export function TransactionsSection({
  items,
  onSelect,
}: {
  items: Transaction[]
  onSelect: (item: Transaction) => void
}) {
  const format = (value: number) => new Intl.NumberFormat('ru-RU').format(value)

  return (
    <section className="surface-card ornate-divider transactions-card">
      <div className="section-head">
        <div>
          <div className="section-kicker">Записи</div>
          <h2>Последние операции</h2>
        </div>
        <button className="ghost-button">Все</button>
      </div>

      <div className="ledger-list">
        {items.map((item) => (
          <button className="ledger-row ledger-row--button" key={item.id} onClick={() => onSelect(item)}>
            <div className="ledger-row__icon">{transactionMark(item.type)}</div>
            <div className="ledger-row__left">
              <div className="ledger-row__title">{item.title}</div>
              <div className="ledger-row__meta">{item.category} · {item.timestamp}</div>
            </div>
            <div className={item.type === 'income' ? 'ledger-row__amount is-income' : 'ledger-row__amount is-expense'}>
              {item.type === 'income' ? '+' : '-'}{format(item.amount)} ₽
            </div>
          </button>
        ))}
      </div>
    </section>
  )
}
