import asyncio
import time as _time
import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.db.session import SessionLocal
from app.repositories.user_repository import UserRepository
from app.telegram.keyboards import saved_actions_keyboard, undo_inline_keyboard

logger = logging.getLogger("finance_bot.telegram")

# Undo window — 60 seconds
UNDO_WINDOW_SECONDS = 60
# Voice confirmation buttons timeout — 5 minutes
VOICE_CONFIRM_TIMEOUT = 300


def _time_now() -> float:
    return _time.time()


def _ensure_user(db, update: Update) -> None:
    tg_user = update.effective_user
    if tg_user is None:
        return
    user_repo = UserRepository(db)
    display_name = tg_user.full_name or tg_user.username
    user = user_repo.get_or_create(tg_user.id, display_name)

    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    try:
        tz = ZoneInfo(user.timezone)
    except Exception:
        tz = ZoneInfo("Europe/Moscow")
    today_str = datetime.now(tz).date().isoformat()
    user_repo.update_streak(user, today_str)

    if user.ignored_evening_reminders > 0:
        user_repo.reset_ignored_evening_reminders(user)

    db.commit()


async def _auto_remove_keyboard(bot, chat_id: int, message_id: int, delay: float = UNDO_WINDOW_SECONDS) -> None:
    await asyncio.sleep(delay)
    try:
        await bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=None,
        )
    except Exception:
        pass


async def _send_saved_with_undo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    transaction_ids: list[str],
    correction_tx_id: str | None = None,
) -> None:
    if correction_tx_id is not None:
        keyboard = saved_actions_keyboard(correction_tx_id)
    else:
        keyboard = undo_inline_keyboard(transaction_ids)
    msg = await update.effective_message.reply_text(
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    asyncio.create_task(
        _auto_remove_keyboard(context.bot, msg.chat_id, msg.message_id)
    )
