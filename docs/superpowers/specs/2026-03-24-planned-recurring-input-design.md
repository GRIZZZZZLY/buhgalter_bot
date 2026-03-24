# Дизайн: свободный ввод запланированных и регулярных платежей

**Дата:** 2026-03-24
**Статус:** Approved
**Область:** Telegram-бот, backend

---

## Цель

Дать пользователю возможность добавлять запланированные расходы и регулярные платежи через кнопки в главном меню, отправив текст или голосовое сообщение в свободном формате. LLM извлекает структурированные данные, бот показывает подтверждение перед сохранением.

---

## UX-флоу

### Запланированные расходы

1. Пользователь нажимает **[📋 Запланированные]** в главном меню.
2. Бот устанавливает `user_data["mode"] = "planned_input"` и отвечает:
   ```
   Опиши запланированный расход — название, сумму и дату.
   Например: «маникюр 2100 рублей 15 апреля»

   [📋 Мои запланированные]  [← Назад]
   ```
3. Пользователь отправляет текст или голосовое сообщение.
4. LLM извлекает: `{title, amount, category_slug, planned_date_iso}`.
5. Бот показывает экран подтверждения:
   ```
   Запланировал:
   🏷 Стоматолог
   💰 8 000 ₽
   📅 22 апреля 2026
   🏥 Здоровье

   [✅ Сохранить]  [❌ Отмена]
   ```
6. Пользователь нажимает **[✅ Сохранить]** → вызывается `PlannedExpenseService.create_manual()`.
7. Бот отвечает: `✅ Запланировано: Стоматолог — 8 000 ₽ на 22 апреля` + показывает главное меню.

### Регулярные платежи

1. Пользователь нажимает **[🔄 Регулярные]** в главном меню.
2. Бот устанавливает `user_data["mode"] = "recurring_input"` и отвечает:
   ```
   Опиши регулярный платёж — название, сумму и периодичность.
   Например: «аренда 30000 каждый месяц 1 числа»
             «зарплата 120000 каждый месяц 10 числа»

   [🔄 Мои регулярные]  [← Назад]
   ```
3. Пользователь отправляет текст или голосовое сообщение.
4. LLM извлекает: `{title, amount, transaction_type, category_slug, frequency, day_value}`.
5. Бот показывает экран подтверждения:
   ```
   Регулярный платёж:
   🏷 Netflix
   💰 −799 ₽
   📅 Каждый месяц, 15-го
   📱 Подписки

   [✅ Сохранить]  [❌ Отмена]
   ```
6. Пользователь нажимает **[✅ Сохранить]** → вызывается `RecurringService.create()`.
7. Бот отвечает: `✅ Добавлено: Netflix −799 ₽ каждый месяц 15-го` + показывает главное меню.

---

## Модель данных

Новых таблиц не создаётся. Используются существующие:

- `planned_expenses` — для запланированных расходов (`source = "manual"`)
- `recurring_transactions` — для регулярных платежей

---

## Архитектура

### `backend/app/services/llm_service.py`

Два новых публичных метода:

#### `extract_planned(text: str, user_categories: list[dict]) -> dict | None`

Вызывает LLM в режиме `response_format={"type": "json_object"}`.

**Системный промпт:**
```
Извлеки из текста параметры запланированного расхода.
Верни JSON: {"title": str, "amount": float, "category_slug": str, "planned_date_iso": str | null}.
Категории пользователя: <список slug: name_ru>.
Если дата не упомянута — planned_date_iso: null.
Дата в формате ISO: "2026-04-22".
```

**Возвращает:** dict с полями или `None` при ошибке LLM.

**Обязательные поля:** `title`, `amount`, `planned_date_iso` (не null).

#### `extract_recurring(text: str, user_categories: list[dict]) -> dict | None`

**Системный промпт:**
```
Извлеки из текста параметры регулярного платежа.
Верни JSON: {"title": str, "amount": float, "transaction_type": "expense"|"income",
"category_slug": str, "frequency": "monthly"|"weekly"|"daily"|"interval_days", "day_value": int}.
Категории пользователя: <список slug: name_ru>.
Для monthly: day_value = день месяца (1-28).
Для weekly: day_value = день недели (0=пн...6=вс).
Для interval_days: day_value = количество дней.
Для daily: day_value = 1.
Если тип не ясен — "expense".
```

**Возвращает:** dict с полями или `None` при ошибке LLM.

**Все поля обязательны.**

### `backend/app/telegram/keyboards.py`

**Изменения в `main_menu_inline_keyboard()`:** добавить две кнопки:
```python
[_btn("📋 Запланированные", "nav:planned_input"),
 _btn("🔄 Регулярные",      "nav:recurring_input")]
```

**Новые функции:**

```python
def planned_confirm_keyboard() -> InlineKeyboardMarkup:
    """[✅ Сохранить] [❌ Отмена]"""

def recurring_confirm_keyboard() -> InlineKeyboardMarkup:
    """[✅ Сохранить] [❌ Отмена]"""

def planned_input_keyboard() -> InlineKeyboardMarkup:
    """[📋 Мои запланированные] [← Назад]"""

def recurring_input_keyboard() -> InlineKeyboardMarkup:
    """[🔄 Мои регулярные] [← Назад]"""
```

### `backend/app/telegram/runtime.py`

#### Новые callback_data

| callback_data | Действие |
|---|---|
| `nav:planned_input` | установить `mode = "planned_input"`, показать подсказку с `planned_input_keyboard()` |
| `nav:recurring_input` | установить `mode = "recurring_input"`, показать подсказку с `recurring_input_keyboard()` |
| `nav:planned_list` | показать список запланированных (существующая логика `/planned`) |
| `nav:recurring_list` | показать список регулярных (существующая логика `/recurring`) |
| `planned:confirm` | сохранить `user_data["pending_planned"]` через `PlannedExpenseService.create_manual()` |
| `planned:cancel` | очистить `mode` и `pending_planned`, вернуть главное меню |
| `recurring:confirm` | сохранить `user_data["pending_recurring"]` через `RecurringService.create()` |
| `recurring:cancel` | очистить `mode` и `pending_recurring`, вернуть главное меню |

#### `text_message_handler` — добавить обработку mode

```python
mode = context.user_data.get("mode")

if mode == "planned_input":
    await _handle_planned_input(update, context, text)
    return

if mode == "recurring_input":
    await _handle_recurring_input(update, context, text)
    return
```

#### `voice_message_handler` — аналогично

После STT-транскрипции, перед обычной обработкой:
```python
mode = context.user_data.get("mode")
if mode == "planned_input":
    await _handle_planned_input(update, context, transcribed_text)
    return
if mode == "recurring_input":
    await _handle_recurring_input(update, context, transcribed_text)
    return
```

#### Сброс mode при навигации

В `nav_callback_handler`, в начале обработки:
```python
context.user_data.pop("mode", None)
context.user_data.pop("pending_planned", None)
context.user_data.pop("pending_recurring", None)
```

#### `_handle_planned_input(update, context, text)`

1. Получить категории пользователя через `CategoryService`.
2. Вызвать `llm_service.extract_planned(text, user_categories)`.
3. При ошибке LLM → «Не смог разобрать. Попробуй ещё раз».
4. Валидация: `planned_date_iso` не null → «Не понял дату. Укажи, например: 15 апреля».
5. Валидация: `planned_date_iso >= today` → «Дата уже прошла. Укажи будущую дату».
6. Сохранить в `user_data["pending_planned"]`.
7. Очистить `user_data["mode"]`.
8. Отправить сообщение подтверждения с `planned_confirm_keyboard()`.

#### `_handle_recurring_input(update, context, text)`

1. Получить категории пользователя через `CategoryService`.
2. Вызвать `llm_service.extract_recurring(text, user_categories)`.
3. При ошибке LLM → «Не смог разобрать. Попробуй ещё раз».
4. Валидация: все обязательные поля присутствуют.
5. Сохранить в `user_data["pending_recurring"]`.
6. Очистить `user_data["mode"]`.
7. Отправить сообщение подтверждения с `recurring_confirm_keyboard()`.

---

## Обработка ошибок

| Ситуация | Ответ бота |
|---|---|
| LLM вернул `null` в `planned_date_iso` | «Не понял дату. Укажи, например: 15 апреля или через 2 недели» |
| `planned_date_iso` в прошлом | «Дата уже прошла. Укажи будущую дату» |
| LLM вернул `null` в обязательном поле | «Не понял [поле]. Попробуй ещё раз» |
| LLM недоступен / исключение | «Не смог разобрать. Попробуй ещё раз» |
| Навигация при активном `mode` | `mode` и `pending_*` очищаются |

---

## Кастомные категории в LLM

LLM получает список категорий пользователя (системные + кастомные) через `CategoryService.list_categories(telegram_user_id)`. Список передаётся в системный промпт как `slug: name_ru` строки. Это обеспечивает корректную работу кастомных категорий (например, «Спорт» → `sport`).

---

## Что НЕ входит в scope

- Редактирование уже сохранённых запланированных/регулярных через этот флоу
- Удаление через этот флоу (остаётся через `/recurring_del`)
- Изменение даты или суммы на экране подтверждения (только Сохранить / Отмена)
- Поддержка `interval_days` в LLM-промпте как особого случая (передаётся как есть)

---

## Замечание по тестам

Добавление двух кнопок в `main_menu_inline_keyboard()` может сломать снапшот-тест в `test_navigation_menu.py`. Обновить при реализации.
