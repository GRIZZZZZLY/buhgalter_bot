import asyncio
import logging

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from app.db.session import SessionLocal
from app.repositories.event_repository import log_event
from app.repositories.user_repository import UserRepository
from app.telegram.bot_service import TelegramBotService
from app.telegram.formatter import TreasuryFormatter
from app.telegram.keyboards import (
    category_resolution_keyboard,
    delete_keyboard,
    deleteall_step1_keyboard,
    deleteall_step2_keyboard,
    done_keyboard,
    low_confidence_keyboard,
    low_confidence_category_keyboard,
    onboarding_step2_keyboard,
    saved_actions_keyboard,
    voice_confirmation_keyboard,
)
from app.telegram.handlers.common import (
    _auto_remove_keyboard,
    _ensure_user,
    _send_saved_with_undo,
    VOICE_CONFIRM_TIMEOUT,
    UNDO_WINDOW_SECONDS,
)
from app.telegram.handlers.planned import _format_planned_confirm_msg
from app.telegram.handlers.recurring import _format_recurring_confirm_msg
from app.telegram.keyboards import planned_freeform_keyboard, recurring_freeform_keyboard
from app.telegram.onboarding import ONBOARDING_STEP_KEY
from app.telegram.handlers.budget import _get_budget_alert

logger = logging.getLogger("finance_bot.telegram")
formatter = TreasuryFormatter()


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
    await update.effective_message.reply_text(
        "⚠️ Это удалит все твои транзакции, бюджеты и настройки безвозвратно.\n\n"
        "Сначала рекомендую сделать экспорт: /export",
        reply_markup=deleteall_step1_keyboard(),
    )


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
        elif query.data == "deleteall:confirm_step1":
            response = {
                "action": "deleteall_step2",
                "message": "🗑 Последнее подтверждение. Это действие необратимо — все данные будут удалены.",
            }
        elif query.data == "deleteall:confirm_final":
            response = service.delete_all_transactions(update.effective_user.id)
        elif query.data == "deleteall:cancel":
            response = {"action": "deleteall_cancelled", "message": formatter.format_deleteall_cancelled()}
        else:
            response = {"action": "delete_unknown", "message": "Неизвестное действие удаления."}

    try:
        if response.get("action") == "deleteall_step2":
            await query.edit_message_text(response["message"], reply_markup=deleteall_step2_keyboard())
        else:
            await query.edit_message_text(response["message"], reply_markup=done_keyboard())
    except BadRequest as exc:
        logger.warning("delete_callback edit failed: %s", exc)


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
        log_event(update.effective_user.id, "undo_used")
        suffix = f" ({deleted_count} записи)" if deleted_count > 1 else ""
        await query.edit_message_text(f"↩ Отменено{suffix}.", reply_markup=done_keyboard())
    else:
        await query.edit_message_text("Запись уже была удалена или не найдена.", reply_markup=done_keyboard())


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
        from app.telegram.handlers_legacy import TelegramTextFlow, _store_get, _store_pop, _store_set, PendingCategoryResolution
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
        from app.telegram.keyboards import evening_checkin_keyboard
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
        from app.telegram.keyboards import evening_checkin_amount_keyboard
        cat_slug = parts[2]
        cat_label = formatter.category_label(cat_slug)
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
        from app.telegram.keyboards import cancel_keyboard
        cat_slug = parts[2]
        if context.user_data is not None:
            context.user_data["awaiting_checkin_category"] = cat_slug
        cat_label = formatter.category_label(cat_slug)
        await query.edit_message_text(f"{cat_label} — введи сумму:", reply_markup=cancel_keyboard("checkin:none"))
        return

    await query.edit_message_text("Хорошо!", reply_markup=done_keyboard())


async def clarify_intent_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except BadRequest:
        pass

    chosen = query.data.split(":")[1]  # transaction | planned | recurring | cancel

    if chosen == "cancel":
        if context.user_data:
            context.user_data.pop("pending_clarification", None)
        try:
            await query.edit_message_text("Отменено.", reply_markup=done_keyboard())
        except BadRequest:
            pass
        return

    pending = (context.user_data or {}).pop("pending_clarification", None)
    if not pending:
        try:
            await query.edit_message_text("❌ Данные устарели. Начни заново.", reply_markup=done_keyboard())
        except BadRequest:
            pass
        return

    telegram_user_id = update.effective_user.id

    if chosen == "transaction":
        from app.services.transaction_service import TransactionService
        from app.schemas.parser import ParseResult
        from decimal import Decimal
        with SessionLocal() as db:
            _ensure_user(db, update)
            svc = TransactionService(db)
            parsed = ParseResult(
                matched=True,
                confidence=0.9,
                confidence_label="high",
                transaction_type=pending.get("tx_type") or "expense",
                amount=Decimal(str(pending.get("amount") or 0)),
                category=pending.get("category") or "other",
                description=pending.get("description") or None,
                pattern="clarify",
                raw_input=pending.get("text") or "",
            )
            tx = svc.create_from_parse(telegram_user_id=telegram_user_id, source="text", parsed=parsed, override_date=None)
            summary = svc.get_summary(telegram_user_id=telegram_user_id, period="month")
        from app.telegram.formatter import TreasuryFormatter
        fmt = TreasuryFormatter()
        balance = summary.balance if summary.balance.startswith("-") else f"+{summary.balance}"
        msg = fmt.format_saved("доход" if tx.type == "income" else "расход", tx.amount, tx.category, balance, None)
        try:
            await query.edit_message_text(msg, reply_markup=saved_actions_keyboard(str(tx.id)))
            asyncio.create_task(_auto_remove_keyboard(context.bot, query.message.chat_id, query.message.message_id))
        except BadRequest:
            pass
        return

    if chosen == "planned":
        item = {
            "title": pending.get("title") or pending.get("description") or "Платёж",
            "amount": pending.get("amount") or "0",
            "category": pending.get("category") or "other",
            "planned_date": pending.get("planned_date") or "",
            "reminder_time": pending.get("reminder_time") or "",
        }
        context.user_data["pending_planned_freeform"] = item
        try:
            await query.edit_message_text(
                _format_planned_confirm_msg(item),
                reply_markup=planned_freeform_keyboard(),
                parse_mode="HTML",
            )
        except BadRequest:
            pass
        return

    if chosen == "recurring":
        item = {
            "title": pending.get("title") or pending.get("description") or "Платёж",
            "amount": pending.get("amount") or "0",
            "category": pending.get("category") or "other",
            "transaction_type": pending.get("transaction_type") or pending.get("tx_type") or "expense",
            "frequency": pending.get("frequency") or "monthly",
            "day_value": pending.get("day_value") or "1",
            "reminder_time": pending.get("reminder_time") or "",
        }
        context.user_data["pending_recurring_freeform"] = item
        try:
            await query.edit_message_text(
                _format_recurring_confirm_msg(item),
                reply_markup=recurring_freeform_keyboard(),
                parse_mode="HTML",
            )
        except BadRequest:
            pass
        return


async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from app.telegram.handlers.settings import _handle_settings_input
    from app.telegram.handlers.budget import _handle_budget_total_input, _handle_budget_category_input
    from app.telegram.handlers.planned import _handle_planned_input
    from app.telegram.handlers.recurring import _handle_recurring_input
    from app.telegram.handlers.advisor import _handle_advisor_text
    from app.telegram.keyboards import edit_item_keyboard, cancel_keyboard, onboarding_step3_keyboard
    from app.telegram.onboarding import OnboardingFlow
    _onboarding = OnboardingFlow()

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
    if mode == "goal_create_input":
        context.user_data.pop("mode", None)
        await _handle_goal_create_input(update, context, text.strip())
        return
    if mode == "goal_deposit_input":
        context.user_data.pop("mode", None)
        goal_id = context.user_data.pop("pending_deposit_goal_id", None)
        await _handle_goal_deposit_input(update, context, text.strip(), goal_id)
        return

    # Handle settings input
    awaiting = context.user_data.get("awaiting_setting") if context.user_data else None
    if awaiting:
        del context.user_data["awaiting_setting"]
        result = _handle_settings_input(update.effective_user.id, awaiting, text.strip())
        await update.effective_message.reply_text(result, reply_markup=done_keyboard(back_target="nav:settings"))
        return

    # Handle onboarding step 2: user types a budget amount
    if context.user_data and context.user_data.get(ONBOARDING_STEP_KEY) == 2:
        raw = text.strip().replace(",", ".").replace(" ", "")
        try:
            budget_amount = float(raw)
            if budget_amount > 0:
                with SessionLocal() as db:
                    _ensure_user(db, update)
                    user_obj = UserRepository(db).get_by_telegram_id(update.effective_user.id)
                    if user_obj:
                        UserRepository(db).update_settings(user_obj, budget_amount=budget_amount)
                        db.commit()
                ob_text, ob_parse, _ = _onboarding.on_budget_or_skip(context.user_data)
                await update.effective_message.reply_text(
                    ob_text, parse_mode=ob_parse, reply_markup=onboarding_step3_keyboard()
                )
                return
        except (ValueError, TypeError):
            await update.effective_message.reply_text(
                "Введи число, например: <b>50000</b>",
                parse_mode="HTML",
            )
            return
        # Not a number — treat as normal transaction (fall through)

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
            from datetime import date
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

    from app.services.recurring_service import parse_recurring_schedule_args
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
            log_event(update.effective_user.id, "tx_added", source="text")

            saved_category = response.get("saved_category")
            if saved_category:
                budget_alert = _get_budget_alert(db, user.telegram_user_id, str(saved_category))

    # Route response to correct handler
    action = response.get("action", "")

    if action == "confirm_voice" and response.get("voice_log_id"):
        msg = await update.effective_message.reply_text(
            response["message"],
            reply_markup=voice_confirmation_keyboard(response["voice_log_id"]),
            parse_mode="HTML",
        )
        asyncio.create_task(_auto_remove_keyboard(context.bot, msg.chat_id, msg.message_id, VOICE_CONFIRM_TIMEOUT))
        return

    if action == "planned_confirm":
        items = response.get("parsed_items") or []
        if items:
            item = items[0]
            context.user_data["pending_planned_freeform"] = item
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
            await update.effective_message.reply_text(
                _format_recurring_confirm_msg(item),
                reply_markup=recurring_freeform_keyboard(),
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
        await update.effective_message.reply_text(
            response["message"],
            reply_markup=low_confidence_keyboard(str(response.get("amount", "0"))),
        )
        return

    if action == "needs_clarification":
        from app.telegram.keyboards import intent_clarify_keyboard
        context.user_data["pending_clarification"] = response.get("pending", {})
        await update.effective_message.reply_text(
            response["message"],
            reply_markup=intent_clarify_keyboard(),
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
        # Onboarding step 1: first transaction saved — advance to step 2
        if context.user_data and context.user_data.get(ONBOARDING_STEP_KEY) == 1:
            from app.telegram.onboarding import OnboardingFlow
            _ob = OnboardingFlow()
            ob_text, ob_parse, _ = _ob.on_first_transaction(context.user_data)
            if ob_text:
                await update.effective_message.reply_text(
                    ob_text, parse_mode=ob_parse, reply_markup=onboarding_step2_keyboard()
                )
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


async def _handle_goal_create_input(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """Handle free-form goal creation text after goals:new."""
    from app.db.session import SessionLocal
    from app.services.llm_service import LLMService
    from app.telegram.keyboards import goal_confirm_keyboard, goals_list_keyboard
    from app.telegram.handlers.common import _ensure_user

    await update.effective_message.reply_text("🤔 Разбираю…")
    user_id = update.effective_user.id
    with SessionLocal() as db:
        _ensure_user(db, update)
        result = LLMService(db).extract_savings_goal(text)

    if result is None:
        await update.effective_message.reply_text(
            "Не смог разобрать. Попробуй подробнее, например:\n«iPhone 15 Pro 120000 к декабрю, 10%»",
            reply_markup=goals_list_keyboard(),
        )
        return

    if not result.get("target_amount"):
        context.user_data["pending_goal"] = result
        context.user_data["mode"] = "goal_amount_input"
        await update.effective_message.reply_text(
            f"🎯 *{result.get('title', 'Новая цель')}*\nСколько нужно накопить (₽)?",
            parse_mode="Markdown",
        )
        return

    title = result.get("title", "Новая цель")
    amount = result.get("target_amount")
    deadline = result.get("deadline_iso") or "не задан"
    auto = result.get("auto_percent")
    msg = (
        f"🎯 *{title}*\n"
        f"Цель: {amount}₽\n"
        f"Дедлайн: {deadline}\n"
        f"Авто: {f'{auto}% от каждого дохода' if auto else 'не задан'}"
    )
    context.user_data["pending_goal"] = result
    await update.effective_message.reply_text(msg, parse_mode="Markdown", reply_markup=goal_confirm_keyboard())


async def _handle_goal_deposit_input(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, goal_id: str | None) -> None:
    """Handle amount input for manual goal deposit."""
    from decimal import Decimal
    from app.db.session import SessionLocal
    from app.services.savings_goal_service import SavingsGoalService
    from app.services.parser_service import ParserService
    from app.telegram.keyboards import goals_list_keyboard
    from app.telegram.handlers.common import _ensure_user

    amount = ParserService._extract_amount(text)
    if amount is None or goal_id is None:
        await update.effective_message.reply_text("Введи сумму числом, например: 5000")
        return

    with SessionLocal() as db:
        _ensure_user(db, update)
        updated, reached = SavingsGoalService(db).deposit(
            user_id=update.effective_user.id, goal_id=goal_id, amount=amount
        )
    pct = min(100, int(updated.current_amount / updated.target_amount * 100))
    bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
    msg = f"💰 +{amount}₽ → *{updated.title}*\n{bar} {pct}%\n{updated.current_amount}₽ / {updated.target_amount}₽"
    if reached:
        msg += "\n\n🎉 Цель достигнута!"
    await update.effective_message.reply_text(msg, parse_mode="Markdown", reply_markup=goals_list_keyboard())
