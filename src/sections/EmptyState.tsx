export function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <section className="surface-card empty-state ornate-frame-soft">
      <div className="section-kicker">Летопись пуста</div>
      <h2>{title}</h2>
      <p>{description}</p>
    </section>
  )
}
