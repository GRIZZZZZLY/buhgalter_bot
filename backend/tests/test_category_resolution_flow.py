from telegram import ReplyKeyboardMarkup

from app.telegram.handlers import TelegramTextFlow
from app.telegram.keyboards import category_resolution_keyboard


def test_category_resolution_offers_reply_keyboard_and_saves_selected_suggestion(db_session) -> None:
    flow = TelegramTextFlow(db_session)

    first = flow.handle_text(telegram_user_id=555, text='расход 1200 красота и здоровье')
    assert first['action'] == 'clarify_category_choice'
    assert first['raw_category'] == 'красота и здоровье'
    assert 'beauty' in first['suggestions']
    assert 'health' in first['suggestions']

    keyboard = category_resolution_keyboard(first['raw_category'], first['suggestions'])
    assert isinstance(keyboard, ReplyKeyboardMarkup)
    labels = [button.text for row in keyboard.keyboard for button in row]
    assert 'Создать «красота и здоровье»' in labels
    assert 'Красота' in labels
    assert 'Здоровье' in labels

    second = flow.handle_text(telegram_user_id=555, text='Красота')
    assert second['action'] == 'saved'
    assert second['remove_keyboard'] is True
    assert 'Красота' in second['message']


def test_category_resolution_can_create_new_category(db_session) -> None:
    flow = TelegramTextFlow(db_session)

    flow.handle_text(telegram_user_id=555, text='расход 900 красота и здоровье')
    second = flow.handle_text(telegram_user_id=555, text='Создать «красота и здоровье»')

    assert second['action'] == 'saved'
    assert 'красота и здоровье' in second['message'].lower()


def test_category_resolution_strips_forward_prefixes(db_session) -> None:
    flow = TelegramTextFlow(db_session)

    first = flow.handle_text(telegram_user_id=555, text='расход 800 красота и здоровье')
    assert first['action'] == 'clarify_category_choice'

    second = flow.handle_text(telegram_user_id=555, text='Переслано от Игорь\nЗдоровье')
    assert second['action'] == 'saved'
    assert 'Здоровье' in second['message']


def test_category_resolution_appears_for_single_strong_suggestion(db_session) -> None:
    flow = TelegramTextFlow(db_session)

    first = flow.handle_text(telegram_user_id=555, text='1000 рублей на массаж')

    assert first['action'] == 'clarify_category_choice'
    assert first['raw_category'] == 'массаж'
    keyboard = category_resolution_keyboard(first['raw_category'], first['suggestions'])
    labels = [button.text for row in keyboard.keyboard for button in row]
    assert 'Создать «массаж»' in labels


def test_category_resolution_treats_new_text_as_new_category_attempt(db_session) -> None:
    flow = TelegramTextFlow(db_session)

    flow.handle_text(telegram_user_id=555, text='1000 рублей на массаж')
    second = flow.handle_text(telegram_user_id=555, text='Красота и здоровье')

    assert second['action'] == 'clarify_category_choice'
    assert second['raw_category'] == 'красота и здоровье'
    assert 'beauty' in second['suggestions']
    assert 'health' in second['suggestions']
