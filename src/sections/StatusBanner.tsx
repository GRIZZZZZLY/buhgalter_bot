export function StatusBanner({
  loading,
  source,
}: {
  loading: boolean
  source: 'api' | 'mock'
}) {
  if (loading) {
    return <section className="status-banner">Обновляю летопись и пересчитываю сводку…</section>
  }

  if (source === 'mock') {
    return <section className="status-banner is-warning">Сейчас открыт демо-режим. Для живых данных нужен backend API.</section>
  }

  return <section className="status-banner is-success">Данные загружены из живой казны.</section>
}
