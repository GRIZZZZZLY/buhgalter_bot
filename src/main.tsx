import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { HashRouter, Route, Routes } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'sonner'

import { initTelegramApp } from '@/lib/telegram'
import { Layout } from '@/components/layout'
import { DashboardPage } from '@/pages/dashboard'
import { BudgetsPage } from '@/pages/budgets'
import { AddTransactionPage } from '@/pages/add-transaction'
import { EditTransactionPage } from '@/pages/edit-transaction'

import '@/app.css'

// ── 1. Init Telegram SDK before React renders ─────────────────────────
initTelegramApp()

// ── 2. TanStack Query client ──────────────────────────────────────────
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60_000,
      gcTime: 10 * 60_000,
      retry: 1,
      refetchOnWindowFocus: false, // Critical: Telegram fires spurious focus events
      refetchOnReconnect: true,
    },
  },
})

// ── 3. Mount ──────────────────────────────────────────────────────────
const rootEl = document.getElementById('root')
if (!rootEl) throw new Error('#root element not found')

createRoot(rootEl).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <HashRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<DashboardPage />} />
            <Route path="budgets" element={<BudgetsPage />} />
            <Route path="add" element={<AddTransactionPage />} />
            <Route path="transaction/:id" element={<EditTransactionPage />} />
          </Route>
        </Routes>
      </HashRouter>
      <Toaster
        position="top-center"
        toastOptions={{
          style: {
            background: 'var(--tg-theme-bg-color, #fff)',
            color: 'var(--tg-theme-text-color, #000)',
            border: '1px solid var(--tg-theme-hint-color, #ccc)',
          },
        }}
      />
    </QueryClientProvider>
  </StrictMode>,
)
