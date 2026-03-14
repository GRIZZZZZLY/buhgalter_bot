import type { CategorySlice, EditableTransaction, Period, Transaction } from './types'
import { categoryLabel } from './categoryLabels'
import { chartData, summary, transactions } from '../mocks/data'

type SummaryResponse = {
  balance: string
  income_total: string
  expense_total: string
  top_expense_categories: { category: string; amount: string }[]
}

type TransactionApiItem = {
  id: string
  type: 'income' | 'expense'
  amount: string
  category: string
  description?: string | null
  created_at: string
}

const API_BASE = import.meta.env.VITE_API_BASE || '/api-proxy'
const CHART_COLORS = ['#2754C5', '#8A1C1C', '#B38728', '#3E6472', '#5B3A29']

function getHeaders() {
  return {
    'Content-Type': 'application/json',
    'X-Telegram-User-Id': '555502880',
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...getHeaders(),
      ...(init?.headers || {}),
    },
  })

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json() as Promise<T>
}

function mapApiTransaction(item: TransactionApiItem): Transaction {
  return {
    id: item.id,
    type: item.type,
    title: item.description || categoryLabel(item.category),
    category: categoryLabel(item.category),
    amount: Number(item.amount),
    timestamp: new Date(item.created_at).toLocaleString('ru-RU', {
      day: '2-digit',
      month: 'long',
      hour: '2-digit',
      minute: '2-digit',
    }),
  }
}

export async function loadDashboard(period: Period): Promise<{
  summary: { balance: number; income: number; expense: number }
  chart: CategorySlice[]
  transactions: Transaction[]
  source: 'api' | 'mock'
}> {
  try {
    const [summaryData, transactionsData] = await Promise.all([
      request<SummaryResponse>(`/api/summary?period=${period}`),
      request<{ items: TransactionApiItem[] }>(`/api/transactions?limit=20&offset=0&period=${period}`),
    ])

    return {
      summary: {
        balance: Number(summaryData.balance),
        income: Number(summaryData.income_total),
        expense: Number(summaryData.expense_total),
      },
      chart: summaryData.top_expense_categories.map((item, index) => ({
        name: categoryLabel(item.category),
        value: Number(item.amount),
        fill: CHART_COLORS[index % CHART_COLORS.length],
      })),
      transactions: transactionsData.items.map(mapApiTransaction),
      source: 'api',
    }
  } catch {
    return {
      summary,
      chart: chartData,
      transactions,
      source: 'mock',
    }
  }
}

export async function updateTransaction(draft: EditableTransaction): Promise<boolean> {
  try {
    await request(`/api/transactions/${draft.id}`, {
      method: 'PUT',
      body: JSON.stringify({
        type: draft.type,
        amount: draft.amount,
        category: draft.category,
        description: draft.title,
      }),
    })
    return true
  } catch {
    return false
  }
}

export async function removeTransaction(id: string): Promise<boolean> {
  try {
    await request(`/api/transactions/${id}`, {
      method: 'DELETE',
    })
    return true
  } catch {
    return false
  }
}
