export function HeroCard({ balance, income, expense }: { balance: number; income: number; expense: number }) {
  const format = (value: number) => new Intl.NumberFormat('ru-RU').format(value)

  return (
    <section className="hero-card ornate-frame">
      <div className="hero-card__topline">
        <div className="hero-card__eyebrow">Летопись казны</div>
        <div className="hero-card__seal">◈</div>
      </div>
      <h1 className="hero-card__title">Остаток</h1>
      <div className="hero-card__balance">{format(balance)} ₽</div>
      <p className="hero-card__note">Видно движение казны за выбранный период без лишнего шума.</p>
      <div className="hero-card__meta">
        <div className="hero-metric is-income">
          <span>Доход</span>
          <strong>+{format(income)} ₽</strong>
        </div>
        <div className="hero-metric is-expense">
          <span>Расход</span>
          <strong>-{format(expense)} ₽</strong>
        </div>
      </div>
    </section>
  )
}
