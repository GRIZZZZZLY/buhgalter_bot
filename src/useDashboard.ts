import { useCallback, useEffect, useState } from 'react'
import { loadDashboard } from './lib/api'
import type { CategorySlice, Period, Transaction } from './lib/types'

export function useDashboard(period: Period) {
  const [state, setState] = useState<{
    loading: boolean
    source: 'api' | 'mock'
    summary: { balance: number; income: number; expense: number }
    chart: CategorySlice[]
    transactions: Transaction[]
  }>({
    loading: true,
    source: 'mock',
    summary: { balance: 0, income: 0, expense: 0 },
    chart: [],
    transactions: [],
  })

  const refresh = useCallback(() => {
    let active = true
    setState((prev) => ({ ...prev, loading: true }))

    loadDashboard(period).then((result) => {
      if (!active) return
      setState({
        loading: false,
        source: result.source,
        summary: result.summary,
        chart: result.chart,
        transactions: result.transactions,
      })
    })

    return () => {
      active = false
    }
  }, [period])

  useEffect(() => {
    const cleanup = refresh()
    return cleanup
  }, [refresh])

  return {
    ...state,
    refresh,
  }
}
