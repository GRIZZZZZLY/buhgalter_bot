import logging

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from app.db.session import SessionLocal
from app.repositories.category_budget_repository import CategoryBudgetRepository
from app.repositories.user_repository import UserRepository
from app.services.analytics_service import AnalyticsService
from app.services.nav_service import NavService
from app.telegram.formatter import TreasuryFormatter
from app.telegram.keyboards import done_keyboard
from app.telegram.handlers.common import _ensure_user

logger = logging.getLogger("finance_bot.telegram")
formatter = TreasuryFormatter()


async def budget_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with SessionLocal() as db:
        _ensure_user(db, update)
        user_repo = UserRepository(db)
        user = user_repo.get_by_telegram_id(update.effective_user.id)

        if user is None:
            await update.effective_message.reply_text("❌ Не нашёл пользователя.", reply_markup=done_keyboard())
            return

        if not context.args or len(context.args) == 0:
            analytics = AnalyticsService(db)
            report = analytics.build_budget_report(user)
            await update.effective_message.reply_text(report, reply_markup=done_keyboard(back_target="nav:budgets"))
            return

        if len(context.args) < 2:
            await update.effective_message.reply_text(
                "Формат: /budget категория сумма\n"
                "Примеры:\n"
                "  /budget еда 15000\n"
                "  /budget транспорт 5000\n"
                "  /budget еда 0  (удалить бюджет)\n"
                "  /budget  (показать все бюджеты)",
                reply_markup=done_keyboard(back_target="nav:budgets"),
            )
            return

        from app.services.parser_service import ParserService
        parser = ParserService()
        category_text = " ".join(context.args[:-1]).lower().strip()
        amount_text = context.args[-1]
        resolved_category = parser.category_lookup.get(category_text, category_text)

        try:
            amount = float(amount_text.replace(",", ".").replace(" ", ""))
        except ValueError:
            await update.effective_message.reply_text(f"❌ Не понял сумму: {amount_text}. Введи число.", reply_markup=done_keyboard(back_target="nav:budgets"))
            return

        budget_repo = CategoryBudgetRepository(db)
        cat_label = formatter.category_label(resolved_category)

        if amount <= 0:
            removed = budget_repo.remove(user.telegram_user_id, resolved_category)
            db.commit()
            if removed:
                await update.effective_message.reply_text(f"✅ Бюджет «{cat_label}» удалён.", reply_markup=done_keyboard(back_target="nav:budgets"))
            else:
                await update.effective_message.reply_text(f"Бюджет «{cat_label}» не был установлен.", reply_markup=done_keyboard(back_target="nav:budgets"))
            return

        budget_repo.upsert(user.telegram_user_id, resolved_category, amount)
        db.commit()
        await update.effective_message.reply_text(f"✅ Бюджет «{cat_label}»: {amount:,.0f} ₽/мес", reply_markup=done_keyboard(back_target="nav:budgets"))


def _get_budget_alert(db, telegram_user_id: int, category: str) -> str | None:
    """Return budget alert text or None (no longer sends a separate message)."""
    analytics = AnalyticsService(db)
    return analytics.check_budget_alert(telegram_user_id, category)


async def _handle_budget_total_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
) -> None:
    """Parse total monthly budget from free-form text or STT transcript."""
    from app.services.parser_service import ParserService
    from app.telegram.keyboards import budget_confirm_keyboard

    amount = ParserService._extract_amount(text)
    if context.user_data:
        context.user_data.pop("mode", None)

    if amount is None or amount <= 0:
        await update.effective_message.reply_text(
            "❌ Не смог распознать сумму. Попробуй ещё раз.",
            reply_markup=done_keyboard(back_target="nav:budgets"),
        )
        return

    if context.user_data is not None:
        context.user_data["pending_budget_total"] = float(amount)

    msg = f"Установить общий бюджет на месяц: {float(amount):,.0f} ₽?"
    await update.effective_message.reply_text(msg, reply_markup=budget_confirm_keyboard())


async def _handle_budget_category_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
) -> None:
    """Parse category budget limit from free-form text or STT transcript."""
    from app.services.parser_service import ParserService
    from app.telegram.keyboards import budget_cat_confirm_keyboard

    amount = ParserService._extract_amount(text)
    slug = (context.user_data or {}).get("pending_budget_slug", "")
    if context.user_data:
        context.user_data.pop("mode", None)

    if amount is None or amount < 0:
        await update.effective_message.reply_text(
            "❌ Не смог распознать сумму. Попробуй ещё раз.",
            reply_markup=done_keyboard(back_target="nav:budgets"),
        )
        return

    if context.user_data is not None:
        context.user_data["pending_budget_cat_amount"] = float(amount)

    cat_label = formatter.category_label(slug)
    if float(amount) == 0:
        msg = f"Удалить бюджет для «{cat_label}»?"
    else:
        msg = f"Установить бюджет «{cat_label}»: {float(amount):,.0f} ₽/мес?"
    await update.effective_message.reply_text(msg, reply_markup=budget_cat_confirm_keyboard())


async def budget_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from telegram.error import BadRequest
    from app.telegram.keyboards import (
        budget_category_keyboard,
        budget_total_input_keyboard,
        budget_cat_input_keyboard,
        budgets_inline_keyboard,
    )
    from app.services.category_service import CategoryService
    from app.repositories.category_budget_repository import CategoryBudgetRepository

    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    data = query.data  # e.g. "budget:set_total"
    action = data[len("budget:"):]

    if action == "set_total":
        if context.user_data is not None:
            context.user_data["mode"] = "budget_total_input"
        try:
            await query.edit_message_text(
                "💰 Введи общий бюджет на месяц.\n"
                "Можно текстом или голосом: «пятьдесят тысяч», «50000».",
                reply_markup=budget_total_input_keyboard(),
            )
        except BadRequest:
            pass
        return

    if action == "pick_category":
        with SessionLocal() as db:
            cat_svc = CategoryService(db)
            cat_svc.ensure_seeded(user_id)
            groups = cat_svc.list_categories(user_id)
        cats = [(c.slug, f"{c.emoji} {c.name_ru}") for c in groups.get("expense", [])]
        try:
            await query.edit_message_text(
                "🗂 Выбери категорию для установки лимита:",
                reply_markup=budget_category_keyboard(cats),
            )
        except BadRequest:
            pass
        return

    if action.startswith("set_category:"):
        slug = action[len("set_category:"):]
        if context.user_data is not None:
            context.user_data["mode"] = "budget_category_input"
            context.user_data["pending_budget_slug"] = slug
        cat_label = formatter.category_label(slug)
        try:
            await query.edit_message_text(
                f"💰 Введи лимит для «{cat_label}».\n"
                "Можно текстом или голосом. Отправь «0» чтобы удалить лимит.",
                reply_markup=budget_cat_input_keyboard(),
            )
        except BadRequest:
            pass
        return

    if action == "total_confirm":
        amount = (context.user_data or {}).get("pending_budget_total")
        if context.user_data:
            context.user_data.pop("pending_budget_total", None)
        with SessionLocal() as db:
            _ensure_user(db, update)
            user_repo = UserRepository(db)
            user = user_repo.get_by_telegram_id(user_id)
            user_repo.update_settings(user, budget_amount=amount if amount else None)
            user_repo.commit()
            nav = NavService(db)
            screen = nav.budgets_screen(user_id)
        msg = f"✅ Бюджет установлен: {amount:,.0f} ₽/мес\n\n" + screen.text if amount else "✅ Бюджет убран.\n\n" + screen.text
        try:
            await query.edit_message_text(msg, reply_markup=budgets_inline_keyboard(), parse_mode=screen.parse_mode)
        except BadRequest:
            await update.effective_chat.send_message(msg, reply_markup=budgets_inline_keyboard(), parse_mode=screen.parse_mode)
        return

    if action == "total_cancel":
        if context.user_data:
            context.user_data.pop("mode", None)
            context.user_data.pop("pending_budget_total", None)
        with SessionLocal() as db:
            nav = NavService(db)
            screen = nav.budgets_screen(user_id)
        try:
            await query.edit_message_text(screen.text, reply_markup=budgets_inline_keyboard(), parse_mode=screen.parse_mode)
        except BadRequest:
            pass
        return

    if action == "cat_confirm":
        slug = (context.user_data or {}).get("pending_budget_slug", "")
        amount = (context.user_data or {}).get("pending_budget_cat_amount", 0.0)
        if context.user_data:
            context.user_data.pop("pending_budget_slug", None)
            context.user_data.pop("pending_budget_cat_amount", None)
        cat_label = formatter.category_label(slug)
        with SessionLocal() as db:
            _ensure_user(db, update)
            budget_repo = CategoryBudgetRepository(db)
            if amount <= 0:
                budget_repo.remove(user_id, slug)
                db.commit()
                status = f"✅ Бюджет «{cat_label}» удалён."
            else:
                budget_repo.upsert(user_id, slug, amount)
                db.commit()
                status = f"✅ Бюджет «{cat_label}»: {amount:,.0f} ₽/мес"
            nav = NavService(db)
            screen = nav.budgets_screen(user_id)
        msg = status + "\n\n" + screen.text
        try:
            await query.edit_message_text(msg, reply_markup=budgets_inline_keyboard(), parse_mode=screen.parse_mode)
        except BadRequest:
            await update.effective_chat.send_message(msg, reply_markup=budgets_inline_keyboard(), parse_mode=screen.parse_mode)
        return

    if action == "cat_cancel":
        if context.user_data:
            context.user_data.pop("mode", None)
            context.user_data.pop("pending_budget_slug", None)
            context.user_data.pop("pending_budget_cat_amount", None)
        with SessionLocal() as db:
            nav = NavService(db)
            screen = nav.budgets_screen(user_id)
        try:
            await query.edit_message_text(screen.text, reply_markup=budgets_inline_keyboard(), parse_mode=screen.parse_mode)
        except BadRequest:
            pass
        return
