import { useQuery } from '@tanstack/react-query'
import { fetchSummary } from '@/lib/api'
import type { Period } from '@/lib/schemas'

export const summaryKeys = {
  all: ['summary'] as const,
  byPeriod: (period: Period) => ['summary', period] as const,
}

export function useSummary(period: Period) {
  return useQuery({
    queryKey: summaryKeys.byPeriod(period),
    queryFn: () => fetchSummary(period),
  })
}
