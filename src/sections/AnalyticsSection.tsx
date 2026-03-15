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

      <div className="chart-shell chart-shell--enhanced chart-shell--reveal">
        <ResponsiveContainer width="100%" height={240}>
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              innerRadius={72}
              outerRadius={98}
              paddingAngle={3}
              stroke="transparent"
              isAnimationActive
              animationBegin={80}
              animationDuration={900}
              animationEasing="ease-out"
              activeIndex={-1}
            >
              {data.map((entry, index) => (
                <Cell key={entry.name} fill={palette[index % palette.length]} stroke="transparent" />
              ))}
            </Pie>
            <Tooltip
              cursor={false}
              formatter={(value: number) => `${new Intl.NumberFormat('ru-RU').format(value)} ₽`}
              contentStyle={{
                borderRadius: 16,
                border: theme === 'light' ? '1px solid rgba(75,121,198,.16)' : '1px solid rgba(224,174,88,.16)',
                background: theme === 'light' ? 'rgba(255,255,255,.96)' : 'rgba(51,20,19,.96)',
                boxShadow: theme === 'light' ? '0 10px 24px rgba(43,73,116,.12)' : '0 12px 28px rgba(0,0,0,.24)',
              }}
              itemStyle={{ color: theme === 'light' ? '#18304f' : '#f3dfc3' }}
              labelStyle={{ color: theme === 'light' ? '#5f7696' : '#d0a987' }}
            />
          </PieChart>
        </ResponsiveContainer>
        <div className="chart-center-badge chart-center-badge--reveal">
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
