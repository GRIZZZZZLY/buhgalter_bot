import asyncio
import logging
import os
from pathlib import Path
import tempfile

from telegram import Update
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
from app.services.financial_qa_service import FinancialQAService
from app.services.nav_service import NavService
from app.services.planned_expense_service import parse_plan_args
from app.services.recurring_service import RecurringService, parse_recurring_args, parse_recurring_schedule_args
from app.services.scheduler_service import SchedulerService
from app.telegram.bot_service import TelegramBotService
from app.telegram.formatter import TreasuryFormatter
from app.telegram.handlers import START_MESSAGE
from app.telegram.keyboards import (
    advisor_keyboard,
    cancel_keyboard,
    category_grid_keyboard,
    category_resolution_keyboard,
    delete_all_confirm_keyboard,
    delete_keyboard,
    done_keyboard,
    edit_categories_keyboard,
    edit_item_keyboard,
    edit_select_keyboard,
    evening_checkin_amount_keyboard,
    evening_checkin_keyboard,
    low_confidence_category_keyboard,
    low_confidence_keyboard,
    main_menu_inline_keyboard,
    planned_expense_due_keyboard,
    planned_manage_keyboard,
    recurring_category_keyboard,
    recurring_manage_keyboard,
    saved_actions_keyboard,
    settings_nav_inline_keyboard,
    start_keyboard,
    suggestion_keyboard,
    undo_inline_keyboard,
    voice_confirmation_keyboard,
)

import time as _time

def _time_now() -> float:
    return _time.time()

_ADVISOR_TIMEOUT = 600  # 10 minutes


def _format_advisor_payload(answer: str, basis: list[str] | None = None, warnings: list[str] | None = None, confidence: str | None = None) -> str:
    parts = [answer.strip()]
    if basis:
        parts.append("\nОснова:\n" + "\n".join(f"• {item}" for item in basis[:3]))
    if warnings:
        parts.append("\nРиски / ограничения:\n" + "\n".join(f"• {item}" for item in warnings[:3]))
    if confidence:
        conf_map = {"low": "низкая", "medium": "средняя", "high": "высокая"}
        parts.append(f"\nУверенность: {conf_map.get(confidence, confidence)}")
    return "\n".join(part for part in parts if part)

_ADVISOR_ONBOARDING = (
    "🧠 *Финансовый советник*\n\n"
    "Задай любой вопрос о своих финансах или выбери готовый сценарий ниже. Например:\n"
    "• Сколько я трачу на еду в месяц?\n"
    "• Укладываюсь ли я в бюджеты?\n"
    "• Какие крупные платежи скоро?\n"
    "• Как изменились мои расходы за 3 месяца?\n\n"
    "Можно писать текстом или голосом 👇"
)

_ADVISOR_SCENARIO_QUESTIONS = {
    "top_expenses": "Покажи топ расходов за этот месяц и на что уходит больше всего денег.",
    "budget_risks": "Где я уже вылезаю из бюджета и по каким категориям риск перерасхода?",
    "upcoming": "Какие платежи и плановые траты у меня скоро?",
    "trends_3m": "Покажи динамику расходов за 3 месяца и что изменилось.",
    "cut_costs": "Что сейчас разумнее всего сократить по моим расходам?",
    "export": "EXPORT_PLACEHOLDER",
}

LOG_PATH = Path(__file__).resolve().parents[2] / "runtime" / "logs" / "telegram-bot.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("finance_bot.telegram")
formatter = TreasuryFormatter()

# Global scheduler reference (set during startup)
_scheduler: SchedulerService | None = None

# Undo window — 30 seconds
UNDO_WINDOW_SECONDS = 30


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


# ---------------------------------------------------------------------------
# catfix callback — catfix:change / catfix:set / catfix:cancel
# ---------------------------------------------------------------------------

_CATFIX_CATEGORIES = [
    "food", "transport", "housing", "health", "beauty", "entertainment",
    "subscriptions", "shopping", "home", "telecom", "work", "education",
    "gifts", "fees", "salary", "freelance", "bonus", "transfer", "refund",
    "other_income", "other",
]


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


async def catfix_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except BadRequest:
        pass

    # catfix:change:<tx_id>
    # catfix:set:<tx_id>:<slug>
    # catfix:cancel:<tx_id>
    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    tx_id  = parts[2] if len(parts) > 2 else ""

    if action == "cancel":
        await query.edit_message_reply_markup(reply_markup=None)
        return

    if action == "change":
        user_id = update.effective_user.id
        with SessionLocal() as _cat_db:
            from app.services.category_service import CategoryService
            _ensure_user(_cat_db, update)
            _cat_svc = CategoryService(_cat_db)
            _cat_svc.ensure_seeded(user_id)
            _all_visible = (
                [c.slug for c in _cat_svc.get_visible_for_type(user_id, "expense")]
                + [c.slug for c in _cat_svc.get_visible_for_type(user_id, "income")]
            )
            _visible_catfix = [s for s in _CATFIX_CATEGORIES if s in _all_visible]
        await query.edit_message_reply_markup(
            reply_markup=category_grid_keyboard(tx_id, _visible_catfix or _CATFIX_CATEGORIES)
        )
        return

    if action == "set":
        slug = parts[3] if len(parts) > 3 else ""
        user_id = update.effective_user.id
        with SessionLocal() as db:
            svc = TelegramBotService(db)
            result = svc.handle_category_correction(user_id, tx_id, slug)
        await query.edit_message_text(result["message"], parse_mode="HTML", reply_markup=done_keyboard())
        return

    await query.edit_message_reply_markup(reply_markup=None)


# ---------------------------------------------------------------------------
# /improve_categories command + sugg callback
# ---------------------------------------------------------------------------

async def improve_categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from app.telegram.handlers import _sugg_set
    await update.effective_message.reply_text("Анализирую транзакции…")
    try:
        with SessionLocal() as db:
            _ensure_user(db, update)
            svc = TelegramBotService(db)
            results = svc.improve_categories(update.effective_user.id)
    except Exception as exc:
        await update.effective_message.reply_text(f"Ошибка при анализе: {exc}", reply_markup=done_keyboard())
        return

    if not results:
        await update.effective_message.reply_text("Предложений нет.", reply_markup=done_keyboard())
        return

    from app.telegram.keyboards import grouped_suggestion_keyboard
    lines = []
    for i, item in enumerate(results, 1):
        _sugg_set(item["key"], item["suggestion"])
        lines.append(f"<b>{i}.</b> {item['text']}")
    await update.effective_message.reply_text(
        "\n\n".join(lines),
        parse_mode="HTML",
        reply_markup=grouped_suggestion_keyboard(results),
    )


async def sugg_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from app.telegram.handlers import _sugg_pop
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except BadRequest:
        pass

    data = query.data          # e.g. "sugg:abc12345_yes"
    key = data.rsplit("_", 1)[0]
    action = data.rsplit("_", 1)[1] if "_" in data else ""

    suggestion = _sugg_pop(key)
    if suggestion is not None and action == "yes":
        with SessionLocal() as db:
            svc = TelegramBotService(db)
            svc.apply_suggestion(suggestion)

    # Rebuild keyboard without the processed row
    remaining_rows = []
    if query.message and query.message.reply_markup:
        for row in query.message.reply_markup.inline_keyboard:
            row_keys = {btn.callback_data.rsplit("_", 1)[0] for btn in row if btn.callback_data}
            if key not in row_keys:
                remaining_rows.append(row)

    if remaining_rows:
        await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup(remaining_rows)
        )
    else:
        await query.edit_message_reply_markup(reply_markup=None)


async def categories_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except BadRequest:
        pass

    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    param = parts[2] if len(parts) > 2 else ""
    # Optional type+page appended by categories_list_keyboard: categories:edit:{slug}:{type}:{page}
    _ctx_type = parts[3] if len(parts) > 3 else ""
    _ctx_page = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 0
    user_id = update.effective_user.id

    def _list_back() -> str:
        """Back target to the category list (or type selector if no context)."""
        t = context.user_data.get("categories_ctx", {}).get("type", _ctx_type)
        p = context.user_data.get("categories_ctx", {}).get("page", _ctx_page)
        return f"nav:categories:{t}:{p}" if t else "nav:categories"

    from app.services.category_service import CategoryService
    from app.telegram.keyboards import (
        category_edit_keyboard,
        category_type_keyboard,
        category_reassign_keyboard,
        category_delete_confirm_keyboard,
    )

    if action == "edit":
        slug = param
        if _ctx_type:
            context.user_data["categories_ctx"] = {"type": _ctx_type, "page": _ctx_page}
        with SessionLocal() as db:
            _ensure_user(db, update)
            svc = CategoryService(db)
            svc.ensure_seeded(user_id)
            cat = svc._repo.get_by_slug(user_id, slug)
        if cat is None:
            await query.edit_message_text("❌ Категория не найдена.", reply_markup=done_keyboard(back_target=_list_back()))
            return
        text = f"✏️ *{cat.emoji} {cat.name_ru}*\n\nЧто изменить?"
        await query.edit_message_text(
            text,
            reply_markup=category_edit_keyboard(slug, cat.is_custom, cat.is_hidden, back_target=_list_back()),
            parse_mode="Markdown",
        )
        return

    if action == "rename":
        slug = param
        context.user_data["awaiting_category_rename"] = slug
        await query.edit_message_text(
            "✏️ Введи новое название категории:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(text="Отмена", callback_data=f"categories:edit:{slug}")
            ]]),
        )
        return

    if action == "emoji":
        slug = param
        context.user_data["awaiting_category_emoji"] = slug
        await query.edit_message_text(
            "🎨 Отправь новый emoji для категории:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(text="Отмена", callback_data=f"categories:edit:{slug}")
            ]]),
        )
        return

    if action == "add":
        context.user_data["awaiting_category_add"] = "name"
        context.user_data.pop("pending_category_add", None)
        await query.edit_message_text(
            "➕ Введи название новой категории:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(text="Отмена", callback_data="nav:categories")
            ]]),
        )
        return

    if action == "set_type":
        cat_type = param
        pending = context.user_data.get("pending_category_add", {})
        name_ru = pending.get("name_ru", "")
        emoji = pending.get("emoji", "")
        if not name_ru or not emoji:
            await query.edit_message_text("❌ Что-то пошло не так. Попробуй снова.", reply_markup=done_keyboard(back_target=_list_back()))
            return
        context.user_data.pop("pending_category_add", None)
        context.user_data.pop("awaiting_category_add", None)
        with SessionLocal() as db:
            _ensure_user(db, update)
            svc = CategoryService(db)
            svc.ensure_seeded(user_id)
            try:
                cat = svc.add_custom(user_id, name_ru, emoji, cat_type)
            except ValueError as e:
                await query.edit_message_text(f"❌ {e}", reply_markup=done_keyboard(back_target=_list_back()))
                return
        await query.edit_message_text(f"✅ Категория «{cat.emoji} {cat.name_ru}» создана!", reply_markup=done_keyboard())
        return

    if action == "delete":
        slug = param
        with SessionLocal() as db:
            _ensure_user(db, update)
            svc = CategoryService(db)
            svc.ensure_seeded(user_id)
            cat = svc._repo.get_by_slug(user_id, slug)
            if cat is None or not cat.is_custom:
                await query.edit_message_text("❌ Нельзя удалить системную категорию.", reply_markup=done_keyboard(back_target=_list_back()))
                return
            count = svc.count_transactions(user_id, slug)
            if count > 0:
                groups = svc.list_categories(user_id)
                compatible = [
                    c
                    for cats in groups.values()
                    for c in cats
                    if c.slug != slug and (c.type == cat.type or c.type == "both" or cat.type == "both")
                ]
        if count > 0:
            await query.edit_message_text(
                f"⚠️ В категории «{cat.name_ru}» есть {count} транзакций.\n"
                f"Куда перенести их перед удалением?",
                reply_markup=category_reassign_keyboard(compatible, slug),
            )
        else:
            await query.edit_message_text(
                f"Удалить категорию «{cat.emoji} {cat.name_ru}»? Это нельзя отменить.",
                reply_markup=category_delete_confirm_keyboard(slug),
            )
        return

    if action == "confirm_delete":
        # Only reached when transaction count == 0 — safe no-op UPDATE
        slug = param
        with SessionLocal() as db:
            _ensure_user(db, update)
            svc = CategoryService(db)
            svc.ensure_seeded(user_id)
            try:
                svc.delete_custom(user_id, slug, reassign_to_slug="other")
            except ValueError as e:
                await query.edit_message_text(f"❌ {e}", reply_markup=done_keyboard(back_target=_list_back()))
                return
        await query.edit_message_text("✅ Категория удалена.", reply_markup=done_keyboard())
        return

    if action == "reassign":
        if "__" not in param:
            await query.edit_message_text("❌ Неверный формат.", reply_markup=done_keyboard(back_target=_list_back()))
            return
        from_slug, to_slug = param.split("__", 1)
        with SessionLocal() as db:
            _ensure_user(db, update)
            svc = CategoryService(db)
            svc.ensure_seeded(user_id)
            try:
                svc.delete_custom(user_id, from_slug, to_slug)
            except ValueError as e:
                await query.edit_message_text(f"❌ {e}", reply_markup=done_keyboard(back_target=_list_back()))
                return
        await query.edit_message_text("✅ Транзакции перенесены, категория удалена.", reply_markup=done_keyboard())
        return

    if action == "toggle_hidden":
        slug = param
        with SessionLocal() as db:
            _ensure_user(db, update)
            svc = CategoryService(db)
            cat = svc.toggle_hidden(user_id, slug)
        if cat is None:
            await query.answer("❌ Категория не найдена", show_alert=True)
            return
        state = "скрыта" if cat.is_hidden else "показана"
        text = f"{'🙈' if cat.is_hidden else '👁'} *{cat.emoji} {cat.name_ru}* — категория {state}.\n\nЧто изменить?"
        await query.edit_message_text(
            text,
            reply_markup=category_edit_keyboard(slug, cat.is_custom, cat.is_hidden),
            parse_mode="Markdown",
        )
        return


async def reset_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles reset:pick, reset:confirm:{scope}, reset:do:{scope}."""
    from app.telegram.keyboards import reset_pick_keyboard, reset_confirm_keyboard
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except BadRequest:
        pass

    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    scope = parts[2] if len(parts) > 2 else ""
    user_id = update.effective_user.id

    if action == "pick":
        await query.edit_message_text(
            "🗑 *Сброс данных*\n\nЧто удалить?",
            reply_markup=reset_pick_keyboard(),
            parse_mode="Markdown",
        )
        return

    if action == "confirm":
        labels = {"all": "все транзакции и бюджеты", "expense": "все расходы", "income": "все доходы"}
        label = labels.get(scope, scope)
        await query.edit_message_text(
            f"⚠️ Удалить *{label}*?\n\nЭто действие нельзя отменить.",
            reply_markup=reset_confirm_keyboard(scope),
            parse_mode="Markdown",
        )
        return

    if action == "do":
        from app.services.transaction_service import TransactionService
        with SessionLocal() as db:
            _ensure_user(db, update)
            svc = TransactionService(db)
            if scope == "all":
                count = svc.delete_all_for_user(user_id)
                # Reset budgets
                from sqlalchemy import delete as sa_delete
                from app.models.category_budget import CategoryBudget
                db.execute(sa_delete(CategoryBudget).where(CategoryBudget.telegram_user_id == user_id))
                user_repo = UserRepository(db)
                u = user_repo.get_by_telegram_id(user_id)
                if u:
                    user_repo.update_settings(u, budget_amount=None)
                db.commit()
                msg = f"✅ Удалено {count} транзакций и все бюджеты."
            else:
                count = svc.delete_by_type(user_id, scope)
                label = "расходов" if scope == "expense" else "доходов"
                msg = f"✅ Удалено {count} {label}."
        await query.edit_message_text(msg, reply_markup=done_keyboard(back_target="nav:settings"))
        return


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
    application.add_handler(CallbackQueryHandler(recurring_callback_handler, pattern=r"^recurring:"))
    application.add_handler(CallbackQueryHandler(edit_callback_handler,    pattern=r"^edit:"))
    application.add_handler(CallbackQueryHandler(nav_callback_handler,     pattern=r"^nav:"))
    application.add_handler(CallbackQueryHandler(checkin_callback_handler, pattern=r"^checkin:"))
    application.add_handler(CallbackQueryHandler(undo_callback_handler,    pattern=r"^undo:"))
    application.add_handler(CallbackQueryHandler(settings_callback_handler, pattern=r"^settings:"))
    application.add_handler(CallbackQueryHandler(delete_callback_handler,  pattern=r"^(delete:|deleteall:)"))
    application.add_handler(CallbackQueryHandler(voice_callback_handler,   pattern=r"^voice:"))
    application.add_handler(CallbackQueryHandler(catres_callback_handler,  pattern=r"^catres:"))
    application.add_handler(CallbackQueryHandler(lowconf_callback_handler, pattern=r"^lowconf:"))
    application.add_handler(CallbackQueryHandler(planned_callback_handler, pattern=r"^planned:"))
    application.add_handler(CallbackQueryHandler(planned_input_callback_handler, pattern=r"^planned_input:"))
    application.add_handler(CallbackQueryHandler(recurring_input_callback_handler, pattern=r"^recurring_input:"))
    application.add_handler(CallbackQueryHandler(catfix_callback_handler,  pattern=r"^catfix:"))
    application.add_handler(CallbackQueryHandler(categories_callback_handler, pattern=r"^categories:"))
    application.add_handler(CallbackQueryHandler(sugg_callback_handler,    pattern=r"^sugg:"))
    application.add_handler(CallbackQueryHandler(advisor_callback_handler, pattern=r"^advisor:"))
    application.add_handler(CallbackQueryHandler(import_callback_handler,   pattern=r"^import:"))
    application.add_handler(CallbackQueryHandler(budget_callback_handler,  pattern=r"^budget:"))
    application.add_handler(CallbackQueryHandler(reset_callback_handler,   pattern=r"^reset:"))
    application.add_handler(MessageHandler(filters.VOICE, voice_message_handler))
    application.add_handler(MessageHandler(filters.Document.ALL, document_message_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
    return application


# ---------------------------------------------------------------------------
# /start — single message
# ---------------------------------------------------------------------------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with SessionLocal() as db:
        _ensure_user(db, update)

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


# ---------------------------------------------------------------------------
# /summary
# ---------------------------------------------------------------------------

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


async def _answer_advisor_question(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    question: str,
    *,
    dialog_mode: bool,
) -> None:
    from app.telegram.keyboards import advisor_keyboard, advisor_session_keyboard

    message = update.effective_message
    if message is None:
        return

    if dialog_mode:
        last_active = context.user_data.get("advisor_last_active", 0)
        if (_time_now() - last_active) > _ADVISOR_TIMEOUT:
            context.user_data["advisor_history"] = []
        history: list[dict] = list(context.user_data.get("advisor_history", []))
    else:
        history = []

    placeholder = await message.reply_text("🤔 Анализирую…")
    with SessionLocal() as db:
        _ensure_user(db, update)
        payload = FinancialQAService(db).answer_payload(question, update.effective_user.id, history=history)

    answer = _format_advisor_payload(
        payload.answer,
        basis=payload.basis,
        warnings=payload.warnings,
        confidence=payload.confidence,
    )

    try:
        await placeholder.delete()
    except Exception:
        pass

    if dialog_mode:
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer})
        if len(history) > 10:
            history = history[2:]
        context.user_data["advisor_history"] = history
        context.user_data["advisor_last_active"] = _time_now()
        reply_markup = advisor_session_keyboard()
    else:
        reply_markup = advisor_keyboard()

    await message.reply_text(answer, reply_markup=reply_markup)


async def _enter_advisor_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from app.telegram.keyboards import advisor_onboarding_keyboard

    context.user_data["mode"] = "advisor"
    context.user_data["advisor_history"] = []
    context.user_data["advisor_last_active"] = _time_now()
    await update.effective_message.reply_text(
        _ADVISOR_ONBOARDING,
        reply_markup=advisor_onboarding_keyboard(),
        parse_mode="Markdown",
    )


async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    question = " ".join(context.args).strip() if context.args else ""
    if not question:
        await _enter_advisor_mode(update, context)
        return
    await _answer_advisor_question(update, context, question, dialog_mode=False)


# ---------------------------------------------------------------------------
# /delete / /deleteall
# ---------------------------------------------------------------------------

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
    await update.effective_message.reply_text(response["message"], reply_markup=done_keyboard())


async def deleteall_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with SessionLocal() as db:
        _ensure_user(db, update)
        service = TelegramBotService(db)
        response = service.process_delete_all_command(update.effective_user.id)

    await update.effective_message.reply_text(
        response["message"],
        reply_markup=delete_all_confirm_keyboard(),
    )


# ---------------------------------------------------------------------------
# /settings
# ---------------------------------------------------------------------------

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with SessionLocal() as db:
        _ensure_user(db, update)
        user_repo = UserRepository(db)
        user = user_repo.get_by_telegram_id(update.effective_user.id)

    if user is None:
        await update.effective_message.reply_text("❌ Не нашёл пользователя.", reply_markup=done_keyboard())
        return

    lines = [
        "⚙️ Настройки\n",
        f"💰 Бюджет: {f'{user.budget_amount:,.0f} ₽/мес' if user.budget_amount else 'не установлен'}",
        f"📅 Начало периода: {user.budget_start_day}-е число",
        f"⏰ Утреннее напоминание: {user.reminder_morning or 'выключено'}",
        f"🌙 Вечернее напоминание: {user.reminder_evening or 'выключено'}",
        f"🌍 Часовой пояс: {user.timezone}",
        f"🔥 Серия: {user.streak_days} дней",
    ]
    await update.effective_message.reply_text(
        "\n".join(lines),
        reply_markup=settings_nav_inline_keyboard(),
    )


# ---------------------------------------------------------------------------
# /edit
# ---------------------------------------------------------------------------

async def edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with SessionLocal() as db:
        _ensure_user(db, update)
        from app.services.transaction_service import TransactionService
        svc = TransactionService(db)
        items = svc.list_recent_for_delete(update.effective_user.id, limit=5)

    if not items:
        await update.effective_message.reply_text("📭 Записей для редактирования нет.", reply_markup=done_keyboard())
        return

    await update.effective_message.reply_text(
        "✏️ Выбери запись для редактирования:",
        reply_markup=edit_select_keyboard(items),
    )


async def edit_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except BadRequest:
        pass

    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    tx_id  = parts[2] if len(parts) > 2 else ""
    extra  = parts[3] if len(parts) > 3 else ""
    user_id = update.effective_user.id

    if action == "select":
        with SessionLocal() as db:
            from app.services.transaction_service import TransactionService
            svc = TransactionService(db)
            items = svc.list_recent_for_delete(user_id, limit=5)
        if not items:
            await query.edit_message_text("📭 Записей нет.", reply_markup=done_keyboard())
            return
        await query.edit_message_text(
            "✏️ Выбери запись для редактирования:",
            reply_markup=edit_select_keyboard(items),
        )
        return

    if action == "item":
        with SessionLocal() as db:
            from app.services.transaction_service import TransactionService
            svc = TransactionService(db)
            items = svc.list_recent_for_delete(user_id, limit=20)
            tx = next((i for i in items if i["id"] == tx_id), None)
        if tx is None:
            await query.edit_message_text("❌ Не нашёл запись.", reply_markup=done_keyboard(back_target="nav:menu"))
            return
        sign  = "↗" if tx["type"] == "income" else "↘"
        label = formatter.category_label(tx["category"])
        text  = f"✏️ {sign} {tx['amount']} ₽ — {label}\n\nЧто изменить?"
        await query.edit_message_text(text, reply_markup=edit_item_keyboard(tx_id))
        return

    if action == "del":
        from app.telegram.keyboards import edit_delete_confirm_keyboard
        await query.edit_message_text(
            "🗑 Удалить эту запись?",
            reply_markup=edit_delete_confirm_keyboard(tx_id),
        )
        return

    if action == "del_confirm":
        with SessionLocal() as db:
            from uuid import UUID
            from app.services.transaction_service import TransactionService
            svc = TransactionService(db)
            deleted = svc.delete_transaction(user_id, UUID(tx_id))
        if deleted:
            await query.edit_message_text("✅ Удалил запись.", reply_markup=done_keyboard())
        else:
            await query.edit_message_text("❌ Не нашёл запись. Возможно, она уже удалена.", reply_markup=done_keyboard(back_target="nav:menu"))
        return

    if action == "type":
        with SessionLocal() as db:
            from uuid import UUID
            from app.services.transaction_service import TransactionService
            from app.schemas.transaction import TransactionUpdateRequest
            svc = TransactionService(db)
            items = svc.list_recent_for_delete(user_id, limit=20)
            tx = next((i for i in items if i["id"] == tx_id), None)
            if tx is None:
                await query.edit_message_text("❌ Не нашёл запись.", reply_markup=done_keyboard(back_target="nav:menu"))
                return
            new_type = "income" if tx["type"] == "expense" else "expense"
            svc.update_transaction(user_id, UUID(tx_id), TransactionUpdateRequest(type=new_type))
        type_label = "↗ доход" if new_type == "income" else "↘ расход"
        await query.edit_message_text(
            f"Тип изменён: {type_label} ✅",
            reply_markup=edit_item_keyboard(tx_id),
        )
        return

    if action == "amount":
        if context.user_data is not None:
            context.user_data["awaiting_edit"] = {
                "field": "amount", "tx_id": tx_id,
                "chat_id": query.message.chat_id,
                "message_id": query.message.message_id,
            }
        await query.edit_message_text("✏️ Введи новую сумму (например: 750 или 1200.50):", reply_markup=cancel_keyboard("edit:select"))
        return

    if action == "cat":
        if extra:
            with SessionLocal() as db:
                from uuid import UUID
                from app.services.transaction_service import TransactionService
                from app.schemas.transaction import TransactionUpdateRequest
                svc = TransactionService(db)
                svc.update_transaction(user_id, UUID(tx_id), TransactionUpdateRequest(category=extra))
            cat_label = formatter.category_label(extra)
            await query.edit_message_text(
                f"Категория изменена: {cat_label} ✅",
                reply_markup=edit_item_keyboard(tx_id),
            )
        else:
            with SessionLocal() as _cat_db:
                from app.services.category_service import CategoryService
                _ensure_user(_cat_db, update)
                _cat_svc = CategoryService(_cat_db)
                _cat_svc.ensure_seeded(user_id)
                _all_visible = (
                    _cat_svc.get_visible_for_type(user_id, "expense")
                    + _cat_svc.get_visible_for_type(user_id, "income")
                )
                seen: set[str] = set()
                _visible_edit: list[tuple[str, str]] = []
                for c in _all_visible:
                    if c.slug not in seen:
                        seen.add(c.slug)
                        _visible_edit.append((c.slug, c.emoji))
            await query.edit_message_text(
                "Выбери категорию:",
                reply_markup=edit_categories_keyboard(tx_id, categories=_visible_edit),
            )
        return


# ---------------------------------------------------------------------------
# /export
# ---------------------------------------------------------------------------

def _import_preview_keyboard(ready: bool):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    if ready:
        rows = [
            [InlineKeyboardButton("✅ Импортировать", callback_data="import:confirm")],
            [InlineKeyboardButton("✕ Отменить", callback_data="import:cancel")],
        ]
    else:
        rows = [[InlineKeyboardButton("✕ Закрыть", callback_data="import:cancel")]]
    return InlineKeyboardMarkup(rows)


async def import_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "Пришли CSV или XLSX файлом, и я сначала покажу dry-run превью.\n"
        "Сохраняю только после отдельного подтверждения.\n\n"
        "PDF пока только распознаю как неподдерживаемый безопасный сценарий, без автоимпорта.",
        reply_markup=done_keyboard(),
    )


async def document_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from app.services.import_service import ImportService

    message = update.effective_message
    if message is None or message.document is None:
        return

    filename = message.document.file_name or "document"
    detected_format = ImportService.detect_format(filename)
    if detected_format not in ImportService.SUPPORTED_EXTENSIONS:
        return

    placeholder = await message.reply_text("📥 Смотрю файл…")
    telegram_file = await context.bot.get_file(message.document.file_id)
    content = bytes(await telegram_file.download_as_bytearray())

    preview = ImportService().build_preview(filename=filename, content=content)
    if context.user_data is not None:
        context.user_data.pop("pending_import_rows", None)
        context.user_data.pop("pending_import_filename", None)
        if preview.ready_to_import:
            context.user_data["pending_import_rows"] = preview.to_pending_payload()
            context.user_data["pending_import_filename"] = preview.filename

    try:
        await placeholder.delete()
    except BadRequest:
        pass

    await message.reply_text(
        ImportService().render_preview_message(preview),
        reply_markup=_import_preview_keyboard(preview.ready_to_import),
    )


async def import_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except BadRequest:
        pass

    action = query.data.removeprefix("import:")
    if action == "cancel":
        if context.user_data is not None:
            context.user_data.pop("pending_import_rows", None)
            context.user_data.pop("pending_import_filename", None)
        await query.edit_message_text("Импорт отменён.", reply_markup=done_keyboard(back_target="nav:menu"))
        return

    pending_rows = (context.user_data or {}).get("pending_import_rows")
    filename = (context.user_data or {}).get("pending_import_filename", "файл")
    if action != "confirm" or not pending_rows:
        await query.edit_message_text(
            "❌ Превью устарело. Пришли файл заново.",
            reply_markup=done_keyboard(back_target="nav:menu"),
        )
        return

    from datetime import date as date_cls
    from app.services.transaction_service import TransactionService

    with SessionLocal() as db:
        _ensure_user(db, update)
        svc = TransactionService(db)
        for row in pending_rows:
            svc.create_imported(
                update.effective_user.id,
                tx_type=str(row["tx_type"]),
                amount=str(row["amount"]),
                category=str(row["category"]),
                description=(str(row["description"]) if row.get("description") else None),
                source=str(row.get("source") or "text"),
                raw_input=f"import:{filename}:row:{row['row_number']}",
                override_date=date_cls.fromisoformat(str(row["created_at"])),
            )

    if context.user_data is not None:
        context.user_data.pop("pending_import_rows", None)
        context.user_data.pop("pending_import_filename", None)

    await query.edit_message_text(
        f"✅ Импортировал {len(pending_rows)} записей из {filename}.",
        reply_markup=done_keyboard(back_target="nav:operations"),
    )


async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import io

    from app.services.export_service import ExportService
    from app.services.transaction_service import TransactionService

    export_service = ExportService()
    period = "month"
    export_format = "csv"

    for arg in context.args:
        normalized = arg.strip().lower()
        if normalized in {"today", "week", "month", "all"}:
            period = export_service.normalize_period(normalized)
        elif normalized in {"csv", "xlsx", "excel"}:
            export_format = export_service.normalize_format(normalized)

    with SessionLocal() as db:
        _ensure_user(db, update)
        svc = TransactionService(db)
        items = svc.list_transactions(update.effective_user.id, limit=1000, offset=0, period=period)

    if not items:
        period_label = {"today": "сегодня", "week": "за неделю", "month": "за месяц", "all": "за всё время"}.get(period, period)
        await update.effective_message.reply_text(f"Записей {period_label} нет.", reply_markup=done_keyboard())
        return

    artifact = export_service.build(items, period=period, export_format=export_format)

    from telegram import InputFile

    await update.effective_message.reply_document(
        document=InputFile(io.BytesIO(artifact.content), filename=artifact.filename),
        caption=artifact.caption,
    )


# ---------------------------------------------------------------------------
# /plan /planned
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Undo
# ---------------------------------------------------------------------------

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


async def undo_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except BadRequest:
        pass

    ids_str = query.data.split(":", 1)[1] if ":" in query.data else ""
    transaction_ids = [tid.strip() for tid in ids_str.split(",") if tid.strip()]

    if not transaction_ids:
        await query.edit_message_text("❌ Не удалось отменить: ID не найден.", reply_markup=done_keyboard())
        return

    deleted_count = 0
    with SessionLocal() as db:
        from uuid import UUID
        from app.services.transaction_service import TransactionService
        svc = TransactionService(db)
        for tid in transaction_ids:
            try:
                if svc.delete_transaction(update.effective_user.id, UUID(tid)):
                    deleted_count += 1
            except Exception:
                pass

    if deleted_count > 0:
        suffix = f" ({deleted_count} записи)" if deleted_count > 1 else ""
        await query.edit_message_text(f"↩ Отменено{suffix}.", reply_markup=done_keyboard())
    else:
        await query.edit_message_text("Запись уже была удалена или не найдена.", reply_markup=done_keyboard())


# ---------------------------------------------------------------------------
# Category resolution callback — catres:*
# ---------------------------------------------------------------------------

async def catres_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline category resolution buttons (replaces Reply keyboard)."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except BadRequest:
        pass

    parts = query.data.split(":", 2)
    action = parts[1] if len(parts) > 1 else ""
    payload = parts[2] if len(parts) > 2 else ""
    user_id = update.effective_user.id

    with SessionLocal() as db:
        from app.telegram.handlers import TelegramTextFlow, _store_get, _store_pop, _store_set, PendingCategoryResolution
        from app.services.parser_service import ParserService
        _ensure_user(db, update)
        flow = TelegramTextFlow(db)

        pending = _store_get(user_id)
        if pending is None:
            await query.edit_message_text("Сессия истекла. Отправь запись заново.", reply_markup=done_keyboard())
            return

        if action == "cancel":
            _store_pop(user_id)
            await query.edit_message_text("Запись отменена.", reply_markup=done_keyboard())
            return

        if action == "use":
            # payload = category slug
            category = payload
            result = flow._save_from_pending(user_id, pending, category, remove_keyboard=False)
            db.commit()
            tx_id = result.get("saved_transaction_id")
            if tx_id:
                await query.edit_message_text(
                    result["message"], parse_mode="HTML",
                    reply_markup=saved_actions_keyboard(tx_id),
                )
                asyncio.create_task(
                    _auto_remove_keyboard(context.bot, query.message.chat_id, query.message.message_id)
                )
            else:
                await query.edit_message_text(result["message"], parse_mode="HTML", reply_markup=done_keyboard())
            return

        if action == "create":
            # payload = raw_category name
            result = flow._save_from_pending(user_id, payload, pending, payload, remove_keyboard=False)
            db.commit()
            tx_id = result.get("saved_transaction_id")
            if tx_id:
                await query.edit_message_text(
                    result["message"], parse_mode="HTML",
                    reply_markup=saved_actions_keyboard(tx_id),
                )
                asyncio.create_task(
                    _auto_remove_keyboard(context.bot, query.message.chat_id, query.message.message_id)
                )
            else:
                await query.edit_message_text(result["message"], parse_mode="HTML", reply_markup=done_keyboard())
            return

    await query.edit_message_text("Не удалось обработать выбор.", reply_markup=done_keyboard())


# ---------------------------------------------------------------------------
# Low confidence callback — lowconf:*
# ---------------------------------------------------------------------------

async def lowconf_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle low-confidence inline buttons (type and category selection)."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except BadRequest:
        pass

    # lowconf:cancel
    # lowconf:expense:<amount>  or  lowconf:income:<amount>
    # lowconf:cat:<type>:<amount>:<slug>
    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "cancel":
        await query.edit_message_text("Запись отменена.", reply_markup=done_keyboard())
        return

    if action in ("expense", "income"):
        # User chose type — now show category keyboard
        amount = parts[2] if len(parts) > 2 else "0"
        user_id = update.effective_user.id
        with SessionLocal() as _cat_db:
            from app.services.category_service import CategoryService
            _ensure_user(_cat_db, update)
            _cat_svc = CategoryService(_cat_db)
            _cat_svc.ensure_seeded(user_id)
            _visible = [c.slug for c in _cat_svc.get_visible_for_type(user_id, action)]
        await query.edit_message_text(
            f"{'↘ Расход' if action == 'expense' else '↗ Доход'} {amount} ₽ — выбери категорию:",
            reply_markup=low_confidence_category_keyboard(action, amount, categories=_visible),
        )
        return

    if action == "cat":
        # lowconf:cat:<type>:<amount>:<slug>
        tx_type = parts[2] if len(parts) > 2 else "expense"
        amount  = parts[3] if len(parts) > 3 else "0"
        slug    = parts[4] if len(parts) > 4 else "other"
        user_id = update.effective_user.id

        with SessionLocal() as db:
            _ensure_user(db, update)
            from decimal import Decimal
            from app.schemas.parser import ParseResult
            from app.services.transaction_service import TransactionService
            svc = TransactionService(db)
            parsed = ParseResult(
                matched=True,
                confidence=0.7,
                confidence_label="medium",
                transaction_type=tx_type,
                amount=Decimal(amount),
                category=slug,
                description=None,
                pattern="manual",
                raw_input=f"{tx_type} {amount} {slug}",
            )
            item = svc.create_from_parse(telegram_user_id=user_id, source="text", parsed=parsed)
            summary = svc.get_summary(telegram_user_id=user_id, period="month")
            db.commit()

        operation_label = "доход" if tx_type == "income" else "расход"
        balance = summary.balance if summary.balance.startswith("-") else f"+{summary.balance}"
        msg = formatter.format_saved(operation_label, str(item.amount), item.category, balance)
        tx_id = str(item.id)
        await query.edit_message_text(
            msg, parse_mode="HTML",
            reply_markup=saved_actions_keyboard(tx_id),
        )
        asyncio.create_task(
            _auto_remove_keyboard(context.bot, query.message.chat_id, query.message.message_id)
        )
        return

    await query.edit_message_text("Не удалось обработать выбор.", reply_markup=done_keyboard())


# ---------------------------------------------------------------------------
# Evening check-in callback — checkin:*
# ---------------------------------------------------------------------------

async def checkin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except BadRequest:
        pass

    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "none":
        await query.edit_message_text("👍 Хорошо, пустой день.", reply_markup=done_keyboard())
        return

    if action == "more":
        from app.services.reminder_service import ReminderService
        from app.services.category_service import CategoryService
        with SessionLocal() as db:
            _ensure_user(db, update)
            user_repo = UserRepository(db)
            user = user_repo.get_by_telegram_id(update.effective_user.id)
            if user is None:
                await query.edit_message_text("❌ Ошибка.", reply_markup=done_keyboard())
                return
            _, top_categories = ReminderService(db).build_evening_checkin(user)
            cat_svc = CategoryService(db)
            cat_svc.ensure_seeded(update.effective_user.id)
            visible_slugs = {c.slug for c in cat_svc.get_visible_for_type(update.effective_user.id, "expense")}
            filtered = [c for c in top_categories if c in visible_slugs]
        await query.edit_message_text(
            "🌙 Что ещё потратил?",
            reply_markup=evening_checkin_keyboard(filtered or top_categories),
        )
        return

    if action == "cat" and len(parts) > 2:
        cat_slug = parts[2]
        cat_label = formatter.category_label(cat_slug)
        # Show quick amount buttons
        await query.edit_message_text(
            f"{cat_label} — выбери сумму:",
            reply_markup=evening_checkin_amount_keyboard(cat_slug),
        )
        return

    if action == "amount" and len(parts) > 3:
        # checkin:amount:<category>:<amount>
        cat_slug = parts[2]
        amount   = parts[3]
        user_id  = update.effective_user.id

        with SessionLocal() as db:
            _ensure_user(db, update)
            from decimal import Decimal
            from app.schemas.parser import ParseResult
            from app.services.transaction_service import TransactionService
            svc = TransactionService(db)
            parsed = ParseResult(
                matched=True,
                confidence=0.9,
                confidence_label="high",
                transaction_type="expense",
                amount=Decimal(amount),
                category=cat_slug,
                description=None,
                pattern="checkin",
                raw_input=f"checkin {amount} {cat_slug}",
            )
            item = svc.create_from_parse(telegram_user_id=user_id, source="text", parsed=parsed)
            summary = svc.get_summary(telegram_user_id=user_id, period="month")
            db.commit()

        balance = summary.balance if summary.balance.startswith("-") else f"+{summary.balance}"
        msg = formatter.format_saved("расход", str(item.amount), item.category, balance)
        from app.telegram.keyboards import evening_checkin_done_keyboard
        await query.edit_message_text(
            msg, parse_mode="HTML",
            reply_markup=evening_checkin_done_keyboard(),
        )
        return

    if action == "custom" and len(parts) > 2:
        # User wants to enter custom amount
        cat_slug = parts[2]
        if context.user_data is not None:
            context.user_data["awaiting_checkin_category"] = cat_slug
        cat_label = formatter.category_label(cat_slug)
        await query.edit_message_text(f"{cat_label} — введи сумму:", reply_markup=cancel_keyboard("checkin:none"))
        return

    await query.edit_message_text("Хорошо!", reply_markup=done_keyboard())


# ---------------------------------------------------------------------------
# Nav callback — nav:*
# ---------------------------------------------------------------------------

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
        context.user_data.pop("advisor_history", None)
        context.user_data.pop("advisor_last_active", None)

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
                # Re-set mode (was cleared above for other nav, re-set here for input sections)
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


async def advisor_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from app.telegram.keyboards import done_keyboard

    query = update.callback_query
    if query is None:
        return
    try:
        await query.answer()
    except BadRequest:
        pass

    data = query.data or ""
    if not data.startswith("advisor:scenario:"):
        return

    slug = data.removeprefix("advisor:scenario:")
    if slug == "export":
        await update.effective_message.reply_text(
            "Экспорт уже доступен:\n• /export month\n• /export xlsx month\n• /export csv week\n• /export xlsx all\n\n"
            "Импорт тоже есть: просто пришли CSV/XLSX файлом, я сначала покажу dry-run превью.",
            reply_markup=done_keyboard(back_target="nav:advisor"),
        )
        return

    question = _ADVISOR_SCENARIO_QUESTIONS.get(slug)
    if not question:
        await update.effective_message.reply_text(
            "Не понял сценарий советника. Попробуй выбрать ещё раз.",
            reply_markup=done_keyboard(back_target="nav:advisor"),
        )
        return

    context.user_data["mode"] = "advisor"
    context.user_data.setdefault("advisor_history", [])
    context.user_data["advisor_last_active"] = _time_now()
    await _answer_advisor_question(update, context, question, dialog_mode=True)


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


# ---------------------------------------------------------------------------
# /budget
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# /recurring
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Settings callback — settings:*
# ---------------------------------------------------------------------------

async def settings_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except BadRequest:
        pass

    action = query.data.split(":", 1)[1] if ":" in query.data else ""

    if action == "budget_day":
        context.user_data["awaiting_setting"] = "budget_day"
        await query.edit_message_text(
            "📅 Введи число начала бюджетного периода (1–28).\n"
            "Например: 1 — с первого числа каждого месяца.",
            reply_markup=cancel_keyboard("nav:settings"),
        )
    elif action == "reminders":
        from app.telegram.keyboards import reminders_inline_keyboard
        await query.edit_message_text(
            "🔔 *Напоминания*\n\nВыбери что настроить:",
            reply_markup=reminders_inline_keyboard(),
            parse_mode="Markdown",
        )
    elif action == "budget":
        context.user_data["awaiting_setting"] = "budget"
        await query.edit_message_text(
            "💰 Введи месячный бюджет в рублях (например: 50000).\n"
            "Или отправь 0 чтобы убрать бюджет.",
            reply_markup=cancel_keyboard("nav:settings"),
        )
    elif action == "morning":
        context.user_data["awaiting_setting"] = "morning"
        await query.edit_message_text(
            "⏰ Введи время утреннего напоминания в формате ЧЧ:ММ (например: 09:00).\n"
            "Или отправь «выкл» чтобы отключить.",
            reply_markup=cancel_keyboard("nav:settings"),
        )
    elif action == "evening":
        context.user_data["awaiting_setting"] = "evening"
        await query.edit_message_text(
            "🌙 Введи время вечернего напоминания в формате ЧЧ:ММ (например: 21:00).\n"
            "Или отправь «выкл» чтобы отключить.",
            reply_markup=cancel_keyboard("nav:settings"),
        )
    elif action == "timezone":
        context.user_data["awaiting_setting"] = "timezone"
        await query.edit_message_text(
            "🌍 Введи часовой пояс (например: Europe/Moscow, Asia/Yekaterinburg).\n"
            "Полный список: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones",
            reply_markup=cancel_keyboard("nav:settings"),
        )
    elif action == "disable_all":
        with SessionLocal() as db:
            user_repo = UserRepository(db)
            user = user_repo.get_by_telegram_id(update.effective_user.id)
            if user:
                user_repo.update_settings(user, reminder_morning=None, reminder_evening=None)
                user_repo.commit()
        await query.edit_message_text("✅ Все напоминания отключены. Включить обратно: /settings", reply_markup=done_keyboard(back_target="nav:settings"))


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Free-form input handlers (planned / recurring)
# ---------------------------------------------------------------------------

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


# Text message handler
# ---------------------------------------------------------------------------

async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.effective_message.text or ""

    # Handle input modes (planned/recurring/budget free-form input)
    mode = context.user_data.get("mode") if context.user_data else None
    if mode == "planned_input":
        await _handle_planned_input(update, context, text.strip())
        return
    if mode == "recurring_input":
        await _handle_recurring_input(update, context, text.strip())
        return
    if mode == "budget_total_input":
        await _handle_budget_total_input(update, context, text.strip())
        return
    if mode == "budget_category_input":
        await _handle_budget_category_input(update, context, text.strip())
        return
    if mode == "advisor":
        await _handle_advisor_text(update, context, text.strip())
        return

    # Handle settings input
    awaiting = context.user_data.get("awaiting_setting") if context.user_data else None
    if awaiting:
        del context.user_data["awaiting_setting"]
        result = _handle_settings_input(update.effective_user.id, awaiting, text.strip())
        await update.effective_message.reply_text(result, reply_markup=done_keyboard(back_target="nav:settings"))
        return

    # Handle /edit awaiting amount input
    awaiting_edit = context.user_data.get("awaiting_edit") if context.user_data else None
    if awaiting_edit and awaiting_edit.get("field") == "amount":
        del context.user_data["awaiting_edit"]
        raw_amount = text.strip().replace(",", ".")
        try:
            amount = float(raw_amount)
            if amount <= 0:
                raise ValueError
        except ValueError:
            await update.effective_message.reply_text(
                f"❌ Не понял сумму: {text.strip()}\nВведи число, например: 750",
                reply_markup=done_keyboard(),
            )
            return

        tx_id = awaiting_edit["tx_id"]
        with SessionLocal() as db:
            from uuid import UUID
            from app.services.transaction_service import TransactionService
            from app.schemas.transaction import TransactionUpdateRequest
            svc = TransactionService(db)
            updated = svc.update_transaction(
                update.effective_user.id, UUID(tx_id),
                TransactionUpdateRequest(amount=f"{amount:.2f}"),
            )
        if updated:
            await update.effective_message.reply_text(
                f"✅ Сумма изменена: {amount:,.2f} ₽",
                reply_markup=edit_item_keyboard(tx_id),
            )
        else:
            await update.effective_message.reply_text("❌ Запись не найдена.", reply_markup=done_keyboard())
        return

    # Handle planned expense custom amount confirmation
    awaiting_planned_amount = context.user_data.get("awaiting_planned_amount") if context.user_data else None
    if awaiting_planned_amount:
        del context.user_data["awaiting_planned_amount"]
        raw_amount = text.strip().replace(",", ".")
        try:
            amount = float(raw_amount)
            if amount <= 0:
                raise ValueError
        except ValueError:
            await update.effective_message.reply_text("❌ Не понял сумму. Введи число, например: 2500", reply_markup=done_keyboard())
            return

        with SessionLocal() as db:
            _ensure_user(db, update)
            service = TelegramBotService(db)
            response = service.confirm_planned_expense(
                telegram_user_id=update.effective_user.id,
                planned_expense_id=int(awaiting_planned_amount),
                actual_amount=amount,
            )
        await update.effective_message.reply_text(response["message"], reply_markup=done_keyboard())
        return

    awaiting_planned_date = context.user_data.get("awaiting_planned_date") if context.user_data else None
    if awaiting_planned_date:
        del context.user_data["awaiting_planned_date"]
        raw_date = text.strip()
        try:
            if "-" in raw_date:
                from datetime import date as date_cls
                parsed_date = date_cls.fromisoformat(raw_date)
            else:
                from datetime import date as date_cls
                day, month = map(int, raw_date.split("."))
                parsed_date = date_cls(date_cls.today().year, month, day)
            if parsed_date < date.today():
                raise ValueError
        except Exception:
            await update.effective_message.reply_text("❌ Не понял дату. Формат: 15.04 или 2030-04-15", reply_markup=done_keyboard())
            return

        with SessionLocal() as db:
            _ensure_user(db, update)
            service = TelegramBotService(db)
            response = service.update_planned_date(
                telegram_user_id=update.effective_user.id,
                planned_expense_id=int(awaiting_planned_date),
                planned_date=parsed_date.isoformat(),
            )
        await update.effective_message.reply_text(response["message"], reply_markup=done_keyboard())
        return

    # --- Category: rename ---
    awaiting_rename = context.user_data.get("awaiting_category_rename") if context.user_data else None
    if awaiting_rename:
        del context.user_data["awaiting_category_rename"]
        with SessionLocal() as db:
            _ensure_user(db, update)
            from app.services.category_service import CategoryService
            svc = CategoryService(db)
            svc.ensure_seeded(update.effective_user.id)
            cat = svc.rename(update.effective_user.id, awaiting_rename, text.strip())
        if cat:
            await update.effective_message.reply_text(
                f"✅ Переименовано: {cat.emoji} {cat.name_ru}",
                reply_markup=done_keyboard(),
            )
        else:
            _ctx = (context.user_data or {}).get("categories_ctx", {})
            _bt = f"nav:categories:{_ctx['type']}:{_ctx['page']}" if _ctx.get("type") else "nav:categories"
            await update.effective_message.reply_text("❌ Категория не найдена.", reply_markup=done_keyboard(back_target=_bt))
        return

    # --- Category: change emoji ---
    awaiting_emoji = context.user_data.get("awaiting_category_emoji") if context.user_data else None
    if awaiting_emoji:
        del context.user_data["awaiting_category_emoji"]
        with SessionLocal() as db:
            _ensure_user(db, update)
            from app.services.category_service import CategoryService
            svc = CategoryService(db)
            svc.ensure_seeded(update.effective_user.id)
            try:
                cat = svc.change_emoji(update.effective_user.id, awaiting_emoji, text.strip())
            except ValueError as e:
                _ctx = (context.user_data or {}).get("categories_ctx", {})
                _bt = f"nav:categories:{_ctx['type']}:{_ctx['page']}" if _ctx.get("type") else "nav:categories"
                await update.effective_message.reply_text(f"❌ {e} Попробуй ещё раз.", reply_markup=done_keyboard(back_target=_bt))
                context.user_data["awaiting_category_emoji"] = awaiting_emoji
                return
        if cat:
            await update.effective_message.reply_text(f"✅ Emoji обновлён: {cat.emoji} {cat.name_ru}", reply_markup=done_keyboard())
        else:
            _ctx = (context.user_data or {}).get("categories_ctx", {})
            _bt = f"nav:categories:{_ctx['type']}:{_ctx['page']}" if _ctx.get("type") else "nav:categories"
            await update.effective_message.reply_text("❌ Категория не найдена.", reply_markup=done_keyboard(back_target=_bt))
        return

    # --- Category: add (name or emoji step) ---
    awaiting_add = context.user_data.get("awaiting_category_add") if context.user_data else None
    if awaiting_add == "name":
        context.user_data["awaiting_category_add"] = "emoji"
        context.user_data["pending_category_add"] = {"name_ru": text.strip(), "emoji": ""}
        await update.effective_message.reply_text(
            f"Название: «{text.strip()}»\n\nТеперь отправь emoji для этой категории:",
            reply_markup=cancel_keyboard("nav:categories"),
        )
        return
    if awaiting_add == "emoji":
        from app.services.category_service import _is_emoji
        emoji_input = text.strip()
        if not _is_emoji(emoji_input):
            await update.effective_message.reply_text(
                "❌ Не похоже на emoji. Попробуй ещё раз (например: 🏋 или ⚽):",
                reply_markup=cancel_keyboard("nav:categories"),
            )
            return
        pending = context.user_data.get("pending_category_add", {})
        pending["emoji"] = emoji_input
        context.user_data["pending_category_add"] = pending
        del context.user_data["awaiting_category_add"]
        from app.telegram.keyboards import category_type_keyboard
        await update.effective_message.reply_text(
            f"Emoji: {emoji_input}\n\nВыбери тип категории:",
            reply_markup=category_type_keyboard(),
        )
        return

    awaiting_recurring_amount = context.user_data.get("awaiting_recurring_amount") if context.user_data else None
    if awaiting_recurring_amount:
        del context.user_data["awaiting_recurring_amount"]
        raw_amount = text.strip().replace(",", ".")
        try:
            amount = float(raw_amount)
            if amount <= 0:
                raise ValueError
        except ValueError:
            await update.effective_message.reply_text("❌ Не понял сумму. Введи число, например: 2500", reply_markup=done_keyboard())
            return

        with SessionLocal() as db:
            _ensure_user(db, update)
            service = TelegramBotService(db)
            response = service.update_recurring_amount(
                telegram_user_id=update.effective_user.id,
                recurring_id=int(awaiting_recurring_amount),
                amount=amount,
            )
        await update.effective_message.reply_text(response["message"], reply_markup=done_keyboard())
        return

    awaiting_recurring_schedule = context.user_data.get("awaiting_recurring_schedule") if context.user_data else None
    if awaiting_recurring_schedule:
        del context.user_data["awaiting_recurring_schedule"]
        parsed = parse_recurring_schedule_args(text.strip().split())
        if isinstance(parsed, str):
            await update.effective_message.reply_text(parsed, reply_markup=done_keyboard())
            return
        with SessionLocal() as db:
            _ensure_user(db, update)
            service = TelegramBotService(db)
            response = service.update_recurring_schedule(
                telegram_user_id=update.effective_user.id,
                recurring_id=int(awaiting_recurring_schedule),
                frequency=parsed["frequency"],
                day_value=parsed["day_value"],
            )
        await update.effective_message.reply_text(response["message"], reply_markup=done_keyboard())
        return

    # Handle evening check-in custom amount
    awaiting_checkin = context.user_data.get("awaiting_checkin_category") if context.user_data else None
    if awaiting_checkin:
        del context.user_data["awaiting_checkin_category"]
        raw_amount = text.strip().replace(",", ".")
        try:
            amount = float(raw_amount)
            if amount <= 0:
                raise ValueError
        except ValueError:
            await update.effective_message.reply_text("❌ Не понял сумму. Введи число, например: 500", reply_markup=done_keyboard())
            return

        with SessionLocal() as db:
            _ensure_user(db, update)
            from decimal import Decimal
            from app.schemas.parser import ParseResult
            from app.services.transaction_service import TransactionService
            svc = TransactionService(db)
            parsed = ParseResult(
                matched=True,
                confidence=0.9,
                confidence_label="high",
                transaction_type="expense",
                amount=Decimal(str(amount)),
                category=awaiting_checkin,
                description=None,
                pattern="checkin",
                raw_input=f"checkin {amount} {awaiting_checkin}",
            )
            item = svc.create_from_parse(telegram_user_id=update.effective_user.id, source="text", parsed=parsed)
            summary = svc.get_summary(telegram_user_id=update.effective_user.id, period="month")
            db.commit()

        balance = summary.balance if summary.balance.startswith("-") else f"+{summary.balance}"
        msg = formatter.format_saved("расход", str(item.amount), item.category, balance)
        await _send_saved_with_undo(update, context, msg, [str(item.id)])
        return

    with SessionLocal() as db:
        _ensure_user(db, update)
        user_repo = UserRepository(db)
        user = user_repo.get_by_telegram_id(update.effective_user.id)
        service = TelegramBotService(db)
        response = service.process_text_message(update.effective_user.id, text)

        budget_alert = None
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

            saved_category = response.get("saved_category")
            if saved_category:
                budget_alert = _get_budget_alert(db, user.telegram_user_id, str(saved_category))

    # Route response to correct handler
    action = response.get("action", "")

    if action == "confirm_voice" and response.get("voice_log_id"):
        await update.effective_message.reply_text(
            response["message"],
            reply_markup=voice_confirmation_keyboard(response["voice_log_id"]),
            parse_mode="HTML",
        )
        return

    if action == "clarify_category_choice":
        await update.effective_message.reply_text(
            response["message"],
            reply_markup=category_resolution_keyboard(
                str(response.get("raw_category", "")),
                list(response.get("suggestions", [])),
            ),
        )
        return

    if action == "clarify_low":
        # Low confidence — show inline type selector
        await update.effective_message.reply_text(
            response["message"],
            reply_markup=low_confidence_keyboard(str(response.get("amount", "0"))),
        )
        return

    if action == "saved" and response.get("saved_transaction_id"):
        tx_id_str = response["saved_transaction_id"]
        saved_msg = response["message"]
        if budget_alert:
            saved_msg += f"\n{budget_alert}"
        await _send_saved_with_undo(
            update, context,
            saved_msg,
            [tx_id_str],
            correction_tx_id=tx_id_str,
        )
        # Real-time insight (max once per day, silent on error)
        try:
            from app.services.insight_service import InsightService
            with SessionLocal() as insight_db:
                user_obj = UserRepository(insight_db).get_by_telegram_id(
                    update.effective_user.id
                )
                if user_obj:
                    insight_text = InsightService(insight_db).get_realtime_insight(
                        user_obj, None
                    )
                    if insight_text:
                        await update.effective_message.reply_text(
                            insight_text, parse_mode="HTML", reply_markup=done_keyboard()
                        )
        except Exception:
            logger.exception("realtime insight failed")
        return

    if action == "advisor":
        from app.telegram.keyboards import advisor_keyboard
        await update.effective_message.reply_text(
            response["message"],
            parse_mode="HTML",
            reply_markup=advisor_keyboard(),
        )
        return

    await update.effective_message.reply_text(
        response["message"],
        parse_mode="HTML",
        reply_markup=done_keyboard(),
    )


# ---------------------------------------------------------------------------
# Voice message handler
# ---------------------------------------------------------------------------

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

    try:
        await context.bot.delete_message(chat_id=placeholder.chat_id, message_id=placeholder.message_id)
    except BadRequest as exc:
        logger.warning("voice placeholder delete failed: %s", exc)

    action = response.get("action", "")

    if action == "confirm_voice" and response.get("voice_log_id"):
        await update.effective_message.reply_text(
            response["message"],
            reply_markup=voice_confirmation_keyboard(response["voice_log_id"]),
            parse_mode="HTML",
        )
        return

    if action == "clarify_category_choice":
        await update.effective_message.reply_text(
            response["message"],
            reply_markup=category_resolution_keyboard(
                str(response.get("raw_category", "")),
                list(response.get("suggestions", [])),
            ),
        )
        return

    await update.effective_message.reply_text(response["message"], parse_mode="HTML", reply_markup=done_keyboard())


# ---------------------------------------------------------------------------
# Voice callback — voice:*
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Delete callback — delete:* / deleteall:*
# ---------------------------------------------------------------------------

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

    await query.edit_message_text(response["message"], reply_markup=done_keyboard())


# ---------------------------------------------------------------------------
# Settings input helper
# ---------------------------------------------------------------------------

def _handle_settings_input(telegram_user_id: int, setting: str, value: str) -> str:
    with SessionLocal() as db:
        user_repo = UserRepository(db)
        user = user_repo.get_by_telegram_id(telegram_user_id)
        if user is None:
            return "❌ Не нашёл пользователя."

        if setting == "budget_day":
            try:
                day = int(value)
                if not (1 <= day <= 28):
                    return "❌ Число должно быть от 1 до 28."
                user_repo.update_settings(user, budget_start_day=day)
                user_repo.commit()
                return f"✅ Начало периода: {day}-е число"
            except ValueError:
                return "❌ Введи число от 1 до 28."

        elif setting == "budget":
            try:
                amount = float(value.replace(",", ".").replace(" ", ""))
                if amount <= 0:
                    user_repo.update_settings(user, budget_amount=None)
                    user_repo.commit()
                    return "✅ Бюджет убран."
                user_repo.update_settings(user, budget_amount=amount)
                user_repo.commit()
                return f"✅ Бюджет установлен: {amount:,.0f} ₽/мес"
            except ValueError:
                return "❌ Не понял сумму. Введи число, например: 50000"

        elif setting == "morning":
            if value.lower() in ("выкл", "off", "0", "нет"):
                user_repo.update_settings(user, reminder_morning=None)
                user_repo.commit()
                return "✅ Утреннее напоминание отключено."
            if _validate_time(value):
                user_repo.update_settings(user, reminder_morning=value)
                user_repo.commit()
                return f"✅ Утреннее напоминание: {value}"
            return "❌ Формат: ЧЧ:ММ (например: 09:00)"

        elif setting == "evening":
            if value.lower() in ("выкл", "off", "0", "нет"):
                user_repo.update_settings(user, reminder_evening=None)
                user_repo.commit()
                return "✅ Вечернее напоминание отключено."
            if _validate_time(value):
                user_repo.update_settings(user, reminder_evening=value)
                user_repo.commit()
                return f"✅ Вечернее напоминание: {value}"
            return "❌ Формат: ЧЧ:ММ (например: 21:00)"

        elif setting == "timezone":
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
            try:
                ZoneInfo(value)
                user_repo.update_settings(user, timezone=value)
                user_repo.commit()
                return f"✅ Часовой пояс: {value}"
            except (ZoneInfoNotFoundError, KeyError):
                return f"❌ Неизвестный часовой пояс: {value}. Пример: Europe/Moscow"

    return "❌ Неизвестная настройка."


def _validate_time(value: str) -> bool:
    try:
        parts = value.split(":")
        if len(parts) != 2:
            return False
        h, m = int(parts[0]), int(parts[1])
        return 0 <= h <= 23 and 0 <= m <= 59
    except (ValueError, IndexError):
        return False


# ---------------------------------------------------------------------------
# Budget free-form input handlers
# ---------------------------------------------------------------------------

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


async def _handle_advisor_text(update: Update, context: ContextTypes.DEFAULT_TYPE, question: str) -> None:
    """Handle text input in advisor mode — route to FinancialQAService with history."""
    await _answer_advisor_question(update, context, question, dialog_mode=True)


# ---------------------------------------------------------------------------
# Budget callback handler
# ---------------------------------------------------------------------------

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


def run_polling() -> None:
    app = build_application()
    logger.info("run_polling start")
    try:
        app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
    finally:
        logger.info("run_polling exit")
