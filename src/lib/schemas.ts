/**
 * Zod schemas for all API responses.
 * These are the single source of truth for runtime validation
 * and TypeScript type inference.
 */
import { z } from 'zod'

// ── Primitives ────────────────────────────────────────────────────────
export const Period = z.enum(['today', 'week', 'month', 'all'])
export type Period = z.infer<typeof Period>

export const TransactionType = z.enum(['income', 'expense'])
export type TransactionType = z.infer<typeof TransactionType>

// ── Transaction ───────────────────────────────────────────────────────
export const TransactionSchema = z.object({
  id: z.string().uuid(),
  telegram_user_id: z.number().int(),
  type: TransactionType,
  amount: z.string(),
  category: z.string(),
  description: z.string().nullable().optional(),
  source: z.enum(['text', 'voice', 'webapp']),
  raw_input: z.string(),
  confidence: z.number(),
  created_at: z.string().datetime({ offset: true }),
  updated_at: z.string().datetime({ offset: true }),
})
export type Transaction = z.infer<typeof TransactionSchema>

export const TransactionListSchema = z.object({
  items: z.array(TransactionSchema),
  limit: z.number(),
  offset: z.number(),
  period: z.string(),
})
export type TransactionList = z.infer<typeof TransactionListSchema>

// ── Summary ───────────────────────────────────────────────────────────
export const CategoryTotalSchema = z.object({
  category: z.string(),
  amount: z.string(),
})

export const SummarySchema = z.object({
  period: z.string(),
  balance: z.string(),
  income_total: z.string(),
  expense_total: z.string(),
  top_expense_categories: z.array(CategoryTotalSchema),
})
export type Summary = z.infer<typeof SummarySchema>

// ── Budget ────────────────────────────────────────────────────────────
export const BudgetItemSchema = z.object({
  category: z.string(),
  limit: z.number(),
  spent: z.number(),
  pct: z.number(),
})
export type BudgetItem = z.infer<typeof BudgetItemSchema>

export const BudgetResponseSchema = z.object({
  items: z.array(BudgetItemSchema),
  total_budget: z.number().nullable(),
  total_spent: z.number(),
  total_pct: z.number().nullable(),
})
export type BudgetResponse = z.infer<typeof BudgetResponseSchema>

// ── Mutations ─────────────────────────────────────────────────────────
export const CreateTransactionSchema = z.object({
  type: TransactionType,
  amount: z.string().regex(/^\d+(\.\d{1,2})?$/),
  category: z.string().min(1),
  description: z.string().optional(),
})
export type CreateTransactionInput = z.infer<typeof CreateTransactionSchema>

export const UpdateTransactionSchema = z.object({
  type: TransactionType.optional(),
  amount: z
    .string()
    .regex(/^\d+(\.\d{1,2})?$/)
    .optional(),
  category: z.string().optional(),
  description: z.string().max(255).optional(),
})
export type UpdateTransactionInput = z.infer<typeof UpdateTransactionSchema>
