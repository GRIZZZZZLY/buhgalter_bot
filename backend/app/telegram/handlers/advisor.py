import logging

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from app.db.session import SessionLocal
from app.repositories.event_repository import log_event
from app.services.financial_qa_service import FinancialQAService, ResponseMode
from app.telegram.formatter import AdvisorFormatter, TreasuryFormatter
from app.telegram.keyboards import (
    advisor_apply_keyboard,
    advisor_session_keyboard,
    back_keyboard,
    done_keyboard,
    undo_keyboard,
)
from app.telegram.handlers.common import _ensure_user, _time_now

logger = logging.getLogger("finance_bot.telegram")
formatter = TreasuryFormatter()

_ADVISOR_TIMEOUT = 600  # 10 minutes
_PENDING_ACTION_TTL = 3600  # 1 hour — pending_action expires after this
_UNDO_TTL = 60  # seconds — window for undoing a reversible action
_SHOWN_RECOMMENDATIONS_KEY = "shown_recommendation_types"
_MAX_SESSION_RECOMMENDATIONS = 5

_ADVISOR_ONBOARDING = (
    "🧠 *Финансовый советник*\n\n"
    "Ты можешь:\n"
    "• задать вопрос по своим финансам\n"
    "• импортировать CSV/XLSX и анализировать отчёт\n"
    "• быстро проверить бюджеты, риски и ближайшие платежи\n"
    "• говорить текстом или голосом\n\n"
    "Начни так:\n"
    "• импортируй файл, если хочешь анализ по выписке\n"
    "• или просто задай вопрос ниже"
)

_ADVISOR_SCENARIO_QUESTIONS = {
    "top_expenses": "Покажи топ расходов за этот месяц и на что уходит больше всего денег.",
    "budget_risks": "Где я уже вылезаю из бюджета и по каким категориям риск перерасхода?",
    "upcoming": "Какие платежи и плановые траты у меня скоро?",
    "trends_3m": "Покажи динамику расходов за 3 месяца и что изменилось.",
    "cut_costs": "Что сейчас разумнее всего сократить по моим расходам?",
    "export": "EXPORT_PLACEHOLDER",
}


def _track_shown_recommendation(context: ContextTypes.DEFAULT_TYPE, action_type: str) -> None:
    shown: list[str] = list(context.user_data.get(_SHOWN_RECOMMENDATIONS_KEY, []))
    if action_type not in shown:
        shown.append(action_type)
    context.user_data[_SHOWN_RECOMMENDATIONS_KEY] = shown[-_MAX_SESSION_RECOMMENDATIONS:]


def _format_advisor_payload(
    answer: str,
    basis: list[str] | None = None,
    warnings: list[str] | None = None,
    confidence: str | None = None,
    recommendations: list[str] | None = None,
    response_mode: ResponseMode = ResponseMode.FULL,
    action_type: str | None = None,
    _payload_obj=None,
) -> str:
    if response_mode == ResponseMode.SHORT:
        return answer.strip()

    if response_mode == ResponseMode.NORMAL:
        parts = [answer.strip()]
        if warnings:
            parts.append("⚠️ " + " · ".join(warnings[:2]))
        if recommendations:
            primary = recommendations[0]
            title = str(primary)
            parts.append(f"→ {title}")
        return "\n\n".join(p for p in parts if p)

    # FULL mode: use action-type-specific renderer when action_type is provided
    if action_type and _payload_obj is not None:
        return AdvisorFormatter().format_for_action_type(_payload_obj, action_type)

    # FULL mode: original full rendering
    parts = [answer.strip()]
    if recommendations:
        parts.append("\nСледующий ход:\n" + "\n".join(f"• {item}" for item in recommendations[:3]))
    if basis:
        parts.append("\nОснова:\n" + "\n".join(f"• {item}" for item in basis[:3]))
    if warnings:
        parts.append("\nРиски / ограничения:\n" + "\n".join(f"• {item}" for item in warnings[:3]))
    if confidence:
        conf_map = {"low": "низкая", "medium": "средняя", "high": "высокая"}
        parts.append(f"\nУверенность: {conf_map.get(confidence, confidence)}")
    return "\n".join(part for part in parts if part)


def _clear_advisor_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in (
        "advisor_history",
        "advisor_last_active",
        "last_advisor_snapshot",
        "last_advisor_analytics",
        "last_advisor_recommendations",
        "last_advisor_generated_at",
        "last_advisor_payload_version",
        "last_advisor_action_type",
        "advisor_session_start",
        "advisor_session_topics",
        "advisor_actions_taken",
    ):
        context.user_data.pop(key, None)


def _advisor_state_is_fresh(context: ContextTypes.DEFAULT_TYPE) -> bool:
    generated_at = context.user_data.get("last_advisor_generated_at", 0)
    if not generated_at:
        return False
    return (_time_now() - float(generated_at)) <= _ADVISOR_TIMEOUT


async def _enter_advisor_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from app.telegram.keyboards import advisor_onboarding_keyboard

    _clear_advisor_state(context)
    context.user_data["mode"] = "advisor"
    context.user_data["advisor_history"] = []
    context.user_data["advisor_last_active"] = _time_now()
    context.user_data["advisor_session_start"] = _time_now()
    context.user_data["advisor_session_topics"] = []
    context.user_data["advisor_actions_taken"] = []
    await update.effective_message.reply_text(
        _ADVISOR_ONBOARDING,
        reply_markup=advisor_onboarding_keyboard(),
        parse_mode="Markdown",
    )


async def _answer_advisor_question(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    question: str,
    *,
    dialog_mode: bool,
) -> None:
    message = update.effective_message
    if message is None:
        return

    query = update.callback_query
    use_edit = bool(query and query.message)

    if dialog_mode:
        last_active = context.user_data.get("advisor_last_active", 0)
        if (_time_now() - last_active) > _ADVISOR_TIMEOUT:
            context.user_data["advisor_history"] = []
            context.user_data["advisor_session_topics"] = []
            context.user_data["advisor_actions_taken"] = []
            context.user_data["advisor_session_start"] = _time_now()
        history: list[dict] = list(context.user_data.get("advisor_history", []))
    else:
        history = []

    placeholder = None
    if use_edit:
        try:
            await query.edit_message_text("🤔 Анализирую…")
        except BadRequest:
            use_edit = False

    if not use_edit:
        try:
            placeholder = await message.reply_text("🤔 Анализирую…")
        except Exception:
            placeholder = None

    exclude_types: list[str] = list(context.user_data.get(_SHOWN_RECOMMENDATIONS_KEY, []))
    session_ctx = {
        "advisor_session_topics": context.user_data.get("advisor_session_topics", []),
        "advisor_actions_taken": context.user_data.get("advisor_actions_taken", []),
    }
    with SessionLocal() as db:
        _ensure_user(db, update)
        payload = FinancialQAService(db).answer_payload(
            question,
            update.effective_user.id,
            history=history,
            exclude_action_types=exclude_types or None,
            session_context=session_ctx if dialog_mode else None,
        )

    _primary = payload.recommendation_snapshot.primary if payload.recommendation_snapshot else None
    _action_type = _primary.action_type if _primary else None
    if payload.next_step:
        answer = AdvisorFormatter().format_action_proposal(payload)
    else:
        answer = _format_advisor_payload(
            payload.answer,
            basis=payload.basis,
            warnings=payload.warnings,
            confidence=payload.confidence,
            recommendations=payload.recommendations,
            response_mode=payload.response_mode,
            action_type=_action_type,
            _payload_obj=payload,
        )

    context.user_data["last_advisor_snapshot"] = payload.snapshot
    context.user_data["last_advisor_analytics"] = payload.analytics
    context.user_data["last_advisor_recommendations"] = payload.recommendation_snapshot
    context.user_data["last_advisor_generated_at"] = _time_now()
    context.user_data["last_advisor_payload_version"] = payload.payload_version
    primary = payload.recommendation_snapshot.primary if payload.recommendation_snapshot else None
    context.user_data["last_advisor_action_type"] = primary.action_type if primary else None
    if primary:
        _track_shown_recommendation(context, primary.action_type)

    # Store pending_action for "Применить" button (with TTL)
    if payload.can_apply and payload.apply_action:
        context.user_data["pending_action"] = payload.apply_action
        context.user_data["pending_action_expires_at"] = _time_now() + _PENDING_ACTION_TTL
    else:
        context.user_data.pop("pending_action", None)
        context.user_data.pop("pending_action_expires_at", None)

    if dialog_mode:
        topic_key = context.user_data.get("last_advisor_action_type") or "general"
        topics: list[str] = list(context.user_data.get("advisor_session_topics", []))
        if topic_key not in topics:
            topics.append(topic_key)
        context.user_data["advisor_session_topics"] = topics[-8:]

    logger.info(
        "advisor state updated: version=%s action_type=%s fresh=%s",
        payload.payload_version,
        context.user_data.get("last_advisor_action_type"),
        _advisor_state_is_fresh(context),
    )

    if dialog_mode:
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer})
        if len(history) > 10:
            history = history[2:]
        context.user_data["advisor_history"] = history
        context.user_data["advisor_last_active"] = _time_now()
        reply_markup = advisor_session_keyboard(payload.recommendation_snapshot)
    else:
        primary = payload.recommendation_snapshot.primary if payload.recommendation_snapshot else None
        action_type = primary.action_type if primary else None
        category: str | None = primary.category if primary else None
        reply_markup = advisor_apply_keyboard(payload, action_type=action_type, category=category)

    if use_edit:
        try:
            await query.edit_message_text(answer, reply_markup=reply_markup)
            return
        except BadRequest:
            pass

    if placeholder is not None:
        try:
            await placeholder.edit_text(answer, reply_markup=reply_markup)
            return
        except Exception:
            pass

    await message.reply_text(answer, reply_markup=reply_markup)


async def apply_action_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show confirm screen for pending_action. Agent v1 — does not execute yet."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    expires_at = context.user_data.get("pending_action_expires_at", 0)
    if _time_now() > expires_at:
        context.user_data.pop("pending_action", None)
        context.user_data.pop("pending_action_expires_at", None)
        await query.answer("Действие устарело. Задай вопрос заново.", show_alert=True)
        return

    pending_action = context.user_data.get("pending_action")
    if not pending_action:
        await query.answer("Действие устарело. Задай вопрос заново.", show_alert=True)
        return

    confirm_keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "✅ Подтвердить",
            callback_data=f"apply_confirm:{pending_action.action_type.value}",
        ),
        InlineKeyboardButton("❌ Отмена", callback_data="apply_cancel"),
    ]])
    reversible_note = "↩ Можно отменить после выполнения" if pending_action.is_reversible else "⚠️ Действие нельзя отменить"
    text = f"<b>Подтвердить действие?</b>\n\n{pending_action.preview_text}\n\n{reversible_note}"
    try:
        await query.edit_message_text(text, reply_markup=confirm_keyboard, parse_mode="HTML")
    except BadRequest:
        pass


async def apply_confirm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Agent v2 — executes pending_action via ActionService."""
    from app.services.action_service import ActionResult, ActionService

    query = update.callback_query
    if query is None:
        return
    await query.answer()

    pending_action = context.user_data.get("pending_action")
    if not pending_action:
        try:
            await query.edit_message_text("Действие устарело.", reply_markup=None)
        except BadRequest:
            pass
        return

    expires_at = context.user_data.get("pending_action_expires_at")
    if expires_at is not None and _time_now() > expires_at:
        context.user_data.pop("pending_action", None)
        context.user_data.pop("pending_action_expires_at", None)
        try:
            await query.edit_message_text("Действие устарело.", reply_markup=None)
        except BadRequest:
            pass
        return

    telegram_user_id = update.effective_user.id if update.effective_user else None
    if telegram_user_id is None:
        return

    try:
        with SessionLocal() as db:
            svc = ActionService(db)
            result = svc.execute(pending_action, telegram_user_id)
    except Exception:
        result = ActionResult(success=False, message="Произошла ошибка при выполнении действия. Попробуйте позже.")

    adv_formatter = AdvisorFormatter()
    text = adv_formatter.format_action_result(result)
    if result.success and result.is_reversible:
        kb = undo_keyboard(result)
        context.user_data["last_action_result"] = result
        context.user_data["last_action_ts"] = _time_now()
    else:
        kb = back_keyboard()

    try:
        await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
    except BadRequest:
        pass

    context.user_data.pop("pending_action", None)
    context.user_data.pop("pending_action_expires_at", None)


async def apply_cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cancel pending_action and return to advisor."""
    query = update.callback_query
    if query is None:
        return
    await query.answer("Отменено.")
    context.user_data.pop("pending_action", None)
    context.user_data.pop("pending_action_expires_at", None)
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except BadRequest:
        pass


async def undo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle undo button — reverses last action within TTL window."""
    from app.services.action_service import ActionResult, ActionService, ActionStatus

    query = update.callback_query
    if query is None:
        return
    await query.answer()

    last_result = context.user_data.get("last_action_result")
    last_ts = context.user_data.get("last_action_ts")

    if not last_result or last_ts is None:
        try:
            await query.edit_message_text("Нечего отменять.", reply_markup=None)
        except BadRequest:
            pass
        return

    # TTL check
    if _time_now() - last_ts > _UNDO_TTL:
        context.user_data.pop("last_action_result", None)
        context.user_data.pop("last_action_ts", None)
        try:
            await query.edit_message_text("Время для отмены истекло (60 сек).", reply_markup=None)
        except BadRequest:
            pass
        return

    if not (last_result.is_reversible and last_result.undo_payload):
        try:
            await query.edit_message_text("Это действие нельзя отменить.", reply_markup=None)
        except BadRequest:
            pass
        return

    telegram_user_id = update.effective_user.id if update.effective_user else None
    if telegram_user_id is None:
        return

    try:
        with SessionLocal() as db:
            svc = ActionService(db)
            undo_result = svc.undo(last_result.undo_payload, telegram_user_id)
    except Exception:
        undo_result = ActionResult(
            status=ActionStatus.FAILURE,
            action_type="undo",
            message="Ошибка при отмене. Данные не изменены.",
        )

    # Очищаем — повторный undo невозможен
    context.user_data.pop("last_action_result", None)
    context.user_data.pop("last_action_ts", None)

    adv_formatter = AdvisorFormatter()
    text = adv_formatter.format_action_result(undo_result)
    kb = back_keyboard()
    try:
        await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
    except BadRequest:
        pass


async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    log_event(update.effective_user.id, "advisor_open")
    question = " ".join(context.args).strip() if context.args else ""
    if not question:
        await _enter_advisor_mode(update, context)
        return
    await _answer_advisor_question(update, context, question, dialog_mode=False)


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
    slug = None
    if data.startswith("advisor:scenario:"):
        slug = data.removeprefix("advisor:scenario:")
    elif data.startswith("advisor:action:"):
        slug = data.removeprefix("advisor:action:")
    else:
        return
    if slug == "export":
        await query.edit_message_text(
            "Экспорт уже доступен:\n• /export month\n• /export xlsx month\n• /export csv week\n• /export xlsx all\n\n"
            "Импорт тоже есть: просто пришли CSV/XLSX файлом, я сначала покажу dry-run превью.",
            reply_markup=done_keyboard(back_target="nav:advisor"),
        )
        return

    question = _ADVISOR_SCENARIO_QUESTIONS.get(slug)
    if not question:
        await query.edit_message_text(
            "Не понял сценарий советника. Попробуй выбрать ещё раз.",
            reply_markup=done_keyboard(back_target="nav:advisor"),
        )
        return

    context.user_data["mode"] = "advisor"
    context.user_data.setdefault("advisor_history", [])
    context.user_data["advisor_last_active"] = _time_now()
    await _answer_advisor_question(update, context, question, dialog_mode=True)


async def advisor_followup_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle contextual advisor follow-up buttons by editing the current message."""
    query = update.callback_query
    if query is None:
        return
    try:
        await query.answer()
    except Exception:
        pass

    data = query.data or ""
    action = data.removeprefix("advisor_followup:")

    # Map action to a natural-language question for the QA service
    if action.startswith("category_detail:"):
        category = action.removeprefix("category_detail:").strip()
        if category:
            question = f"Подробно расскажи о моих расходах в категории {category}: сколько трачу, динамика, советы по оптимизации."
        else:
            question = "Подробно расскажи о структуре моих расходов по категориям."
    elif action == "upcoming_all":
        question = "Покажи все ближайшие запланированные платежи и подписки."
    elif action == "trend":
        question = "Покажи динамику моих доходов и расходов за последние 3 месяца."
    else:
        question = "Дай мне финансовый совет на основе моих последних транзакций."

    # Track which follow-up actions the user has taken in this session
    if context.user_data is not None:
        actions_taken: list[str] = list(context.user_data.get("advisor_actions_taken", []))
        if action not in actions_taken:
            actions_taken.append(action)
        context.user_data["advisor_actions_taken"] = actions_taken[-16:]

    await _answer_advisor_question(update, context, question, dialog_mode=False)


async def _handle_advisor_text(update: Update, context: ContextTypes.DEFAULT_TYPE, question: str) -> None:
    """Handle text input in advisor mode — route to FinancialQAService with history."""
    await _answer_advisor_question(update, context, question, dialog_mode=True)
