export const CATEGORY_LABELS_RU: Record<string, string> = {
  food: 'Еда',
  transport: 'Транспорт',
  housing: 'Жильё',
  health: 'Здоровье',
  beauty: 'Красота',
  entertainment: 'Развлечения',
  subscriptions: 'Подписки',
  shopping: 'Покупки',
  home: 'Дом',
  telecom: 'Связь',
  work: 'Работа',
  education: 'Обучение',
  gifts: 'Подарки',
  fees: 'Комиссии',
  salary: 'Зарплата',
  freelance: 'Фриланс',
  bonus: 'Премии',
  transfer: 'Переводы',
  refund: 'Возвраты',
  other_income: 'Прочий доход',
  other: 'Прочее',
}

export function categoryLabel(category: string) {
  return CATEGORY_LABELS_RU[category] || category
}
