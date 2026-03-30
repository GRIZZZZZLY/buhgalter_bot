import asyncio
import logging
import os
import tempfile
from pathlib import Path

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from app.db.session import SessionLocal
from app.repositories.user_repository import UserRepository
from app.telegram.bot_service import TelegramBotService
from app.telegram.handlers.common import (
    VOICE_CONFIRM_TIMEOUT,
    _auto_remove_keyboard,
    _ensure_user,
)
from app.telegram.handlers.budget import _handle_budget_category_input, _handle_budget_total_input
from app.telegram.handlers.advisor import _handle_advisor_text
from app.telegram.handlers.planned import _format_planned_confirm_msg, _handle_planned_input
from app.telegram.handlers.recurring import _format_recurring_confirm_msg, _handle_recurring_input
from app.telegram.keyboards import (
    category_resolution_keyboard,
    done_keyboard,
    planned_freeform_keyboard,
    recurring_freeform_keyboard,
    saved_actions_keyboard,
    undo_inline_keyboard,
    voice_confirmation_keyboard,
)
from app.schemas.telegram import TelegramVoicePayload

logger = logging.getLogger("finance_bot.telegram")


async def voice_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    voice = update.effective_message.voice
    if voice is None:
        await update.effective_message.reply_text("Не нашёл voice payload.", reply_markup=done_keyboard())
        return

    placeholder = await update.effective_message.reply_text("🎤 Обрабатываю голосовое…")

    logger.info("voice message received: user=%s file_id=%s", update.effective_user.id, voice.file_id)
    telegram_file = await context.bot.get_file(voice.file_id)
    fd, temp_path = tempfile.mkstemp(prefix="finance-bot-voice-", suffix=".ogg")
    os.close(fd)
    Path(temp_path).unlink(missing_ok=True)
    await telegram_file.download_to_drive(custom_path=temp_path)

    # Handle input modes via STT
    mode = context.user_data.get("mode") if context.user_data else None
    if mode in ("planned_input", "recurring_input", "budget_total_input", "budget_category_input", "advisor"):
        try:
            from app.services.audio_file_service import AudioFileService
            from app.services.stt_service import STTService
            audio_svc = AudioFileService()
            wav_path = audio_svc.prepare_wav_from_ogg(temp_path)
            stt = STTService()
            stt_result = stt.transcribe(wav_path)
            transcribed = stt_result.text or ""
            if transcribed:
                if mode == "planned_input":
                    await _handle_planned_input(update, context, transcribed)
                elif mode == "recurring_input":
                    await _handle_recurring_input(update, context, transcribed)
                elif mode == "budget_total_input":
                    await _handle_budget_total_input(update, context, transcribed)
                elif mode == "advisor":
                    await _handle_advisor_text(update, context, transcribed)
                else:
                    await _handle_budget_category_input(update, context, transcribed)
            else:
                await update.effective_message.reply_text(
                    "❌ Не удалось распознать речь. Попробуй ещё раз.",
                    reply_markup=done_keyboard(),
                )
        except Exception as exc:
            logger.error("voice mode input error: %s", exc)
            await update.effective_message.reply_text(
                "❌ Не смог обработать голосовое. Попробуй ещё раз.",
                reply_markup=done_keyboard(),
            )
        finally:
            from pathlib import Path as _Path
            _Path(temp_path).unlink(missing_ok=True)
            try:
                await placeholder.delete()
            except Exception:
                pass
        return

    try:
        with SessionLocal() as db:
            _ensure_user(db, update)
            service = TelegramBotService(db)
            response, debug = service.process_voice_message(
                TelegramVoicePayload(
                    telegram_user_id=update.effective_user.id,
                    telegram_message_id=update.effective_message.message_id,
                    file_id=voice.file_id,
                    original_file_path=temp_path,
                )
            )

            if response.get("action") == "saved":
                user_repo = UserRepository(db)
                user = user_repo.get_by_telegram_id(update.effective_user.id)
                if user:
                    from datetime import datetime, timezone as tz_mod
                    from zoneinfo import ZoneInfo
                    try:
                        tz = ZoneInfo(user.timezone)
                    except Exception:
                        tz = ZoneInfo("Europe/Moscow")
                    today_str = datetime.now(tz).date().isoformat()
                    user_repo.increment_transactions_today(user, today_str)
                    db.commit()
    finally:
        try:
            Path(temp_path).unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("failed to delete downloaded voice file %s: %s", temp_path, exc)

    logger.info("voice processed: action=%s debug=%s", response.get("action"), debug)

    action = response.get("action", "")

    if action == "confirm_voice" and response.get("voice_log_id"):
        try:
            await placeholder.edit_text(
                response["message"],
                reply_markup=voice_confirmation_keyboard(response["voice_log_id"]),
                parse_mode="HTML",
            )
        except BadRequest:
            placeholder = await update.effective_message.reply_text(
                response["message"],
                reply_markup=voice_confirmation_keyboard(response["voice_log_id"]),
                parse_mode="HTML",
            )
        asyncio.create_task(_auto_remove_keyboard(context.bot, placeholder.chat_id, placeholder.message_id, VOICE_CONFIRM_TIMEOUT))
        return

    if action == "planned_confirm":
        items = response.get("parsed_items") or []
        if items:
            item = items[0]
            context.user_data["pending_planned_freeform"] = item
            try:
                await placeholder.edit_text(
                    _format_planned_confirm_msg(item),
                    reply_markup=planned_freeform_keyboard(),
                    parse_mode="HTML",
                )
            except BadRequest:
                await update.effective_message.reply_text(
                    _format_planned_confirm_msg(item),
                    reply_markup=planned_freeform_keyboard(),
                    parse_mode="HTML",
                )
        return

    if action == "recurring_confirm":
        items = response.get("parsed_items") or []
        if items:
            item = items[0]
            context.user_data["pending_recurring_freeform"] = item
            try:
                await placeholder.edit_text(
                    _format_recurring_confirm_msg(item),
                    reply_markup=recurring_freeform_keyboard(),
                    parse_mode="HTML",
                )
            except BadRequest:
                await update.effective_message.reply_text(
                    _format_recurring_confirm_msg(item),
                    reply_markup=recurring_freeform_keyboard(),
                    parse_mode="HTML",
                )
        return

    if action == "clarify_category_choice":
        try:
            await placeholder.edit_text(
                response["message"],
                reply_markup=category_resolution_keyboard(
                    str(response.get("raw_category", "")),
                    list(response.get("suggestions", [])),
                ),
            )
        except BadRequest:
            await update.effective_message.reply_text(
                response["message"],
                reply_markup=category_resolution_keyboard(
                    str(response.get("raw_category", "")),
                    list(response.get("suggestions", [])),
                ),
            )
        return

    try:
        await placeholder.edit_text(response["message"], parse_mode="HTML", reply_markup=done_keyboard())
    except BadRequest:
        await update.effective_message.reply_text(response["message"], parse_mode="HTML", reply_markup=done_keyboard())


async def voice_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except BadRequest:
        logger.warning("callback query answer failed: data=%s", query.data)

    try:
        _, action, voice_log_id = query.data.split(":", 2)
    except ValueError:
        await query.edit_message_text("Некорректный callback payload.", reply_markup=done_keyboard())
        return

    with SessionLocal() as db:
        service = TelegramBotService(db)
        if action == "confirm":
            response = service.confirm_voice(voice_log_id)
            if response.get("action") in ("voice_confirmed", "saved"):
                user_repo = UserRepository(db)
                user = user_repo.get_by_telegram_id(update.effective_user.id)
                if user:
                    from datetime import datetime, timezone as tz_mod
                    from zoneinfo import ZoneInfo
                    try:
                        tz = ZoneInfo(user.timezone)
                    except Exception:
                        tz = ZoneInfo("Europe/Moscow")
                    today_str = datetime.now(tz).date().isoformat()
                    user_repo.increment_transactions_today(user, today_str)
                    db.commit()
        elif action == "cancel":
            response = service.cancel_voice(voice_log_id)
        elif action == "edit":
            response = service.start_voice_edit(voice_log_id)
        else:
            response = {"action": "voice_fallback", "message": "Неизвестное действие."}

    logger.info("voice callback: action=%s response=%s", action, response.get("action"))

    tx_ids = response.get("saved_transaction_ids", [])
    if response.get("action") == "voice_confirmed" and tx_ids:
        # Use first tx_id for catfix correction; show unified saved_actions_keyboard
        correction_id = tx_ids[0] if len(tx_ids) == 1 else None
        kb = saved_actions_keyboard(correction_id) if correction_id else undo_inline_keyboard(list(tx_ids))
        await query.edit_message_text(response["message"], parse_mode="HTML", reply_markup=kb)
        asyncio.create_task(
            _auto_remove_keyboard(context.bot, query.message.chat_id, query.message.message_id)
        )
    else:
        await query.edit_message_text(response["message"], parse_mode="HTML", reply_markup=done_keyboard())
