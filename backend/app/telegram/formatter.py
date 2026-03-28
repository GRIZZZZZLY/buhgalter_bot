from __future__ import annotations

from datetime import date
from decimal import Decimal


class TreasuryFormatter:
    PERIOD_LABELS = {
        "today": "сегодня",
        "week": "неделю",
        "month": "месяц",
        "all": "всё время",
    }

    CATEGORY_LABELS_RU = {
        "food": "Еда",
        "transport": "Транспорт",
        "housing": "Жильё",
        "health": "Здоровье",
        "beauty": "Красота",
        "entertainment": "Развлечения",
        "subscriptions": "Подписки",
        "shopping": "Покупки",
        "home": "Дом",
        "telecom": "Связь",
        "work": "Работа",
        "education": "Обучение",
        "gifts": "Подарки",
        "fees": "Комиссии",
        "salary": "Зарплата",
        "freelance": "Фриланс",
        "bonus": "Премии",
        "transfer": "Переводы",
        "refund": "Возвраты",
        "other_income": "Прочий доход",
        "other": "Прочее",
    }

    def category_label(self, category: str) -> str:
        return self.CATEGORY_LABELS_RU.get(category, category)

    # ------------------------------------------------------------------
    # /start
    # ------------------------------------------------------------------

    def format_start(self) -> str:
        return (
            "Привет! Я записываю доходы и расходы.\n\n"
            "Просто напиши что потратил или получил:\n"
            "• <code>500 еда</code>\n"
            "• <code>такси 350</code>\n"
            "• <code>зарплата 80000</code>\n"
            "• <code>вчера кофе 200</code>\n\n"
            "Или отправь голосовое — распознаю и попрошу подтвердить."
        )

    # ------------------------------------------------------------------
    # Saved confirmation
    # ------------------------------------------------------------------

    def format_saved(
        self,
        operation_label: str,
        amount: str,
        category: str,
        balance: str,
        past_date: "date | None" = None,
        learned_mapping: str | None = None,
    ) -> str:
        date_suffix = f" (за {past_date.strftime('%d.%m')})" if past_date else ""
        sign = "↗" if operation_label == "доход" else "↘"
        lines = [
            f"✅ {sign} {operation_label.capitalize()} {amount} ₽ — "
            f"{self.category_label(category)}{date_suffix}",
            f"Баланс за месяц: {balance} ₽",
        ]
        if learned_mapping:
            lines.append(f"_(запомнил: {learned_mapping} → {self.category_label(category)})_")
        return "\n".join(lines)

    def format_saved_many(self, items: list[dict[str, str]], balance: str) -> str:
        lines = ["✅ Записано:"]
        for idx, item in enumerate(items, start=1):
            sign = "↗" if item["type"] == "доход" else "↘"
            lines.append(f"{idx}. {sign} {item['type']} {item['amount']} ₽ — {self.category_label(item['category'])}")
        lines.append(f"Баланс за месяц: {balance} ₽")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Category resolution
    # ------------------------------------------------------------------

    def format_category_resolution_prompt(
        self,
        raw_category: str,
        suggestions: list[str],
        merchant_label: str | None = None,
    ) -> str:
        subject = merchant_label or raw_category
        if merchant_label:
            if suggestions:
                options = ", ".join(self.category_label(s) for s in suggestions)
                return (
                    f"«{subject}» — к какой категории отнести?\n"
                    f"Похожие: {options}"
                )
            return f"«{subject}» — к какой категории отнести?"
        if suggestions:
            options = ", ".join(self.category_label(s) for s in suggestions)
            return (
                f"Категория «{subject}» не найдена.\n"
                f"Похожие варианты: {options}"
            )
        return f"Категория «{subject}» не найдена. Выбери из списка или создай новую."

    def format_category_resolution_retry(
        self,
        raw_category: str,
        suggestions: list[str],
        merchant_label: str | None = None,
    ) -> str:
        subject = merchant_label or raw_category
        if suggestions:
            options = ", ".join(self.category_label(s) for s in suggestions)
            return f"«{subject}» — выбери категорию. Похожие: {options}"
        return f"«{subject}» — выбери категорию из списка."

    @staticmethod
    def format_create_category_option(raw_category: str) -> str:
        return f"Создать «{raw_category}»"

    def format_use_category_option(self, category: str) -> str:
        return f"Использовать «{self.category_label(category)}»"

    @staticmethod
    def format_category_resolution_cancelled() -> str:
        return "Запись отменена."

    # ------------------------------------------------------------------
    # Clarify / fallback
    # ------------------------------------------------------------------

    def format_clarify_category(self, amount: str, description: str | None) -> str:
        return f"Вижу сумму {amount} ₽. Уточни категорию: {description}"

    def format_clarify(self, amount: str) -> str:
        return f"Нашёл сумму {amount} ₽ — это расход или доход?"

    def format_fallback(self) -> str:
        return (
            "Не понял. Попробуй так:\n"
            "• <code>500 еда</code>\n"
            "• <code>такси 350</code>\n"
            "• <code>зарплата 80000</code>\n"
            "• <code>вчера кофе 200</code>"
        )

    # ------------------------------------------------------------------
    # Empty states
    # ------------------------------------------------------------------

    def format_empty_summary(self) -> str:
        return (
            "📊 Пока нет записей за этот месяц.\n\n"
            "Начни прямо здесь — напиши трату:\n"
            "  _такси 300_ или _зарплата 50000_"
        )

    def format_empty_budgets(self) -> str:
        return (
            "💰 Бюджеты не настроены.\n\n"
            "Установи лимиты чтобы видеть:\n"
            "• сколько осталось до конца месяца\n"
            "• где превышаешь план\n"
            "• прогноз советника по рискам"
        )

    def format_empty_planned(self) -> str:
        return (
            "📋 Запланированных платежей нет.\n\n"
            "Добавь аренду, подписки или другие\n"
            "регулярные расходы — советник будет\n"
            "предупреждать заранее."
        )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def format_summary(
        self,
        period: str,
        balance: str,
        income_total: str,
        expense_total: str,
        top_items: list[dict[str, str]],
    ) -> str:
        top = ", ".join(
            f"{self.category_label(item['category'])}: {item['amount']} ₽"
            for item in top_items
        ) or "нет расходов"
        return (
            f"Сводка за {self.PERIOD_LABELS.get(period, period)}\n"
            f"Баланс: {balance} ₽\n"
            f"Доход: +{income_total} ₽\n"
            f"Расход: −{expense_total} ₽\n"
            f"Топ категорий: {top}"
        )

    # ------------------------------------------------------------------
    # Voice
    # ------------------------------------------------------------------

    def format_voice_confirm(
        self,
        tx_type: str,
        amount: str,
        category: str,
        transcript: str | None = None,
    ) -> str:
        """Show the parsed transaction, not the raw transcript."""
        sign = "↗" if tx_type == "доход" else "↘"
        type_label = tx_type.capitalize()
        cat_label = self.category_label(category)
        lines = [f"{sign} {type_label} {amount} ₽ — {cat_label}"]
        if transcript:
            lines.append(f"<i>«{transcript}»</i>")
        lines.append("\nВерно?")
        return "\n".join(lines)

    def format_voice_confirm_many(self, items: list[dict[str, str]], transcript: str | None = None) -> str:
        lines = [f"Распознал {len(items)} записи:"]
        for idx, item in enumerate(items, start=1):
            sign = "↗" if item["type"] == "доход" else "↘"
            lines.append(f"{idx}. {sign} {item['type']} {item['amount']} ₽ — {self.category_label(item['category'])}")
        if transcript:
            lines.append(f"<i>«{transcript}»</i>")
        lines.append("\nВерно?")
        return "\n".join(lines)

    def format_voice_edit_prompt(self, transcript: str) -> str:
        return f"✏️ Исправь текст и отправь следующим сообщением:\n<code>{transcript}</code>"

    def format_voice_saved(
        self,
        operation_label: str,
        amount: str,
        category: str,
        balance: str,
        transcript: str | None = None,
    ) -> str:
        sign = "↗" if operation_label == "доход" else "↘"
        lines = [
            f"✅ {sign} {operation_label.capitalize()} {amount} ₽ — {self.category_label(category)}",
            f"Баланс за месяц: {balance} ₽",
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def format_delete_prompt(self) -> str:
        return "Выбери запись для удаления:"

    def format_delete_empty(self) -> str:
        return "Записей для удаления нет."

    def format_delete_done(self) -> str:
        return "✅ Удалил запись."

    def format_delete_missing(self) -> str:
        return "❌ Не нашёл запись. Возможно, она уже удалена."

    def format_delete_button(self, amount: str, category: str) -> str:
        return f"Удалить {amount} ₽ {self.category_label(category)}"

    def format_deleteall_confirm(self) -> str:
        return "Это удалит все записи. Точно удалить всё?"

    def format_deleteall_done(self, count: int) -> str:
        return f"✅ Удалено записей: {count}."

    def format_deleteall_cancelled(self) -> str:
        return "Отмена — записи не тронуты."

    # ------------------------------------------------------------------
    # Navigation screens
    # ------------------------------------------------------------------

    PERIOD_LABELS_GEN = {
        "today": "сегодня",
        "week": "за неделю",
        "month": "за месяц",
        "all": "за всё время",
    }

    PERIOD_MONTH_NAMES = {
        1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
        5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
        9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
    }

    def _period_header(self, period: str) -> str:
        if period == "today":
            return f"сегодня, {date.today().strftime('%d.%m')}"
        if period == "week":
            return "за неделю"
        if period == "all":
            return "за всё время"
        today = date.today()
        return self.PERIOD_MONTH_NAMES.get(today.month, "месяц")

    def format_balance_screen(
        self,
        income_total: str,
        expense_total: str,
        balance: str,
        period: str = "month",
    ) -> str:
        header = self._period_header(period)
        sign = "+" if not balance.startswith("-") else ""
        return (
            f"💰 *Баланс за {header}*\n\n"
            f"{sign}{balance} ₽\n\n"
            f"↗ {income_total} ₽  — доходы\n"
            f"↘ {expense_total} ₽  — расходы"
        )

    def format_stats_screen(
        self,
        income_total: str,
        expense_total: str,
        balance: str,
        top_items: list[dict[str, str]],
        period: str = "month",
    ) -> str:
        # Show empty state hint when there are no transactions this period
        try:
            has_data = float(income_total.replace(",", "")) != 0 or float(expense_total.replace(",", "")) != 0
        except (ValueError, AttributeError):
            has_data = bool(top_items)
        if not has_data and period == "month":
            return self.format_empty_summary()
        header = self._period_header(period)
        sign = "+" if not balance.startswith("-") else ""
        lines = [f"📊 *Сводка за {header}*\n"]
        lines.append(f"Баланс: {sign}{balance} ₽")
        lines.append(f"Доходы: +{income_total} ₽")
        lines.append(f"Расходы: −{expense_total} ₽")
        if top_items:
            lines.append("\nТоп категорий расходов:")
            for item in top_items:
                lines.append(f"  • {self.category_label(item['category'])}: {item['amount']} ₽")
        return "\n".join(lines)

    def format_operations_screen(self, items: list[dict], period: str = "month") -> str:
        header = self._period_header(period)
        if not items:
            return f"📋 *Операции за {header}*\n\nЗаписей нет."
        lines = [f"📋 *Операции за {header}*\n"]
        for item in items[:10]:
            sign = "↗" if item.get("type") == "income" else "↘"
            cat = self.category_label(item.get("category", "other"))
            amount = item.get("amount", "0")
            created = item.get("created_at", "")[:10] if item.get("created_at") else ""
            date_part = f"  {created}" if created else ""
            lines.append(f"{sign} {amount} ₽ — {cat}{date_part}")
        if len(items) > 10:
            lines.append(f"\n...и ещё {len(items) - 10}")
        return "\n".join(lines)

    def format_categories_screen(self) -> str:
        return "📂 *Категории*\n\nВыбери тип:"

    def format_categories_type_screen(self, tx_type: str, top_cats: list[str]) -> str:
        sign = "↗" if tx_type == "income" else "↘"
        type_label = "Доходы" if tx_type == "income" else "Расходы"
        if not top_cats:
            return f"{sign} *{type_label}*\n\nКатегорий пока нет."
        from app.telegram.keyboards import CATEGORY_EMOJI
        lines = [f"{sign} *{type_label}* — топ категорий:\n"]
        for slug in top_cats[:8]:
            emoji = CATEGORY_EMOJI.get(slug, "•")
            lines.append(f"{emoji} {self.category_label(slug)}")
        return "\n".join(lines)

    def format_settings_screen(self, user) -> str:
        budget_str = f"{float(user.budget_amount):,.0f} ₽/мес" if user.budget_amount else "не установлен"
        morning = user.reminder_morning or "выключено"
        evening = user.reminder_evening or "выключено"
        return (
            "⚙️ *Настройки*\n\n"
            f"📅 Начало периода: {user.budget_start_day}-е число\n"
            f"💰 Бюджет: {budget_str}\n"
            f"⏰ Утреннее: {morning}\n"
            f"🌙 Вечернее: {evening}\n"
            f"🌍 Часовой пояс: {user.timezone}\n"
            f"🔥 Серия: {user.streak_days} дней"
        )

    def format_help_screen(self) -> str:
        return (
            "ℹ️ *Как пользоваться*\n\n"
            "Просто напиши что потратил или получил:\n"
            "• `купил продукты на 750`\n"
            "• `такси 350`\n"
            "• `зарплата 120000`\n"
            "• `вчера кофе 200`\n"
            "• `10.03 аренда 45000`\n\n"
            "Или отправь голосовое сообщение.\n\n"
            "*Команды:*\n"
            "/summary — сводка\n"
            "/budget — бюджеты\n"
            "/edit — редактировать запись\n"
            "/export — выгрузить CSV\n"
            "/settings — настройки\n"
            "/delete — удалить запись\n"
            "/menu — главное меню"
        )

    def format_main_menu_screen(self) -> str:
        return "Выбери раздел или напиши расход/доход:"

    # ------------------------------------------------------------------
    # Planned expenses
    # ------------------------------------------------------------------

    def format_planned_created(self, title: str, amount: str, category: str, planned_date: str) -> str:
        return f"✅ Запланировано: {title} — {amount} ₽, {self.category_label(category)}, {planned_date}"

    def format_planned_empty(self) -> str:
        return self.format_empty_planned()

    def format_planned_list(self, items: list[dict[str, str]]) -> str:
        if not items:
            return self.format_planned_empty()
        overdue = [item for item in items if item.get("is_overdue")]
        future = [item for item in items if not item.get("is_overdue")]

        lines = ["📌 Запланированные расходы:\n"]

        if overdue:
            lines.append("⚠️ Просроченные:")
            for item in overdue:
                lines.append(
                    f"• {item['planned_date']} — {item['title']} — {item['amount']} ₽ — {self.category_label(item['category'])}"
                )
            if future:
                lines.append("")

        if future:
            lines.append("📅 Ближайшие:")
            for item in future:
                lines.append(
                    f"• {item['planned_date']} — {item['title']} — {item['amount']} ₽ — {self.category_label(item['category'])}"
                )
        return "\n".join(lines)

    def format_planned_confirmed(self, title: str, amount: str, category: str) -> str:
        return f"✅ Учтено: {title} — {amount} ₽, {self.category_label(category)}"

    def format_planned_cancelled(self, title: str) -> str:
        return f"✅ Отменил запланированный расход: {title}."

    def format_planned_updated(self, title: str, planned_date: str) -> str:
        return f"✅ Обновил дату для «{title}»: {planned_date}"

    def format_recurring_updated(self, title: str, amount: str | None = None) -> str:
        if amount is not None:
            return f"✅ Обновил правило «{title}»: новая сумма {amount} ₽"
        return f"✅ Обновил правило «{title}»."

    def format_recurring_deleted(self, title: str) -> str:
        return f"✅ Отключил правило «{title}»."

    def format_recurring_rule(self, title: str, amount: str, category: str, schedule: str, next_run_date: str) -> str:
        return (
            f"🔁 {title} — {amount} ₽\n"
            f"Категория: {self.category_label(category)}\n"
            f"Период: {schedule}\n"
            f"Следующий planned expense: {next_run_date}"
        )

    def format_planned_due(self, title: str, amount: str, category: str, planned_date: str) -> str:
        return (
            f"Сегодня запланировано: {title} — {amount} ₽, {self.category_label(category)}.\n"
            "Что делаем?"
        )

    def format_weekly_planned_digest(self, items: list[dict[str, str]]) -> str:
        if not items:
            return "На следующую неделю запланированных расходов нет."
        total = sum(float(item["amount"]) for item in items)
        lines = [
            f"На следующую неделю запланировано {len(items)} расхода(ов) на {total:,.0f} ₽\n"
        ]
        for item in items:
            lines.append(
                f"• {item['planned_date']} — {item['title']} — {item['amount']} ₽ — {self.category_label(item['category'])}"
            )
        return "\n".join(lines)


class AdvisorFormatter:
    """Action-type-specific renderers for advisor answer payloads."""

    def format_for_action_type(self, payload, action_type: str | None) -> str:
        renderers = {
            "cut_costs":        self._render_cut_costs,
            "prepare_payment":  self._render_payment_warning,
            "review_budget":    self._render_budget_status,
            "improve_cashflow": self._render_cashflow_trend,
        }
        renderer = renderers.get(action_type or "", self._render_default)
        return renderer(payload)

    def _render_cut_costs(self, payload) -> str:
        # Акцент: конкретная категория и сумма перерасхода
        lines = [payload.answer]
        if payload.basis:
            lines.append("📊 На чём основано:")
            for fact in payload.basis[:3]:
                lines.append(f"  • {fact}")
        if payload.recommendations:
            rec = payload.recommendations[0]
            lines.append(f"\n→ {rec}")
        return "\n".join(lines)

    def _render_payment_warning(self, payload) -> str:
        # Акцент: даты и суммы ближайших платежей
        lines = [payload.answer]
        if payload.warnings:
            for w in payload.warnings:
                lines.append(f"⚠️ {w}")
        return "\n".join(lines)

    def _render_budget_status(self, payload) -> str:
        # Акцент: процент использования бюджетов — answer уже содержит цифры
        return payload.answer

    def _render_cashflow_trend(self, payload) -> str:
        # Акцент: динамика, было/стало, тренд
        lines = [payload.answer]
        if payload.basis:
            lines.append("📈 Данные за период:")
            for fact in payload.basis:
                lines.append(f"  {fact}")
        return "\n".join(lines)

    def _render_default(self, payload) -> str:
        return payload.answer
