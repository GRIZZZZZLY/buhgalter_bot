import pytest
from app.services.input_guard import InputGuard

guard = InputGuard()

REJECTION_MSG = "Я работаю только с финансами — расходами, доходами и бюджетом."


# --- Blacklist: explicit off-topic → rejected ---

@pytest.mark.parametrize("text", [
    "расскажи анекдот",
    "Расскажи Анекдот",                  # case-insensitive
    "напиши стих про осень",
    "привет как дела",
    "здравствуй",
    "добрый день",
    "какая погода завтра",
    "новости спорта",
    "дай рецепт борща",
    "помоги с домашним заданием",
    "расскажи анекдот про 100 рублей",   # blacklist wins over digit
    "как дела с бюджетом?",              # blacklist "как дела" wins over whitelist "бюджет"
])
def test_blacklist_rejected(text):
    assert guard.check(text) == REJECTION_MSG


# --- Whitelist: financial signals → passed ---

@pytest.mark.parametrize("text", [
    "потратил 500 на еду",
    "купил кофе за 150",
    "заплатил 3000 за интернет",
    "получил зарплату 80000",
    "перевел 1000 маме",
    "списали 299₽ за подписку",
    "налог 13%",
    "кредит закрыт",
    "расход на такси",                   # financial keyword, no digit
    "бюджет на месяц",
    "напиши расход на такси",            # "напиши" NOT in blacklist; whitelist "расход" saves it
    "расскажи сколько я потратил",       # NOT blacklisted; whitelist "потратил" saves it
])
def test_whitelist_passed(text):
    assert guard.check(text) is None


@pytest.mark.parametrize("text", [
    "потратил на еду",        # financial keyword без цифры
    "доход вырос",
    "долг перед банком",
    "депозит открыл",
    "выплата по кредиту",
])
def test_whitelist_keywords_no_digit(text):
    assert guard.check(text) is None


# --- Default reject: no signals on either side ---

@pytest.mark.parametrize("text", [
    "ок",
    "хорошо",
    "понял",
    "да",
    "нет",
    "",
    "   ",
    "lorem ipsum",
    "расскажи",          # "расскажи" alone — not blacklisted, no financial signal → default reject
    "напиши",            # same
])
def test_default_rejected(text):
    assert guard.check(text) == REJECTION_MSG
