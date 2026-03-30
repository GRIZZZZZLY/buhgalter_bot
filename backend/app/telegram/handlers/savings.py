import logging
from datetime import date
from decimal import Decimal

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from app.db.session import SessionLocal
from app.telegram.handlers.common import _ensure_user
from app.telegram.keyboards import (
    goal_confirm_keyboard,
    goal_deposit_keyboard,
    goal_settings_keyboard,
    goals_list_keyboard,
    done_keyboard,
)

logger = logging.getLogger("finance_bot.telegram")


def _goals_list_text(goals) -> str:
    if not goals:
        return (
            "🎯 *Копилки*\n\n"
            "У тебя пока нет целей накопления.\n"
            "Нажми *Новая цель* и опиши что хочешь накопить."
        )
    lines = ["🎯 *Копилки*\n"]
    for goal in goals:
        pct = min(100, int(goal.current_amount / goal.target_amount * 100))
        bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
        deadline_str = f" • До: {goal.deadline.strftime('%d.%m.%Y')}" if goal.deadline else ""
        auto_str = f" • Авто: {goal.auto_percent}%" if goal.auto_percent else ""
        lines.append(
            f"*{goal.title}*\n"
            f"{bar} {pct}% ({goal.current_amount}₽ / {goal.target_amount}₽)"
            f"{deadline_str}{auto_str}"
        )
    return "\n\n".join(lines)


async def goals_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except BadRequest:
        pass

    data = query.data
    user_id = update.effective_user.id

    try:
        if data == "goals:new":
            context.user_data["mode"] = "goal_create_input"
            try:
                await query.edit_message_text(
                    "🎯 Опиши цель накопления:\n\n"
                    "Например:\n"
                    "• *iPhone 15 Pro 120к к декабрю, 10%*\n"
                    "• *Отпуск в Испании 150000*\n"
                    "• *Машина 800к, откладывать 15% от дохода*",
                    parse_mode="Markdown",
                    reply_markup=goals_list_keyboard(),
                )
            except BadRequest:
                await update.effective_chat.send_message(
                    "🎯 Опиши цель накопления:",
                    reply_markup=goals_list_keyboard(),
                )
            return

        elif data == "goals:confirm":
            parsed = context.user_data.pop("pending_goal", None)
            if not parsed:
                await query.edit_message_text("Сессия истекла. Попробуй снова.")
                return
            with SessionLocal() as db:
                _ensure_user(db, update)
                from app.services.savings_goal_service import SavingsGoalService
                deadline = None
                if parsed.get("deadline_iso"):
                    try:
                        deadline = date.fromisoformat(parsed["deadline_iso"])
                    except ValueError:
                        pass
                goal = SavingsGoalService(db).create(
                    user_id=user_id,
                    title=parsed["title"],
                    target_amount=Decimal(str(parsed["target_amount"])),
                    deadline=deadline,
                    auto_percent=parsed.get("auto_percent"),
                )
            await query.edit_message_text(
                f"✅ Цель создана: *{goal.title}* — {goal.target_amount}₽",
                parse_mode="Markdown",
                reply_markup=goals_list_keyboard(),
            )

        elif data == "goals:cancel":
            context.user_data.pop("pending_goal", None)
            context.user_data.pop("mode", None)
            with SessionLocal() as db:
                _ensure_user(db, update)
                from app.services.savings_goal_service import SavingsGoalService
                goals = SavingsGoalService(db).list_active(user_id)
            await query.edit_message_text(
                _goals_list_text(goals),
                parse_mode="Markdown",
                reply_markup=goals_list_keyboard(),
            )

        elif data.startswith("goals:complete:"):
            goal_id = data.split(":", 2)[2]
            with SessionLocal() as db:
                _ensure_user(db, update)
                from app.services.savings_goal_service import SavingsGoalService
                svc = SavingsGoalService(db)
                svc.complete(user_id, goal_id)
                goals = svc.list_active(user_id)
            await query.edit_message_text(
                "✅ Цель завершена! Поздравляем! 🎉\n\n" + _goals_list_text(goals),
                parse_mode="Markdown",
                reply_markup=goals_list_keyboard(),
            )

        elif data.startswith("goals:deposit:"):
            goal_id = data.split(":", 2)[2]
            context.user_data["pending_deposit_goal_id"] = goal_id
            context.user_data["mode"] = "goal_deposit_input"
            try:
                await query.edit_message_text("💰 Сколько кладём в копилку (₽)?")
            except BadRequest:
                await update.effective_chat.send_message("💰 Сколько кладём в копилку (₽)?")

        elif data.startswith("goals:settings:"):
            goal_id = data.split(":", 2)[2]
            try:
                await query.edit_message_text(
                    "⚙️ Настройки цели",
                    reply_markup=goal_settings_keyboard(goal_id),
                )
            except BadRequest:
                await update.effective_chat.send_message(
                    "⚙️ Настройки цели",
                    reply_markup=goal_settings_keyboard(goal_id),
                )

        elif data.startswith("goals:nav:"):
            goal_id = data.split(":", 2)[2]
            with SessionLocal() as db:
                _ensure_user(db, update)
                from app.services.savings_goal_service import SavingsGoalService
                from app.repositories.savings_goal_repository import SavingsGoalRepository
                goal = SavingsGoalRepository(db).get(user_id, goal_id)
            if goal is None:
                await query.edit_message_text("Цель не найдена.", reply_markup=goals_list_keyboard())
                return
            try:
                await query.edit_message_text(
                    f"🎯 *{goal.title}*\n{goal.current_amount}₽ / {goal.target_amount}₽",
                    parse_mode="Markdown",
                    reply_markup=goal_deposit_keyboard(goal_id),
                )
            except BadRequest:
                pass

        else:
            logger.warning("unknown goals callback: %s", data)

    except Exception as exc:
        logger.exception("goals_callback error data=%s: %s", data, exc)
        try:
            await update.effective_chat.send_message(
                "❌ Ошибка. Попробуй ещё раз.",
                reply_markup=done_keyboard(),
            )
        except Exception:
            pass
