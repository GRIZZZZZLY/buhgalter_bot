import logging

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from app.db.session import SessionLocal
from app.services.recurring_service import RecurringService, parse_recurring_args, parse_recurring_schedule_args
from app.telegram.bot_service import TelegramBotService
from app.telegram.formatter import TreasuryFormatter
from app.telegram.keyboards import (
    cancel_keyboard,
    done_keyboard,
    main_menu_inline_keyboard,
    recurring_category_keyboard,
    recurring_freeform_keyboard,
    recurring_manage_keyboard,
)
from app.telegram.handlers.common import _ensure_user

logger = logging.getLogger("finance_bot.telegram")
formatter = TreasuryFormatter()


def _format_recurring_schedule(rt) -> str:
    """Format schedule label for a RecurringTransaction object."""
    _weekday_labels = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
    if rt.frequency == "daily":
        return "каждый день"
    if rt.frequency == "interval_days":
        return f"каждые {rt.day_value} дн."
    if rt.frequency == "weekly":
        label = _weekday_labels[rt.day_value] if 0 <= rt.day_value <= 6 else "?"
        return f"каждую неделю ({label})"
    return f"каждый месяц, {rt.day_value}-го"


def _format_recurring_confirm_msg(item: dict) -> str:
    """Format confirmation message for a free-form recurring transaction."""
    amount = float(item.get("amount") or 0)
    title = item.get("title") or "Платёж"
    tx_type = item.get("transaction_type", "expense")
    cat = formatter.category_label(item.get("category") or "other")
    _weekday_labels = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
    freq = item.get("frequency", "monthly")
    day_value = int(item.get("day_value") or 1)
    if freq == "daily":
        schedule = "каждый день"
    elif freq == "interval_days":
        schedule = f"каждые {day_value} дн."
    elif freq == "weekly":
        wd = _weekday_labels[day_value] if 0 <= day_value <= 6 else "?"
        schedule = f"каждую неделю ({wd})"
    else:
        schedule = f"каждый месяц, {day_value}-го"
    type_label = "доход" if tx_type == "income" else "расход"
    return (
        f"🔄 <b>Добавить регулярный платёж?</b>\n"
        f"💳 {title} — <b>{amount:,.0f} ₽</b> ({type_label})\n"
        f"🏷 Категория: {cat}\n"
        f"📆 Расписание: {schedule}"
    )


async def recurring_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with SessionLocal() as db:
        _ensure_user(db, update)
        svc = RecurringService(db)

        if not context.args:
            items = svc.list_active(update.effective_user.id)
            if not items:
                await update.effective_message.reply_text(svc.format_list(items), reply_markup=done_keyboard())
                return
            await update.effective_message.reply_text("📋 Правила регулярных операций:")
            for rt in items[:5]:
                await update.effective_message.reply_text(
                    formatter.format_recurring_rule(
                        rt.title,
                        f"{float(rt.amount):,.0f}",
                        rt.category,
                        svc._format_schedule(rt),
                        rt.next_run_date,
                    ),
                    reply_markup=recurring_manage_keyboard(rt.id),
                )
            return

        parsed = parse_recurring_args(list(context.args))
        if isinstance(parsed, str):
            await update.effective_message.reply_text(parsed, reply_markup=done_keyboard())
            return

        from app.services.parser_service import ParserService
        parser = ParserService()
        category_slug = parser.category_lookup.get(parsed["category"], parsed["category"])

        rt = svc.create(
            telegram_user_id=update.effective_user.id,
            title=parsed["title"],
            amount=parsed["amount"],
            transaction_type=parsed["transaction_type"],
            category=category_slug,
            frequency=parsed["frequency"],
            day_value=parsed["day_value"],
        )
        await update.effective_message.reply_text(svc.format_created(rt), reply_markup=done_keyboard())


async def recurring_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except BadRequest:
        pass

    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    recurring_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    extra = parts[3] if len(parts) > 3 else ""

    if not recurring_id:
        await query.edit_message_text("Некорректное правило recurring.", reply_markup=done_keyboard(back_target="nav:recurring_list"))
        return

    if action == "amount":
        if context.user_data is not None:
            context.user_data["awaiting_recurring_amount"] = recurring_id
        await query.edit_message_text("Введи новую сумму для правила:", reply_markup=cancel_keyboard("nav:recurring_list"))
        return

    if action == "schedule":
        if context.user_data is not None:
            context.user_data["awaiting_recurring_schedule"] = recurring_id
        await query.edit_message_text("Введи новый период: ежемесячно 10 / еженедельно 4 / каждые 30", reply_markup=cancel_keyboard("nav:recurring_list"))
        return

    if action == "category":
        categories = [
            "food", "transport", "housing", "health", "beauty", "entertainment",
            "subscriptions", "shopping", "home", "telecom", "work", "education",
            "gifts", "fees", "salary", "freelance", "bonus", "transfer", "refund",
            "other_income", "other",
        ]
        await query.edit_message_text("Выбери категорию:", reply_markup=recurring_category_keyboard(recurring_id, categories))
        return

    with SessionLocal() as db:
        service = TelegramBotService(db)
        if action == "disable":
            response = service.deactivate_recurring(update.effective_user.id, recurring_id)
        elif action == "set_category" and extra:
            response = service.update_recurring_category(update.effective_user.id, recurring_id, extra)
        elif action == "cancel":
            response = {"action": "recurring_cancelled", "message": "Отмена."}
        else:
            response = {"action": "recurring_missing", "message": "Неизвестное действие."}

    await query.edit_message_text(response["message"], reply_markup=done_keyboard())


async def recurring_del_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.effective_message.reply_text("Формат: /recurring_del <номер>\nСписок: /recurring", reply_markup=done_keyboard())
        return

    try:
        rt_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text(f"❌ Номер должен быть числом, получил: {context.args[0]}", reply_markup=done_keyboard())
        return

    with SessionLocal() as db:
        svc = RecurringService(db)
        ok = svc.deactivate(update.effective_user.id, rt_id)

    if ok:
        await update.effective_message.reply_text(f"✅ Повторяющаяся транзакция #{rt_id} удалена.", reply_markup=done_keyboard())
    else:
        await update.effective_message.reply_text(f"❌ Транзакция #{rt_id} не найдена.", reply_markup=done_keyboard())


async def recurring_input_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handles recurring_input:confirm and recurring_input:cancel."""
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
            context.user_data.pop("pending_recurring", None)
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
    pending = (context.user_data or {}).pop("pending_recurring", None)
    if not pending:
        try:
            await query.edit_message_text(
                "❌ Данные устарели. Начни заново.",
                reply_markup=main_menu_inline_keyboard(),
            )
        except BadRequest:
            pass
        return

    from app.services.recurring_service import RecurringService

    with SessionLocal() as db:
        svc = RecurringService(db)
        rt = svc.create(
            telegram_user_id=user_id,
            title=pending["title"],
            amount=float(pending["amount"]),
            transaction_type=pending["transaction_type"],
            category=pending["category"],
            frequency=pending["frequency"],
            day_value=int(pending["day_value"]),
        )

    sign = "+" if rt.transaction_type == "income" else "−"
    freq_label = _format_recurring_schedule(rt)
    from app.telegram.keyboards import recurring_done_keyboard
    try:
        await query.edit_message_text(
            f"✅ Добавлено: {rt.title} {sign}{float(rt.amount):,.0f} ₽ — {freq_label}",
            reply_markup=recurring_done_keyboard(),
        )
    except BadRequest:
        pass


async def recurring_freeform_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
            context.user_data.pop("pending_recurring_freeform", None)
        try:
            await query.edit_message_text("Отменено.", reply_markup=main_menu_inline_keyboard())
        except BadRequest:
            pass
        return

    pending = (context.user_data or {}).pop("pending_recurring_freeform", None)
    if not pending:
        try:
            await query.edit_message_text("❌ Данные устарели. Начни заново.", reply_markup=main_menu_inline_keyboard())
        except BadRequest:
            pass
        return

    from app.services.recurring_service import RecurringService

    with SessionLocal() as db:
        _ensure_user(db, update)
        svc = RecurringService(db)
        rt = svc.create(
            telegram_user_id=update.effective_user.id,
            title=pending.get("title") or "Платёж",
            amount=float(pending.get("amount") or 0),
            transaction_type=pending.get("transaction_type") or "expense",
            category=pending.get("category") or "other",
            frequency=pending.get("frequency") or "monthly",
            day_value=int(pending.get("day_value") or 1),
            reminder_time=pending.get("reminder_time") or None,
        )

    sign = "+" if rt.transaction_type == "income" else "−"
    freq_label = _format_recurring_schedule(rt)
    from app.telegram.keyboards import recurring_done_keyboard
    try:
        await query.edit_message_text(
            f"✅ Добавлено: {rt.title} {sign}{float(rt.amount):,.0f} ₽ — {freq_label}",
            reply_markup=recurring_done_keyboard(),
        )
    except BadRequest:
        pass


async def _handle_recurring_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
) -> None:
    """Process free-form text as a recurring transaction via LLM extraction."""
    from app.services.category_service import CategoryService
    from app.services.llm_service import LLMService
    from app.telegram.keyboards import recurring_confirm_keyboard

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
        result = llm.extract_recurring(text, user_categories)

    if result is None:
        await update.effective_message.reply_text(
            "❌ Не смог разобрать. Попробуй ещё раз.",
            reply_markup=done_keyboard(),
        )
        return

    required_keys = ("title", "amount", "transaction_type", "category_slug", "frequency", "day_value")
    missing = [k for k in required_keys if result.get(k) is None]
    if missing:
        await update.effective_message.reply_text(
            f"❌ Не понял: {', '.join(missing)}. Попробуй ещё раз.",
            reply_markup=done_keyboard(),
        )
        return

    # Validate category slug — fallback to "other"
    valid_slugs = {c["slug"] for c in user_categories}
    category_slug = result.get("category_slug") or "other"
    if category_slug not in valid_slugs:
        category_slug = "other"

    tx_type = result.get("transaction_type", "expense")
    if tx_type not in ("income", "expense"):
        tx_type = "expense"

    title = result.get("title") or ""
    amount = float(result.get("amount") or 0)
    frequency = result.get("frequency", "monthly")
    day_value = int(result.get("day_value") or 1)

    # Clear mode only on success — errors keep mode so user can retry
    if context.user_data:
        context.user_data.pop("mode", None)

    if context.user_data is not None:
        context.user_data["pending_recurring"] = {
            "title": title,
            "amount": amount,
            "transaction_type": tx_type,
            "category": category_slug,
            "frequency": frequency,
            "day_value": day_value,
        }

    sign = "+" if tx_type == "income" else "−"
    cat_label = formatter.category_label(category_slug)
    _weekday_labels = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
    if frequency == "daily":
        freq_label = "каждый день"
    elif frequency == "interval_days":
        freq_label = f"каждые {day_value} дн."
    elif frequency == "weekly":
        wl = _weekday_labels[day_value] if 0 <= day_value <= 6 else "?"
        freq_label = f"каждую неделю ({wl})"
    else:
        freq_label = f"каждый месяц, {day_value}-го"

    msg = (
        "Регулярный платёж:\n"
        f"🏷 {title}\n"
        f"💰 {sign}{amount:,.0f} ₽\n"
        f"📅 {freq_label.capitalize()}\n"
        f"🗂 {cat_label}"
    )
    await update.effective_message.reply_text(msg, reply_markup=recurring_confirm_keyboard())
