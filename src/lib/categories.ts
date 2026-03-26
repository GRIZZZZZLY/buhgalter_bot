export const CATEGORY_LABELS: Record<string, string> = {
  // Expenses
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
  other: 'Прочее',
  // Income
  salary: 'Зарплата',
  freelance: 'Фриланс',
  bonus: 'Премия',
  transfer: 'Перевод',
  refund: 'Возврат',
  other_income: 'Прочий доход',
}

export const EXPENSE_CATEGORIES = [
  'food',
  'transport',
  'housing',
  'health',
  'beauty',
  'entertainment',
  'subscriptions',
  'shopping',
  'home',
  'telecom',
  'education',
  'gifts',
  'fees',
  'work',
  'other',
] as const

export const INCOME_CATEGORIES = [
  'salary',
  'freelance',
  'bonus',
  'transfer',
  'refund',
  'other_income',
] as const

export type ExpenseCategory = (typeof EXPENSE_CATEGORIES)[number]
export type IncomeCategory = (typeof INCOME_CATEGORIES)[number]

export function getCategoryLabel(slug: string): string {
  return CATEGORY_LABELS[slug] ?? slug
}

export function getCategoriesForType(type: 'income' | 'expense') {
  return type === 'expense' ? EXPENSE_CATEGORIES : INCOME_CATEGORIES
}

/** Donut chart color palette — maps to category index */
export const CATEGORY_COLORS = [
  '#3390ec', // tg-blue
  '#34c759', // green
  '#ff9500', // orange
  '#ff3b30', // red
  '#af52de', // purple
  '#5ac8fa', // light-blue
  '#ffcc00', // yellow
  '#ff2d55', // pink
] as const
