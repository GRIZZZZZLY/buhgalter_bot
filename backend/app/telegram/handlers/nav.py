import logging

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from app.db.session import SessionLocal
from app.services.nav_service import NavService
from app.telegram.formatter import TreasuryFormatter
from app.telegram.keyboards import done_keyboard, help_topic_keyboard, main_menu_inline_keyboard
from app.telegram.handlers.common import _ensure_user, _time_now
from app.telegram.handlers.advisor import _clear_advisor_state, _ADVISOR_ONBOARDING

logger = logging.getLogger("finance_bot.telegram")
formatter = TreasuryFormatter()

_HELP_TOPIC_TEXTS: dict = {}  # populated after formatter is available


def _get_help_topic_texts():
    return {
        "input":   lambda: formatter.format_help_topic_input(),
        "voice":   lambda: formatter.format_help_topic_voice(),
        "summary": lambda: formatter.format_help_topic_summary(),
        "budget":  lambda: formatter.format_help_topic_budget(),
        "advisor": lambda: formatter.format_help_topic_advisor(),
    }


async def _nav_send_or_edit(query, update: Update, screen) -> None:
    try:
        await query.edit_message_text(
            screen.text,
            reply_markup=screen.keyboard,
            parse_mode=screen.parse_mode,
        )
    except BadRequest as exc:
        logger.debug("nav edit failed (%s), sending new message", exc)
        await update.effective_chat.send_message(
            screen.text,
            reply_markup=screen.keyboard,
            parse_mode=screen.parse_mode,
        )


async def nav_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except BadRequest:
        pass

    data = query.data
    parts = data.split(":")
    section = parts[1] if len(parts) > 1 else ""
    sub     = parts[2] if len(parts) > 2 else ""
    extra   = parts[3] if len(parts) > 3 else ""
    user_id = update.effective_user.id

    # Clear any pending input states when navigating
    for key in list(context.user_data.keys()):
        if key.startswith("awaiting_"):
            del context.user_data[key]

    # Clear any pending input mode on navigation
    if context.user_data:
        context.user_data.pop("mode", None)
        context.user_data.pop("pending_planned", None)
        context.user_data.pop("pending_recurring", None)
        _clear_advisor_state(context)

    try:
        with SessionLocal() as db:
            nav = NavService(db)

            if section == "stats":
                period = sub if sub in ("today", "week", "month", "all") else "month"
                screen = nav.stats_screen(user_id, period)
            elif section == "ops":
                if sub in ("today", "week", "month", "all"):
                    screen = nav.operations_screen(user_id, sub)
                elif sub == "delete_mode":
                    period = extra if extra in ("today", "week", "month", "all") else "month"
                    screen = nav.operations_delete_screen(user_id, period)
                elif sub == "del" and extra:
                    uuid_str = extra
                    period_after = parts[4] if len(parts) > 4 else "month"
                    from uuid import UUID
                    from app.services.transaction_service import TransactionService
                    tx_svc = TransactionService(db)
                    tx_svc.delete_transaction(user_id, UUID(uuid_str))
                    screen = nav.operations_screen(user_id, period_after)
                else:
                    screen = nav.operations_screen(user_id, "month")
            elif section == "planned_list":
                screen = nav.planned_screen(user_id)
            elif section == "recurring_list":
                screen = nav.recurring_screen(user_id)
            elif section == "planned_input":
                context.user_data["mode"] = "planned_input"
                from app.telegram.keyboards import planned_input_keyboard
                try:
                    await query.edit_message_text(
                        "Опиши запланированный расход — название, сумму и дату.\n"
                        "Например: «маникюр 2100 рублей 15 апреля»",
                        reply_markup=planned_input_keyboard(),
                    )
                except BadRequest:
                    pass
                return
            elif section == "recurring_input":
                context.user_data["mode"] = "recurring_input"
                from app.telegram.keyboards import recurring_input_keyboard
                try:
                    await query.edit_message_text(
                        "Опиши регулярный платёж — название, сумму и периодичность.\n"
                        "Например: «аренда 30000 каждый месяц 1 числа»\n"
                        "          «зарплата 120000 каждый месяц 10 числа»",
                        reply_markup=recurring_input_keyboard(),
                    )
                except BadRequest:
                    pass
                return
            elif section == "goals":
                from app.services.savings_goal_service import SavingsGoalService
                from app.telegram.keyboards import goals_list_keyboard
                from app.telegram.handlers.savings import _goals_list_text
                goals = SavingsGoalService(db).list_active(user_id)
                text = _goals_list_text(goals)
                try:
                    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=goals_list_keyboard())
                except BadRequest:
                    await update.effective_chat.send_message(text, parse_mode="Markdown", reply_markup=goals_list_keyboard())
                return
            elif section == "budgets":
                screen = nav.budgets_screen(user_id)
            elif section == "settings":
                screen = nav.settings_screen(user_id)
            elif section == "categories":
                if sub in ("expense", "income"):
                    page = int(extra) if extra.isdigit() else 0
                    screen = nav.categories_list_screen(user_id, sub, page)
                else:
                    screen = nav.categories_screen(user_id)
            elif section == "advisor":
                context.user_data["mode"] = "advisor"
                context.user_data["advisor_history"] = []
                context.user_data["advisor_last_active"] = _time_now()
                from app.telegram.keyboards import advisor_onboarding_keyboard
                try:
                    await query.edit_message_text(
                        _ADVISOR_ONBOARDING,
                        reply_markup=advisor_onboarding_keyboard(),
                        parse_mode="Markdown",
                    )
                except BadRequest:
                    await update.effective_chat.send_message(
                        _ADVISOR_ONBOARDING,
                        reply_markup=advisor_onboarding_keyboard(),
                        parse_mode="Markdown",
                    )
                return
            elif section == "help":
                screen = nav.help_screen()
            elif section == "menu":
                try:
                    await query.edit_message_text(
                        formatter.format_main_menu_screen(),
                        reply_markup=main_menu_inline_keyboard(),
                    )
                except BadRequest:
                    await update.effective_chat.send_message(
                        formatter.format_main_menu_screen(),
                        reply_markup=main_menu_inline_keyboard(),
                    )
                return
            else:
                logger.warning("unknown nav section: %s", section)
                return

        await _nav_send_or_edit(query, update, screen)
    except Exception as exc:
        logger.exception("nav_callback error section=%s: %s", section, exc)
        await update.effective_chat.send_message("❌ Ошибка при открытии раздела. Попробуй ещё раз.", reply_markup=done_keyboard())


async def help_topic_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except BadRequest:
        pass

    topic = query.data.split(":")[2] if len(query.data.split(":")) > 2 else ""
    text_fn = _get_help_topic_texts().get(topic)
    if text_fn is None:
        return

    try:
        await query.edit_message_text(text_fn(), reply_markup=help_topic_keyboard(), parse_mode="Markdown")
    except BadRequest as exc:
        logger.debug("help topic edit failed (%s), sending new message", exc)
        await update.effective_chat.send_message(text_fn(), reply_markup=help_topic_keyboard(), parse_mode="Markdown")
