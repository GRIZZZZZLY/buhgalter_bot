export type Period = 'today' | 'week' | 'month' | 'all'

export type Transaction = {
  id: string
  type: 'income' | 'expense'
  title: string
  category: string
  amount: number
  timestamp: string
}

export type CategorySlice = {
  name: string
  value: number
  fill: string
}

export type EditableTransaction = {
  id: string
  type: 'income' | 'expense'
  title: string
  category: string
  amount: string
  timestamp: string
}
