import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchBudgets, upsertBudget } from '@/lib/api'

export const budgetKeys = {
  all: ['budgets'] as const,
}

export function useBudgets() {
  return useQuery({
    queryKey: budgetKeys.all,
    queryFn: fetchBudgets,
  })
}

export function useUpsertBudget() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ category, amount }: { category: string; amount: number }) =>
      upsertBudget(category, amount),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: budgetKeys.all })
    },
  })
}
