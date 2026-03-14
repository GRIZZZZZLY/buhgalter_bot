export function HeroCard({ balance, income, expense }: { balance: number; income: number; expense: number }) {
  const format = (value: number) => new Intl.NumberFormat('ru-RU').format(value)

  return (
    <section className="hero-card ornate-frame">
      <div className="hero-card__eyebrow">Летопись казны</div>
      <h1 className="hero-card__title">Остаток</h1>
      <div className="hero-card__balance">{format(balance)} ₽</div>
      <div className="hero-card__meta">
        <div>
          <span>Доход</span>
          <strong>+{format(income)} ₽</strong>
        </div>
        <div>
          <span>Расход</span>
          <strong>-{format(expense)} ₽</strong>
        </div>
      </div>
    </section>
  )
}
