import logging

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from app.core.settings import get_settings
from app.db.session import SessionLocal
from app.repositories.user_repository import UserRepository
from app.telegram.bot_service import TelegramBotService
from app.telegram.formatter import TreasuryFormatter
from app.telegram.handlers_legacy import START_MESSAGE
from app.telegram.keyboards import (
    done_keyboard,
    main_menu_inline_keyboard,
    onboarding_step2_keyboard,
    onboarding_step3_keyboard,
    start_keyboard,
)
from app.telegram.onboarding import OnboardingFlow, ONBOARDING_STEP_KEY
from app.telegram.handlers.common import _ensure_user

logger = logging.getLogger("finance_bot.telegram")
formatter = TreasuryFormatter()
_onboarding = OnboardingFlow()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with SessionLocal() as db:
        _ensure_user(db, update)

    # Start onboarding for new users (step key not yet set)
    if context.user_data is not None and context.user_data.get(ONBOARDING_STEP_KEY) is None:
        text, parse_mode = _onboarding.start(context.user_data)
        await update.effective_message.reply_text(
            text, parse_mode=parse_mode, reply_markup=main_menu_inline_keyboard()
        )
        return

    settings = get_settings()
    webapp_kb = start_keyboard(settings.telegram_webhook_url or None)

    # Single message: greeting + menu inline buttons
    await update.effective_message.reply_text(
        START_MESSAGE,
        reply_markup=webapp_kb or main_menu_inline_keyboard(),
        parse_mode="HTML",
    )
    # If WebApp button exists, also show the nav menu
    if webapp_kb:
        await update.effective_message.reply_text(
            formatter.format_main_menu_screen(),
            reply_markup=main_menu_inline_keyboard(),
        )


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with SessionLocal() as db:
        _ensure_user(db, update)
    await update.effective_message.reply_text(
        formatter.format_main_menu_screen(),
        reply_markup=main_menu_inline_keyboard(),
    )


async def onboarding_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except Exception:
        pass

    if query.data == "onboarding:skip_budget":
        if context.user_data is None:
            await query.edit_message_text("❌ Сессия устарела.", reply_markup=done_keyboard())
            return
        ob_text, ob_parse, _ = _onboarding.on_budget_or_skip(context.user_data)
        if ob_text:
            await query.edit_message_text(
                ob_text, parse_mode=ob_parse, reply_markup=onboarding_step3_keyboard()
            )


async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    period = "month"
    if context.args:
        candidate = context.args[0].strip().lower()
        if candidate in {"today", "week", "month", "all"}:
            period = candidate

    with SessionLocal() as db:
        _ensure_user(db, update)
        service = TelegramBotService(db)
        response = service.process_summary_command(update.effective_user.id, period=period)
    await update.effective_message.reply_text(response["message"], reply_markup=done_keyboard())
