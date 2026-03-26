import { format, formatDistanceToNow, parseISO } from 'date-fns'
import { ru } from 'date-fns/locale'

const RUB = new Intl.NumberFormat('ru-RU', {
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
})

export function formatAmount(value: number | string): string {
  return RUB.format(Number(value))
}

export function formatAmountSigned(value: number | string, type: 'income' | 'expense'): string {
  const sign = type === 'income' ? '+' : '−'
  return `${sign}${formatAmount(value)} ₽`
}

export function formatDate(isoString: string): string {
  try {
    const date = parseISO(isoString)
    return format(date, 'd MMM, HH:mm', { locale: ru })
  } catch {
    return isoString
  }
}

export function formatDateRelative(isoString: string): string {
  try {
    const date = parseISO(isoString)
    return formatDistanceToNow(date, { addSuffix: true, locale: ru })
  } catch {
    return isoString
  }
}

export function formatPercent(value: number): string {
  return `${Math.round(value)}%`
}
