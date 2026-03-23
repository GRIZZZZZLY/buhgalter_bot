from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, WebAppInfo

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


# ---------------------------------------------------------------------------
# Main menu — inline keyboard
# ---------------------------------------------------------------------------

MENU_BTN_BALANCE  = "💰 Баланс"
MENU_BTN_STATS    = "📊 Статистика"
MENU_BTN_OPS      = "📋 Операции"
MENU_BTN_CATS     = "📂 Категории"
MENU_BTN_SETTINGS = "⚙️ Настройки"
MENU_BTN_HELP     = "ℹ️ Помощь"


def main_menu_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn(MENU_BTN_BALANCE, "nav:balance"), _btn(MENU_BTN_STATS, "nav:stats")],
        [_btn(MENU_BTN_OPS, "nav:ops")],
        [_btn(MENU_BTN_CATS, "nav:cats"), _btn(MENU_BTN_SETTINGS, "nav:settings")],
        [_btn(MENU_BTN_HELP, "nav:help")],
    ])


# ---------------------------------------------------------------------------
# Balance / Stats / Operations sections
# ---------------------------------------------------------------------------

def _period_row(section: str, current: str) -> list[InlineKeyboardButton]:
    periods = [("Сег", "today"), ("Нед", "week"), ("Мес", "month"), ("Всё", "all")]
    return [
        _btn(label + (" ✓" if current == key else ""), f"nav:{section}:{key}")
        for label, key in periods
    ]


def balance_inline_keyboard(period: str = "month") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        _period_row("balance", period),
        [_btn("📊 Статистика", "nav:stats"), _menu_btn()],
    ])


def stats_inline_keyboard(period: str = "month") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        _period_row("stats", period),
        [_btn("💰 Баланс", "nav:balance"), _menu_btn()],
    ])


def operations_inline_keyboard(period: str = "month") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        _period_row("ops", period),
        [_btn("🗑 Удалить", "nav:ops:delete_mode"), _menu_btn()],
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

def categories_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn("↗ Доходы", "nav:cats:income"), _btn("↘ Траты", "nav:cats:expense")],
        [_back_btn()],
    ])


def categories_list_inline_keyboard(tx_type: str, top_cats: list[str]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for slug in top_cats[:8]:
        emoji = CATEGORY_EMOJI.get(slug, "•")
        label = formatter.category_label(slug)
        rows.append([_btn(f"{emoji} {label}", f"nav:cats:detail:{slug}")])
    rows.append([_back_btn("nav:cats"), _menu_btn()])
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# Settings section
# ---------------------------------------------------------------------------

def settings_nav_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn("📅 Начало периода", "settings:budget_day")],
        [_btn("💰 Бюджет на месяц", "settings:budget")],
        [_btn("🔔 Напоминания", "settings:reminders")],
        [_btn("🌍 Часовой пояс", "settings:timezone")],
        [_btn("⏰ Утреннее", "settings:morning"), _btn("🌙 Вечернее", "settings:evening")],
        [_btn("❌ Выключить все", "settings:disable_all")],
        [_back_btn()],
    ])


def settings_keyboard() -> InlineKeyboardMarkup:
    """Used by /settings command."""
    return InlineKeyboardMarkup([
        [_btn("💰 Бюджет", "settings:budget")],
        [_btn("⏰ Утреннее напоминание", "settings:morning")],
        [_btn("🌙 Вечернее напоминание", "settings:evening")],
        [_btn("🌍 Часовой пояс", "settings:timezone")],
        [_btn("❌ Выключить напоминания", "settings:disable_all")],
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


def low_confidence_category_keyboard(tx_type: str, amount: str) -> InlineKeyboardMarkup:
    """After type is chosen — pick category."""
    if tx_type == "income":
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


def edit_categories_keyboard(transaction_id: str) -> InlineKeyboardMarkup:
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
        InlineKeyboardButton(slug, callback_data=f"catfix:set:{transaction_id}:{slug}")
        for slug in categories
    ]
    rows = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]
    rows.append([InlineKeyboardButton("❌ Отмена", callback_data=f"catfix:cancel:{transaction_id}")])
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# Suggestion approval keyboard (/improve_categories)
# ---------------------------------------------------------------------------

def suggestion_keyboard(suggestion_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Да", callback_data=f"{suggestion_key}_yes"),
        InlineKeyboardButton("❌ Нет", callback_data=f"{suggestion_key}_no"),
    ]])


# ---------------------------------------------------------------------------
# Compatibility shim — remove_reply_keyboard kept for any remaining callers
# ---------------------------------------------------------------------------

def remove_reply_keyboard() -> ReplyKeyboardRemove:
    """Kept for backward compatibility. No longer used in new flows."""
    return ReplyKeyboardRemove()
