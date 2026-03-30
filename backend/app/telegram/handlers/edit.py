import logging

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from app.db.session import SessionLocal
from app.telegram.formatter import TreasuryFormatter
from app.telegram.keyboards import (
    cancel_keyboard,
    done_keyboard,
    edit_categories_keyboard,
    edit_item_keyboard,
    edit_select_keyboard,
)
from app.telegram.handlers.common import _ensure_user

logger = logging.getLogger("finance_bot.telegram")
formatter = TreasuryFormatter()


async def edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with SessionLocal() as db:
        _ensure_user(db, update)
        from app.services.transaction_service import TransactionService
        svc = TransactionService(db)
        items = svc.list_recent_for_delete(update.effective_user.id, limit=5)

    if not items:
        await update.effective_message.reply_text("📭 Записей для редактирования нет.", reply_markup=done_keyboard())
        return

    await update.effective_message.reply_text(
        "✏️ Выбери запись для редактирования:",
        reply_markup=edit_select_keyboard(items),
    )


async def edit_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except BadRequest:
        pass

    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    tx_id  = parts[2] if len(parts) > 2 else ""
    extra  = parts[3] if len(parts) > 3 else ""
    user_id = update.effective_user.id

    if action == "select":
        with SessionLocal() as db:
            from app.services.transaction_service import TransactionService
            svc = TransactionService(db)
            items = svc.list_recent_for_delete(user_id, limit=5)
        if not items:
            await query.edit_message_text("📭 Записей нет.", reply_markup=done_keyboard())
            return
        await query.edit_message_text(
            "✏️ Выбери запись для редактирования:",
            reply_markup=edit_select_keyboard(items),
        )
        return

    if action == "item":
        with SessionLocal() as db:
            from app.services.transaction_service import TransactionService
            svc = TransactionService(db)
            items = svc.list_recent_for_delete(user_id, limit=20)
            tx = next((i for i in items if i["id"] == tx_id), None)
        if tx is None:
            await query.edit_message_text("❌ Не нашёл запись.", reply_markup=done_keyboard(back_target="nav:menu"))
            return
        sign  = "↗" if tx["type"] == "income" else "↘"
        label = formatter.category_label(tx["category"])
        text  = f"✏️ {sign} {tx['amount']} ₽ — {label}\n\nЧто изменить?"
        await query.edit_message_text(text, reply_markup=edit_item_keyboard(tx_id))
        return

    if action == "del":
        from app.telegram.keyboards import edit_delete_confirm_keyboard
        await query.edit_message_text(
            "🗑 Удалить эту запись?",
            reply_markup=edit_delete_confirm_keyboard(tx_id),
        )
        return

    if action == "del_confirm":
        with SessionLocal() as db:
            from uuid import UUID
            from app.services.transaction_service import TransactionService
            svc = TransactionService(db)
            deleted = svc.delete_transaction(user_id, UUID(tx_id))
        if deleted:
            await query.edit_message_text("✅ Удалил запись.", reply_markup=done_keyboard())
        else:
            await query.edit_message_text("❌ Не нашёл запись. Возможно, она уже удалена.", reply_markup=done_keyboard(back_target="nav:menu"))
        return

    if action == "type":
        with SessionLocal() as db:
            from uuid import UUID
            from app.services.transaction_service import TransactionService
            from app.schemas.transaction import TransactionUpdateRequest
            svc = TransactionService(db)
            items = svc.list_recent_for_delete(user_id, limit=20)
            tx = next((i for i in items if i["id"] == tx_id), None)
            if tx is None:
                await query.edit_message_text("❌ Не нашёл запись.", reply_markup=done_keyboard(back_target="nav:menu"))
                return
            new_type = "income" if tx["type"] == "expense" else "expense"
            svc.update_transaction(user_id, UUID(tx_id), TransactionUpdateRequest(type=new_type))
        type_label = "↗ доход" if new_type == "income" else "↘ расход"
        await query.edit_message_text(
            f"Тип изменён: {type_label} ✅",
            reply_markup=edit_item_keyboard(tx_id),
        )
        return

    if action == "amount":
        if context.user_data is not None:
            context.user_data["awaiting_edit"] = {
                "field": "amount", "tx_id": tx_id,
                "chat_id": query.message.chat_id,
                "message_id": query.message.message_id,
            }
        await query.edit_message_text("✏️ Введи новую сумму (например: 750 или 1200.50):", reply_markup=cancel_keyboard("edit:select"))
        return

    if action == "cat":
        if extra:
            with SessionLocal() as db:
                from uuid import UUID
                from app.services.transaction_service import TransactionService
                from app.schemas.transaction import TransactionUpdateRequest
                svc = TransactionService(db)
                svc.update_transaction(user_id, UUID(tx_id), TransactionUpdateRequest(category=extra))
            cat_label = formatter.category_label(extra)
            await query.edit_message_text(
                f"Категория изменена: {cat_label} ✅",
                reply_markup=edit_item_keyboard(tx_id),
            )
        else:
            with SessionLocal() as _cat_db:
                from app.services.category_service import CategoryService
                _ensure_user(_cat_db, update)
                _cat_svc = CategoryService(_cat_db)
                _cat_svc.ensure_seeded(user_id)
                _all_visible = (
                    _cat_svc.get_visible_for_type(user_id, "expense")
                    + _cat_svc.get_visible_for_type(user_id, "income")
                )
                seen: set[str] = set()
                _visible_edit: list[tuple[str, str]] = []
                for c in _all_visible:
                    if c.slug not in seen:
                        seen.add(c.slug)
                        _visible_edit.append((c.slug, c.emoji))
            await query.edit_message_text(
                "Выбери категорию:",
                reply_markup=edit_categories_keyboard(tx_id, categories=_visible_edit),
            )
        return
