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

    def format_start(self) -> str:
        return (
            "Привет! Я веду летопись твоих доходов и расходов.\n\n"
            "Примеры:\n"
            "• расход 500 еда\n"
            "• доход 3000 аванс\n"
            "• купил продукты на 750\n"
            "• можно отправить голосовое, я распознаю и попрошу подтвердить\n\n"
            "Команды:\n"
            "• /summary — сводка\n"
            "• /delete — удалить одну запись\n"
            "• /deleteall — удалить все записи"
        )

    def format_saved(self, operation_label: str, amount: str, category: str, balance: str) -> str:
        return f"✅ В летопись внесено: {operation_label} {amount}₽ — {self.category_label(category)}\nОстаток казны за месяц: {balance}₽"

    def format_saved_many(self, items: list[dict[str, str]], balance: str) -> str:
        lines = ["✅ В летопись внесены записи:"]
        for idx, item in enumerate(items, start=1):
            lines.append(f"{idx}. {item['type']} {item['amount']}₽ — {self.category_label(item['category'])}")
        lines.append(f"Остаток казны за месяц: {balance}₽")
        return "\n".join(lines)

    def format_clarify_category(self, amount: str, description: str | None) -> str:
        return f"Вижу сумму {amount}₽. Уточни, к какой категории отнести: {description}"

    def format_category_resolution_prompt(self, raw_category: str, suggestions: list[str], merchant_label: str | None = None) -> str:
        subject = merchant_label or raw_category
        if merchant_label:
            if suggestions:
                options = ", ".join(self.category_label(item) for item in suggestions)
                return (
                    f"Похоже, это место покупки: «{subject}». К какой категории отнести расход?\n"
                    f"Похожие варианты: {options}.\n"
                    f"Можно выбрать похожую категорию кнопками ниже, создать новую или написать другой вариант текстом."
                )
            return (
                f"Похоже, это место покупки: «{subject}». К какой категории отнести расход?\n"
                f"Можно создать новую категорию кнопкой ниже, отменить или написать другой вариант текстом."
            )
        if suggestions:
            options = ", ".join(self.category_label(item) for item in suggestions)
            return (
                f"Категория «{subject}» не найдена. Что делаем?\n"
                f"Похожие варианты: {options}.\n"
                f"Можно создать новую категорию, выбрать похожую кнопками ниже или просто написать другой вариант текстом."
            )
        return (
            f"Категория «{subject}» не найдена. Что делаем?\n"
            f"Можно создать новую категорию кнопкой ниже, отменить или просто написать другой вариант текстом."
        )

    def format_category_resolution_retry(self, raw_category: str, suggestions: list[str], merchant_label: str | None = None) -> str:
        subject = merchant_label or raw_category
        if merchant_label:
            if suggestions:
                options = ", ".join(self.category_label(item) for item in suggestions)
                return f"Понял это как новое место покупки: «{subject}». Выбери категорию кнопками ниже, создай новую или напиши ещё один вариант. Похожие: {options}."
            return f"Понял это как новое место покупки: «{subject}». Можно создать новую категорию, отменить или написать ещё один вариант."
        if suggestions:
            options = ", ".join(self.category_label(item) for item in suggestions)
            return f"Понял это как новую попытку категории: «{subject}». Выбери кнопку ниже, создай новую категорию или напиши ещё один вариант. Похожие: {options}."
        return f"Понял это как новую попытку категории: «{subject}». Можно создать новую категорию, отменить или написать ещё один вариант."

    @staticmethod
    def format_create_category_option(raw_category: str) -> str:
        return f"Создать «{raw_category}»"

    def format_use_category_option(self, category: str) -> str:
        return f"Использовать «{self.category_label(category)}»"

    @staticmethod
    def format_category_resolution_cancelled() -> str:
        return "Окей, создание записи отменил."

    def format_clarify(self, amount: str) -> str:
        return f"Нашёл сумму {amount}₽. Это расход или доход? И к чему её отнести?"

    def format_fallback(self) -> str:
        return "Не понял запись. Попробуй так: расход 500 еда"

    def format_summary(self, period: str, balance: str, income_total: str, expense_total: str, top_items: list[dict[str, str]]) -> str:
        top = ", ".join(f"{self.category_label(item['category'])}: {item['amount']}₽" for item in top_items) or "нет расходов"
        return (
            f"Сводка казны за {self.PERIOD_LABELS.get(period, period)}\n"
            f"Баланс: {balance}₽\n"
            f"Доход: +{income_total}₽\n"
            f"Расход: -{expense_total}₽\n"
            f"Топ категорий: {top}"
        )

    def format_voice_confirm(self, transcript: str) -> str:
        return f"Я услышал: {transcript}. Верно?"

    def format_voice_edit_prompt(self, transcript: str) -> str:
        return f"Исправь текст и отправь его следующим сообщением:\n{transcript}"

    def format_voice_confirm_many(self, items: list[dict[str, str]]) -> str:
        lines = [f"Я услышал {len(items)} записи:"]
        for idx, item in enumerate(items, start=1):
            lines.append(f"{idx}. {item['type']} {item['amount']}₽ — {self.category_label(item['category'])}")
        lines.append("Верно?")
        return "\n".join(lines)

    def format_voice_saved(self, operation_label: str, amount: str, category: str, balance: str, transcript: str | None = None) -> str:
        suffix = f"\nТранскрипт: {transcript}" if transcript else ""
        return f"✅ В летопись внесено: {operation_label} {amount}₽ — {self.category_label(category)}\nОстаток казны за месяц: {balance}₽{suffix}"

    def format_delete_prompt(self) -> str:
        return "Выбери запись для удаления:"

    def format_delete_empty(self) -> str:
        return "В летописи нет записей для удаления."

    def format_delete_done(self) -> str:
        return "✅ Запись удалена из летописи."

    def format_delete_missing(self) -> str:
        return "Не нашёл эту запись. Возможно, она уже удалена."

    def format_delete_button(self, amount: str, category: str) -> str:
        return f"Удалить {amount}₽ {self.category_label(category)}"

    def format_deleteall_confirm(self) -> str:
        return "Это удалит все записи из летописи. Точно удалить всё?"

    def format_deleteall_done(self, count: int) -> str:
        return f"✅ Все записи удалены из летописи. Всего удалено: {count}."

    def format_deleteall_cancelled(self) -> str:
        return "Окей, летопись оставляю без изменений."
