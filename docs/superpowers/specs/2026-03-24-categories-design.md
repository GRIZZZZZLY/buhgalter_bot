# Дизайн: раздел «Категории» в Telegram-боте

**Дата:** 2026-03-24
**Статус:** Approved
**Область:** Telegram-бот, backend

---

## Цель

Дать пользователю возможность видеть список своих категорий, добавлять кастомные и редактировать любые (системные и кастомные): имя, emoji. Удалять можно только кастомные категории.

---

## Модель данных

### Новая таблица `user_categories`

| Поле | Тип | SQLAlchemy | Ограничения | Описание |
|---|---|---|---|---|
| `id` | INTEGER | `Integer` | PK, autoincrement | |
| `telegram_user_id` | BIGINT | `BigInteger` | NOT NULL, index | владелец (как во всех других моделях) |
| `slug` | VARCHAR(50) | `String(50)` | NOT NULL | ключ категории (`food`, `sport`) |
| `name_ru` | VARCHAR(100) | `String(100)` | NOT NULL | отображаемое имя на русском |
| `emoji` | VARCHAR(10) | `String(10)` | NOT NULL | emoji-иконка |
| `type` | VARCHAR(10) | `String(10)` | NOT NULL | `expense` / `income` / `both` |
| `is_custom` | BOOLEAN | `Boolean` | NOT NULL, default False | системная или кастомная |
| `sort_order` | INTEGER | `Integer` | NOT NULL, default 0 | порядок в списке |
| `created_at` | DATETIME | `DateTime(timezone=True)` | server_default now | |
| `updated_at` | DATETIME | `DateTime(timezone=True)` | server_default now, onupdate now | как во всех других моделях |

**Уникальный индекс:** `(telegram_user_id, slug)`

### Инициализация (seeding)

При первом открытии раздела «Категории» вызывается `seed_system_categories(telegram_user_id)`.

Метод должен быть **идемпотентным и race-safe**: использовать `INSERT OR IGNORE` / `ON CONFLICT (telegram_user_id, slug) DO NOTHING` на уровне SQL. Двойной tap или параллельный вызов не вызывает ошибок.

Системные категории:
- `is_custom = False` — нельзя удалить, можно переименовать и поменять emoji
- `sort_order` задаётся по порядку из YAML (0, 1, 2 ...)

Кастомные категории:
- `is_custom = True` — можно удалить, редактировать
- `sort_order = max(sort_order) + 1` среди всех категорий пользователя (вычисляется в репозитории)

### Замечание: rename не затрагивает транзакции

`rename` изменяет только `name_ru`. Поле `Transaction.category` хранит **slug** (`food`), а не отображаемое имя, поэтому rename безопасен — транзакции и `UserCategoryMapping` трогать не нужно.

---

## Архитектура

### Фаза 1 — Backend (данные)

**`backend/app/models/user_category.py`** — ORM-модель `UserCategory`

**`backend/alembic/versions/XXXXXX_create_user_categories.py`** — миграция. Важно: `telegram_user_id` должен быть `BigInteger`, не `Integer`, для совместимости с PostgreSQL.

**`backend/app/repositories/user_category_repository.py`** — методы:
- `get_all(telegram_user_id)` → list[UserCategory], отсортировано по `sort_order`
- `get_by_slug(telegram_user_id, slug)` → UserCategory | None
- `create(telegram_user_id, slug, name_ru, emoji, type)` → UserCategory; `sort_order = SELECT MAX(sort_order)+1`
- `update(category_id, **kwargs)` → UserCategory
- `delete(category_id)` → None
- `seed_system_categories(telegram_user_id)` — race-safe INSERT OR IGNORE из `categories.yaml`

**`backend/app/services/category_service.py`** — бизнес-логика:
- `list_categories(telegram_user_id)` → dict с группировкой `expense` / `income` / `both`
- `add_custom(telegram_user_id, name_ru, emoji, cat_type)` → UserCategory
  - slug = транслитерация `name_ru` через `transliterate` / ручной маппинг букв, lowercase, только `[a-z0-9_]`
  - при коллизии со существующим slug: добавить суффикс `_2`, `_3` и т.д.
  - максимальная длина slug: 50 символов
- `rename(telegram_user_id, slug, new_name)` → UserCategory
- `change_emoji(telegram_user_id, slug, new_emoji)` → UserCategory; валидация: строка должна содержать хотя бы один Unicode emoji-символ (категория `So` / `Sm` / `Cs` или проверка через `emoji` lib)
- `delete_custom(telegram_user_id, slug, reassign_to_slug)`:
  - проверяет `is_custom=True`, иначе raises `ValueError`
  - переносит транзакции: `UPDATE transactions SET category=reassign_to_slug WHERE telegram_user_id=... AND category=slug`
  - удаляет запись из `user_categories`
  - удаляет маппинги из `user_category_mappings` где `category=slug`
- `count_transactions(telegram_user_id, slug)` → int

### Фаза 2 — Telegram UI

**`backend/app/telegram/keyboards.py`** — новые функции:
- `categories_nav_keyboard(categories)` — список категорий с кнопками ✏️ / 🗑 (только для кастомных)
- `category_edit_keyboard(slug, is_custom)` — «Изменить название», «Изменить emoji», опционально «Удалить»
- `category_type_keyboard()` — выбор типа при создании: [💸 Расход] [💰 Доход] [↔️ Оба]
- `category_reassign_keyboard(categories, deleting_slug)` — список категорий **того же type** (или `both`) для переноса транзакций; `deleting_slug` исключается из списка

Добавить в `main_menu_inline_keyboard()`:
```python
[_btn("🗂 Категории", "nav:categories")]
```

**`backend/app/services/nav_service.py`** — новый метод:
- `categories_screen(telegram_user_id)` → NavScreen

**`backend/app/telegram/runtime.py`** — новые обработчики callback_data:

| callback_data | Действие |
|---|---|
| `nav:categories` | показать список |
| `categories:edit:{slug}` | показать меню редактирования |
| `categories:rename:{slug}` | установить `user_data["awaiting_category_rename"] = slug`, попросить ввести имя |
| `categories:emoji:{slug}` | установить `user_data["awaiting_category_emoji"] = slug`, попросить ввести emoji |
| `categories:delete:{slug}` | проверить транзакции → подтверждение или выбор куда перенести |
| `categories:confirm_delete:{slug}` | удалить без переноса (0 транзакций) |
| `categories:reassign:{from_slug}__{to_slug}` | перенести транзакции и удалить (`__` как разделитель двух slug) |
| `categories:add` | установить `user_data["awaiting_category_add"] = "name"`, запросить имя |
| `categories:set_type:{type}` | финальный шаг добавления, читает `user_data["pending_category_add"]` |

**`user_data` ключи:**

| Ключ | Тип | Когда используется |
|---|---|---|
| `awaiting_category_rename` | `str` (slug) | ожидание текстового ввода нового имени |
| `awaiting_category_emoji` | `str` (slug) | ожидание текстового ввода emoji |
| `awaiting_category_add` | `str` (`"name"` или `"emoji"`) | шаг флоу добавления |
| `pending_category_add` | `dict` с `name_ru`, `emoji` | накопленные данные нового шага добавления |

Все `awaiting_*` ключи очищаются после обработки или по кнопке «Отмена».

---

## UX-флоу

### Список категорий

```
🗂 Категории

Расходы
🍕 Еда                    [✏️]
🚗 Транспорт              [✏️]
🏠 Жильё                  [✏️]
...
🏋 Спорт                  [✏️] [🗑]   ← кастомная

Доходы
💼 Зарплата               [✏️]
...

[➕ Добавить]    [← Назад]
```

### Добавить кастомную категорию

1. Бот: «Введи название новой категории»
2. Пользователь: «Спорт»
3. Бот: «Теперь отправь emoji для этой категории» (пользователь отправляет, валидируется как emoji)
4. Бот: «Тип категории:» → кнопки [💸 Расход] [💰 Доход] [↔️ Оба]
5. Бот: «✅ Категория "🏋 Спорт" создана»

### Редактировать категорию

```
✏️ Еда 🍕

[Изменить название]
[Изменить emoji]
[← Назад]
```
(для кастомных добавляется кнопка [🗑 Удалить])

### Удалить кастомную с транзакциями

```
⚠️ В категории "Спорт" есть 7 транзакций.
Куда перенести их перед удалением?

[🍕 Еда]  [🏠 Жильё]  [• Прочее]   ← только категории совместимого type
[Отмена]
```

### Удалить кастомную без транзакций

```
Удалить категорию "Спорт"? Это действие нельзя отменить.

[✅ Да, удалить]  [Отмена]
```

---

## Парсер и кастомные категории

Кастомные категории **не** добавляют синонимы в парсер автоматически. Пользователь «обучает» бот через стандартный флоу исправления категории: при первом вводе «зал 1500» бот спрашивает категорию → пользователь выбирает «Спорт» → маппинг `зал → sport` сохраняется в `user_category_mappings`.

При последующих вводах «зал ...» парсер находит маппинг и сразу ставит «Спорт».

---

## Что НЕ входит в scope

- Синонимы при создании кастомной категории (усложняет флоу)
- Изменение `type` уже существующей категории
- Реордеринг категорий вручную
- Экспорт/импорт категорий
- Скрытие системных категорий

---

## Замечание по тестам

Добавление кнопки «🗂 Категории» в `main_menu_inline_keyboard()` может сломать снапшот-тест в `backend/tests/test_telegram_formatter_style.py` если там есть проверка разметки главного меню. Обновить снапшот при реализации Фазы 2.

---

## Разбивка на фазы реализации

| Фаза | Файлы | Задача |
|---|---|---|
| 1 | `models/user_category.py`, `alembic/versions/`, `repositories/user_category_repository.py`, `services/category_service.py` | Модель + репозиторий + сервис |
| 2 | `telegram/keyboards.py`, `services/nav_service.py`, `telegram/runtime.py` | Telegram UI + обработчики |
