"""
runtime.py — assembly point for the Telegram bot.

Contains only: configure_logging, on_startup, on_shutdown, error_handler,
build_application, run_polling.  All handler logic lives in app.telegram.handlers.*
"""
import logging
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    SQLAlchemyPersistence,
    filters,
)

from app.core.settings import get_settings
from app.services.scheduler_service import SchedulerService

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_PATH = Path(__file__).resolve().parents[2] / "runtime" / "logs" / "telegram-bot.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("finance_bot.telegram")

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
    from telegram import BotCommand
    await app.bot.set_my_commands([
        BotCommand("menu", "Главное меню"),
        BotCommand("ask", "Спросить советника"),
        BotCommand("export", "Экспорт данных"),
        BotCommand("import", "Импорт данных"),
    ])


async def on_shutdown(app: Application) -> None:
    global _scheduler
    logger.info("telegram bot shutdown")
    if _scheduler:
        _scheduler.stop()
        _scheduler = None


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("telegram handler error, update=%s", update, exc_info=context.error)


# ---------------------------------------------------------------------------
# Handler imports
# ---------------------------------------------------------------------------

from app.telegram.handlers.start import (
    start_command,
    menu_command,
    onboarding_callback_handler,
    summary_command,
)
from app.telegram.handlers.advisor import (
    ask_command,
    advisor_callback_handler,
    advisor_followup_callback_handler,
    apply_action_handler,
    apply_confirm_handler,
    apply_cancel_handler,
    undo_handler,
)
from app.telegram.handlers.nav import nav_callback_handler, help_topic_callback_handler
from app.telegram.handlers.budget import budget_command, budget_callback_handler
from app.telegram.handlers.categories import (
    catfix_callback_handler,
    improve_categories_command,
    sugg_callback_handler,
    categories_callback_handler,
    reset_callback_handler,
)
from app.telegram.handlers.settings import settings_command, settings_callback_handler
from app.telegram.handlers.edit import edit_command, edit_callback_handler
from app.telegram.handlers.import_export import (
    import_command,
    export_command,
    document_message_handler,
    import_callback_handler,
    export_callback_handler,
)
from app.telegram.handlers.planned import (
    plan_command,
    planned_command,
    planned_callback_handler,
    planned_input_callback_handler,
    planned_freeform_callback_handler,
)
from app.telegram.handlers.recurring import (
    recurring_command,
    recurring_del_command,
    recurring_callback_handler,
    recurring_input_callback_handler,
    recurring_freeform_callback_handler,
)
from app.telegram.handlers.transactions import (
    delete_command,
    deleteall_command,
    delete_callback_handler,
    undo_callback_handler,
    catres_callback_handler,
    lowconf_callback_handler,
    checkin_callback_handler,
    clarify_intent_callback_handler,
    text_message_handler,
)
from app.telegram.handlers.voice import voice_message_handler, voice_callback_handler


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def build_application() -> Application:
    configure_logging()
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")

    persistence = SQLAlchemyPersistence(url=settings.database_url)
    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .persistence(persistence)
        .post_init(on_startup)
        .post_shutdown(on_shutdown)
        .build()
    )
    application.add_error_handler(error_handler)

    # Commands
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("summary", summary_command))
    application.add_handler(CommandHandler("delete", delete_command))
    application.add_handler(CommandHandler("deleteall", deleteall_command))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("budget", budget_command))
    application.add_handler(CommandHandler("recurring", recurring_command))
    application.add_handler(CommandHandler("recurring_del", recurring_del_command))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("edit", edit_command))
    application.add_handler(CommandHandler("export", export_command))
    application.add_handler(CommandHandler("import", import_command))
    application.add_handler(CommandHandler("plan", plan_command))
    application.add_handler(CommandHandler("planned", planned_command))
    application.add_handler(CommandHandler("ask", ask_command))
    application.add_handler(CommandHandler("improve_categories", improve_categories_command))

    # Callback query handlers
    application.add_handler(CallbackQueryHandler(recurring_callback_handler,          pattern=r"^recurring:"))
    application.add_handler(CallbackQueryHandler(edit_callback_handler,               pattern=r"^edit:"))
    application.add_handler(CallbackQueryHandler(nav_callback_handler,                pattern=r"^nav:"))
    application.add_handler(CallbackQueryHandler(checkin_callback_handler,            pattern=r"^checkin:"))
    application.add_handler(CallbackQueryHandler(undo_callback_handler,               pattern=r"^undo:"))
    application.add_handler(CallbackQueryHandler(settings_callback_handler,           pattern=r"^settings:"))
    application.add_handler(CallbackQueryHandler(delete_callback_handler,             pattern=r"^(delete:|deleteall:)"))
    application.add_handler(CallbackQueryHandler(voice_callback_handler,              pattern=r"^voice:"))
    application.add_handler(CallbackQueryHandler(catres_callback_handler,             pattern=r"^catres:"))
    application.add_handler(CallbackQueryHandler(lowconf_callback_handler,            pattern=r"^lowconf:"))
    application.add_handler(CallbackQueryHandler(planned_callback_handler,            pattern=r"^planned:"))
    application.add_handler(CallbackQueryHandler(planned_input_callback_handler,      pattern=r"^planned_input:"))
    application.add_handler(CallbackQueryHandler(recurring_input_callback_handler,    pattern=r"^recurring_input:"))
    application.add_handler(CallbackQueryHandler(planned_freeform_callback_handler,   pattern=r"^planned_freeform:"))
    application.add_handler(CallbackQueryHandler(recurring_freeform_callback_handler, pattern=r"^recurring_freeform:"))
    application.add_handler(CallbackQueryHandler(catfix_callback_handler,             pattern=r"^catfix:"))
    application.add_handler(CallbackQueryHandler(categories_callback_handler,         pattern=r"^categories:"))
    application.add_handler(CallbackQueryHandler(sugg_callback_handler,               pattern=r"^sugg:"))
    application.add_handler(CallbackQueryHandler(advisor_callback_handler,            pattern=r"^advisor:"))
    application.add_handler(CallbackQueryHandler(advisor_followup_callback_handler,   pattern=r"^advisor_followup:"))
    application.add_handler(CallbackQueryHandler(apply_action_handler,                pattern=r"^apply:[^_]"))
    application.add_handler(CallbackQueryHandler(apply_confirm_handler,               pattern=r"^apply_confirm:"))
    application.add_handler(CallbackQueryHandler(apply_cancel_handler,                pattern=r"^apply_cancel$"))
    application.add_handler(CallbackQueryHandler(undo_handler,                        pattern=r"^action:undo$"))
    application.add_handler(CallbackQueryHandler(export_callback_handler,             pattern=r"^export:"))
    application.add_handler(CallbackQueryHandler(import_callback_handler,             pattern=r"^import:"))
    application.add_handler(CallbackQueryHandler(budget_callback_handler,             pattern=r"^budget:"))
    application.add_handler(CallbackQueryHandler(reset_callback_handler,              pattern=r"^reset:"))
    application.add_handler(CallbackQueryHandler(onboarding_callback_handler,         pattern=r"^onboarding:"))
    application.add_handler(CallbackQueryHandler(help_topic_callback_handler,         pattern=r"^help:topic:"))
    application.add_handler(CallbackQueryHandler(clarify_intent_callback_handler,     pattern=r"^clarify:"))

    # Message handlers
    application.add_handler(MessageHandler(filters.VOICE, voice_message_handler))
    application.add_handler(MessageHandler(filters.Document.ALL, document_message_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))

    return application


def run_polling() -> None:
    app = build_application()
    logger.info("run_polling start")
    try:
        app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
    finally:
        logger.info("run_polling exit")
