# Design: Персистентность user_data через SQLAlchemyPersistence

**Дата:** 2026-03-30
**Статус:** Approved

## Проблема

`context.user_data` в python-telegram-bot живёт в памяти процесса. При перезапуске бота (деплой, crash) теряется:
- Незавершённое голосовое подтверждение (pending voice confirm)
- Состояние советника (advisor_history, advisor_actions_taken)
- Pending flows (planned, recurring freeform confirmation)
- Режим ввода (mode)

211 обращений к `context.user_data` в handlers — менять их все вручную нецелесообразно.

## Решение

Использовать встроенный `SQLAlchemyPersistence` из `python-telegram-bot[sql]`.

- Работает с тем же `DATABASE_URL` (SQLite dev / PostgreSQL prod)
- Ноль изменений в handlers — PTB сериализует/десериализует автоматически
- Данные в одной БД с транзакциями — единый бэкап

## Архитектура

### Зависимости

```toml
# pyproject.toml
"python-telegram-bot[sql]>=21.5"
```

PTB создаёт таблицу `telegram_persistence` через свой engine (отдельный от нашего `SessionLocal`).

### Изменения в runtime.py

```python
from telegram.ext import SQLAlchemyPersistence

def build_application() -> Application:
    settings = get_settings()
    persistence = SQLAlchemyPersistence(url=settings.database_url)
    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .persistence(persistence)
        .post_init(on_startup)
        .post_shutdown(on_shutdown)
        .build()
    )
    ...
```

### Alembic миграция

PTB создаёт таблицу сам через `metadata.create_all()`. Добавляем пустую Alembic-миграцию для документирования:

```python
# alembic revision: "document telegram_persistence table (managed by PTB)"
# up: pass  (таблица уже создана PTB)
# down: op.drop_table("telegram_persistence")
```

### Settings

Никаких новых env-переменных не нужно — `DATABASE_URL` уже есть.

## Поведение после перезапуска

| Состояние | До | После |
|-----------|-----|-------|
| mode="planned_input" | Потеряно | Восстановлено |
| advisor_history | Потеряно | Восстановлено |
| pending_recurring_freeform | Потеряно | Восстановлено |
| awaiting_* (эфемерные) | Потеряно | Восстановлено* |

*Эфемерные `awaiting_*` ключи тоже персистируются — это безопасно, они перезаписываются при следующем вводе пользователя.

## TTL / устаревшие данные

PTB не имеет встроенного TTL. Существующие handlers уже проверяют свежесть через `_advisor_state_is_fresh()` и `pending_action_expires_at`. Это достаточно — явный TTL на уровне БД не нужен.

## Тестирование

- Существующие 505 тестов не затронуты (тесты не используют persistence)
- Ручная проверка: запустить бот → начать голосовое подтверждение → перезапустить бот → убедиться что pending state восстановлен

## Риски

| Риск | Вероятность | Митигация |
|------|-------------|-----------|
| PTB меняет схему таблицы при обновлении версии | Низкая | Alembic downgrade в миграции |
| Большой объём данных при тысячах пользователей | Средняя | Приемлемо на текущем масштабе, мониторить размер таблицы |
| Конфликт connection pool с нашим SessionLocal | Низкая | PTB использует отдельный engine |

## Scope реализации

1. `backend/pyproject.toml` — добавить `[sql]` extra
2. `backend/app/telegram/runtime.py` — добавить `SQLAlchemyPersistence` в `build_application()`
3. `backend/alembic/versions/` — новая миграция-документация
4. Ручное тестирование восстановления состояния
