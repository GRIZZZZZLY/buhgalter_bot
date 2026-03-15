from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo

from app.telegram.formatter import TreasuryFormatter

formatter = TreasuryFormatter()


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
