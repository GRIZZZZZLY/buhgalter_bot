import type { Period } from '../lib/types'

const labels: Record<Period, string> = {
  today: 'Сегодня',
  week: 'Неделя',
  month: 'Месяц',
  all: 'Всё',
}

export function PeriodTabs({ value, onChange }: { value: Period; onChange: (value: Period) => void }) {
  return (
    <div className="period-tabs">
      {(Object.keys(labels) as Period[]).map((item) => (
        <button
          key={item}
          className={item === value ? 'period-tab is-active' : 'period-tab'}
          onClick={() => onChange(item)}
        >
          <span className="period-tab__label">{labels[item]}</span>
        </button>
      ))}
    </div>
  )
}
