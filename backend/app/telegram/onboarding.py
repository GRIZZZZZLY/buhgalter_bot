# backend/app/telegram/onboarding.py

ONBOARDING_STEP_KEY = "onboarding_step"

ONBOARDING_STEP1_TEXT = (
    "👋 Привет! Я помогу вести финансы прямо в Telegram.\n\n"
    "Попробуй прямо сейчас — напиши любую трату:\n"
    "  • <i>кофе 200</i>\n"
    "  • <i>такси 450</i>\n"
    "  • <i>продукты 1800</i>\n\n"
    "Или отправь голосовое — я пойму 🎤"
)

ONBOARDING_STEP2_TEXT = (
    "✅ Записано!\n\n"
    "Теперь установи месячный бюджет — сколько планируешь тратить в месяц?\n"
    "Напиши число, например: <b>50000</b>"
)

ONBOARDING_STEP3_TEXT = (
    "🎉 Всё готово!\n\n"
    "Что умею:\n"
    "• записывать траты текстом и голосом\n"
    "• показывать сводку и бюджеты\n"
    "• отвечать на вопросы о твоих финансах"
)


class OnboardingFlow:

    def is_active(self, user_data: dict) -> bool:
        step = user_data.get(ONBOARDING_STEP_KEY)
        return step in (1, 2)

    def is_complete(self, user_data: dict) -> bool:
        return user_data.get(ONBOARDING_STEP_KEY) == "done"

    def start(self, user_data: dict) -> tuple[str, str | None]:
        """Returns (text, parse_mode). Sets step=1."""
        user_data[ONBOARDING_STEP_KEY] = 1
        return ONBOARDING_STEP1_TEXT, "HTML"

    def on_first_transaction(self, user_data: dict) -> tuple[str, str | None, dict | None]:
        """Called after user's first transaction during onboarding.
        Returns (text, parse_mode, keyboard_spec).
        keyboard_spec: {"skip_callback": "onboarding:skip_budget"}
        """
        if user_data.get(ONBOARDING_STEP_KEY) != 1:
            return None, None, None
        user_data[ONBOARDING_STEP_KEY] = 2
        return ONBOARDING_STEP2_TEXT, "HTML", {"skip_callback": "onboarding:skip_budget"}

    def on_budget_or_skip(self, user_data: dict) -> tuple[str, str | None, dict | None]:
        """Called after budget is set or skipped.
        Returns (text, parse_mode, keyboard_spec).
        keyboard_spec: {"summary_callback": "nav:summary", "advisor_callback": "nav:advisor"}
        """
        if user_data.get(ONBOARDING_STEP_KEY) != 2:
            return None, None, None
        user_data[ONBOARDING_STEP_KEY] = "done"
        return ONBOARDING_STEP3_TEXT, "HTML", {
            "summary_callback": "nav:summary",
            "advisor_callback": "nav:advisor",
        }
