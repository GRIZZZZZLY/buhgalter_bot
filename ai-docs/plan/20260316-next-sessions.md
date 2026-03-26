# План разработки: ближайшие 2-3 сессии

**Дата:** 2026-03-16
**Горизонт:** 2-3 рабочих сессии (~6-10 часов суммарно)
**Цель:** Устранить критические блокеры безопасности и стабилизировать стек перед закрытым тестированием

---

## Текущее состояние

Проект функционально богатый: голосовой ввод, бюджеты, напоминания, streak, WebApp-дашборд, 23 теста.
Но есть 4 критических блокера, которые делают публичный деплой небезопасным.

### Критические блокеры (из code review)

| # | Проблема | Файл | Риск |
|---|---|---|---|
| C1 | Нет аутентификации API — любой может читать/менять данные любого пользователя | `api/deps.py`, `src/lib/api.ts` | Утечка данных |
| C2 | Захардкоженный user ID `555502880` в фронтенде | `src/lib/api.ts:27` | Все запросы от одного пользователя |
| C3 | Тихий fallback на mock-данные при ошибке API | `src/lib/api.ts:93-100` | Пользователь видит чужие фейковые данные |
| C4 | Race condition: `_pending_category_resolutions` — class variable | `telegram/handlers.py:25` | Пользователи перезаписывают состояние друг друга |

### Важные проблемы (MAJOR)

| # | Проблема | Файл |
|---|---|---|
| M1 | WhisperModel загружается заново на каждое сообщение (5-30 сек) | `services/stt_service.py` |
| M2 | subprocess без timeout — повреждённый файл блокирует event loop | `services/stt_service.py` |
| M3 | Временные аудиофайлы не удаляются — диск заполнится | `telegram/runtime.py`, `services/audio_file_service.py` |
| M4 | Нет CORS middleware — production-запросы из браузера заблокированы | `app/main.py` |
| M5 | `init_db()` конфликтует с Alembic — `create_all()` при каждом старте | `db/init_db.py` |
| M6 | Vite proxy только для dev — production API-запросы дадут 404 | `vite.config.ts` |

---

## Сессия 1 — Безопасность и аутентификация (~3-4 часа)

**Цель:** Устранить C1, C2, C3 — закрыть API от несанкционированного доступа.

**Что будет работать в конце:** WebApp передаёт `initData` на бэкенд, бэкенд верифицирует HMAC-SHA256 подпись Telegram. Захардкоженный ID убран. При ошибке API — явное сообщение об ошибке, не mock-данные.

### Шаги

**1. Backend: верификация initData (1.5 ч)**
- В `backend/app/api/deps.py` добавить функцию `verify_telegram_init_data(init_data: str, bot_token: str) -> int`
- Алгоритм: HMAC-SHA256 по документации Telegram (data-check-string + secret key)
- Заменить `get_telegram_user_id` на зависимость, которая принимает заголовок `X-Telegram-Init-Data` и возвращает верифицированный `user_id`
- Добавить `TELEGRAM_BOT_TOKEN` в зависимость через `get_settings()`

```python
# Алгоритм верификации (Telegram docs)
import hashlib, hmac
from urllib.parse import parse_qsl

def verify_init_data(init_data: str, bot_token: str) -> dict:
    parsed = dict(parse_qsl(init_data, strict_parsing=True))
    received_hash = parsed.pop("hash", None)
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        raise HTTPException(401, "Invalid initData signature")
    return parsed
```

**2. Frontend: передача initData (45 мин)**
- В `src/lib/telegram.ts` добавить экспорт `getInitData(): string` — возвращает `WebApp.initData`
- В `src/lib/api.ts` в `getHeaders()` заменить захардкоженный ID на `X-Telegram-Init-Data: getInitData()`
- Убрать импорт `'555502880'`

**3. Frontend: убрать тихий fallback на mock (30 мин)**
- В `src/lib/api.ts` в блоке `catch` вместо возврата mock-данных — пробрасывать ошибку
- В `src/useDashboard.ts` добавить состояние `error: string | null`
- В `src/App.tsx` показывать компонент ошибки вместо дашборда при `error !== null`
- Mock-данные оставить только для явного dev-режима (`import.meta.env.DEV && !WebApp.initData`)

**4. Тест верификации (30 мин)**
- Добавить unit-тест в `backend/tests/test_api.py`: запрос без заголовка → 401, с невалидным hash → 401, с валидным → 200

**Checkpoint:** `curl -H "X-Telegram-Init-Data: invalid" http://localhost:8000/api/summary` → 401. WebApp в Telegram открывается и показывает реальные данные.

**Не делаем в этой сессии:** CORS, Docker, production-деплой.

---

## Сессия 2 — Стабильность backend (~2-3 часа)

**Цель:** Устранить C4, M1, M2, M3, M4, M5 — сделать backend надёжным для многопользовательской работы.

**Что будет работать в конце:** Голосовые сообщения обрабатываются быстро (модель кэширована), временные файлы чистятся, состояние пользователей изолировано, CORS настроен.

### Шаги

**1. Перенести user state из class variable в context.user_data (45 мин)**
- В `backend/app/telegram/handlers.py` убрать `_pending_category_resolutions: dict = {}` как class variable
- Использовать `context.user_data["pending_category"]` из python-telegram-bot
- Добавить TTL-очистку: если запись старше 10 минут — удалять при следующем обращении

**2. Кэшировать WhisperModel (30 мин)**
- В `backend/app/services/stt_service.py` вынести создание `WhisperModel` в `__init__` или синглтон
- Модель создаётся один раз при старте сервиса, переиспользуется для всех запросов

**3. Добавить timeout к subprocess (20 мин)**
- В `stt_service.py` добавить `timeout=60` к вызовам `subprocess.run` для ffmpeg и whisper-cpp
- При `subprocess.TimeoutExpired` — логировать и возвращать понятную ошибку пользователю

**4. Очистка временных аудиофайлов (20 мин)**
- В `backend/app/telegram/runtime.py` и `audio_file_service.py` добавить `finally`-блок с удалением `.ogg` и `.wav`
- Альтернатива: использовать `tempfile.NamedTemporaryFile(delete=True)`

**5. CORS middleware (15 мин)**
- В `backend/app/main.py` добавить `CORSMiddleware` из `fastapi.middleware.cors`
- Для dev: `allow_origins=["*"]`; для prod: список конкретных доменов через `.env`

**6. Убрать `init_db()` из startup (15 мин)**
- В `backend/app/main.py` убрать вызов `init_db()` из `startup()`
- Миграции управляются только через Alembic — `alembic upgrade head`
- Оставить `init_db()` только для тестов через `conftest.py`

**Checkpoint:** Отправить 3 голосовых сообщения подряд — каждое обрабатывается быстро (< 5 сек после первого). Файлы в `runtime/audio/` не накапливаются. Два разных пользователя одновременно вводят категорию — не мешают друг другу.

**Не делаем в этой сессии:** Docker, production nginx, новые фичи.

---

## Сессия 3 — Production-готовность и деплой (~2-3 часа)

**Цель:** Устранить M6, подготовить production-конфигурацию, задокументировать деплой.

**Что будет работать в конце:** Собранный фронтенд работает с backend через nginx. Есть Dockerfile или systemd-конфиг. Проект готов к закрытому тестированию на VPS.

### Шаги

**1. Production API URL для фронтенда (30 мин)**
- В `vite.config.ts` убедиться, что `VITE_API_BASE` используется в production-билде
- В `.env.example` добавить `VITE_API_BASE=https://your-domain.com`
- В `src/lib/api.ts` убедиться, что `import.meta.env.VITE_API_BASE` корректно подставляется

**2. Nginx-конфиг (30 мин)**
- Создать `deploy/nginx.conf` с:
  - Раздача `dist/` как статики
  - Проксирование `/api/` → `http://127.0.0.1:8000`
  - HTTPS (Let's Encrypt)

**3. Systemd или Docker (1 ч)**

Вариант A — systemd (проще):
- `deploy/buhgalter-api.service` — uvicorn
- `deploy/buhgalter-bot.service` — run_bot.py

Вариант B — Docker (рекомендуется для воспроизводимости):
- `backend/Dockerfile` — Python-образ с зависимостями
- `docker-compose.yml` — api + bot + (опционально) nginx

**4. Деплой-скрипт (30 мин)**
- `scripts/deploy.sh`: git pull → alembic upgrade head → systemctl restart / docker compose up -d → npm run build → nginx reload

**5. Smoke-тест на VPS (30 мин)**
- `curl https://your-domain.com/health` → `{"status":"ok"}`
- Открыть WebApp в Telegram → данные загружаются, не mock
- Отправить текстовый расход → записывается
- Отправить голосовое → обрабатывается

**Checkpoint:** Бот работает на VPS, WebApp открывается через Telegram, данные реальные, аутентификация работает.

**Не делаем в этой сессии:** Новые фичи, PostgreSQL-миграция, мониторинг.

---

## Что НЕ входит в эти 3 сессии (Parking Lot)

Всё это важно, но после стабилизации:

- Повторяющиеся транзакции (модель есть, UI нет)
- Ввод даты в прошлом
- Редактирование транзакций из Telegram (inline-кнопки)
- Экспорт в CSV (`/export`)
- **Conversational Financial Intelligence** — команда `/ask` (или вопрос в свободной форме): пользователь спрашивает «сколько я трачу на кофе?» или «могу ли я позволить себе абонемент в зал за 5000₽?», бот отвечает на основе реальных данных пользователя. Меняет парадигму с «смотреть на цифры» на «разговаривать с финансами». Вся инфраструктура уже есть: LLM (Groq), репозитории с агрегацией, Telegram-хендлер. Нужно: 1 новый сервис `FinancialQAService` (~150 строк) + правка `runtime.py`. Зафиксировано 2026-03-24.
- Детекция аномалий и «кофе-индекс»
- Финансовый балл (0-100)
- Цели накоплений
- Переход с SQLite на PostgreSQL
- Rate limiting (защита от спама голосовыми)
- Accessibility (aria-атрибуты в WebApp)
- ESLint/Prettier для фронтенда
- Мониторинг и алерты (Sentry, Prometheus)

---

## Метрика успеха

Проект считается готовым к закрытому тестированию, если:
- [ ] `curl -H "X-Telegram-Init-Data: invalid" /api/summary` → 401
- [ ] WebApp в Telegram показывает реальные данные текущего пользователя
- [ ] Голосовое сообщение обрабатывается < 10 сек (после прогрева модели)
- [ ] `runtime/audio/` не растёт после обработки сообщений
- [ ] Два пользователя одновременно вводят данные — не мешают друг другу
- [ ] `https://your-domain.com/health` → `{"status":"ok"}`

---

## С чего начать прямо сейчас (первые 15 минут)

1. Открыть `backend/app/api/deps.py` — это точка входа для аутентификации
2. Добавить функцию `verify_init_data()` по алгоритму из Сессии 1
3. Написать тест: `test_api.py` — запрос без заголовка → 401

---

*Связанные документы:*
- `ai-docs/plan/20260315-143000-full-code-review.md` — полный список проблем с файлами и строками
- `ai-docs/plan/20260315-150000-product-strategy-features.md` — продуктовая стратегия (фичи после стабилизации)
