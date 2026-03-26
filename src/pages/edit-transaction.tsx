import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { toast } from 'sonner'
import { Trash2 } from 'lucide-react'
import { z } from 'zod'
import { motion } from 'motion/react'
import { useQueryClient } from '@tanstack/react-query'
import { useUpdateTransaction, useDeleteTransaction } from '@/hooks/use-transactions'
import { fetchTransactions } from '@/lib/api'
import { getCategoriesForType, getCategoryLabel } from '@/lib/categories'
import { formatAmount } from '@/lib/format'
import type { Transaction } from '@/lib/schemas'

const schema = z.object({
  type: z.enum(['income', 'expense']),
  amount: z
    .string()
    .min(1, 'Введи сумму')
    .refine((v) => !isNaN(parseFloat(v)) && parseFloat(v) > 0, 'Сумма должна быть больше 0'),
  category: z.string().min(1),
  description: z.string().optional(),
})

type FormValues = z.infer<typeof schema>

export function EditTransactionPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [tx, setTx] = useState<Transaction | null>(null)
  const [loading, setLoading] = useState(true)
  const [txType, setTxType] = useState<'expense' | 'income'>('expense')

  const { mutateAsync: updateAsync, isPending: isUpdating } = useUpdateTransaction()
  const { mutateAsync: deleteAsync, isPending: isDeleting } = useDeleteTransaction()

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    reset,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { type: 'expense', category: 'other' },
  })

  const selectedCategory = watch('category')

  // Load transaction from cache or fetch
  useEffect(() => {
    if (!id) return

    // Try to find in query cache first
    const cached = queryClient
      .getQueriesData<{ pages: { items: Transaction[] }[] }>({ queryKey: ['transactions'] })
      .flatMap(([, data]) => data?.pages.flatMap((p) => p.items) ?? [])
      .find((t) => t.id === id)

    if (cached) {
      setTx(cached)
      setTxType(cached.type)
      reset({
        type: cached.type,
        amount: String(parseFloat(cached.amount)),
        category: cached.category,
        description: cached.description ?? '',
      })
      setLoading(false)
    } else {
      // Fallback: fetch from API
      fetchTransactions('all', 100, 0)
        .then((list) => {
          const found = list.items.find((t) => t.id === id)
          if (found) {
            setTx(found)
            setTxType(found.type)
            reset({
              type: found.type,
              amount: String(parseFloat(found.amount)),
              category: found.category,
              description: found.description ?? '',
            })
          }
        })
        .catch(() => toast.error('Не удалось загрузить запись'))
        .finally(() => setLoading(false))
    }
  }, [id, queryClient, reset])

  const handleTypeChange = (next: 'expense' | 'income') => {
    setTxType(next)
    setValue('type', next)
    const cats = getCategoriesForType(next)
    if (!cats.includes(selectedCategory as never)) {
      setValue('category', cats[0] ?? 'other')
    }
  }

  const onSubmit = async (values: FormValues) => {
    if (!id) return
    try {
      await updateAsync({
        id,
        input: {
          type: values.type,
          amount: parseFloat(values.amount).toFixed(2),
          category: values.category,
          description: values.description?.trim() || undefined,
        },
      })
      toast.success('Запись обновлена')
      void navigate(-1)
    } catch {
      toast.error('Не удалось сохранить')
    }
  }

  const handleDelete = async () => {
    if (!id) return
    try {
      await deleteAsync(id)
      toast.success('Запись удалена')
      void navigate(-1)
    } catch {
      toast.error('Не удалось удалить')
    }
  }

  const categories = getCategoriesForType(txType)
  const isPending = isUpdating || isDeleting

  if (loading) {
    return (
      <div className="page-content px-4 pt-4">
        <div className="skeleton h-8 w-40 mb-4" />
        <div className="skeleton h-32 mb-3" />
        <div className="skeleton h-24" />
      </div>
    )
  }

  if (!tx) {
    return (
      <div className="page-content px-4 pt-4">
        <div className="empty-state">
          <p className="text-3xl mb-3">🔍</p>
          <p className="font-display font-semibold" style={{ fontSize: 16, color: '#1a1208' }}>
            Запись не найдена
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="page-content flex flex-col gap-4 px-4 pt-4 pb-24">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <span className="section-kicker">Редактирование</span>
          <h1
            className="font-display font-semibold mt-0.5"
            style={{ fontSize: 22, color: '#1a1208' }}
          >
            {tx.description ?? getCategoryLabel(tx.category)}
          </h1>
          <p style={{ fontSize: 12, color: 'rgba(26,18,8,0.40)', marginTop: 2 }}>
            Оригинал: <span className="amount font-display">{formatAmount(tx.amount)} ₽</span>
          </p>
        </div>
        {/* Delete button */}
        <motion.button
          className="btn-danger mt-1"
          whileTap={{ scale: 0.95 }}
          onClick={() => void handleDelete()}
          disabled={isPending}
        >
          <Trash2 className="w-4 h-4 mr-1.5" />
          Удалить
        </motion.button>
      </div>

      <form onSubmit={(e) => void handleSubmit(onSubmit)(e)} className="flex flex-col gap-4">
        {/* Type toggle */}
        <div className="type-toggle">
          {(['expense', 'income'] as const).map((t) => (
            <motion.button
              key={t}
              type="button"
              whileTap={{ scale: 0.97 }}
              onClick={() => handleTypeChange(t)}
              className={`type-btn ${txType === t ? (t === 'expense' ? 'is-expense' : 'is-income') : ''}`}
            >
              {t === 'expense' ? '↘ Расход' : '↗ Доход'}
            </motion.button>
          ))}
        </div>

        {/* Amount */}
        <div className="field-card">
          <label
            className="block mb-2"
            style={{
              fontSize: 11,
              color: 'rgba(26,18,8,0.45)',
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
            }}
          >
            Сумма, ₽
          </label>
          <input
            {...register('amount')}
            type="number"
            inputMode="decimal"
            className="amount-input"
            style={{ fontSize: 'clamp(36px, 10vw, 48px)', fontWeight: 700 }}
          />
          {errors.amount && (
            <p className="mt-1.5" style={{ fontSize: 12, color: 'var(--color-expense)' }}>
              {errors.amount.message}
            </p>
          )}
        </div>

        {/* Category */}
        <div>
          <p className="section-kicker mb-2.5">Категория</p>
          <div className="flex flex-wrap gap-2">
            {categories.map((slug) => (
              <motion.button
                key={slug}
                type="button"
                whileTap={{ scale: 0.95 }}
                onClick={() => setValue('category', slug)}
                className={`category-pill ${selectedCategory === slug ? 'is-active' : ''}`}
              >
                {getCategoryLabel(slug)}
              </motion.button>
            ))}
          </div>
        </div>

        {/* Description */}
        <div className="field-card">
          <label
            className="block mb-2"
            style={{
              fontSize: 11,
              color: 'rgba(26,18,8,0.45)',
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
            }}
          >
            Описание
          </label>
          <input
            {...register('description')}
            type="text"
            placeholder="Описание операции…"
            className="field-input"
          />
        </div>

        <button type="submit" disabled={isPending} className="btn-primary">
          {isUpdating ? 'Сохраняю…' : 'Сохранить изменения'}
        </button>
      </form>
    </div>
  )
}
