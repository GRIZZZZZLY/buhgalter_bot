import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import type { CategorySlice } from '../lib/types'

export function AnalyticsSection({ data }: { data: CategorySlice[] }) {
  const total = data.reduce((acc, item) => acc + item.value, 0)
  const formattedTotal = new Intl.NumberFormat('ru-RU').format(total)
  const lead = data[0]

  return (
    <section className="surface-card ornate-divider analytics-card">
      <div className="section-head">
        <div>
          <div className="section-kicker">Структура трат</div>
          <h2>Категории</h2>
        </div>
        <div className="analytics-total">
          <span>Всего</span>
          <strong>{formattedTotal} ₽</strong>
        </div>
      </div>

      {lead ? (
        <div className="analytics-highlight">
          <span>Главная статья</span>
          <strong>{lead.name}</strong>
          <em>{new Intl.NumberFormat('ru-RU').format(lead.value)} ₽</em>
        </div>
      ) : null}

      <div className="chart-shell chart-shell--enhanced">
        <ResponsiveContainer width="100%" height={240}>
          <PieChart>
            <Pie data={data} dataKey="value" innerRadius={66} outerRadius={96} paddingAngle={4} stroke="none">
              {data.map((entry) => (
                <Cell key={entry.name} fill={entry.fill} />
              ))}
            </Pie>
            <Tooltip formatter={(value: number) => `${new Intl.NumberFormat('ru-RU').format(value)} ₽`} />
          </PieChart>
        </ResponsiveContainer>
        <div className="chart-center-badge ornate-frame-soft">
          <span>Казна</span>
          <strong>{formattedTotal} ₽</strong>
        </div>
      </div>

      <div className="legend-list">
        {data.map((item, index) => (
          <div className="legend-item" key={item.name}>
            <div className="legend-rank">{String(index + 1).padStart(2, '0')}</div>
            <span className="legend-dot" style={{ backgroundColor: item.fill }} />
            <span className="legend-name">{item.name}</span>
            <strong>{new Intl.NumberFormat('ru-RU').format(item.value)} ₽</strong>
          </div>
        ))}
      </div>
    </section>
  )
}
