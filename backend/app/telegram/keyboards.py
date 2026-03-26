from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

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


def advisor_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for one-off QA responses: [🧠 Продолжить в советнике] [≡ Меню]."""
    return InlineKeyboardMarkup([
        [_btn("🧠 Продолжить в советнике", "nav:advisor")],
        [_btn("📊 Сводка", "nav:stats"), _menu_btn()],
    ])


def advisor_session_keyboard() -> InlineKeyboardMarkup:
    """Keyboard after each advisor answer in dialog mode: [✕ Завершить]."""
    return InlineKeyboardMarkup([[_btn("✕ Завершить", "nav:menu")]])


def advisor_onboarding_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for advisor onboarding screen."""
    return InlineKeyboardMarkup([[_back_btn(), _menu_btn()]])


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


def recurring_confirm_keyboard() -> InlineKeyboardMarkup:
    """Confirmation keyboard after LLM extraction of recurring transaction."""
    return InlineKeyboardMarkup([
        [_btn("✅ Сохранить", "recurring_input:confirm"),
         _btn("❌ Отмена", "recurring_input:cancel")],
    ])


def categories_nav_keyboard(categories_by_type: dict) -> InlineKeyboardMarkup:
    """Per-category row: emoji+name button (noop) + ✏️ + optional 🗑."""
    rows: list[list[InlineKeyboardButton]] = []
    for group_type in ("expense", "income", "both"):
        for cat in categories_by_type.get(group_type, []):
            row = [
                _btn(f"{cat.emoji} {cat.name_ru}", f"categories:noop:{cat.slug}"),
                _btn("✏️", f"categories:edit:{cat.slug}"),
            ]
            if cat.is_custom:
                row.append(_btn("🗑", f"categories:delete:{cat.slug}"))
            rows.append(row)
    rows.append([_btn("➕ Добавить", "categories:add"), _back_btn()])
    return InlineKeyboardMarkup(rows)


def category_edit_keyboard(slug: str, is_custom: bool, is_hidden: bool) -> InlineKeyboardMarkup:
    hide_label = "👁 Показать" if is_hidden else "🙈 Скрыть"
    rows = [
        [_btn("✏️ Изменить название", f"categories:rename:{slug}")],
        [_btn("🎨 Изменить emoji", f"categories:emoji:{slug}")],
        [_btn(hide_label, f"categories:toggle_hidden:{slug}")],
    ]
    if is_custom:
        rows.append([_btn("🗑 Удалить", f"categories:delete:{slug}")])
    rows.append([_back_btn("nav:categories")])
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
            _btn("Отмена", "nav:categories"),
        ]
    ])


def budgets_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn("✏️ Общий бюджет", "budget:set_total"),
         _btn("🗂 По категории", "budget:pick_category")],
        [_menu_btn()],
    ])


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
        [_back_btn()],
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
    return InlineKeyboardMarkup([[_back_btn()]])


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
            _btn("✏️ Изменить сумму и учесть", f"planned:edit_amount:{planned_id}"),
        ],
        [_btn("📅 Изменить дату", f"planned:edit_date:{planned_id}"), _btn("❌ Отменить", f"planned:cancel:{planned_id}")],
    ])


def planned_manage_keyboard(planned_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            _btn("✅ Учесть", f"planned:confirm:{planned_id}"),
            _btn("✏️ Учесть с другой суммой", f"planned:edit_amount:{planned_id}"),
        ],
        [
            _btn("📅 Изменить дату", f"planned:edit_date:{planned_id}"),
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


def delete_all_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text="Да, удалить всё", callback_data="deleteall:confirm")],
        [InlineKeyboardButton(text="Отмена", callback_data="deleteall:cancel")],
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
        [_btn("↕️ Тип", f"edit:type:{transaction_id}"),
         _btn("🗑 Удалить", f"edit:del:{transaction_id}")],
        [_back_btn("edit:select")],
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

def suggestion_keyboard(suggestion_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Да", callback_data=f"{suggestion_key}_yes"),
        InlineKeyboardButton("❌ Нет", callback_data=f"{suggestion_key}_no"),
    ]])


