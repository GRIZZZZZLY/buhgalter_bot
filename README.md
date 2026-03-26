# Бухгалтер — персональный финансовый Telegram-бот

Telegram-бот для личных финансов с голосовым вводом, LLM-категоризацией и WebApp-дашбордом.

Монорепозиторий: `backend/` (FastAPI + python-telegram-bot) и `src/` (React 19 + Vite, Telegram WebApp).

---

## Возможности

### Ввод операций
- **Текстом** — свободный ввод на русском: `купил продукты на 750`, `зарплата 85000`
- **Голосом** — распознавание через Whisper STT, подтверждение перед сохранением
- **Редактирование** — изменение суммы, категории или удаление после сохранения
- **Обучаемая категоризация** — бот запоминает маппинги merchant → category для каждого пользователя
- **Запланированные расходы** — свободный текст/голос → LLM-извлечение → подтверждение
- **Регулярные платежи** — свободный текст/голос → LLM-извлечение → подтверждение

### Аналитика
- Сводка по периодам: сегодня / неделя / месяц / всё время
- Бюджеты по категориям с прогресс-барами
- Алерты при превышении бюджета — мгновенно после записи
- Инсайты (5 детекторов): резкий рост расходов, серия дней, превышение бюджета, аномалии, достижения
- LLM-генерация мотивирующих сообщений (OpenRouter API)

### Проактивные уведомления (APScheduler)
- **Утренний брифинг** — дневной бюджет, прогресс месяца, streak, инсайты
- **Вечерний чек-ин** — напоминание, если за день ничего не записано
- **Итоги первой недели** — автоматический анализ через 7 дней
- **Еженедельный дайджест** — каждое воскресенье

### Навигация в боте
Полностью inline-кнопочный UX без необходимости помнить команды:
```
[📊 Сводка]
[📋 Запланированные | 🔄 Регулярные]
[🗂 Категории | 💰 Бюджеты]
[⚙️ Настройки | ℹ️ Помощь]
```

### Управление категориями
- Двухуровневая навигация: Расходы / Доходы → список с пагинацией (8 на странице)
- Переименование, смена эмодзи, удаление кастомных категорий
- Системные категории — нельзя удалить

### Настройки
- Бюджет, время напоминаний, часовой пояс
- Сброс данных: всё / только расходы / только доходы

### WebApp-дашборд (React + Vite)
- Баланс, список транзакций, donut-chart по категориям
- Редактирование и удаление транзакций
- Управление бюджетами
- Responsive дизайн (мобильный + Telegram WebApp)

---

## Структура репозитория

```
buhgalter_bot/
├── src/                        # Фронтенд Telegram WebApp (React 19 + Vite)
│   ├── pages/                  # Маршруты react-router v7 (dashboard, budgets, add/edit)
│   ├── components/             # UI-компоненты (donut-chart, hero-card, transaction-item)
│   ├── hooks/                  # React Query хуки (use-transactions, use-budgets, use-summary)
│   └── lib/                    # API-клиент, Zod-схемы, утилиты
├── backend/
│   ├── app/
│   │   ├── api/                # FastAPI роуты (transactions, summary, budget, chart, user)
│   │   ├── services/           # 20+ сервисов: парсер, STT, insights, планировщик и др.
│   │   ├── repositories/       # 9 репозиториев — слой доступа к данным
│   │   ├── models/             # SQLAlchemy-модели (8 моделей)
│   │   ├── schemas/            # Pydantic-схемы
│   │   ├── telegram/           # Telegram-бот (handlers, formatter, keyboards, runtime)
│   │   ├── config/             # YAML-конфигурация категорий, паттернов, глаголов
│   │   └── db/                 # Сессия БД, инициализация
│   ├── alembic/                # Миграции БД (9 миграций)
│   ├── tests/                  # 36 тестовых файлов, 415+ тестов
│   └── run_bot.py              # Точка входа Telegram-бота
├── deploy/                     # Конфиги для production
│   ├── nginx.conf              # Nginx: HTTPS + proxy → FastAPI
│   ├── buhgalter-api.service   # systemd: FastAPI
│   └── buhgalter-bot.service   # systemd: Telegram-бот
├── scripts/                    # setup:dev, deploy.sh
└── vite.config.ts              # Vite + dev-proxy /api → localhost:8000
```

---

## Таблицы БД

| Таблица | Назначение |
|---|---|
| `users` | Профиль, бюджет, часовой пояс, streak, время напоминаний |
| `transactions` | Все финансовые записи |
| `voice_logs` | Лог голосовых сообщений |
| `user_category_mappings` | Обучаемые маппинги merchant → category per-user |
| `category_budgets` | Бюджеты по категориям |
| `recurring_transactions` | Повторяющиеся транзакции |
| `planned_expenses` | Запланированные расходы |
| `user_categories` | Пользовательские категории (системные + кастомные) |

---

## Требования

| Компонент | Версия |
|---|---|
| Python | 3.12+ |
| Node.js | 18+ |
| ffmpeg | любая (для голосового ввода) |

Если тестируешь только текстовый ввод и WebApp — ffmpeg не обязателен.

---

## Переменные окружения

Скопируй `backend/.env.example` в `backend/.env` и заполни:

```env
# Обязательно
TELEGRAM_BOT_TOKEN=...
DATABASE_URL=sqlite:///./finance_bot.db

# LLM (OpenRouter) — для инсайтов и извлечения плановых/регулярных
OPENROUTER_API_KEY=...

# Голосовой ввод
FFMPEG_BIN=ffmpeg
STT_PROVIDER=faster-whisper
WHISPER_MODEL=small
WHISPER_DEVICE=cpu

# Production
TELEGRAM_MODE=polling        # или webhook
CORS_ORIGINS=https://your-domain.com
```

---

## Локальный запуск

### Подготовка одной командой

```bash
npm run setup:dev
```

Устанавливает зависимости, создаёт `.venv`, копирует `.env`, прогоняет миграции, проверяет ffmpeg.

### Запуск

```bash
npm run dev:all          # фронтенд (4173) + backend API (8000)
npm run dev:all:bot      # + Telegram-бот в polling-режиме
```

### Ручной запуск

```bash
# Фронтенд
npm install && npm run dev

# Backend
cd backend
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .[dev]
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Бот (отдельный терминал)
cd backend && python run_bot.py
```

### Проверка

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok"}
```

---

## Тесты

```bash
cd backend && pytest
# 415 тестов, 36 файлов
```

Покрытие: парсер, STT, голосовой flow, API, транзакции, аналитика, бюджеты, инсайты, категории, плановые/регулярные, навигация, форматтер, keyboards, scheduler.

---

## Деплой на VPS

Deploy-файлы готовы в `deploy/` и `scripts/deploy.sh`.

### Первоначальная настройка

```bash
# 1. Создать пользователя и директорию
adduser buhgalter
mkdir -p /opt/buhgalter-bot && chown buhgalter:buhgalter /opt/buhgalter-bot

# 2. Клонировать репо
git clone <repo_url> /opt/buhgalter-bot

# 3. Настроить окружение
cp /opt/buhgalter-bot/backend/.env.example /opt/buhgalter-bot/backend/.env
# Заполнить TELEGRAM_BOT_TOKEN, DATABASE_URL, OPENROUTER_API_KEY, CORS_ORIGINS

# 4. Python-зависимости и миграции
python3 -m venv /opt/buhgalter-bot/.venv
/opt/buhgalter-bot/.venv/bin/pip install -e /opt/buhgalter-bot/backend/.[dev]
cd /opt/buhgalter-bot/backend && ../.venv/bin/alembic upgrade head

# 5. Сборка фронтенда
cd /opt/buhgalter-bot && npm ci && npm run build

# 6. Systemd-сервисы
cp deploy/buhgalter-api.service deploy/buhgalter-bot.service /etc/systemd/system/
systemctl enable --now buhgalter-api buhgalter-bot

# 7. Nginx + SSL (заменить YOUR_DOMAIN в nginx.conf)
sed -i 's/YOUR_DOMAIN/your-domain.com/g' deploy/nginx.conf
cp deploy/nginx.conf /etc/nginx/sites-available/buhgalter
ln -s /etc/nginx/sites-available/buhgalter /etc/nginx/sites-enabled/
certbot --nginx -d your-domain.com
systemctl reload nginx
```

### Обновление

```bash
./scripts/deploy.sh
```

Скрипт: `git pull` → миграции → сборка фронтенда → перезапуск сервисов → smoke test.

---

## Известные ограничения

- Заголовок `X-Telegram-User-Id` не верифицируется через HMAC-SHA256 `initData` — для публичного prod нужна верификация
- WhisperModel загружается при первом голосовом сообщении после старта сервиса (5-30 сек первый раз)
- Временные аудиофайлы в `backend/runtime/audio/` очищаются по TTL, но не мгновенно

---

## Полезные файлы

| Файл | Назначение |
|---|---|
| `backend/.env.example` | Пример всех переменных окружения |
| `backend/app/config/` | YAML-конфигурация категорий и паттернов |
| `backend/app/telegram/runtime.py` | Главный файл обработчиков Telegram |
| `deploy/nginx.conf` | Конфиг nginx для production |
| `scripts/deploy.sh` | Скрипт обновления на сервере |
| `docs/superpowers/specs/` | Технические дизайн-документы |
