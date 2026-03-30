import logging

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from app.db.session import SessionLocal
from app.services.planned_expense_service import parse_plan_args
from app.telegram.bot_service import TelegramBotService
from app.telegram.formatter import TreasuryFormatter
from app.telegram.keyboards import (
    cancel_keyboard,
    done_keyboard,
    main_menu_inline_keyboard,
    planned_freeform_keyboard,
    planned_manage_keyboard,
)
from app.telegram.handlers.common import _ensure_user

logger = logging.getLogger("finance_bot.telegram")
formatter = TreasuryFormatter()


def _format_planned_confirm_msg(item: dict) -> str:
    """Format confirmation message for a free-form planned expense."""
    amount = float(item.get("amount") or 0)
    title = item.get("title") or "Платёж"
    planned_date = item.get("planned_date") or ""
    reminder_time = item.get("reminder_time") or ""
    cat = formatter.category_label(item.get("category") or "other")

    date_line = f"\n📅 Дата: {planned_date}" if planned_date else ""
    time_line = f"\n⏰ Напоминание: {reminder_time}" if reminder_time else ""
    return (
        f"📋 <b>Запланировать платёж?</b>\n"
        f"💳 {title} — <b>{amount:,.0f} ₽</b>\n"
        f"🏷 Категория: {cat}"
        f"{date_line}"
        f"{time_line}"
    )


async def plan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with SessionLocal() as db:
        _ensure_user(db, update)
        if not context.args:
            await update.effective_message.reply_text(
                "Формат: /plan название сумма дата категория\n"
                "Примеры:\n"
                "  /plan маникюр 2100 15.04 красота\n"
                "  /plan стоматолог 8000 2030-04-22 здоровье\n"
                "  /plan маникюр 2100 завтра красота\n"
                "  /plan маникюр 2100 через 10 дней красота\n"
                "  /plan маникюр 2100 в следующий вторник красота\n"
                "  /plan маникюр 2100 1 мая красота"
            )
            return

        parsed = parse_plan_args(list(context.args))
        if isinstance(parsed, str):
            await update.effective_message.reply_text(parsed, reply_markup=done_keyboard())
            return

        from app.services.parser_service import ParserService
        parser = ParserService()
        category_slug = parser.category_lookup.get(parsed["category"], parsed["category"])

        service = TelegramBotService(db)
        response = service.process_plan_command(
            telegram_user_id=update.effective_user.id,
            title=parsed["title"],
            amount=parsed["amount"],
            category=category_slug,
            planned_date=parsed["planned_date"].isoformat(),
        )
    await update.effective_message.reply_text(response["message"], reply_markup=done_keyboard())


async def planned_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from datetime import date as date_cls
    with SessionLocal() as db:
        _ensure_user(db, update)
        service = TelegramBotService(db)
        response = service.process_planned_command(update.effective_user.id)
        items = service.planned_expense_service.list_all(update.effective_user.id)
    if not items:
        await update.effective_message.reply_text(response["message"], reply_markup=done_keyboard())
        return
    await update.effective_message.reply_text(response["message"])
    for item in items[:5]:
        marker = "⚠️ " if item.planned_date < date_cls.today().isoformat() else "📅 "
        await update.effective_message.reply_text(
            f"{marker}{item.planned_date} — {item.title} — {item.amount} ₽ — {formatter.category_label(item.category)}",
            reply_markup=planned_manage_keyboard(item.id),
        )


async def planned_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except BadRequest:
        pass

    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    planned_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    user_id = update.effective_user.id

    if not planned_id:
        await query.edit_message_text("Некорректный planned expense.", reply_markup=done_keyboard(back_target="nav:planned_list"))
        return

    if action == "edit_amount":
        if context.user_data is not None:
            context.user_data["awaiting_planned_amount"] = planned_id
        await query.edit_message_text("Введи новую сумму для учёта:", reply_markup=cancel_keyboard("nav:planned_list"))
        return

    if action == "edit_date":
        if context.user_data is not None:
            context.user_data["awaiting_planned_date"] = planned_id
        await query.edit_message_text("Введи новую дату: 15.04 или 2030-04-15", reply_markup=cancel_keyboard("nav:planned_list"))
        return

    with SessionLocal() as db:
        service = TelegramBotService(db)
        if action == "confirm":
            response = service.confirm_planned_expense(user_id, planned_id)
        elif action == "cancel":
            response = service.cancel_planned_expense(user_id, planned_id)
        else:
            response = {"action": "planned_missing", "message": "Неизвестное действие."}

    await query.edit_message_text(response["message"], reply_markup=done_keyboard())


async def planned_input_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handles planned_input:confirm and planned_input:cancel."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except BadRequest:
        pass

    action = query.data.split(":")[1]  # "confirm" or "cancel"
    user_id = update.effective_user.id

    if action == "cancel":
        if context.user_data:
            context.user_data.pop("pending_planned", None)
            context.user_data.pop("mode", None)
        try:
            await query.edit_message_text(
                "Отменено.",
                reply_markup=main_menu_inline_keyboard(),
            )
        except BadRequest:
            pass
        return

    # confirm
    pending = (context.user_data or {}).pop("pending_planned", None)
    if not pending:
        try:
            await query.edit_message_text(
                "❌ Данные устарели. Начни заново.",
                reply_markup=main_menu_inline_keyboard(),
            )
        except BadRequest:
            pass
        return

    from datetime import date as _date
    from app.services.planned_expense_service import PlannedExpenseService

    with SessionLocal() as db:
        svc = PlannedExpenseService(db)
        item = svc.create_manual(
            telegram_user_id=user_id,
            title=pending["title"],
            amount=float(pending["amount"]),
            category=pending["category"],
            planned_date=_date.fromisoformat(pending["planned_date"]),
        )

    from app.telegram.keyboards import planned_done_keyboard
    try:
        await query.edit_message_text(
            f"✅ Запланировано: {item.title} — {float(item.amount):,.0f} ₽ на {item.planned_date}",
            reply_markup=planned_done_keyboard(),
        )
    except BadRequest:
        pass


async def planned_freeform_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except BadRequest:
        pass

    action = query.data.split(":")[1]  # "save" or "cancel"

    if action == "cancel":
        if context.user_data:
            context.user_data.pop("pending_planned_freeform", None)
        try:
            await query.edit_message_text("Отменено.", reply_markup=main_menu_inline_keyboard())
        except BadRequest:
            pass
        return

    pending = (context.user_data or {}).pop("pending_planned_freeform", None)
    if not pending:
        try:
            await query.edit_message_text("❌ Данные устарели. Начни заново.", reply_markup=main_menu_inline_keyboard())
        except BadRequest:
            pass
        return

    from datetime import date as date_cls, timedelta
    from app.services.planned_expense_service import PlannedExpenseService

    raw_date = pending.get("planned_date") or ""
    try:
        planned_date = date_cls.fromisoformat(raw_date) if raw_date else date_cls.today() + timedelta(days=1)
    except ValueError:
        planned_date = date_cls.today() + timedelta(days=1)

    reminder_time = pending.get("reminder_time") or None

    with SessionLocal() as db:
        _ensure_user(db, update)
        svc = PlannedExpenseService(db)
        item = svc.create_manual(
            telegram_user_id=update.effective_user.id,
            title=pending.get("title") or "Платёж",
            amount=float(pending.get("amount") or 0),
            category=pending.get("category") or "other",
            planned_date=planned_date,
            reminder_time=reminder_time,
        )

    date_str = item.planned_date.isoformat() if hasattr(item.planned_date, "isoformat") else str(item.planned_date)
    time_str = f" в {reminder_time}" if reminder_time else ""
    from app.telegram.keyboards import planned_done_keyboard
    try:
        await query.edit_message_text(
            f"✅ Запланировано: {item.title} — {float(item.amount):,.0f} ₽\n📅 {date_str}{time_str}",
            reply_markup=planned_done_keyboard(),
        )
    except BadRequest:
        pass


async def _handle_planned_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
) -> None:
    """Process free-form text as a planned expense via LLM extraction."""
    from datetime import date as _date
    from app.services.category_service import CategoryService
    from app.services.llm_service import LLMService
    from app.telegram.keyboards import planned_confirm_keyboard

    user_id = update.effective_user.id

    with SessionLocal() as db:
        cat_svc = CategoryService(db)
        cat_svc.ensure_seeded(user_id)
        categories_grouped = cat_svc.list_categories(user_id)
        user_categories = [
            {"slug": c.slug, "name_ru": c.name_ru}
            for group in categories_grouped.values()
            for c in group
        ]
        llm = LLMService(db)
        result = llm.extract_planned(text, user_categories)

    if result is None:
        await update.effective_message.reply_text(
            "❌ Не смог разобрать. Попробуй ещё раз.",
            reply_markup=done_keyboard(),
        )
        return

    planned_date_iso = result.get("planned_date_iso")
    if not planned_date_iso:
        await update.effective_message.reply_text(
            "❌ Не понял дату. Укажи, например: «15 апреля» или «через 2 недели».",
            reply_markup=done_keyboard(),
        )
        return

    try:
        planned_date = _date.fromisoformat(planned_date_iso)
    except ValueError:
        await update.effective_message.reply_text(
            "❌ Не понял дату. Укажи, например: «15 апреля» или «через 2 недели».",
            reply_markup=done_keyboard(),
        )
        return

    if planned_date < _date.today():
        await update.effective_message.reply_text(
            "❌ Дата уже прошла. Укажи будущую дату.",
            reply_markup=done_keyboard(),
        )
        return

    # Validate category slug — fallback to "other"
    valid_slugs = {c["slug"] for c in user_categories}
    category_slug = result.get("category_slug") or "other"
    if category_slug not in valid_slugs:
        category_slug = "other"

    title = result.get("title") or ""
    amount = float(result.get("amount") or 0)

    # Clear mode only on success — errors keep mode so user can retry
    if context.user_data:
        context.user_data.pop("mode", None)

    if context.user_data is not None:
        context.user_data["pending_planned"] = {
            "title": title,
            "amount": amount,
            "category": category_slug,
            "planned_date": planned_date_iso,
        }

    cat_label = formatter.category_label(category_slug)
    msg = (
        "Запланировал:\n"
        f"🏷 {title}\n"
        f"💰 {amount:,.0f} ₽\n"
        f"📅 {planned_date_iso}\n"
        f"🗂 {cat_label}"
    )
    await update.effective_message.reply_text(msg, reply_markup=planned_confirm_keyboard())
