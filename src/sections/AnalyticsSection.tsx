import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import type { CategorySlice } from '../lib/types'

export function AnalyticsSection({ data }: { data: CategorySlice[] }) {
  return (
    <section className="surface-card ornate-divider">
      <div className="section-head">
        <div>
          <div className="section-kicker">Структура трат</div>
          <h2>Категории</h2>
        </div>
      </div>

      <div className="chart-shell">
        <ResponsiveContainer width="100%" height={220}>
          <PieChart>
            <Pie data={data} dataKey="value" innerRadius={58} outerRadius={88} paddingAngle={3} stroke="none">
              {data.map((entry) => (
                <Cell key={entry.name} fill={entry.fill} />
              ))}
            </Pie>
            <Tooltip formatter={(value: number) => `${new Intl.NumberFormat('ru-RU').format(value)} ₽`} />
          </PieChart>
        </ResponsiveContainer>
      </div>

      <div className="legend-list">
        {data.map((item) => (
          <div className="legend-item" key={item.name}>
            <span className="legend-dot" style={{ backgroundColor: item.fill }} />
            <span className="legend-name">{item.name}</span>
            <strong>{new Intl.NumberFormat('ru-RU').format(item.value)} ₽</strong>
          </div>
        ))}
      </div>
    </section>
  )
}
