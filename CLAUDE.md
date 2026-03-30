# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Проект

Telegram-first персональный финансовый бот с голосовым вводом и WebApp-дашбордом. Монорепозиторий: `backend/` (FastAPI + python-telegram-bot) и `src/` (React 19 + Vite, Telegram WebApp).

## Команды разработки

### Первоначальная настройка
```bash
npm run setup:dev   # установка зависимостей, .venv, .env, миграции, проверка ffmpeg
```

### Запуск
```bash
npm run dev:all          # фронтенд (4173) + backend API (8000)
npm run dev:all:bot      # + Telegram-бот (polling)
npm run dev              # только фронтенд
```

### Backend вручную (из backend/)
```bash
pip install -e .[dev]
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
python run_bot.py        # бот в отдельном терминале
```

### Тесты
```bash
cd backend && pytest                  # все тесты
cd backend && pytest tests/test_parser_service.py   # один файл
```

### Фронтенд
```bash
npm run lint       # ESLint (0 warnings)
npm run typecheck  # tsc --noEmit
npm run format     # prettier
npm test           # vitest run
```

### Миграции
```bash
cd backend && alembic upgrade head
cd backend && alembic revision --autogenerate -m "описание"
```

## Архитектура

### Backend (backend/app/)

```
api/
  deps.py          — зависимости FastAPI (get_db, get_current_user по X-Telegram-User-Id)
  routes/          — transactions.py, summary.py, budget.py
services/
  parser_service.py      — парсинг текста в транзакцию (YAML-паттерны из app/config/)
  stt_service.py         — Speech-to-Text через faster-whisper
  voice_flow_service.py  — полный flow голосового ввода (STT → парсер → подтверждение)
  transaction_service.py — бизнес-логика транзакций
  scheduler_service.py   — APScheduler: утренний брифинг, вечерний чек-ин, дайджест
  recurring_service.py   — повторяющиеся транзакции
  date_extractor.py      — извлечение дат из текста
telegram/
  handlers.py    — обработчики команд и сообщений
  keyboards.py   — inline/reply клавиатуры
  formatter.py   — форматирование сообщений
  runtime.py     — инициализация Application
  bot_service.py — бизнес-операции уровня бота
repositories/    — слой доступа к данным (SQLAlchemy)
models/          — ORM: User, Transaction, VoiceLog, UserCategoryMapping, RecurringTransaction
schemas/         — Pydantic request/response схемы
config/          — YAML: категории, паттерны парсера, глаголы
db/              — сессия БД, init_db
```

### Frontend (src/)

- **pages/** — страницы роутера (react-router v7)
- **hooks/** — React Query хуки: use-transactions, use-budgets, use-summary
- **components/** — UI-компоненты: donut-chart, hero-card, transaction-item, skeleton-card, layout
- **components/ui/** — Radix UI примитивы (shadcn/ui-style)
- **lib/api-client.ts** — axios-клиент с заголовком `X-Telegram-User-Id`
- **lib/categories.ts** — маппинг категорий на иконки/цвета
- **lib/schemas.ts** — Zod схемы
- Стейт-менеджмент: Zustand + TanStack Query

### Аутентификация

`X-Telegram-User-Id` в заголовке — **не верифицируется** через HMAC. Для prod нужна верификация `initData`. В фронтенде (`src/lib/api-client.ts`) используется захардкоженный ID `555502880` — известное ограничение.

### База данных

SQLite (dev) / PostgreSQL (prod). Управляется через Alembic. Таблицы: `users`, `transactions`, `voice_logs`, `user_category_mappings`, `category_budgets`, `recurring_transactions`.

### Переменные окружения (backend/.env)

```env
TELEGRAM_BOT_TOKEN=...
DATABASE_URL=sqlite:///./finance_bot.db
FFMPEG_BIN=ffmpeg
STT_PROVIDER=faster-whisper   # для голосового ввода
WHISPER_MODEL=small
WHISPER_DEVICE=cpu
TELEGRAM_MODE=polling          # или webhook
```

## Ключевые особенности

- **Парсер транзакций** (`parser_service.py`) работает на YAML-паттернах из `backend/app/config/` — для расширения логики категорий и глаголов менять YAML, не код.
- **WhisperModel** кэшируется как singleton в `stt_service.py` (`_whisper_model_cache`).
- **Vite proxy** в dev-режиме проксирует `/api` → `http://localhost:8000`.
- Аудиофайлы пишутся в `backend/runtime/audio/` и удаляются APScheduler каждый час.
- **Telegram handlers** разбиты по доменам в `telegram/handlers/` — `runtime.py` только точка сборки.

## 🚫 Никогда

Агент никогда не делает следующее без явного подтверждения пользователя:

1. **git push --force** или любой force-push в main/master
2. **Коммитить `.env`** или любые файлы с реальными API-ключами, токенами, паролями
3. **DROP TABLE**, `alembic downgrade` или любые деструктивные миграции
4. **rm -rf** или массовое удаление файлов/директорий
5. **Менять `DATABASE_URL`** на prod-базу в любом скрипте или конфиге
6. **Пушить изменения** в публичное репо если в diff есть credentials или PII
7. **Создавать issues/PR** с личными данными пользователей
8. **Менять цены, лимиты, тарифы** без явного запроса
9. **Останавливать/перезапускать prod-процессы** без подтверждения
10. **Амендить уже запушенные коммиты** (`git commit --amend` после push)

1. Прежде чем писать код, опиши свой подход и дождись подтверждения. Всегда задавай уточняющие вопросы, если требования неясны.

2. Если задача затрагивает больше 3 файлов, остановись и разбей её на более мелкие подзадачи.

3. После написания кода, перечисли, что может сломаться, и предложи тесты для проверки.

4. При баге сначала напиши тест, который его воспроизводит, затем исправляй код, пока тест не проходит.

5. Каждый раз, когда я исправляю тебя, добавляй новое правило в CLAUDE .md файл, чтобы это больше не повторялось.