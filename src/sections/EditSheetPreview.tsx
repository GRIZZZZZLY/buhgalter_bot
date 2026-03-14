import { useEffect, useState } from 'react'
import type { EditableTransaction, Transaction } from '../lib/types'

function toEditable(item: Transaction): EditableTransaction {
  return {
    ...item,
    amount: String(item.amount),
  }
}

export function EditSheetPreview({
  item,
  onClose,
  onSave,
  onDelete,
  saving,
}: {
  item: Transaction | null
  onClose: () => void
  onSave: (item: EditableTransaction) => void | Promise<void>
  onDelete: (id: string) => void | Promise<void>
  saving: boolean
}) {
  const [draft, setDraft] = useState<EditableTransaction | null>(item ? toEditable(item) : null)

  useEffect(() => {
    setDraft(item ? toEditable(item) : null)
  }, [item])

  if (!draft) return null

  return (
    <div className="sheet-overlay" onClick={onClose}>
      <section className="sheet-preview ornate-frame-soft" onClick={(event) => event.stopPropagation()}>
        <div className="sheet-preview__grabber" />
        <div className="section-kicker">Правка записи</div>
        <h2>Редактирование</h2>
        <p className="sheet-preview__note">Исправь сумму, категорию или описание. Изменения применятся сразу после сохранения.</p>
        <div className="field-grid">
          <label>
            <span>Сумма</span>
            <input value={draft.amount} onChange={(e) => setDraft({ ...draft, amount: e.target.value })} />
          </label>
          <label>
            <span>Категория</span>
            <input value={draft.category} onChange={(e) => setDraft({ ...draft, category: e.target.value })} />
          </label>
          <label className="is-wide">
            <span>Описание</span>
            <input value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
          </label>
        </div>
        <div className="sheet-actions">
          <button className="danger-button" onClick={() => onDelete(draft.id)} disabled={saving}>Удалить</button>
          <button className="ghost-button" onClick={onClose} disabled={saving}>Отмена</button>
          <button className="primary-button" onClick={() => onSave(draft)} disabled={saving}>
            {saving ? 'Сохраняю...' : 'Сохранить'}
          </button>
        </div>
      </section>
    </div>
  )
}
