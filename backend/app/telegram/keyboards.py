from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.services.recommendation_service import RecommendationSnapshot
from app.telegram.formatter import TreasuryFormatter

formatter = TreasuryFormatter()

# ---------------------------------------------------------------------------
# Category emoji map (shared)
# ---------------------------------------------------------------------------
CATEGORY_EMOJI = {
    "food": "🍽",
    "transport": "🚌",
    "housing": "🏠",
    "health": "💊",
    "beauty": "✨",
    "entertainment": "🎬",
    "subscriptions": "📱",
    "shopping": "🛍",
    "home": "🪴",
    "telecom": "📡",
    "work": "💼",
    "education": "📚",
    "gifts": "🎁",
    "fees": "💳",
    "salary": "💰",
    "freelance": "🖥",
    "bonus": "🏆",
    "transfer": "↔",
    "refund": "↩",
    "other_income": "💵",
    "other": "•",
}

# ---------------------------------------------------------------------------
# Shared inline button helpers
# ---------------------------------------------------------------------------

def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def _menu_btn() -> InlineKeyboardButton:
    return _btn("≡ Меню", "nav:menu")


def _back_btn(target: str = "nav:menu") -> InlineKeyboardButton:
    return _btn("← Назад", target)


def done_keyboard(back_target: str | None = None) -> InlineKeyboardMarkup:
    """Post-action keyboard: [← Назад] [≡ Меню] or just [≡ Меню]."""
    if back_target:
        return InlineKeyboardMarkup([[_back_btn(back_target), _menu_btn()]])
    return InlineKeyboardMarkup([[_menu_btn()]])


ADVISOR_QUICK_SCENARIOS = [
    ("top_expenses", "📊 Топ расходов"),
    ("budget_risks", "⚠️ Где вылезаю из бюджета?"),
    ("upcoming", "📅 Платежи скоро"),
    ("trends_3m", "📈 Динамика за 3 месяца"),
    ("cut_costs", "💡 Что сократить?"),
    ("export", "📥 Скачать отчёт"),
]


def _advisor_scenario_btn(slug: str, text: str) -> InlineKeyboardButton:
    return _btn(text, f"advisor:scenario:{slug}")


def _advisor_action_target(action_type: str | None) -> tuple[str, str] | None:
    mapping = {
        "cut_costs": ("⚠️ Разобрать риск", "advisor:action:budget_risks"),
        "budget_check": ("⚠️ Проверить бюджет", "advisor:action:budget_risks"),
        "upcoming_payment": ("📅 Разобрать платёж", "advisor:action:upcoming"),
        "forecast_control": ("📈 Проверить прогноз", "advisor:action:trends_3m"),
        "top_category_pressure": ("📊 Разобрать категорию", "advisor:action:top_expenses"),
    }
    return mapping.get(action_type)


def advisor_action_rows(recommendations: RecommendationSnapshot | None) -> list[list[InlineKeyboardButton]]:
    if recommendations is None:
        return []
    seen: set[str] = set()
    rows: list[list[InlineKeyboardButton]] = []
    items = []
    if recommendations.primary is not None:
        items.append(recommendations.primary)
    items.extend(recommendations.secondary[:2])
    for item in items:
        target = _advisor_action_target(item.action_type)
        if not target:
            continue
        label, callback = target
        if callback in seen:
            continue
        seen.add(callback)
        rows.append([_btn(label, callback)])
    return rows[:3]


def advisor_keyboard(recommendations: RecommendationSnapshot | None = None) -> InlineKeyboardMarkup:
    """Keyboard for one-off QA responses plus recommendation action buttons."""
    rows = advisor_action_rows(recommendations)
    rows.extend([
        [_btn("🧠 Продолжить в советнике", "nav:advisor")],
        [_btn("📊 Сводка", "nav:stats"), _menu_btn()],
    ])
    return InlineKeyboardMarkup(rows)


def advisor_contextual_keyboard(
    action_type: str | None,
    category: str | None = None,
    recommendation_snapshot: RecommendationSnapshot | None = None,
) -> InlineKeyboardMarkup:
    """Keyboard for non-dialog advisor responses — buttons depend on action_type."""
    base = [
        _btn("← Назад", "nav:advisor"),
        _btn("≡ Меню", "nav:menu"),
    ]

    contextual_map: dict[str, list[InlineKeyboardButton]] = {
        "cut_costs": [
            _btn(
                f"📊 Разбор категории{' ' + category if category else ''}",
                f"advisor_followup:category_detail:{category or ''}",
            ),
        ],
        "prepare_payment": [
            _btn("📅 Все ближайшие платежи", "advisor_followup:upcoming_all"),
        ],
        "review_budget": [
            _btn("💰 Открыть бюджеты", "nav:budgets"),
        ],
        "improve_cashflow": [
            _btn("📈 Динамика за 3 месяца", "advisor_followup:trend"),
        ],
    }

    context_buttons = contextual_map.get(action_type or "", [])

    rows: list[list[InlineKeyboardButton]] = []
    if context_buttons:
        rows.append(context_buttons)
    rows.append([_btn("📥 Скачать отчёт", "export:choose")])
    rows.append(base)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def advisor_apply_keyboard(payload, action_type: str | None = None, category: str | None = None) -> InlineKeyboardMarkup:
    """Contextual keyboard that prepends '✅ Применить' row when payload.can_apply=True."""
    rows: list[list[InlineKeyboardButton]] = []

    if payload.can_apply and payload.apply_action:
        apply_cb = payload.apply_action.to_callback_data()
        rows.append([
            _btn("✅ Применить", apply_cb),
        ])

    contextual_map: dict[str, list[InlineKeyboardButton]] = {
        "cut_costs": [
            _btn(
                f"📊 Разбор категории{' ' + category if category else ''}",
                f"advisor_followup:category_detail:{category or ''}",
            ),
        ],
        "upcoming_payment": [
            _btn("📅 Все ближайшие платежи", "advisor_followup:upcoming_all"),
        ],
        "review_budget": [
            _btn("💰 Открыть бюджеты", "nav:budgets"),
        ],
        "forecast_control": [
            _btn("📈 Динамика за 3 месяца", "advisor_followup:trend"),
        ],
    }
    context_buttons = contextual_map.get(action_type or "", [])
    if context_buttons:
        rows.append(context_buttons)
    rows.append([_btn("📥 Скачать отчёт", "export:choose")])
    rows.append([_btn("← Назад", "nav:advisor"), _btn("≡ Меню", "nav:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def advisor_session_keyboard(recommendations: RecommendationSnapshot | None = None) -> InlineKeyboardMarkup:
    """Keyboard after each advisor answer in dialog mode with action buttons and quick follow-up scenarios."""
    rows = advisor_action_rows(recommendations)
    rows.extend([
        [
            _advisor_scenario_btn("budget_risks", "⚠️ Бюджеты"),
            _advisor_scenario_btn("upcoming", "📅 Скоро"),
        ],
        [
            _advisor_scenario_btn("top_expenses", "📊 Топ"),
            _advisor_scenario_btn("trends_3m", "📈 3 месяца"),
        ],
        [
            _advisor_scenario_btn("cut_costs", "💡 Сократить"),
            _advisor_scenario_btn("export", "📥 Отчёт"),
        ],
        [_back_btn("nav:advisor"), _btn("✕ Завершить", "nav:menu")],
        [_menu_btn()],
    ])
    return InlineKeyboardMarkup(rows)


def advisor_onboarding_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for advisor onboarding screen."""
    rows = []
    for idx in range(0, len(ADVISOR_QUICK_SCENARIOS), 2):
        pair = ADVISOR_QUICK_SCENARIOS[idx: idx + 2]
        rows.append([_advisor_scenario_btn(slug, text) for slug, text in pair])
    rows.append([_back_btn(), _menu_btn()])
    return InlineKeyboardMarkup(rows)


def cancel_keyboard(back_target: str) -> InlineKeyboardMarkup:
    """Keyboard for input prompts: [❌ Отмена]."""
    return InlineKeyboardMarkup([[_btn("❌ Отмена", back_target)]])


# ---------------------------------------------------------------------------
# Main menu — inline keyboard
# ---------------------------------------------------------------------------

MENU_BTN_PLANNED  = "📋 Запланированные"
MENU_BTN_RECURRING = "🔄 Регулярные"
MENU_BTN_BUDGETS  = "💰 Бюджеты"
MENU_BTN_SETTINGS = "⚙️ Настройки"
MENU_BTN_HELP     = "ℹ️ Помощь"
MENU_BTN_CATEGORIES = "🗂 Категории"
MENU_BTN_ADVISOR = "🧠 Советник"


def main_menu_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn("📊 Сводка", "nav:stats")],
        [_btn(MENU_BTN_PLANNED, "nav:planned_input"), _btn(MENU_BTN_RECURRING, "nav:recurring_input")],
        [_btn(MENU_BTN_BUDGETS, "nav:budgets"), _btn(MENU_BTN_CATEGORIES, "nav:categories")],
        [_btn("🎯 Копилки", "nav:goals")],
        [_btn(MENU_BTN_ADVISOR, "nav:advisor")],
        [_btn(MENU_BTN_SETTINGS, "nav:settings"), _btn(MENU_BTN_HELP, "nav:help")],
    ])


def planned_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn("➕ Добавить", "nav:planned_input")],
        [_back_btn(), _menu_btn()],
    ])


def recurring_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn("➕ Добавить", "nav:recurring_input")],
        [_back_btn(), _menu_btn()],
    ])


def planned_input_keyboard() -> InlineKeyboardMarkup:
    """Shown when entering planned input mode."""
    return InlineKeyboardMarkup([
        [_btn("📋 Мои запланированные", "nav:planned_list")],
        [_back_btn("nav:menu")],
    ])


def recurring_input_keyboard() -> InlineKeyboardMarkup:
    """Shown when entering recurring input mode."""
    return InlineKeyboardMarkup([
        [_btn("🔄 Мои регулярные", "nav:recurring_list")],
        [_back_btn("nav:menu")],
    ])


def planned_confirm_keyboard() -> InlineKeyboardMarkup:
    """Confirmation keyboard after LLM extraction of planned expense."""
    return InlineKeyboardMarkup([
        [_btn("✅ Сохранить", "planned_input:confirm"),
         _btn("❌ Отмена", "planned_input:cancel")],
    ])


def planned_done_keyboard() -> InlineKeyboardMarkup:
    """After planned expense saved: add another or go to menu."""
    return InlineKeyboardMarkup([
        [_btn("📋 Ещё один", "nav:planned_input"), _menu_btn()],
    ])


def recurring_confirm_keyboard() -> InlineKeyboardMarkup:
    """Confirmation keyboard after LLM extraction of recurring transaction."""
    return InlineKeyboardMarkup([
        [_btn("✅ Сохранить", "recurring_input:confirm"),
         _btn("❌ Отмена", "recurring_input:cancel")],
    ])


def recurring_done_keyboard() -> InlineKeyboardMarkup:
    """After recurring rule saved: add another or go to menu."""
    return InlineKeyboardMarkup([
        [_btn("🔄 Ещё один", "nav:recurring_input"), _menu_btn()],
    ])


def planned_freeform_keyboard() -> InlineKeyboardMarkup:
    """Confirmation keyboard for planned expense detected from free-form text/voice."""
    return InlineKeyboardMarkup([
        [_btn("✅ Сохранить", "planned_freeform:save"),
         _btn("❌ Отмена", "planned_freeform:cancel")],
    ])


def recurring_freeform_keyboard() -> InlineKeyboardMarkup:
    """Confirmation keyboard for recurring transaction detected from free-form text/voice."""
    return InlineKeyboardMarkup([
        [_btn("✅ Сохранить", "recurring_freeform:save"),
         _btn("❌ Отмена", "recurring_freeform:cancel")],
    ])


def categories_nav_keyboard(categories_by_type: dict) -> InlineKeyboardMarkup:
    """Per-category row: emoji+name button (→edit) + ✏️ + optional 🗑."""
    rows: list[list[InlineKeyboardButton]] = []
    for group_type in ("expense", "income", "both"):
        for cat in categories_by_type.get(group_type, []):
            row = [
                _btn(f"{cat.emoji} {cat.name_ru}", f"categories:edit:{cat.slug}"),
                _btn("✏️", f"categories:edit:{cat.slug}"),
            ]
            if cat.is_custom:
                row.append(_btn("🗑", f"categories:delete:{cat.slug}"))
            rows.append(row)
    rows.append([_btn("➕ Добавить", "categories:add"), _back_btn()])
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# Categories v2 — type selector + paginated list
# ---------------------------------------------------------------------------

CATEGORIES_PAGE_SIZE = 8


def categories_type_keyboard() -> InlineKeyboardMarkup:
    """First categories screen: choose expense or income."""
    return InlineKeyboardMarkup([
        [_btn("💸 Расходы", "nav:categories:expense:0"),
         _btn("💰 Доходы", "nav:categories:income:0")],
        [_btn("➕ Добавить", "categories:add"), _back_btn()],
    ])


def categories_list_keyboard(
    cats: list,
    cat_type: str,
    page: int,
    total: int,
) -> InlineKeyboardMarkup:
    """Paginated list of categories for a given type.

    cats: slice of categories for this page (already sliced).
    cat_type: 'expense' or 'income'.
    page: current 0-based page index.
    total: total number of categories (for pagination math).
    """
    rows: list[list[InlineKeyboardButton]] = []

    # Category buttons — 2 per row
    row: list[InlineKeyboardButton] = []
    for cat in cats:
        row.append(_btn(
            f"{cat.emoji} {cat.name_ru}",
            f"categories:edit:{cat.slug}:{cat_type}:{page}",
        ))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    # Pagination row
    total_pages = max(1, (total + CATEGORIES_PAGE_SIZE - 1) // CATEGORIES_PAGE_SIZE)
    if total_pages > 1:
        nav_row: list[InlineKeyboardButton] = []
        if page > 0:
            nav_row.append(_btn("← Пред", f"nav:categories:{cat_type}:{page - 1}"))
        if page < total_pages - 1:
            nav_row.append(_btn("→ След", f"nav:categories:{cat_type}:{page + 1}"))
        if nav_row:
            rows.append(nav_row)

    rows.append([_btn("➕ Добавить", "categories:add"),
                 _back_btn("nav:categories")])
    return InlineKeyboardMarkup(rows)


def category_edit_keyboard(
    slug: str, is_custom: bool, is_hidden: bool, back_target: str = "nav:categories"
) -> InlineKeyboardMarkup:
    hide_label = "👁 Показать" if is_hidden else "🙈 Скрыть"
    rows = [
        [_btn("✏️ Изменить название", f"categories:rename:{slug}")],
        [_btn("🎨 Изменить emoji", f"categories:emoji:{slug}")],
        [_btn(hide_label, f"categories:toggle_hidden:{slug}")],
    ]
    if is_custom:
        rows.append([_btn("🗑 Удалить", f"categories:delete:{slug}")])
    rows.append([_back_btn(back_target)])
    return InlineKeyboardMarkup(rows)


def category_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            _btn("💸 Расход", "categories:set_type:expense"),
            _btn("💰 Доход", "categories:set_type:income"),
            _btn("↔️ Оба", "categories:set_type:both"),
        ],
        [_back_btn("nav:categories")],
    ])


def category_reassign_keyboard(categories: list, deleting_slug: str) -> InlineKeyboardMarkup:
    """List of same-type categories to reassign transactions to before deletion."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for cat in categories:
        if cat.slug == deleting_slug:
            continue
        btn = _btn(
            f"{cat.emoji} {cat.name_ru}",
            f"categories:reassign:{deleting_slug}__{cat.slug}",
        )
        row.append(btn)
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([_btn("❌ Отмена", "nav:categories")])
    return InlineKeyboardMarkup(rows)


def category_delete_confirm_keyboard(slug: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            _btn("✅ Да, удалить", f"categories:confirm_delete:{slug}"),
            _btn("❌ Отмена", "nav:categories"),
        ]
    ])


def budgets_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn("✏️ Общий бюджет", "budget:set_total"),
         _btn("🗂 По категории", "budget:pick_category")],
        [_menu_btn()],
    ])
    return InlineKeyboardMarkup(rows)


def budget_category_keyboard(categories: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    """Inline grid of expense categories to set budget for.

    categories: list of (slug, label) tuples.
    """
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for slug, label in categories:
        row.append(_btn(label, f"budget:set_category:{slug}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([_back_btn("nav:budgets")])
    return InlineKeyboardMarkup(rows)


def budget_confirm_keyboard() -> InlineKeyboardMarkup:
    """Confirmation after free-form total budget input."""
    return InlineKeyboardMarkup([
        [_btn("✅ Сохранить", "budget:total_confirm"),
         _btn("❌ Отмена", "budget:total_cancel")],
    ])


def budget_cat_confirm_keyboard() -> InlineKeyboardMarkup:
    """Confirmation after free-form category budget input."""
    return InlineKeyboardMarkup([
        [_btn("✅ Сохранить", "budget:cat_confirm"),
         _btn("❌ Отмена", "budget:cat_cancel")],
    ])


def budget_total_input_keyboard() -> InlineKeyboardMarkup:
    """Cancel button shown while awaiting total budget text/voice input."""
    return InlineKeyboardMarkup([[_btn("❌ Отмена", "budget:total_cancel")]])


def budget_cat_input_keyboard() -> InlineKeyboardMarkup:
    """Cancel button shown while awaiting category budget text/voice input."""
    return InlineKeyboardMarkup([[_btn("❌ Отмена", "budget:cat_cancel")]])


# ---------------------------------------------------------------------------
# Balance / Stats / Operations sections
# ---------------------------------------------------------------------------

def _period_row(section: str, current: str) -> list[InlineKeyboardButton]:
    periods = [("Сег", "today"), ("Нед", "week"), ("Мес", "month"), ("Всё", "all")]
    return [
        _btn(label + (" ✓" if current == key else ""), f"nav:{section}:{key}")
        for label, key in periods
    ]


def stats_inline_keyboard(period: str = "month") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        _period_row("stats", period),
        [_btn("📋 Операции", f"nav:ops:{period}"), _menu_btn()],
    ])


def operations_inline_keyboard(period: str = "month") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        _period_row("ops", period),
        [_btn("🗑 Удалить", f"nav:ops:delete_mode:{period}"), _btn("📊 Сводка", f"nav:stats:{period}"), _menu_btn()],
    ])


def operations_delete_keyboard(items: list[dict], period: str = "month") -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in items[:5]:
        sign = "+" if item["type"] == "income" else "−"
        cat_label = formatter.category_label(item["category"])
        rows.append([_btn(
            f"{sign}{item['amount']}₽  {cat_label}",
            f"nav:ops:del:{item['id']}:{period}",
        )])
    rows.append([_back_btn(f"nav:ops:{period}"), _menu_btn()])
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# Categories section
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Settings section
# ---------------------------------------------------------------------------

def settings_nav_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn("📅 Начало периода", "settings:budget_day")],
        [_btn("🔔 Напоминания", "settings:reminders")],
        [_btn("🌍 Часовой пояс", "settings:timezone")],
        [_btn("🗑 Сбросить данные", "reset:pick")],
        [_back_btn()],
    ])


def reset_pick_keyboard() -> InlineKeyboardMarkup:
    """Choose what to reset."""
    return InlineKeyboardMarkup([
        [_btn("🗑 Всё", "reset:confirm:all"),
         _btn("↘ Расходы", "reset:confirm:expense"),
         _btn("↗ Доходы", "reset:confirm:income")],
        [_back_btn("nav:settings")],
    ])


def reset_confirm_keyboard(scope: str) -> InlineKeyboardMarkup:
    """Confirm before destructive reset."""
    return InlineKeyboardMarkup([
        [_btn("✅ Да, удалить", f"reset:do:{scope}"),
         _btn("❌ Отмена", "nav:settings")],
    ])



def reminders_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn("⏰ Утреннее", "settings:morning"), _btn("🌙 Вечернее", "settings:evening")],
        [_btn("❌ Выключить все", "settings:disable_all")],
        [_back_btn("nav:settings")],
    ])


# ---------------------------------------------------------------------------
# Help section
# ---------------------------------------------------------------------------

def help_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn("💸 Как записать трату", "help:topic:input"), _btn("🎤 Голосовой ввод", "help:topic:voice")],
        [_btn("📊 Сводка", "help:topic:summary"), _btn("💰 Бюджеты", "help:topic:budget")],
        [_btn("🤖 Советник", "help:topic:advisor")],
        [_back_btn()],
    ])


def help_topic_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[_back_btn("nav:help")]])


# ---------------------------------------------------------------------------
# Voice confirmation
# ---------------------------------------------------------------------------

def voice_confirmation_keyboard(voice_log_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(text="✅ Да", callback_data=f"voice:confirm:{voice_log_id}"),
            InlineKeyboardButton(text="✏️ Изменить", callback_data=f"voice:edit:{voice_log_id}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"voice:cancel:{voice_log_id}"),
        ],
    ])


# ---------------------------------------------------------------------------
# Category resolution — INLINE (replaces Reply keyboard completely)
# ---------------------------------------------------------------------------

def category_resolution_keyboard(raw_category: str, suggestions: list[str]) -> InlineKeyboardMarkup:
    """Inline keyboard for unknown category resolution.
    Shows up to 3 suggested categories + 'Create new' + 'Cancel'.
    No Reply keyboard — everything stays in the message.
    """
    rows: list[list[InlineKeyboardButton]] = []

    # Suggested categories (up to 3), two per row
    suggestion_btns: list[InlineKeyboardButton] = []
    for slug in suggestions[:3]:
        emoji = CATEGORY_EMOJI.get(slug, "•")
        label = formatter.category_label(slug)
        suggestion_btns.append(_btn(f"{emoji} {label}", f"catres:use:{slug}"))
    # Pack into rows of 2
    for i in range(0, len(suggestion_btns), 2):
        rows.append(suggestion_btns[i:i + 2])

    # Create new category
    rows.append([_btn(f"➕ Создать «{raw_category}»", f"catres:create:{raw_category}")])
    # Cancel
    rows.append([_btn("❌ Отмена", "catres:cancel")])

    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# Low confidence — ask type (income / expense) inline
# ---------------------------------------------------------------------------

def low_confidence_keyboard(amount: str) -> InlineKeyboardMarkup:
    """When only amount is known — ask type first."""
    return InlineKeyboardMarkup([
        [
            _btn("↘ Расход", f"lowconf:expense:{amount}"),
            _btn("↗ Доход", f"lowconf:income:{amount}"),
        ],
        [_btn("❌ Отмена", "lowconf:cancel")],
    ])


def low_confidence_category_keyboard(
    tx_type: str, amount: str, categories: list[str] | None = None
) -> InlineKeyboardMarkup:
    """After type is chosen — pick category."""
    if categories is not None:
        slugs = categories
    elif tx_type == "income":
        slugs = ["salary", "freelance", "bonus", "transfer", "refund", "other_income"]
    else:
        slugs = ["food", "transport", "housing", "health", "entertainment",
                 "subscriptions", "shopping", "other"]

    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for slug in slugs:
        emoji = CATEGORY_EMOJI.get(slug, "•")
        label = formatter.category_label(slug)
        row.append(_btn(f"{emoji} {label}", f"lowconf:cat:{tx_type}:{amount}:{slug}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([_btn("❌ Отмена", "lowconf:cancel")])
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# Planned expenses
# ---------------------------------------------------------------------------

def planned_expense_due_keyboard(planned_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            _btn("✅ Учесть", f"planned:confirm:{planned_id}"),
            _btn("✏️ Другая сумма", f"planned:edit_amount:{planned_id}"),
        ],
        [_btn("📅 Новая дата", f"planned:edit_date:{planned_id}"), _btn("❌ Отмена", f"planned:cancel:{planned_id}")],
    ])


def planned_manage_keyboard(planned_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            _btn("✅ Учесть", f"planned:confirm:{planned_id}"),
            _btn("✏️ Другая сумма", f"planned:edit_amount:{planned_id}"),
        ],
        [
            _btn("📅 Новая дата", f"planned:edit_date:{planned_id}"),
            _btn("🗑 Удалить", f"planned:cancel:{planned_id}"),
        ],
    ])


# ---------------------------------------------------------------------------
# Evening check-in — quick category + amount inline
# ---------------------------------------------------------------------------

def evening_checkin_keyboard(top_categories: list[str]) -> InlineKeyboardMarkup:
    """Top categories as inline buttons + 'Nothing today'."""
    rows: list[list[InlineKeyboardButton]] = []
    cat_buttons: list[InlineKeyboardButton] = []
    for cat in top_categories[:3]:
        emoji = CATEGORY_EMOJI.get(cat, "•")
        label = formatter.category_label(cat)
        cat_buttons.append(_btn(f"{emoji} {label}", f"checkin:cat:{cat}"))
    if cat_buttons:
        rows.append(cat_buttons)
    rows.append([_btn("✅ Ничего не тратил", "checkin:none")])
    return InlineKeyboardMarkup(rows)


def evening_checkin_done_keyboard() -> InlineKeyboardMarkup:
    """After check-in save: add another expense or finish."""
    return InlineKeyboardMarkup([
        [_btn("➕ Ещё расход", "checkin:more"), _menu_btn()],
    ])


def evening_checkin_amount_keyboard(category: str) -> InlineKeyboardMarkup:
    """Quick amount buttons after category is chosen."""
    amounts = ["100", "200", "500", "1000", "2000"]
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for amt in amounts:
        row.append(_btn(amt + " ₽", f"checkin:amount:{category}:{amt}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([_btn("✏️ Другая сумма", f"checkin:custom:{category}")])
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# Undo
# ---------------------------------------------------------------------------

def undo_inline_keyboard(transaction_ids: list[str]) -> InlineKeyboardMarkup:
    ids_str = ",".join(transaction_ids)
    return InlineKeyboardMarkup([[_btn("↩ Отменить", f"undo:{ids_str}")]])


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def delete_keyboard(items: list[dict[str, str]]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=formatter.format_delete_button(item["amount"], item["category"]),
            callback_data=f"delete:one:{item['id']}",
        )]
        for item in items
    ]
    return InlineKeyboardMarkup(rows)


def deleteall_step1_keyboard() -> InlineKeyboardMarkup:
    """Первый шаг — предупреждение с кнопкой подтверждения шага 1."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚠️ Да, удалить ВСЕ данные", callback_data="deleteall:confirm_step1"),
            InlineKeyboardButton("❌ Отмена", callback_data="deleteall:cancel"),
        ],
    ])


def deleteall_step2_keyboard() -> InlineKeyboardMarkup:
    """Второй шаг — последнее подтверждение."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🗑 Удалить всё (последний шанс)", callback_data="deleteall:confirm_final"),
            InlineKeyboardButton("❌ Отмена", callback_data="deleteall:cancel"),
        ],
    ])


# ---------------------------------------------------------------------------
# Edit section
# ---------------------------------------------------------------------------

def edit_select_keyboard(items: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in items[:5]:
        sign = "+" if item["type"] == "income" else "−"
        cat = formatter.category_label(item["category"])
        label = f"{sign}{item['amount']}₽  {cat}"
        rows.append([_btn(label, f"edit:item:{item['id']}")])
    rows.append([_back_btn()])
    return InlineKeyboardMarkup(rows)


def edit_item_keyboard(transaction_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn("✏️ Сумма", f"edit:amount:{transaction_id}"),
         _btn("🗂 Категория", f"edit:cat:{transaction_id}")],
        [_btn("↕️ Тип", f"edit:type:{transaction_id}")],
        [_btn("🗑 Удалить", f"edit:del:{transaction_id}")],
        [_back_btn("edit:select")],
    ])


def edit_delete_confirm_keyboard(transaction_id: str) -> InlineKeyboardMarkup:
    """Confirm before deleting a transaction from edit screen."""
    return InlineKeyboardMarkup([
        [_btn("🗑 Да, удалить", f"edit:del_confirm:{transaction_id}"),
         _btn("❌ Отмена", f"edit:item:{transaction_id}")],
    ])


def edit_categories_keyboard(
    transaction_id: str, categories: list[tuple[str, str]] | None = None
) -> InlineKeyboardMarkup:
    if categories is not None:
        slugs = categories
    else:
        slugs = [
            ("food", "🍽"), ("transport", "🚌"), ("housing", "🏠"), ("health", "💊"),
            ("beauty", "✨"), ("entertainment", "🎬"), ("subscriptions", "📱"), ("shopping", "🛍"),
            ("home", "🪴"), ("telecom", "📡"), ("work", "💼"), ("education", "📚"),
            ("gifts", "🎁"), ("fees", "💳"), ("salary", "💰"), ("freelance", "🖥"),
            ("bonus", "🏆"), ("other", "•"),
        ]
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for slug, emoji in slugs:
        label_ru = formatter.category_label(slug)
        row.append(_btn(f"{emoji} {label_ru}", f"edit:cat:{transaction_id}:{slug}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([_back_btn(f"edit:item:{transaction_id}")])
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# WebApp launcher
# ---------------------------------------------------------------------------

def start_keyboard(webapp_url: str | None = None) -> InlineKeyboardMarkup | None:
    if not webapp_url:
        return None
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(text="📊 Открыть дашборд", web_app=WebAppInfo(url=webapp_url))]]
    )


# ---------------------------------------------------------------------------
# Category correction after save
# ---------------------------------------------------------------------------

def saved_actions_keyboard(transaction_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("↩️ Отменить", callback_data=f"undo:{transaction_id}"),
            InlineKeyboardButton("✏️ Категория", callback_data=f"catfix:change:{transaction_id}"),
        ]
    ])


def category_grid_keyboard(transaction_id: str, categories: list[str]) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            f"{CATEGORY_EMOJI.get(slug, '•')} {formatter.category_label(slug)}",
            callback_data=f"catfix:set:{transaction_id}:{slug}",
        )
        for slug in categories
    ]
    rows = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]
    rows.append([InlineKeyboardButton("❌ Отмена", callback_data=f"catfix:cancel:{transaction_id}")])
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# Recurring management
# ---------------------------------------------------------------------------

def recurring_manage_keyboard(recurring_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            _btn("💰 Изменить сумму", f"recurring:amount:{recurring_id}"),
            _btn("📅 Изменить период", f"recurring:schedule:{recurring_id}"),
        ],
        [
            _btn("📂 Изменить категорию", f"recurring:category:{recurring_id}"),
            _btn("⏸ Отключить", f"recurring:disable:{recurring_id}"),
        ],
    ])


def recurring_category_keyboard(recurring_id: int, categories: list[str]) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(formatter.category_label(slug), callback_data=f"recurring:set_category:{recurring_id}:{slug}")
        for slug in categories
    ]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton("❌ Отмена", callback_data=f"recurring:cancel:{recurring_id}")])
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# Suggestion approval keyboard (/improve_categories)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Onboarding keyboards
# ---------------------------------------------------------------------------

def onboarding_step2_keyboard() -> InlineKeyboardMarkup:
    """Step 2: skip budget button."""
    return InlineKeyboardMarkup([[_btn("Пропустить →", "onboarding:skip_budget")]])


def onboarding_step3_keyboard() -> InlineKeyboardMarkup:
    """Step 3: open summary or advisor."""
    return InlineKeyboardMarkup([
        [
            _btn("📊 Открыть сводку", "nav:stats"),
            _btn("🧠 Задать вопрос", "nav:advisor"),
        ]
    ])


def suggestion_keyboard(suggestion_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Да", callback_data=f"{suggestion_key}_yes"),
        InlineKeyboardButton("❌ Нет", callback_data=f"{suggestion_key}_no"),
    ]])


def grouped_suggestion_keyboard(items: list[dict]) -> InlineKeyboardMarkup:
    """One keyboard with numbered ✅/❌ per suggestion."""
    rows: list[list[InlineKeyboardButton]] = []
    for i, item in enumerate(items, 1):
        rows.append([
            InlineKeyboardButton(f"✅ {i}", callback_data=f"{item['key']}_yes"),
            InlineKeyboardButton(f"❌ {i}", callback_data=f"{item['key']}_no"),
        ])
    return InlineKeyboardMarkup(rows)


def intent_clarify_keyboard() -> InlineKeyboardMarkup:
    """Ask user to clarify payment intent when LLM confidence < 0.75."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Уже оплачено", callback_data="clarify:transaction"),
            InlineKeyboardButton("📅 Запланировать", callback_data="clarify:planned"),
        ],
        [
            InlineKeyboardButton("🔄 Регулярный", callback_data="clarify:recurring"),
            InlineKeyboardButton("❌ Отмена", callback_data="clarify:cancel"),
        ],
    ])


def undo_keyboard(result) -> InlineKeyboardMarkup:
    """
    Клавиатура после успешного действия.
    Показывает кнопку отмены если result.is_reversible и undo_payload непустой.
    """
    rows = []
    if result.is_reversible and result.undo_payload:
        rows.append([InlineKeyboardButton("↩ Отменить", callback_data="action:undo")])
    rows.append([
        InlineKeyboardButton("← К советнику", callback_data="nav:advisor"),
        InlineKeyboardButton("≡ Меню", callback_data="nav:menu"),
    ])
    return InlineKeyboardMarkup(rows)


def back_keyboard() -> InlineKeyboardMarkup:
    """Простая навигация без undo."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("← К советнику", callback_data="nav:advisor"),
        InlineKeyboardButton("≡ Меню", callback_data="nav:menu"),
    ]])


# ---------------------------------------------------------------------------
# Savings Goal keyboards
# ---------------------------------------------------------------------------


def goals_list_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn("🎯 Новая цель", "goals:new")],
        [_menu_btn()],
    ])


def goal_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn("✅ Создать", "goals:confirm"), _btn("✏️ Изменить", "goals:edit")],
        [_btn("❌ Отмена", "goals:cancel")],
    ])


def goal_deposit_keyboard(goal_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn("💰 Пополнить", f"goals:deposit:{goal_id}")],
        [_btn("⚙️ Настроить", f"goals:settings:{goal_id}"), _btn("◀️ Назад", "nav:goals")],
    ])


def goal_settings_keyboard(goal_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn("✅ Завершить", f"goals:complete:{goal_id}")],
        [_btn("◀️ Назад", f"goals:nav:{goal_id}")],
    ])

