import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  createTransaction,
  deleteTransaction,
  fetchTransactions,
  updateTransaction,
} from '@/lib/api'
import type { CreateTransactionInput, Period, UpdateTransactionInput } from '@/lib/schemas'

export const transactionKeys = {
  all: ['transactions'] as const,
  byPeriod: (period: Period) => ['transactions', period] as const,
}

export function useTransactions(period: Period) {
  return useInfiniteQuery({
    queryKey: transactionKeys.byPeriod(period),
    queryFn: ({ pageParam = 0 }) => fetchTransactions(period, 20, pageParam as number),
    initialPageParam: 0,
    getNextPageParam: (lastPage) => {
      const nextOffset = lastPage.offset + lastPage.limit
      return lastPage.items.length === lastPage.limit ? nextOffset : undefined
    },
  })
}

export function useCreateTransaction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: CreateTransactionInput) => createTransaction(input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: transactionKeys.all })
      void queryClient.invalidateQueries({ queryKey: ['summary'] })
      void queryClient.invalidateQueries({ queryKey: ['budgets'] })
    },
  })
}

export function useUpdateTransaction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: UpdateTransactionInput }) =>
      updateTransaction(id, input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: transactionKeys.all })
      void queryClient.invalidateQueries({ queryKey: ['summary'] })
    },
  })
}

export function useDeleteTransaction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteTransaction(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: transactionKeys.all })
      void queryClient.invalidateQueries({ queryKey: ['summary'] })
      void queryClient.invalidateQueries({ queryKey: ['budgets'] })
    },
  })
}
