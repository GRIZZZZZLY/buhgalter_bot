import logging
import os
from pathlib import Path
import tempfile

from telegram import ReplyKeyboardRemove, Update
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.core.settings import get_settings
from app.db.session import SessionLocal
from app.schemas.telegram import TelegramVoicePayload
from app.telegram.bot_service import TelegramBotService
from app.telegram.formatter import TreasuryFormatter
from app.telegram.handlers import START_MESSAGE
from app.telegram.keyboards import (
    delete_all_confirm_keyboard,
    delete_keyboard,
    category_resolution_keyboard,
    start_keyboard,
    voice_confirmation_keyboard,
)

LOG_PATH = Path(__file__).resolve().parents[2] / "runtime" / "logs" / "telegram-bot.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("finance_bot.telegram")
formatter = TreasuryFormatter()


def configure_logging() -> None:
    if logger.handlers:
        return

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logging.basicConfig(level=logging.INFO, handlers=[file_handler, stream_handler], force=True)
    logger.setLevel(logging.INFO)
    logger.info("logging configured, path=%s", LOG_PATH)


async def on_startup(app: Application) -> None:
    logger.info("telegram bot startup")


async def on_shutdown(app: Application) -> None:
    logger.info("telegram bot shutdown")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("telegram handler error, update=%s", update, exc_info=context.error)


def build_application() -> Application:
    configure_logging()
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")

    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(on_startup)
        .post_shutdown(on_shutdown)
        .build()
    )
    application.add_error_handler(error_handler)
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("summary", summary_command))
    application.add_handler(CommandHandler("delete", delete_command))
    application.add_handler(CommandHandler("deleteall", deleteall_command))
    application.add_handler(CallbackQueryHandler(delete_callback_handler, pattern=r"^(delete:|deleteall:)"))
    application.add_handler(CallbackQueryHandler(voice_callback_handler, pattern=r"^voice:"))
    application.add_handler(MessageHandler(filters.VOICE, voice_message_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
    return application


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = get_settings()
    reply_markup = start_keyboard(settings.telegram_webhook_url or None)
    kwargs = {"reply_markup": reply_markup} if reply_markup else {"reply_markup": ReplyKeyboardRemove()}
    await update.effective_message.reply_text(START_MESSAGE, **kwargs)


async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    period = "month"
    if context.args:
        candidate = context.args[0].strip().lower()
        if candidate in {"today", "week", "month", "all"}:
            period = candidate

    with SessionLocal() as db:
        service = TelegramBotService(db)
        response = service.process_summary_command(update.effective_user.id, period=period)
    await update.effective_message.reply_text(response["message"], reply_markup=ReplyKeyboardRemove())


async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with SessionLocal() as db:
        service = TelegramBotService(db)
        response = service.process_delete_command(update.effective_user.id)

    if response["action"] == "delete_select":
        await update.effective_message.reply_text(
            response["message"],
            reply_markup=delete_keyboard(response["items"]),
        )
        return
    await update.effective_message.reply_text(response["message"], reply_markup=ReplyKeyboardRemove())


async def deleteall_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with SessionLocal() as db:
        service = TelegramBotService(db)
        response = service.process_delete_all_command(update.effective_user.id)

    await update.effective_message.reply_text(
        response["message"],
        reply_markup=delete_all_confirm_keyboard(),
    )


async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.effective_message.text or ""
    with SessionLocal() as db:
        service = TelegramBotService(db)
        response = service.process_text_message(update.effective_user.id, text)
    if response.get("action") == "confirm_voice" and response.get("voice_log_id"):
        await update.effective_message.reply_text(
            response["message"],
            reply_markup=voice_confirmation_keyboard(response["voice_log_id"]),
        )
        return
    if response.get("action") == "clarify_category_choice":
        await update.effective_message.reply_text(
            response["message"],
            reply_markup=category_resolution_keyboard(str(response.get("raw_category", "")), list(response.get("suggestions", []))),
        )
        return
    if response.get("remove_keyboard"):
        await update.effective_message.reply_text(response["message"], reply_markup=ReplyKeyboardRemove())
        return
    await update.effective_message.reply_text(response["message"], reply_markup=ReplyKeyboardRemove())


async def voice_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    voice = update.effective_message.voice
    if voice is None:
        await update.effective_message.reply_text("Не нашёл voice payload.")
        return

    placeholder = await update.effective_message.reply_text("🎤 Обрабатываю голосовое…", reply_markup=ReplyKeyboardRemove())

    logger.info("voice message received: user=%s message=%s file_id=%s", update.effective_user.id, update.effective_message.message_id, voice.file_id)
    telegram_file = await context.bot.get_file(voice.file_id)
    fd, temp_path = tempfile.mkstemp(prefix="finance-bot-voice-", suffix=".ogg")
    os.close(fd)
    Path(temp_path).unlink(missing_ok=True)
    await telegram_file.download_to_drive(custom_path=temp_path)
    logger.info("voice downloaded: path=%s", temp_path)

    with SessionLocal() as db:
        service = TelegramBotService(db)
        response, debug = service.process_voice_message(
            TelegramVoicePayload(
                telegram_user_id=update.effective_user.id,
                telegram_message_id=update.effective_message.message_id,
                file_id=voice.file_id,
                original_file_path=temp_path,
            )
        )

    logger.info("voice processed: action=%s debug=%s", response.get("action"), debug)
    try:
        await context.bot.delete_message(chat_id=placeholder.chat_id, message_id=placeholder.message_id)
    except BadRequest as exc:
        logger.warning(
            "voice placeholder delete failed: error=%s chat_id=%s message_id=%s action=%s",
            str(exc),
            placeholder.chat_id,
            placeholder.message_id,
            response.get("action"),
        )

    if response.get("action") == "confirm_voice" and response.get("voice_log_id"):
        await update.effective_message.reply_text(
            response["message"],
            reply_markup=voice_confirmation_keyboard(response["voice_log_id"]),
        )
        return
    if response.get("action") == "clarify_category_choice":
        await update.effective_message.reply_text(
            response["message"],
            reply_markup=category_resolution_keyboard(str(response.get("raw_category", "")), list(response.get("suggestions", []))),
        )
        return

    await update.effective_message.reply_text(response["message"], reply_markup=ReplyKeyboardRemove())


async def delete_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except BadRequest:
        logger.warning("delete callback answer failed: data=%s", query.data)

    with SessionLocal() as db:
        service = TelegramBotService(db)
        if query.data.startswith("delete:one:"):
            transaction_id = query.data.split(":", 2)[2]
            response = service.delete_transaction(update.effective_user.id, transaction_id)
        elif query.data == "deleteall:confirm":
            response = service.delete_all_transactions(update.effective_user.id)
        elif query.data == "deleteall:cancel":
            response = {"action": "deleteall_cancelled", "message": formatter.format_deleteall_cancelled()}
        else:
            response = {"action": "delete_unknown", "message": "Неизвестное действие удаления."}

    await query.edit_message_text(response["message"])


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
        await query.edit_message_text("Некорректный callback payload.")
        return

    with SessionLocal() as db:
        service = TelegramBotService(db)
        if action == "confirm":
            response = service.confirm_voice(voice_log_id)
        elif action == "cancel":
            response = service.cancel_voice(voice_log_id)
        elif action == "edit":
            response = service.start_voice_edit(voice_log_id)
        else:
            response = {"action": "voice_fallback", "message": "Неизвестное действие."}

    logger.info("voice callback processed: action=%s response_action=%s", action, response.get("action"))
    await query.edit_message_text(response["message"])


def run_polling() -> None:
    app = build_application()
    logger.info("run_polling start")
    try:
        app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
    finally:
        logger.info("run_polling exit")
