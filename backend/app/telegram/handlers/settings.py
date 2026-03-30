import logging

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from app.db.session import SessionLocal
from app.repositories.user_repository import UserRepository
from app.telegram.keyboards import (
    cancel_keyboard,
    done_keyboard,
    settings_nav_inline_keyboard,
)
from app.telegram.handlers.common import _ensure_user

logger = logging.getLogger("finance_bot.telegram")


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


def _validate_time(value: str) -> bool:
    try:
        parts = value.split(":")
        if len(parts) != 2:
            return False
        h, m = int(parts[0]), int(parts[1])
        return 0 <= h <= 23 and 0 <= m <= 59
    except (ValueError, IndexError):
        return False


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
