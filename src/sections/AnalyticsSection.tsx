import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import type { CategorySlice } from '../lib/types'

function paletteForTheme(theme: 'light' | 'dark') {
  return theme === 'light'
    ? ['#1f4f9f', '#356bc0', '#4f86d5', '#79a8e6', '#a9c7ef']
    : ['#e0ae58', '#c85b47', '#8d2d24', '#a36a2d', '#6e4a28']
}

export function AnalyticsSection({ data, theme }: { data: CategorySlice[]; theme: 'light' | 'dark' }) {
  const total = data.reduce((acc, item) => acc + item.value, 0)
  const formattedTotal = new Intl.NumberFormat('ru-RU').format(total)
  const lead = data[0]
  const palette = paletteForTheme(theme)

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
            <Pie data={data} dataKey="value" innerRadius={72} outerRadius={98} paddingAngle={3} stroke="none">
              {data.map((entry, index) => (
                <Cell key={entry.name} fill={palette[index % palette.length]} />
              ))}
            </Pie>
            <Tooltip formatter={(value: number) => `${new Intl.NumberFormat('ru-RU').format(value)} ₽`} />
          </PieChart>
        </ResponsiveContainer>
        <div className="chart-center-badge">
          <span>Всего</span>
          <strong>{formattedTotal} ₽</strong>
        </div>
      </div>

      <div className="legend-list">
        {data.map((item, index) => {
          const fill = palette[index % palette.length]
          return (
            <div className="legend-item" key={item.name}>
              <div className="legend-rank">{String(index + 1).padStart(2, '0')}</div>
              <span className="legend-dot" style={{ backgroundColor: fill }} />
              <span className="legend-name">{item.name}</span>
              <strong>{new Intl.NumberFormat('ru-RU').format(item.value)} ₽</strong>
            </div>
          )
        })}
      </div>
    </section>
  )
}
