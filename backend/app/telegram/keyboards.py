from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo

from app.telegram.formatter import TreasuryFormatter

formatter = TreasuryFormatter()

CATEGORY_EMOJI = {
    "food": "\U0001f354",
    "transport": "\U0001f695",
    "housing": "\U0001f3e0",
    "health": "\U0001f48a",
    "beauty": "\U0001f484",
    "entertainment": "\U0001f3ad",
    "subscriptions": "\U0001f4f1",
    "shopping": "\U0001f6cd\ufe0f",
    "home": "\U0001f3e1",
    "telecom": "\U0001f4de",
    "work": "\U0001f4bb",
    "education": "\U0001f4da",
    "gifts": "\U0001f381",
    "fees": "\U0001f4b3",
    "salary": "\U0001f4b0",
    "freelance": "\U0001f4bc",
    "other": "\U0001f4cc",
}


def start_keyboard(webapp_url: str | None = None) -> InlineKeyboardMarkup | None:
    if not webapp_url:
        return None
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(text="Открыть сводку", web_app=WebAppInfo(url=webapp_url))]]
    )


def voice_confirmation_keyboard(voice_log_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(text="Да", callback_data=f"voice:confirm:{voice_log_id}"),
                InlineKeyboardButton(text="Отмена", callback_data=f"voice:cancel:{voice_log_id}"),
            ],
            [InlineKeyboardButton(text="Изменить", callback_data=f"voice:edit:{voice_log_id}")],
        ]
    )


def delete_keyboard(items: list[dict[str, str]]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=formatter.format_delete_button(item["amount"], item["category"]),
                callback_data=f"delete:one:{item['id']}",
            )
        ]
        for item in items
    ]
    return InlineKeyboardMarkup(rows)


def delete_all_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(text="Да, удалить всё", callback_data="deleteall:confirm")],
            [InlineKeyboardButton(text="Отмена", callback_data="deleteall:cancel")],
        ]
    )



def category_resolution_keyboard(raw_category: str, suggestions: list[str]) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = []
    rows.append([KeyboardButton(text=formatter.format_create_category_option(raw_category))])
    for suggestion in suggestions[:3]:
        rows.append([KeyboardButton(text=formatter.category_label(suggestion))])
    rows.append([KeyboardButton(text="Отменить")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, one_time_keyboard=True, selective=True)


def evening_checkin_keyboard(top_categories: list[str]) -> ReplyKeyboardMarkup:
    """Build a reply keyboard with the user's top categories + 'Не тратил' button."""
    rows: list[list[KeyboardButton]] = []
    category_buttons: list[KeyboardButton] = []
    for cat in top_categories[:3]:
        emoji = CATEGORY_EMOJI.get(cat, "\U0001f4cc")
        label = formatter.category_label(cat)
        category_buttons.append(KeyboardButton(text=f"{emoji} {label}"))
    if category_buttons:
        rows.append(category_buttons)
    rows.append([KeyboardButton(text="\u2705 Не тратил")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, one_time_keyboard=True)


def settings_keyboard() -> InlineKeyboardMarkup:
    """Build settings menu keyboard."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text="\U0001f4b0 Бюджет", callback_data="settings:budget")],
        [InlineKeyboardButton(text="\u23f0 Утреннее напоминание", callback_data="settings:morning")],
        [InlineKeyboardButton(text="\U0001f319 Вечернее напоминание", callback_data="settings:evening")],
        [InlineKeyboardButton(text="\U0001f30d Часовой пояс", callback_data="settings:timezone")],
        [InlineKeyboardButton(text="\u274c Выключить напоминания", callback_data="settings:disable_all")],
    ])
