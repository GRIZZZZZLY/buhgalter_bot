import type { CategorySlice, Transaction } from '../lib/types'

export const summary = {
  balance: 18450,
  income: 45200,
  expense: 26750,
}

export const chartData: CategorySlice[] = [
  { name: 'Еда', value: 9200, fill: '#2754C5' },
  { name: 'Транспорт', value: 4300, fill: '#8A1C1C' },
  { name: 'Красота', value: 2300, fill: '#B38728' },
  { name: 'Подписки', value: 1800, fill: '#3E6472' },
  { name: 'Работа', value: 1200, fill: '#5B3A29' },
]

export const transactions: Transaction[] = [
  { id: '1', type: 'expense', title: 'Продукты в Пятёрке', category: 'Еда', amount: 2600, timestamp: 'Сегодня, 14:20' },
  { id: '2', type: 'expense', title: 'Такси домой', category: 'Транспорт', amount: 400, timestamp: 'Сегодня, 13:05' },
  { id: '3', type: 'expense', title: 'Ресницы', category: 'Красота', amount: 2300, timestamp: 'Вчера, 18:40' },
  { id: '4', type: 'income', title: 'Оплата от клиента', category: 'Фриланс', amount: 12000, timestamp: 'Вчера, 11:15' },
  { id: '5', type: 'expense', title: 'Spotify', category: 'Подписки', amount: 299, timestamp: '12 марта, 09:10' },
]
