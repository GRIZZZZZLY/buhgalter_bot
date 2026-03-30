# Backlog Roadmap — 2026-03-30

Фиксирует приоритеты и статус задач после сессии 2026-03-30.

## Уже сделано сегодня

| Задача | Коммит |
|--------|--------|
| WhisperModel кэширование + small модель + cpu_threads | `2141aae` |
| TTL-очистка аудиофайлов (APScheduler + cleanup_stale_files) | `2141aae` |
| Разбить runtime.py на handlers/ по доменам | `33f774a` |
| Фикс: голосовое в главном меню не показывало recurring/planned_confirm | `e912bde` |

---

## НЕМЕДЛЕННО (сегодня)

### 1. Заменить реальный ключ в .env.example
- **Файл:** `backend/.env.example`
- **Что:** `OPENROUTER_API_KEY` содержит реальный ключ → заменить на `sk-or-v1-YOUR_KEY_HERE`
- **Риск:** скомпрометированные credentials в публичном репо

### 2. Секция 🚫 Никогда в CLAUDE.md
- **Файл:** `CLAUDE.md`
- **Что:** добавить явный список запретов для агента:
  - не пушить в main/master без подтверждения
  - не менять `DATABASE_URL` в prod
  - не удалять миграции
  - не коммитить `.env` с реальными ключами
  - не менять цены/тарифы без явного запроса
  - не создавать публичные issues с личными данными
  - не делать необратимые действия (DROP TABLE, rm -rf) без подтверждения
- **Зачем:** закрывает агентные риски, 10 минут работы

---

## 1–2 МЕСЯЦА

### ✅ 3. HMAC-верификация Telegram initData
- Реализовано в `backend/app/api/deps.py` — `_verify_telegram_init_data()` + `get_telegram_user_id()`
- Prod требует `X-Telegram-Init-Data` с HMAC-SHA256, dev fallback через `TELEGRAM_BOT_TOKEN` empty check

### ✅ 4. Убрать захардкоженный user_id в WebApp
- Реализовано в `src/lib/api-client.ts` + `src/lib/telegram.ts`
- `getInitData()` читает `initDataRaw` через `@tma.js/sdk-react`, dev fallback через `VITE_DEV_USER_ID`

### 5. Определить NSM (North Star Metric)
- **Что:** одно предложение — "Наш NSM = X, потому что когда пользователь достигает Y, мы растём"
- **Зачем:** даёт фильтр для всех продуктовых решений, снижает scope creep
- **Формат:** секция в `CLAUDE.md` или отдельный `docs/product/nsm.md`

### 6. Персистить user_data (онбординг) в БД
- **Что:** `context.user_data` теряется при перезапуске бота — состояние онбординга, pending actions
- **Где:** новая таблица `user_sessions` или поле `meta JSON` в `users`
- **Риск:** пользователь теряет незавершённое действие при деплое

---

## КВАРТАЛ+

### 7. Метрики использования
- **Что:** счётчики событий: транзакции/день, голос vs текст, советник открыт/закрыт, undo использован
- **Где:** отдельная таблица `events` или интеграция с Plausible/PostHog
- **Зачем:** без метрик невозможно понять что работает

### 8. Eval-набор для LLM/парсера
- **Что:** 3-5 golden test cases на каждый критический пайплайн (парсер, LLM, STT)
- **Формат:** `backend/tests/evals/` — ввод/ожидаемый-вывод
- **Зачем:** защита от деградации при смене модели или промпта

### 9. Savings Goals
- **Дизайн готов:** `docs/superpowers/specs/2026-03-25-savings-goals-design.md`
- **План готов:** `docs/superpowers/plans/2026-03-25-savings-goals.md`
- **Статус:** ожидает реализации

### 10. PostgreSQL в dev/staging
- **Что:** переключить dev с SQLite на PostgreSQL через Docker Compose
- **Зачем:** устранить расхождение SQLite (dev) vs PostgreSQL (prod) — разные типы, разное поведение миграций
- **Формат:** `docker-compose.dev.yml` + обновление `setup:dev` скрипта

---

## Порядок реализации

```
Немедленно:   [1] .env.example → [2] CLAUDE.md 🚫
1-2 месяца:   [3] HMAC → [4] WebApp user_id → [5] NSM → [6] user_data persist
Квартал+:     [7] Метрики → [8] Eval → [9] Savings Goals → [10] PostgreSQL
```
