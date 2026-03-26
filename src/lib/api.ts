/**
 * API functions — thin wrappers over apiRequest with Zod validation.
 * Each function validates the response at runtime and returns typed data.
 */
import { apiRequest } from './api-client'
import {
  BudgetItemSchema,
  BudgetResponseSchema,
  SummarySchema,
  TransactionListSchema,
  TransactionSchema,
  type BudgetItem,
  type BudgetResponse,
  type CreateTransactionInput,
  type Period,
  type Summary,
  type Transaction,
  type TransactionList,
  type UpdateTransactionInput,
} from './schemas'

// ── Summary ───────────────────────────────────────────────────────────
export async function fetchSummary(period: Period): Promise<Summary> {
  const raw = await apiRequest(`/api/summary?period=${period}`)
  return SummarySchema.parse(raw)
}

// ── Transactions ──────────────────────────────────────────────────────
export async function fetchTransactions(
  period: Period,
  limit = 20,
  offset = 0,
): Promise<TransactionList> {
  const raw = await apiRequest(`/api/transactions?period=${period}&limit=${limit}&offset=${offset}`)
  return TransactionListSchema.parse(raw)
}

export async function createTransaction(input: CreateTransactionInput): Promise<Transaction> {
  const raw = await apiRequest('/api/transactions', {
    method: 'POST',
    body: JSON.stringify(input),
  })
  return TransactionSchema.parse(raw)
}

export async function updateTransaction(
  id: string,
  input: UpdateTransactionInput,
): Promise<Transaction> {
  const raw = await apiRequest(`/api/transactions/${id}`, {
    method: 'PUT',
    body: JSON.stringify(input),
  })
  return TransactionSchema.parse(raw)
}

export async function deleteTransaction(id: string): Promise<void> {
  await apiRequest(`/api/transactions/${id}`, { method: 'DELETE' })
}

// ── Budgets ───────────────────────────────────────────────────────────
export async function fetchBudgets(): Promise<BudgetResponse> {
  const raw = await apiRequest('/api/budgets')
  return BudgetResponseSchema.parse(raw)
}

export async function upsertBudget(category: string, amount: number): Promise<BudgetItem> {
  const raw = await apiRequest('/api/budgets', {
    method: 'PUT',
    body: JSON.stringify({ category, amount }),
  })
  return BudgetItemSchema.parse(raw)
}
