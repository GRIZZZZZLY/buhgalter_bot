import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from app.db.session import SessionLocal
from app.repositories.event_repository import log_event
from app.telegram.bot_service import TelegramBotService
from app.telegram.keyboards import (
    category_grid_keyboard,
    done_keyboard,
)
from app.telegram.handlers.common import _ensure_user

logger = logging.getLogger("finance_bot.telegram")

_CATFIX_CATEGORIES = [
    "food", "transport", "housing", "health", "beauty", "entertainment",
    "subscriptions", "shopping", "home", "telecom", "work", "education",
    "gifts", "fees", "salary", "freelance", "bonus", "transfer", "refund",
    "other_income", "other",
]


async def catfix_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except BadRequest:
        pass

    # catfix:change:<tx_id>
    # catfix:set:<tx_id>:<slug>
    # catfix:cancel:<tx_id>
    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    tx_id  = parts[2] if len(parts) > 2 else ""

    if action == "cancel":
        await query.edit_message_reply_markup(reply_markup=None)
        return

    if action == "change":
        user_id = update.effective_user.id
        with SessionLocal() as _cat_db:
            from app.services.category_service import CategoryService
            _ensure_user(_cat_db, update)
            _cat_svc = CategoryService(_cat_db)
            _cat_svc.ensure_seeded(user_id)
            _all_visible = (
                [c.slug for c in _cat_svc.get_visible_for_type(user_id, "expense")]
                + [c.slug for c in _cat_svc.get_visible_for_type(user_id, "income")]
            )
            _visible_catfix = [s for s in _CATFIX_CATEGORIES if s in _all_visible]
        await query.edit_message_reply_markup(
            reply_markup=category_grid_keyboard(tx_id, _visible_catfix or _CATFIX_CATEGORIES)
        )
        return

    if action == "set":
        slug = parts[3] if len(parts) > 3 else ""
        user_id = update.effective_user.id
        with SessionLocal() as db:
            svc = TelegramBotService(db)
            result = svc.handle_category_correction(user_id, tx_id, slug)
        log_event(user_id, "catfix_applied")
        await query.edit_message_text(result["message"], parse_mode="HTML", reply_markup=done_keyboard())
        return

    await query.edit_message_reply_markup(reply_markup=None)


async def improve_categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from app.telegram.handlers_legacy import _sugg_set
    await update.effective_message.reply_text("Анализирую транзакции…")
    try:
        with SessionLocal() as db:
            _ensure_user(db, update)
            svc = TelegramBotService(db)
            results = svc.improve_categories(update.effective_user.id)
    except Exception as exc:
        await update.effective_message.reply_text(f"Ошибка при анализе: {exc}", reply_markup=done_keyboard())
        return

    if not results:
        await update.effective_message.reply_text("Предложений нет.", reply_markup=done_keyboard())
        return

    from app.telegram.keyboards import grouped_suggestion_keyboard
    lines = []
    for i, item in enumerate(results, 1):
        _sugg_set(item["key"], item["suggestion"])
        lines.append(f"<b>{i}.</b> {item['text']}")
    await update.effective_message.reply_text(
        "\n\n".join(lines),
        parse_mode="HTML",
        reply_markup=grouped_suggestion_keyboard(results),
    )


async def sugg_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from app.telegram.handlers_legacy import _sugg_pop
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except BadRequest:
        pass

    data = query.data          # e.g. "sugg:abc12345_yes"
    key = data.rsplit("_", 1)[0]
    action = data.rsplit("_", 1)[1] if "_" in data else ""

    suggestion = _sugg_pop(key)
    if suggestion is not None and action == "yes":
        with SessionLocal() as db:
            svc = TelegramBotService(db)
            svc.apply_suggestion(suggestion)

    # Rebuild keyboard without the processed row
    remaining_rows = []
    if query.message and query.message.reply_markup:
        for row in query.message.reply_markup.inline_keyboard:
            row_keys = {btn.callback_data.rsplit("_", 1)[0] for btn in row if btn.callback_data}
            if key not in row_keys:
                remaining_rows.append(row)

    if remaining_rows:
        await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup(remaining_rows)
        )
    else:
        await query.edit_message_reply_markup(reply_markup=None)


async def categories_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except BadRequest:
        pass

    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    param = parts[2] if len(parts) > 2 else ""
    # Optional type+page appended by categories_list_keyboard: categories:edit:{slug}:{type}:{page}
    _ctx_type = parts[3] if len(parts) > 3 else ""
    _ctx_page = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 0
    user_id = update.effective_user.id

    def _list_back() -> str:
        """Back target to the category list (or type selector if no context)."""
        t = context.user_data.get("categories_ctx", {}).get("type", _ctx_type)
        p = context.user_data.get("categories_ctx", {}).get("page", _ctx_page)
        return f"nav:categories:{t}:{p}" if t else "nav:categories"

    from app.services.category_service import CategoryService
    from app.telegram.keyboards import (
        category_edit_keyboard,
        category_type_keyboard,
        category_reassign_keyboard,
        category_delete_confirm_keyboard,
    )

    if action == "edit":
        slug = param
        if _ctx_type:
            context.user_data["categories_ctx"] = {"type": _ctx_type, "page": _ctx_page}
        with SessionLocal() as db:
            _ensure_user(db, update)
            svc = CategoryService(db)
            svc.ensure_seeded(user_id)
            cat = svc._repo.get_by_slug(user_id, slug)
        if cat is None:
            await query.edit_message_text("❌ Категория не найдена.", reply_markup=done_keyboard(back_target=_list_back()))
            return
        text = f"✏️ *{cat.emoji} {cat.name_ru}*\n\nЧто изменить?"
        await query.edit_message_text(
            text,
            reply_markup=category_edit_keyboard(slug, cat.is_custom, cat.is_hidden, back_target=_list_back()),
            parse_mode="Markdown",
        )
        return

    if action == "rename":
        slug = param
        context.user_data["awaiting_category_rename"] = slug
        await query.edit_message_text(
            "✏️ Введи новое название категории:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(text="Отмена", callback_data=f"categories:edit:{slug}")
            ]]),
        )
        return

    if action == "emoji":
        slug = param
        context.user_data["awaiting_category_emoji"] = slug
        await query.edit_message_text(
            "🎨 Отправь новый emoji для категории:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(text="Отмена", callback_data=f"categories:edit:{slug}")
            ]]),
        )
        return

    if action == "add":
        context.user_data["awaiting_category_add"] = "name"
        context.user_data.pop("pending_category_add", None)
        await query.edit_message_text(
            "➕ Введи название новой категории:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(text="Отмена", callback_data="nav:categories")
            ]]),
        )
        return

    if action == "set_type":
        cat_type = param
        pending = context.user_data.get("pending_category_add", {})
        name_ru = pending.get("name_ru", "")
        emoji = pending.get("emoji", "")
        if not name_ru or not emoji:
            await query.edit_message_text("❌ Что-то пошло не так. Попробуй снова.", reply_markup=done_keyboard(back_target=_list_back()))
            return
        context.user_data.pop("pending_category_add", None)
        context.user_data.pop("awaiting_category_add", None)
        with SessionLocal() as db:
            _ensure_user(db, update)
            svc = CategoryService(db)
            svc.ensure_seeded(user_id)
            try:
                cat = svc.add_custom(user_id, name_ru, emoji, cat_type)
            except ValueError as e:
                await query.edit_message_text(f"❌ {e}", reply_markup=done_keyboard(back_target=_list_back()))
                return
        await query.edit_message_text(f"✅ Категория «{cat.emoji} {cat.name_ru}» создана!", reply_markup=done_keyboard())
        return

    if action == "delete":
        slug = param
        with SessionLocal() as db:
            _ensure_user(db, update)
            svc = CategoryService(db)
            svc.ensure_seeded(user_id)
            cat = svc._repo.get_by_slug(user_id, slug)
            if cat is None or not cat.is_custom:
                await query.edit_message_text("❌ Нельзя удалить системную категорию.", reply_markup=done_keyboard(back_target=_list_back()))
                return
            count = svc.count_transactions(user_id, slug)
            if count > 0:
                groups = svc.list_categories(user_id)
                compatible = [
                    c
                    for cats in groups.values()
                    for c in cats
                    if c.slug != slug and (c.type == cat.type or c.type == "both" or cat.type == "both")
                ]
        if count > 0:
            await query.edit_message_text(
                f"⚠️ В категории «{cat.name_ru}» есть {count} транзакций.\n"
                f"Куда перенести их перед удалением?",
                reply_markup=category_reassign_keyboard(compatible, slug),
            )
        else:
            await query.edit_message_text(
                f"Удалить категорию «{cat.emoji} {cat.name_ru}»? Это нельзя отменить.",
                reply_markup=category_delete_confirm_keyboard(slug),
            )
        return

    if action == "confirm_delete":
        slug = param
        with SessionLocal() as db:
            _ensure_user(db, update)
            svc = CategoryService(db)
            svc.ensure_seeded(user_id)
            try:
                svc.delete_custom(user_id, slug, reassign_to_slug="other")
            except ValueError as e:
                await query.edit_message_text(f"❌ {e}", reply_markup=done_keyboard(back_target=_list_back()))
                return
        await query.edit_message_text("✅ Категория удалена.", reply_markup=done_keyboard())
        return

    if action == "reassign":
        if "__" not in param:
            await query.edit_message_text("❌ Неверный формат.", reply_markup=done_keyboard(back_target=_list_back()))
            return
        from_slug, to_slug = param.split("__", 1)
        with SessionLocal() as db:
            _ensure_user(db, update)
            svc = CategoryService(db)
            svc.ensure_seeded(user_id)
            try:
                svc.delete_custom(user_id, from_slug, to_slug)
            except ValueError as e:
                await query.edit_message_text(f"❌ {e}", reply_markup=done_keyboard(back_target=_list_back()))
                return
        await query.edit_message_text("✅ Транзакции перенесены, категория удалена.", reply_markup=done_keyboard())
        return

    if action == "toggle_hidden":
        slug = param
        with SessionLocal() as db:
            _ensure_user(db, update)
            svc = CategoryService(db)
            cat = svc.toggle_hidden(user_id, slug)
        if cat is None:
            await query.answer("❌ Категория не найдена", show_alert=True)
            return
        state = "скрыта" if cat.is_hidden else "показана"
        text = f"{'🙈' if cat.is_hidden else '👁'} *{cat.emoji} {cat.name_ru}* — категория {state}.\n\nЧто изменить?"
        await query.edit_message_text(
            text,
            reply_markup=category_edit_keyboard(slug, cat.is_custom, cat.is_hidden),
            parse_mode="Markdown",
        )
        return


async def reset_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles reset:pick, reset:confirm:{scope}, reset:do:{scope}."""
    from app.telegram.keyboards import reset_pick_keyboard, reset_confirm_keyboard
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except BadRequest:
        pass

    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    scope = parts[2] if len(parts) > 2 else ""
    user_id = update.effective_user.id

    if action == "pick":
        await query.edit_message_text(
            "🗑 *Сброс данных*\n\nЧто удалить?",
            reply_markup=reset_pick_keyboard(),
            parse_mode="Markdown",
        )
        return

    if action == "confirm":
        labels = {"all": "все транзакции и бюджеты", "expense": "все расходы", "income": "все доходы"}
        label = labels.get(scope, scope)
        await query.edit_message_text(
            f"⚠️ Удалить *{label}*?\n\nЭто действие нельзя отменить.",
            reply_markup=reset_confirm_keyboard(scope),
            parse_mode="Markdown",
        )
        return

    if action == "do":
        from app.services.transaction_service import TransactionService
        with SessionLocal() as db:
            _ensure_user(db, update)
            svc = TransactionService(db)
            if scope == "all":
                count = svc.delete_all_for_user(user_id)
                from sqlalchemy import delete as sa_delete
                from app.models.category_budget import CategoryBudget
                db.execute(sa_delete(CategoryBudget).where(CategoryBudget.telegram_user_id == user_id))
                from app.repositories.user_repository import UserRepository
                user_repo = UserRepository(db)
                u = user_repo.get_by_telegram_id(user_id)
                if u:
                    user_repo.update_settings(u, budget_amount=None)
                db.commit()
                msg = f"✅ Удалено {count} транзакций и все бюджеты."
            else:
                count = svc.delete_by_type(user_id, scope)
                label = "расходов" if scope == "expense" else "доходов"
                msg = f"✅ Удалено {count} {label}."
        await query.edit_message_text(msg, reply_markup=done_keyboard(back_target="nav:settings"))
        return
