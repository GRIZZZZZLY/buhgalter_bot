import { useState } from 'react'
import { useNavigate } from 'react-router'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { toast } from 'sonner'
import { z } from 'zod'
import { motion } from 'motion/react'
import { useCreateTransaction } from '@/hooks/use-transactions'
import { getCategoriesForType, getCategoryLabel } from '@/lib/categories'

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

export function AddTransactionPage() {
  const navigate = useNavigate()
  const { mutateAsync, isPending } = useCreateTransaction()
  const [txType, setTxType] = useState<'expense' | 'income'>('expense')

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { type: 'expense', category: 'food' },
  })

  const selectedCategory = watch('category')

  const handleTypeChange = (next: 'expense' | 'income') => {
    setTxType(next)
    setValue('type', next)
    const cats = getCategoriesForType(next)
    setValue('category', cats[0] ?? 'other')
  }

  const onSubmit = async (values: FormValues) => {
    try {
      await mutateAsync({
        type: values.type,
        amount: parseFloat(values.amount).toFixed(2),
        category: values.category,
        description: values.description?.trim() || undefined,
      })
      toast.success(values.type === 'income' ? 'Доход добавлен' : 'Расход добавлен')
      void navigate(-1)
    } catch {
      toast.error('Не удалось сохранить')
    }
  }

  const categories = getCategoriesForType(txType)

  return (
    <div className="page-content flex flex-col gap-4 px-4 pt-4 pb-24">
      {/* Header */}
      <div>
        <span className="section-kicker">Казначей</span>
        <h1
          className="font-display font-semibold mt-0.5"
          style={{ fontSize: 22, color: '#1a1208' }}
        >
          Новая операция
        </h1>
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
            placeholder="0"
            className="amount-input"
            style={{ fontSize: 'clamp(36px, 10vw, 48px)', fontWeight: 700 }}
            autoFocus
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
            Описание (необязательно)
          </label>
          <input
            {...register('description')}
            type="text"
            placeholder="Пятёрочка, зарплата за март…"
            className="field-input"
          />
        </div>

        <button type="submit" disabled={isPending} className="btn-primary">
          {isPending ? 'Сохраняю…' : 'Добавить'}
        </button>
      </form>
    </div>
  )
}
