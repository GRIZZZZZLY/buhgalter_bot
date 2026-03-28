# buhgalter_bot_fresh — полное описание проекта

## Что это за проект

`buhgalter_bot_fresh` — это Telegram-first финансовый ассистент.

Его главная идея:
- основной интерфейс жизни проекта — **Telegram-бот**,
- пользователь может работать **текстом и голосом**,
- данные хранятся в БД,
- поверх данных работает слой аналитики,
- поверх аналитики работает слой советника,
- рядом уже есть **экспорт** и **импорт с dry-run preview**.

Проект не сводится к одному `/summary` или одному чату с LLM.
Это уже составная система из:
- Telegram runtime,
- backend/API,
- БД + репозиториев,
- аналитики,
- advisor-слоя,
- import/export,
- recurring/planned/budget/category flows,
- голосового контура.

Коротко:
**это не просто “бот учёта”, а финансовый Telegram-ассистент с живым operational workflow.**

---

## Для чего он предназначен

Основные задачи проекта:

1. **Быстрый учёт финансов**
   - текстом: `такси 300`, `зарплата 50000`, `еда 540`
   - голосом: короткие голосовые, которые распознаются и превращаются в транзакции

2. **Понимание текущего состояния**
   - сколько заработал,
   - сколько потратил,
   - баланс,
   - по каким категориям уходит больше всего,
   - где бюджет уже перегрет,
   - что скоро нужно оплатить.

3. **Работа с планированием**
   - planned expenses,
   - recurring transactions,
   - бюджеты по категориям,
   - общая месячная рамка.

4. **Режим “Советник”**
   - ответ на финансовые вопросы по реальным данным пользователя,
   - не просто LLM-чтение промпта, а связка:
     `snapshot -> analytics -> recommendations -> answer`.

5. **Экспорт и импорт данных**
   - export в CSV/XLSX,
   - import CSV/XLSX через preview + explicit confirm/cancel,
   - PDF импорт пока честно не реализован как настоящий парсер.

---

## Текущий общий контур проекта

### Поверхности проекта

#### 1. Telegram bot
Это главный интерфейс.
Именно здесь находятся:
- команды,
- inline buttons,
- режимы ввода,
- advisor mode,
- import/export UX,
- voice flow,
- recurring/planned/budget/category screens.

#### 2. Backend
Backend содержит:
- FastAPI API,
- бизнес-логику,
- Telegram runtime,
- сервисы аналитики,
- импорт/экспорт,
- STT/LLM сервисы,
- репозитории и модели.

#### 3. WebApp / frontend
WebApp есть, но сейчас это **не единственный и не главный интерфейс**.
По текущему канону проект остаётся **Telegram-first**:
- ввод через Telegram,
- WebApp — это dashboard/management surface.

---

## Структура проекта

### Корень
- `README.md`
- `backend/`
- `src/` — фронтенд
- `deploy/` — deploy/systemd/nginx контур
- `scripts/` — служебные скрипты
- `docs/` — проектные заметки

### Важные backend-зоны

#### `backend/app/api/`
HTTP API роуты:
- `summary`
- `transactions`
- `budget`
- `chart`
- `user`

#### `backend/app/models/`
SQLAlchemy модели:
- `user`
- `transaction`
- `planned_expense`
- `recurring_transaction`
- `category_budget`
- `user_category`
- `user_category_mapping`
- `voice_log`

#### `backend/app/repositories/`
Низкоуровневый доступ к БД.

#### `backend/app/services/`
Главная бизнес-логика. Важные сервисы:
- `financial_snapshot_service.py`
- `financial_analytics_service.py`
- `financial_qa_service.py`
- `recommendation_service.py`
- `export_service.py`
- `import_service.py`
- `transaction_service.py`
- `planned_expense_service.py`
- `recurring_service.py`
- `analytics_service.py`
- `category_service.py`
- `parser_service.py`
- `llm_service.py`
- `stt_service.py`
- `audio_file_service.py`
- `scheduler_service.py`
- `reminder_service.py`

#### `backend/app/telegram/`
Telegram-specific слой:
- `runtime.py` — основной runtime и wiring,
- `handlers.py` — текстовые/потоковые handler’ы,
- `keyboards.py` — inline keyboards,
- `formatter.py` — форматирование экранов,
- `bot_service.py` — orchestration между runtime и сервисами.

#### `backend/tests/`
Тесты на:
- advisor,
- analytics,
- rendering,
- import/export,
- keyboards,
- fallback behavior.

---

## Главный workflow пользователя

Ниже не “технический список файлов”, а **как проект реально живёт для пользователя**.

### 1. Пользователь заходит в бота
Основные входы:
- `/start`
- `/menu`
- обычное текстовое сообщение
- голосовое сообщение
- advisor entry через `/ask`
- advisor entry через inline кнопку `🧠 Советник`

### 2. Пользователь фиксирует деньги
Типовые сценарии:
- текстом вводит расход/доход,
- голосом проговаривает трату,
- исправляет/подтверждает,
- получает сохранение и при необходимости undo.

### 3. Пользователь открывает экраны
Навигация идёт через callback-based inline UI:
- сводка,
- бюджеты,
- категории,
- planned,
- recurring,
- settings,
- advisor,
- export/import.

### 4. Пользователь спрашивает “Советник”
Советник отвечает по текущим данным БД, а не “из головы”.

### 5. Пользователь импортирует/экспортирует данные
- экспортирует CSV/XLSX,
- может прислать CSV/XLSX обратно,
- сначала получает **dry-run preview**,
- только потом подтверждает импорт.

---

## Как именно работает “Советник”

Это один из самых важных кусков проекта.

### Что это такое по сути
“Советник” — это **не автономный агент**, а **умный финансовый advisor layer**.

Текущая логика такая:

```text
данные пользователя из БД
-> FinancialSnapshotService
-> FinancialAnalyticsService
-> RecommendationService
-> FinancialQAService
-> Telegram rendering
```

### Его слои

#### 1. Snapshot layer
`FinancialSnapshotService`
собирает структурированный снимок:
- summary,
- top categories,
- recent transactions,
- monthly stats,
- budgets,
- planned expenses,
- recurring payments.

#### 2. Analytics layer
`FinancialAnalyticsService`
считает кодом:
- прогноз к концу месяца,
- состояние бюджетов,
- главный риск.

#### 3. Recommendation layer
`RecommendationService`
считает **scored recommendations**:
- что сейчас главный next step,
- какие вторичные follow-up actions полезны,
- какая data quality у текущей картины.

#### 4. QA layer
`FinancialQAService`
берёт:
- snapshot,
- analytics,
- recommendations,
- историю диалога,
- вопрос пользователя,
и формирует ответ в structured payload.

### Что возвращает advisor payload
Сейчас payload уже не просто строка.
Он несёт:
- `answer`
- `basis`
- `warnings`
- `confidence`
- `recommendations`
- payload/state versioning
- attached computed state (snapshot / analytics / recommendation snapshot)

### Что советник уже умеет
- one-shot answer,
- dialog mode,
- quick scenarios,
- short memory/history,
- text + voice,
- structured response,
- deterministic fallback,
- next-step action buttons,
- follow-up actions.

### Что он пока НЕ умеет
- полноценный agent loop,
- task memory с долгим follow-up,
- safe action execution layer,
- persistent financial intentions,
- reconciliation with bank-grade import,
- truly reliable PDF parsing.

Именно поэтому сейчас правильнее называть его:
**сильный финансовый советник / financial copilot v1**, а не полноценный финансовый агент.

---

## Команды и основные пользовательские точки входа

Текущие ключевые команды/зоны:

### Базовые
- `/start`
- `/menu`
- `/summary`
- `/settings`

### Советник
- `/ask`
- `/ask <вопрос>`

### Экспорт / импорт
- `/export`
- `/import`

### Бюджеты
- `/budget`

### Planned / recurring
- `/plan`
- `/planned`
- `/recurring`
- `/recurring_del`

### Прочее
- `/edit`
- `/delete`
- `/deleteall`
- `/improve_categories`

---

## Кнопки и навигация

Ниже не каждый callback в коде, а **операционно важные группы кнопок**.

### Главное меню
Основные пункты меню:
- `📊 Сводка`
- `📋 Запланированные`
- `🔄 Регулярные`
- `💰 Бюджеты`
- `🗂 Категории`
- `🧠 Советник`
- `⚙️ Настройки`
- `ℹ️ Помощь`

### Advisor onboarding buttons
Сценарии:
- `📊 Топ расходов`
- `⚠️ Где вылезаю из бюджета?`
- `📅 Платежи скоро`
- `📈 Динамика за 3 месяца`
- `💡 Что сократить?`
- `📥 Скачать отчёт`

### Advisor session buttons
После ответа советника доступны:
- quick scenarios,
- `← Назад` к advisor screen,
- `✕ Завершить`,
- `≡ Меню`.

### Recommendation action buttons
Новый слой поверх рекомендаций:
- реальные **next-step buttons**,
- затем follow-up actions,
- логика уже не просто “открой экран”, а “углуби advisor по нужной теме”.

Примеры направлений:
- бюджетный риск,
- ближайшие платежи,
- тренд/прогноз,
- разбор категории.

### Budget flow buttons
Есть отдельные callback flows для:
- total budget,
- category budget,
- confirm/cancel,
- выбор категории.

### Planned / recurring buttons
Есть confirm/cancel/edit/manage flows.

### Import preview buttons
После dry-run preview:
- `confirm`
- `cancel`
- close/return path when import is unsupported.

---

## Состояния и режимы

Проект довольно stateful. Это важно понимать.

### Основной паттерн
Многое хранится в `context.user_data`.

### Важные режимы (`mode`)
Используются как минимум такие режимы:
- `advisor`
- `planned_input`
- `recurring_input`
- `budget_total_input`
- `budget_category_input`
- ещё несколько awaiting/pending контуров для отдельных flows

### Advisor state
В advisor flow используются:
- `advisor_history`
- `advisor_last_active`
- `last_advisor_snapshot`
- `last_advisor_analytics`
- `last_advisor_recommendations`
- `last_advisor_generated_at`
- `last_advisor_payload_version`
- `last_advisor_action_type`

TTL advisor-состояния:
- `_ADVISOR_TIMEOUT = 600` секунд

То есть idle > 10 минут → dialog memory очищается.

### Pending import state
Import flow хранит preview state примерно так:
- `pending_import_rows`
- `pending_import_filename`

Это позволяет:
- сначала показать preview,
- не писать в БД,
- затем подтвердить импорт вручную.

### Прочие pending/awaiting состояния
Есть отдельные состояния для:
- budget input,
- category edit,
- planned amount/date,
- recurring amount/schedule,
- settings input,
- category add/rename/emoji,
- evening checkin,
- voice correction.

### Важная особенность навигации
При general navigation большая часть transient state **чистится aggressively**.
Это сделано, чтобы не тащить старые pending-контексты между экранами.

---

## Голосовой workflow

Voice layer уже встроен в живой workflow.

### Как это работает
1. Пользователь шлёт voice.
2. Telegram runtime скачивает `.ogg`.
3. `AudioFileService.prepare_wav_from_ogg(...)` переводит в wav.
4. `STTService.transcribe(...)` делает распознавание.
5. Дальше transcript уходит в соответствующий flow:
   - normal transaction,
   - advisor,
   - planned input,
   - recurring input,
   - budget input.

### Где voice уже поддержан
- обычный ввод транзакций,
- advisor mode,
- budget total,
- budget category,
- planned input,
- recurring input.

### Ограничения
Если STT/LLM-ключи/voice pipeline падают, поведение должно деградировать аккуратно, но голосовой контур всё ещё более хрупкий, чем чистый текст.

---

## Export / Import workflow

## Export
Сейчас реально работает:
- CSV export,
- XLSX export.

Поддерживаемые периоды:
- `today`
- `week`
- `month`
- `all`

Примеры:
- `/export month`
- `/export xlsx month`
- `/export csv week`
- `/export xlsx all`

### Экспортный слой
`ExportService` строит артефакт:
- filename,
- content,
- mime_type,
- caption.

### XLSX уже не фейковый
Используется отдельный экспортный сервис, а не “псевдо-таблица в тексте”.

---

## Import
Сейчас реально поддержан:
- CSV
- XLSX

### Как работает import
1. Пользователь присылает файл.
2. `ImportService.detect_format()` определяет формат.
3. `ImportService.build_preview()` делает dry-run preview.
4. Пользователь видит:
   - сколько строк импортируется,
   - сколько пропущено,
   - какие warnings,
   - что **ничего ещё не записано**.
5. Только после confirm записи сохраняются в БД.

### Важное решение
Импорт сохраняет source через уже существующий enum-safe путь:
- `text`
- `voice`
- `webapp`

Отдельный source=`import` **не вводили**, чтобы не ломать схему без отдельной миграции.

### PDF
PDF-import сейчас **не реализован как настоящий parser**.
И это осознанное решение.

То есть проект честно говорит:
- CSV/XLSX — да,
- PDF — пока нет, только safe unsupported path.

---

## Бюджеты, planned, recurring, categories

Это не “добавки”, а полноценные рабочие модули.

### Бюджеты
Есть:
- общий месячный бюджет,
- бюджеты по категориям,
- проверки риска,
- budget health logic,
- быстрые budget flows через text/voice/callbacks.

### Planned expenses
Есть:
- ручное создание,
- free-form extraction,
- future-date validation,
- pending confirm/cancel,
- отображение upcoming items,
- связь с advisor upcoming analysis.

### Recurring transactions
Есть:
- recurring rule create/manage,
- free-form recurring input,
- recurring scheduling,
- category/type validation.

### Categories
Есть:
- seeded system categories,
- custom categories,
- rename,
- emoji change,
- hide/unhide,
- delete with reassignment,
- user-specific category mappings.

---

## Последние реализованные слои

Ниже — самое важное по свежей истории, не вся древняя археология.

### Серия последних коммитов
- `dbf4253` — `Implement advisor v1 foundation`
- `71d62cd` — `Add structured advisor responses`
- `316c4e0` — `Add advisor analytics layer`
- `eabe071` — `Add Excel export support`
- `66bda5d` — `Add import dry-run preview flow`
- `6b6613a` — `Clarify advisor onboarding message`
- `f24f046` — `Add back button to advisor session keyboard`
- `b7464ba` — `Edit advisor scenario replies in place`
- `db952cb` — `Add advisor recommendation layer`
- `0cfd9f5` — `Stabilize advisor state contract`
- `abf0c07` — `Add advisor action buttons`
- `fe602d3` — `Add advisor follow-up actions`

### Что это значит по-человечески
Последними слоями проект получил:

1. **foundation advisor mode**
2. **structured advisor payload**
3. **code-driven analytics**
4. **Excel export**
5. **CSV/XLSX import with dry-run preview**
6. **better onboarding**
7. **better session navigation**
8. **in-place advisor scenario replies**
9. **recommendation layer**
10. **state contract stabilization**
11. **action buttons**
12. **follow-up actions поверх рекомендаций**

То есть советник уже перестал быть просто “вопрос-ответом к LLM”.

---

## Что именно реализовано последним

Если совсем коротко:

### Последний законченный слой
**Advisor follow-up actions**.

Смысл:
- recommendation buttons теперь ведут не просто в экран,
- а запускают **осмысленный follow-up внутри advisor flow**,
- без лишнего мусора в чате,
- в том же message-oriented UX.

То есть пользователь получает цепочку:

```text
вопрос -> ответ -> рекомендация -> action button -> углублённый follow-up
```

Это уже заметно ближе к financial copilot, чем к просто “умной болталке”.

---

## Что сейчас в планах

### Ближайший practical roadmap

#### 1. Action-specific rendering
Сделать follow-up ответы чуть умнее по форме:
- разные сценарии можно рендерить по-разному,
- где-то сильнее выводить риски,
- где-то сильнее показывать цифры и basis,
- где-то показывать “что сделать прямо сейчас”.

#### 2. Anti-loop logic
Не давать советнику зацикливаться:
- если пользователь уже нажал похожий follow-up,
- не повторять ту же рекомендацию снова и снова.

#### 3. Recommendation/session memory
Чуть лучше помнить, какие advisor actions уже были нажаты в этой сессии.

#### 4. Stronger import / reconcile
Импорт уже есть, но дальше нужен более зрелый слой:
- better matching,
- possible dedupe,
- cleaner reconcile logic,
- maybe later statement-level workflows.

#### 5. Safe action layer
Следующий большой шаг к “финансовому агенту”, а не только advisor:
- confirmable actions,
- task/follow-up memory,
- weekly loop,
- explainability of actions.

#### 6. PDF only when honest
PDF parsing только если будет реальный, ограниченный, проверяемый путь.
Не через fake parser.

---

## На какой стадии проект сейчас

### Как финансовый ассистент
Примерно:
- **72–78% готовности**

Почему так высоко:
- уже есть advisor,
- analytics,
- recommendations,
- import/export,
- voice/text,
- budgets/plans/recurring,
- Telegram UX уже не сырой.

### Как финансовый агент
Скорее:
- **45–55%**

Почему ниже:
- нет полноценного action loop,
- нет task/follow-up memory как зрелого слоя,
- нет stable confirmable action engine,
- reconcile/import ещё не зрелый,
- PDF/import intelligence ещё не дотянуты.

То есть сейчас проект — это:

> **крепкий финансовый советник / strong MVP financial copilot**

но ещё не полноценный “финансовый агент v1”.

---

## Главные сильные стороны проекта

1. **Telegram-first UX**
   Это очень сильная ставка для реального использования.

2. **Не один LLM-промпт, а нормальная архитектура**
   Snapshot + analytics + recommendations уже дают опору.

3. **Structured advisor payload**
   Это сильно лучше обычной “простыни текста”.

4. **Import/export уже встроены в пользовательский workflow**
   Не отдельно где-то “на потом”, а уже как часть продукта.

5. **Voice layer уже не декоративный**
   Он реально встроен в flows.

6. **Система состояний уже живая**
   Это важно для реального Telegram-продукта.

---

## Главные текущие слабые места

1. **PDF пока честно не готов**
2. **Action layer ещё неглубокий**
3. **Follow-up memory ещё короткая и session-local**
4. **Import/reconcile ещё не bank-grade**
5. **Есть старый unrelated migration noise в worktree**, который надо продолжать держать вне продуктовых коммитов
6. **Canonical repo port ещё не завершён**, работа идёт в `buhgalter_bot_fresh`

---

## Где сейчас правда проекта

Если совсем в одной фразе:

**`buhgalter_bot_fresh` — это уже рабочий Telegram-first финансовый ассистент с advisor-слоем, аналитикой, рекомендациями, export/import и живыми UX-сценариями, но ещё не полный финансовый агент с task memory и action loop.**

---

## Практический вывод

Если смотреть не как на “идеальный продукт”, а как на живой operational contour:
- проект уже **можно тестировать и использовать**,
- advisor уже **имеет смысл**, а не “для галочки”,
- import/export уже **приносят пользу**, 
- следующий реальный скачок ценности даст не ещё один промпт, а:
  - stronger actions,
  - anti-loop behavior,
  - better memory of prior follow-ups,
  - stronger reconcile/import layer.

---

## Текущий recommended next step

Самый логичный следующий слой:

1. **action-specific rendering**
2. **anti-loop logic**
3. **recommendation memory in session**
4. потом уже deeper import/reconcile

Именно это двигает проект из “умного советника” в “почти агента”.
