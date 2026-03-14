export function HeroCard({ balance, income, expense }: { balance: number; income: number; expense: number }) {
  const format = (value: number) => new Intl.NumberFormat('ru-RU').format(value)

  return (
    <section className="hero-card ornate-frame ornate-frame--hero">
      <div className="hero-card__motif hero-card__motif--left">✥</div>
      <div className="hero-card__motif hero-card__motif--right">✥</div>
      <div className="hero-card__crest">✦</div>
      <div className="hero-card__topline">
        <div className="hero-card__eyebrow">Главная книга</div>
        <div className="hero-card__chapter">Месячная казна</div>
      </div>
      <h1 className="hero-card__title">Остаток в казне</h1>
      <div className="hero-card__balance">{format(balance)} ₽</div>
      <p className="hero-card__note">Сводка доходов и расходов в виде живой летописи, а не сухой таблицы.</p>
      <div className="hero-card__ornament" />
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
