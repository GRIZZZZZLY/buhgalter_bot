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
from app.repositories.category_budget_repository import CategoryBudgetRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_category_mapping_repository import UserCategoryMappingRepository
from app.schemas.telegram import TelegramVoicePayload
from app.services.analytics_service import AnalyticsService
from app.services.scheduler_service import SchedulerService
from app.telegram.bot_service import TelegramBotService
from app.telegram.formatter import TreasuryFormatter
from app.telegram.handlers import START_MESSAGE
from app.telegram.keyboards import (
    delete_all_confirm_keyboard,
    delete_keyboard,
    category_resolution_keyboard,
    evening_checkin_keyboard,
    settings_keyboard,
    start_keyboard,
    voice_confirmation_keyboard,
)

LOG_PATH = Path(__file__).resolve().parents[2] / "runtime" / "logs" / "telegram-bot.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("finance_bot.telegram")
formatter = TreasuryFormatter()

# Global scheduler reference (set during startup)
_scheduler: SchedulerService | None = None


def configure_logging() -> None:
    if logger.handlers:
        return

    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(fmt)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)

    logging.basicConfig(level=logging.INFO, handlers=[file_handler, stream_handler], force=True)
    logger.setLevel(logging.INFO)
    logger.info("logging configured, path=%s", LOG_PATH)


async def on_startup(app: Application) -> None:
    global _scheduler
    logger.info("telegram bot startup")
    _scheduler = SchedulerService(app)
    _scheduler.start()
    logger.info("scheduler started")


async def on_shutdown(app: Application) -> None:
    global _scheduler
    logger.info("telegram bot shutdown")
    if _scheduler:
        _scheduler.stop()
        _scheduler = None


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("telegram handler error, update=%s", update, exc_info=context.error)


def _ensure_user(db, update: Update) -> None:
    """Ensure user exists in DB and update activity tracking."""
    tg_user = update.effective_user
    if tg_user is None:
        return
    user_repo = UserRepository(db)
    display_name = tg_user.full_name or tg_user.username
    user = user_repo.get_or_create(tg_user.id, display_name)

    # Update streak and daily counter
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    try:
        tz = ZoneInfo(user.timezone)
    except Exception:
        tz = ZoneInfo("Europe/Moscow")
    today_str = datetime.now(tz).date().isoformat()
    user_repo.update_streak(user, today_str)

    # Reset ignored evening reminders on any user activity
    if user.ignored_evening_reminders > 0:
        user_repo.reset_ignored_evening_reminders(user)

    db.commit()


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
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("budget", budget_command))
    application.add_handler(CallbackQueryHandler(settings_callback_handler, pattern=r"^settings:"))
    application.add_handler(CallbackQueryHandler(delete_callback_handler, pattern=r"^(delete:|deleteall:)"))
    application.add_handler(CallbackQueryHandler(voice_callback_handler, pattern=r"^voice:"))
    application.add_handler(MessageHandler(filters.VOICE, voice_message_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
    return application


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with SessionLocal() as db:
        _ensure_user(db, update)

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
        _ensure_user(db, update)
        service = TelegramBotService(db)
        response = service.process_summary_command(update.effective_user.id, period=period)
    await update.effective_message.reply_text(response["message"], reply_markup=ReplyKeyboardRemove())


async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with SessionLocal() as db:
        _ensure_user(db, update)
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
        _ensure_user(db, update)
        service = TelegramBotService(db)
        response = service.process_delete_all_command(update.effective_user.id)

    await update.effective_message.reply_text(
        response["message"],
        reply_markup=delete_all_confirm_keyboard(),
    )


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with SessionLocal() as db:
        _ensure_user(db, update)
        user_repo = UserRepository(db)
        user = user_repo.get_by_telegram_id(update.effective_user.id)

    if user is None:
        await update.effective_message.reply_text("Ошибка: пользователь не найден.")
        return

    lines = [
        "\u2699\ufe0f Настройки\n",
        f"\U0001f4b0 Бюджет: {f'{user.budget_amount:,.0f} ₽/мес' if user.budget_amount else 'не установлен'}",
        f"\U0001f4c5 Начало периода: {user.budget_start_day}-е число",
        f"\u23f0 Утреннее напоминание: {user.reminder_morning or 'выключено'}",
        f"\U0001f319 Вечернее напоминание: {user.reminder_evening or 'выключено'}",
        f"\U0001f30d Часовой пояс: {user.timezone}",
        f"\U0001f525 Серия: {user.streak_days} дней",
    ]
    await update.effective_message.reply_text(
        "\n".join(lines),
        reply_markup=settings_keyboard(),
    )


async def budget_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /budget command. Usage: /budget [category] [amount] or /budget (show all)."""
    with SessionLocal() as db:
        _ensure_user(db, update)
        user_repo = UserRepository(db)
        user = user_repo.get_by_telegram_id(update.effective_user.id)

        if user is None:
            await update.effective_message.reply_text("Ошибка: пользователь не найден.")
            return

        if not context.args or len(context.args) == 0:
            # Show budget report
            analytics = AnalyticsService(db)
            report = analytics.build_budget_report(user)
            await update.effective_message.reply_text(report, reply_markup=ReplyKeyboardRemove())
            return

        if len(context.args) < 2:
            await update.effective_message.reply_text(
                "Формат: /budget категория сумма\n"
                "Примеры:\n"
                "  /budget еда 15000\n"
                "  /budget транспорт 5000\n"
                "  /budget еда 0  (удалить бюджет)\n"
                "  /budget  (показать все бюджеты)",
                reply_markup=ReplyKeyboardRemove(),
            )
            return

        # Parse category and amount
        from app.services.parser_service import ParserService
        parser = ParserService()
        category_text = " ".join(context.args[:-1]).lower().strip()
        amount_text = context.args[-1]

        # Resolve category
        resolved_category = parser.category_lookup.get(category_text, category_text)

        try:
            amount = float(amount_text.replace(",", ".").replace(" ", ""))
        except ValueError:
            await update.effective_message.reply_text(
                f"\u274c Не понял сумму: {amount_text}. Введи число.",
                reply_markup=ReplyKeyboardRemove(),
            )
            return

        budget_repo = CategoryBudgetRepository(db)
        cat_label = formatter.category_label(resolved_category)

        if amount <= 0:
            removed = budget_repo.remove(user.telegram_user_id, resolved_category)
            db.commit()
            if removed:
                await update.effective_message.reply_text(
                    f"\u2705 Бюджет \u00ab{cat_label}\u00bb удалён.",
                    reply_markup=ReplyKeyboardRemove(),
                )
            else:
                await update.effective_message.reply_text(
                    f"Бюджет \u00ab{cat_label}\u00bb не был установлен.",
                    reply_markup=ReplyKeyboardRemove(),
                )
            return

        budget_repo.upsert(user.telegram_user_id, resolved_category, amount)
        db.commit()
        await update.effective_message.reply_text(
            f"\u2705 Бюджет \u00ab{cat_label}\u00bb: {amount:,.0f} \u20bd/мес",
            reply_markup=ReplyKeyboardRemove(),
        )


async def _check_and_send_budget_alert(
    update: Update, db, telegram_user_id: int, category: str
) -> None:
    """Check if a budget alert should be sent after a transaction."""
    analytics = AnalyticsService(db)
    alert = analytics.check_budget_alert(telegram_user_id, category)
    if alert:
        await update.effective_message.reply_text(alert)


async def settings_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except BadRequest:
        pass

    action = query.data.split(":", 1)[1] if ":" in query.data else ""

    if action == "budget":
        context.user_data["awaiting_setting"] = "budget"
        await query.edit_message_text(
            "\U0001f4b0 Введи месячный бюджет в рублях (например: 50000).\n"
            "Или отправь 0 чтобы убрать бюджет."
        )
    elif action == "morning":
        context.user_data["awaiting_setting"] = "morning"
        await query.edit_message_text(
            "\u23f0 Введи время утреннего напоминания в формате ЧЧ:ММ (например: 09:00).\n"
            "Или отправь «выкл» чтобы отключить."
        )
    elif action == "evening":
        context.user_data["awaiting_setting"] = "evening"
        await query.edit_message_text(
            "\U0001f319 Введи время вечернего напоминания в формате ЧЧ:ММ (например: 21:00).\n"
            "Или отправь «выкл» чтобы отключить."
        )
    elif action == "timezone":
        context.user_data["awaiting_setting"] = "timezone"
        await query.edit_message_text(
            "\U0001f30d Введи часовой пояс (например: Europe/Moscow, Asia/Yekaterinburg, Europe/Samara).\n"
            "Полный список: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones"
        )
    elif action == "disable_all":
        with SessionLocal() as db:
            user_repo = UserRepository(db)
            user = user_repo.get_by_telegram_id(update.effective_user.id)
            if user:
                user_repo.update_settings(user, reminder_morning=None, reminder_evening=None)
                user_repo.commit()
        await query.edit_message_text("\u2705 Все напоминания отключены. Включить обратно: /settings")


async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.effective_message.text or ""

    # Handle settings input
    awaiting = context.user_data.get("awaiting_setting") if context.user_data else None
    if awaiting:
        del context.user_data["awaiting_setting"]
        result = _handle_settings_input(update.effective_user.id, awaiting, text.strip())
        await update.effective_message.reply_text(result, reply_markup=ReplyKeyboardRemove())
        return

    # Handle evening check-in responses
    stripped = text.strip()
    if stripped == "\u2705 Не тратил":
        await update.effective_message.reply_text(
            "\U0001f44d Отлично, так и запишем!",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    with SessionLocal() as db:
        _ensure_user(db, update)

        # Track transaction count for smart silence
        user_repo = UserRepository(db)
        user = user_repo.get_by_telegram_id(update.effective_user.id)

        service = TelegramBotService(db)
        response = service.process_text_message(update.effective_user.id, text)

        # If a transaction was saved, update daily counter and check budget alert
        if response.get("action") == "saved" and user:
            from datetime import datetime, timezone as tz_mod
            from zoneinfo import ZoneInfo
            try:
                tz = ZoneInfo(user.timezone)
            except Exception:
                tz = ZoneInfo("Europe/Moscow")
            today_str = datetime.now(tz).date().isoformat()
            user_repo.increment_transactions_today(user, today_str)
            db.commit()

            # Check budget alert for the saved category
            saved_category = response.get("saved_category")
            if saved_category:
                await _check_and_send_budget_alert(update, db, user.telegram_user_id, str(saved_category))

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

    placeholder = await update.effective_message.reply_text("\U0001f3a4 Обрабатываю голосовое\u2026", reply_markup=ReplyKeyboardRemove())

    logger.info("voice message received: user=%s message=%s file_id=%s", update.effective_user.id, update.effective_message.message_id, voice.file_id)
    telegram_file = await context.bot.get_file(voice.file_id)
    fd, temp_path = tempfile.mkstemp(prefix="finance-bot-voice-", suffix=".ogg")
    os.close(fd)
    Path(temp_path).unlink(missing_ok=True)
    await telegram_file.download_to_drive(custom_path=temp_path)
    logger.info("voice downloaded: path=%s", temp_path)

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

        # Track transaction count if voice was auto-confirmed
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

            # Track transaction count on voice confirm
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

    logger.info("voice callback processed: action=%s response_action=%s", action, response.get("action"))
    await query.edit_message_text(response["message"])


def _handle_settings_input(telegram_user_id: int, setting: str, value: str) -> str:
    """Process a settings value from the user."""
    with SessionLocal() as db:
        user_repo = UserRepository(db)
        user = user_repo.get_by_telegram_id(telegram_user_id)
        if user is None:
            return "Ошибка: пользователь не найден."

        if setting == "budget":
            try:
                amount = float(value.replace(",", ".").replace(" ", ""))
                if amount <= 0:
                    user_repo.update_settings(user, budget_amount=None)
                    user_repo.commit()
                    return "\u2705 Бюджет убран."
                user_repo.update_settings(user, budget_amount=amount)
                user_repo.commit()
                return f"\u2705 Бюджет установлен: {amount:,.0f} \u20bd/мес"
            except ValueError:
                return "\u274c Не понял сумму. Введи число, например: 50000"

        elif setting == "morning":
            if value.lower() in ("выкл", "off", "0", "нет"):
                user_repo.update_settings(user, reminder_morning=None)
                user_repo.commit()
                return "\u2705 Утреннее напоминание отключено."
            if _validate_time(value):
                user_repo.update_settings(user, reminder_morning=value)
                user_repo.commit()
                return f"\u2705 Утреннее напоминание: {value}"
            return "\u274c Формат: ЧЧ:ММ (например: 09:00)"

        elif setting == "evening":
            if value.lower() in ("выкл", "off", "0", "нет"):
                user_repo.update_settings(user, reminder_evening=None)
                user_repo.commit()
                return "\u2705 Вечернее напоминание отключено."
            if _validate_time(value):
                user_repo.update_settings(user, reminder_evening=value)
                user_repo.commit()
                return f"\u2705 Вечернее напоминание: {value}"
            return "\u274c Формат: ЧЧ:ММ (например: 21:00)"

        elif setting == "timezone":
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
            try:
                ZoneInfo(value)
                user_repo.update_settings(user, timezone=value)
                user_repo.commit()
                return f"\u2705 Часовой пояс: {value}"
            except (ZoneInfoNotFoundError, KeyError):
                return f"\u274c Неизвестный часовой пояс: {value}. Пример: Europe/Moscow"

    return "\u274c Неизвестная настройка."


def _validate_time(value: str) -> bool:
    """Validate HH:MM format."""
    try:
        parts = value.split(":")
        if len(parts) != 2:
            return False
        h, m = int(parts[0]), int(parts[1])
        return 0 <= h <= 23 and 0 <= m <= 59
    except (ValueError, IndexError):
        return False


def run_polling() -> None:
    app = build_application()
    logger.info("run_polling start")
    try:
        app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
    finally:
        logger.info("run_polling exit")
