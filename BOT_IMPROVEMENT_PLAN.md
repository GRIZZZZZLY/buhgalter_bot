# buhgalter_bot_fresh — план улучшений UX и функциональности

> Версия: 1.0 · Дата: 28.03.2026  
> Область: функциональные и UX-улучшения, без монетизации  
> Контекст: проект на стадии strong MVP (~72–78% готовности как финансового ассистента)

---

## Содержание

1. [Принципы приоритизации](#1-принципы-приоритизации)
2. [Спринт 1 — Чистка интерфейса и быстрые UX-фиксы](#2-спринт-1--чистка-интерфейса-и-быстрые-ux-фиксы)
3. [Спринт 2 — Онбординг и первое впечатление](#3-спринт-2--онбординг-и-первое-впечатление)
4. [Спринт 3 — Оптимизация советника](#4-спринт-3--оптимизация-советника)
5. [Спринт 4 — Anti-loop и session memory](#5-спринт-4--anti-loop-и-session-memory)
6. [Спринт 5 — Action-specific rendering](#6-спринт-5--action-specific-rendering)
7. [Спринт 6 — Улучшение импорта и reconcile](#7-спринт-6--улучшение-импорта-и-reconcile)
8. [Что не трогать сейчас](#8-что-не-трогать-сейчас)
9. [Сводная таблица задач](#9-сводная-таблица-задач)

---

## 1. Принципы приоритизации

Все задачи оцениваются по трём критериям:

- **Impact** — насколько улучшает ежедневный опыт пользователя
- **Effort** — сколько реального времени займёт реализация
- **Risk** — вероятность сломать что-то работающее

Порядок спринтов выстроен по принципу: сначала убираем раздражители → потом улучшаем основные сценарии → потом углубляем советника.

---

## 2. Спринт 1 — Чистка интерфейса и быстрые UX-фиксы

**Цель:** убрать всё что мешает, не ломая то что работает.  
**Оценка:** 2–3 дня  
**Риск:** низкий

### 2.1 Сокращение видимых команд в BotFather

**Проблема:** у бота сейчас 15+ команд. Обычный пользователь запоминает максимум 3–4. Длинный список команд создаёт ощущение сложности ещё до начала работы.

**Что оставить в публичном списке команд:**

| Команда | Назначение |
|---|---|
| `/menu` | единственная точка навигации |
| `/ask` | shortcut в советника |
| `/export` | shortcut для опытных пользователей |
| `/import` | shortcut для опытных пользователей |
| `/start` | онбординг (скрыть из меню, оставить обработчик) |

**Что убрать из BotFather-списка** (обработчики оставить, из меню убрать):

- `/summary` — дублирует сводку из `/menu`
- `/settings` — переехать в меню
- `/plan` — дублирует `/planned`
- `/planned`, `/recurring`, `/recurring_del`, `/budget` — всё через меню
- `/edit`, `/delete` — из истории транзакций через inline кнопки
- `/improve_categories` — в настройках категорий

**Файлы для изменения:**
- `backend/app/telegram/runtime.py` — регистрация команд
- BotFather → `/setcommands`

---

### 2.2 Защита опасной команды /deleteall

**Проблема:** команда удаляет все данные и доступна из общего списка. Один случайный тап = потеря всей истории.

**Решение:**

```python
# runtime.py — обработчик /deleteall
@dp.message(Command("deleteall"))
async def deleteall_command(message: Message, context: CallbackContext):
    # 1. Убрать из публичного BotFather-списка
    # 2. Добавить двойное подтверждение
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="⚠️ Да, удалить ВСЕ данные",
            callback_data="deleteall:confirm_step1"
        ),
        InlineKeyboardButton(text="Отмена", callback_data="deleteall:cancel"),
    ]])
    await message.reply(
        "⚠️ Это удалит все твои транзакции, бюджеты и настройки безвозвратно.\n\n"
        "Сначала рекомендую сделать экспорт: /export",
        reply_markup=keyboard
    )

# После первого подтверждения — второй экран с обратным отсчётом
@dp.callback_query(F.data == "deleteall:confirm_step1")
async def deleteall_step2(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="🗑 Удалить всё (последний шанс отказаться)",
            callback_data="deleteall:confirm_final"
        ),
        InlineKeyboardButton(text="Отмена", callback_data="deleteall:cancel"),
    ]])
    await callback.message.edit_text(
        "Последнее подтверждение. Данные будут удалены полностью.",
        reply_markup=keyboard
    )
```

**Файлы:** `backend/app/telegram/runtime.py`, `backend/app/telegram/keyboards.py`

---

### 2.3 Таймаут на кнопки подтверждения транзакций

**Проблема:** кнопки "Отменить / Изменить категорию" после записи транзакции остаются в чате навсегда. Через неделю чат превращается в кладбище старых кнопок.

**Решение:**

```python
# После отправки подтверждения транзакции — планировать удаление кнопок
import asyncio

async def _send_transaction_confirmation(
    message: Message,
    transaction: Transaction
) -> None:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton("↩ Отменить", callback_data=f"undo:{transaction.id}"),
        InlineKeyboardButton("✏️ Категория", callback_data=f"edit_cat:{transaction.id}"),
    ]])
    
    sent = await message.reply(
        f"✅ {transaction.description} · {transaction.amount} ₽\n"
        f"Категория: {transaction.category}",
        reply_markup=keyboard
    )
    
    # Убрать кнопки через 60 секунд
    asyncio.create_task(_remove_buttons_after_timeout(sent, delay=60))

async def _remove_buttons_after_timeout(
    message: Message,
    delay: int
) -> None:
    await asyncio.sleep(delay)
    try:
        await message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass  # Сообщение уже удалено или изменено — игнорируем
```

**Файлы:** `backend/app/telegram/handlers.py`, `backend/app/telegram/bot_service.py`

---

### 2.4 Edit вместо Send для статусных сообщений

**Проблема:** промежуточные сообщения ("⏳ Обрабатываю...", "Загружаю данные...") создают шум в чате.

**Правило:** любое сообщение-статус должно редактироваться, а не быть новым сообщением.

```python
# Паттерн для всех мест где есть промежуточный статус

# ❌ Было
await message.reply("⏳ Загружаю данные советника...")
result = await get_advisor_response(...)
await message.reply(result)

# ✅ Стало
status_msg = await message.reply("⏳ Загружаю...")
result = await get_advisor_response(...)
await status_msg.edit_text(result, reply_markup=keyboard)
```

**Файлы:** `backend/app/telegram/runtime.py`, `backend/app/telegram/bot_service.py`

---

## 3. Спринт 2 — Онбординг и первое впечатление

**Цель:** новый пользователь должен записать первую транзакцию в течение 60 секунд после `/start`.  
**Оценка:** 3–4 дня  
**Риск:** низкий

### 3.1 Трёхшаговый онбординг

**Проблема:** сейчас `/start` запускает бота, но непонятно что делать дальше. Большинство пользователей не догадаются написать "такси 300".

**Решение — интерактивный онбординг из 3 шагов:**

```
Шаг 1 (сразу после /start):
─────────────────────────────
👋 Привет! Я помогу вести финансы прямо в Telegram.

Попробуй прямо сейчас — напиши любую трату:
  • "кофе 200"
  • "такси 450"  
  • "продукты 1800"

Или отправь голосовое — я пойму 🎤
─────────────────────────────

Шаг 2 (после первой транзакции):
─────────────────────────────
✅ Записано! Вот как это выглядит в сводке.

Теперь установи месячный бюджет — сколько планируешь 
тратить в месяц? Напиши число, например: 50000
[Пропустить →]
─────────────────────────────

Шаг 3 (после бюджета или пропуска):
─────────────────────────────
🎉 Всё готово!

Что умею:
• записывать траты текстом и голосом
• показывать сводку и бюджеты
• отвечать на вопросы о твоих финансах

[📊 Открыть сводку]  [🧠 Задать вопрос советнику]
─────────────────────────────
```

**Реализация:**

```python
# Новый файл: backend/app/telegram/onboarding.py

ONBOARDING_STEP_KEY = "onboarding_step"

class OnboardingFlow:
    
    async def start(self, message: Message, context: CallbackContext) -> None:
        context.user_data[ONBOARDING_STEP_KEY] = 1
        await message.reply(ONBOARDING_STEP1_TEXT)
    
    async def handle_first_transaction(
        self, 
        message: Message, 
        context: CallbackContext
    ) -> None:
        if context.user_data.get(ONBOARDING_STEP_KEY) != 1:
            return
        context.user_data[ONBOARDING_STEP_KEY] = 2
        await message.reply(
            ONBOARDING_STEP2_TEXT,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Пропустить →", callback_data="onboarding:skip_budget")
            ]])
        )
    
    async def handle_budget_set(
        self, 
        message: Message, 
        context: CallbackContext
    ) -> None:
        if context.user_data.get(ONBOARDING_STEP_KEY) != 2:
            return
        context.user_data[ONBOARDING_STEP_KEY] = "done"
        await self._show_completion(message)
    
    async def _show_completion(self, message: Message) -> None:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton("📊 Сводка", callback_data="nav:summary"),
            InlineKeyboardButton("🧠 Советник", callback_data="nav:advisor"),
        ]])
        await message.reply(ONBOARDING_STEP3_TEXT, reply_markup=keyboard)
    
    def is_complete(self, context: CallbackContext) -> bool:
        return context.user_data.get(ONBOARDING_STEP_KEY) == "done"
```

**Файлы:** 
- Создать: `backend/app/telegram/onboarding.py`
- Изменить: `backend/app/telegram/runtime.py` — интегрировать OnboardingFlow
- Изменить: `backend/app/telegram/handlers.py` — проверять шаг онбординга

---

### 3.2 Контекстные подсказки при первых действиях

**Проблема:** после онбординга пользователь попадает в "пустую" сводку без понимания что делать дальше.

**Решение — пустые состояния с действием:**

```python
# formatter.py — пустые состояния

def format_empty_summary() -> str:
    return (
        "📊 Пока нет записей за этот месяц.\n\n"
        "Начни прямо здесь — напиши трату:\n"
        "  _такси 300_ или _зарплата 50000_"
    )

def format_empty_budgets() -> str:
    return (
        "💰 Бюджеты не настроены.\n\n"
        "Установи лимиты чтобы видеть:\n"
        "• сколько осталось до конца месяца\n"
        "• где превышаешь план\n"
        "• прогноз советника по рискам"
    )

def format_empty_planned() -> str:
    return (
        "📋 Запланированных платежей нет.\n\n"
        "Добавь аренду, подписки или другие\n"
        "регулярные расходы — советник будет\n"
        "предупреждать заранее."
    )
```

**Файлы:** `backend/app/telegram/formatter.py`

---

## 4. Спринт 3 — Оптимизация советника

**Цель:** советник должен отвечать по-человечески коротко на простые вопросы и развёрнуто на запросы анализа.  
**Оценка:** 4–5 дней  
**Риск:** средний (изменение QA-сервиса)

### 4.1 Адаптивная длина ответа

**Проблема:** сейчас советник всегда возвращает полный structured payload — answer + basis + warnings + confidence + recommendations. Для простого вопроса "сколько потратил сегодня?" это избыточно.

**Решение — три режима ответа:**

```python
# financial_qa_service.py

class ResponseMode(Enum):
    SHORT   = "short"    # только answer, 1–2 предложения
    NORMAL  = "normal"   # answer + basis + recommendations
    FULL    = "full"     # полный payload со всеми полями

INTENT_TO_MODE = {
    IntentType.RECENT:         ResponseMode.SHORT,
    IntentType.BUDGET_CHECK:   ResponseMode.NORMAL,
    IntentType.CATEGORY_SPEND: ResponseMode.NORMAL,
    IntentType.TREND_ANALYSIS: ResponseMode.FULL,
    IntentType.ADVICE:         ResponseMode.FULL,
    IntentType.UPCOMING:       ResponseMode.NORMAL,
    IntentType.GENERAL:        ResponseMode.NORMAL,
}

def _render_response(
    self, 
    payload: AdvisorPayload, 
    mode: ResponseMode
) -> str:
    if mode == ResponseMode.SHORT:
        return payload.answer
    
    if mode == ResponseMode.NORMAL:
        parts = [payload.answer]
        if payload.warnings:
            parts.append("⚠️ " + " · ".join(payload.warnings))
        if payload.recommendations:
            primary = payload.recommendations[0]
            parts.append(f"→ {primary.title}")
        return "\n\n".join(parts)
    
    # FULL — существующий рендеринг
    return self._render_full_payload(payload)
```

---

### 4.2 Улучшение system prompt советника

**Проблема:** советник иногда добавляет излишние оговорки и повторяет данные которые пользователь и так видит в сводке.

**Что добавить в system prompt:**

```python
ADVISOR_SYSTEM_PROMPT_ADDITIONS = """
Правила общения:
- Если вопрос простой (цифра, факт) — отвечай одним предложением
- Не повторяй вопрос пользователя в ответе
- Не добавляй фраз "Исходя из ваших данных..." — это очевидно
- Не пиши "Рекомендую вам..." — просто скажи что делать
- Если всё хорошо — скажи это прямо, не ищи проблемы
- Числа округляй до целых рублей в тексте

Тон: коллега который хорошо разбирается в финансах,
а не финансовый консультант пишущий отчёт.
"""
```

---

### 4.3 Контекстный вопрос вместо универсальной клавиатуры

**Проблема:** после любого ответа советника показывается одна и та же клавиатура с 6 кнопками. Это не контекстно.

**Решение — клавиатура зависит от типа ответа:**

```python
# keyboards.py

def advisor_contextual_keyboard(
    action_type: str | None,
    category: str | None = None
) -> InlineKeyboardMarkup:
    
    # Базовые кнопки всегда
    base = [
        InlineKeyboardButton("← Назад", callback_data="nav:advisor"),
        InlineKeyboardButton("≡ Меню", callback_data="nav:menu"),
    ]
    
    # Контекстные кнопки по типу рекомендации
    contextual_map = {
        "cut_costs": [
            InlineKeyboardButton(
                f"📊 Разбор категории {category or ''}",
                callback_data=f"advisor_followup:category_detail:{category}"
            ),
        ],
        "prepare_payment": [
            InlineKeyboardButton(
                "📅 Все ближайшие платежи",
                callback_data="advisor_followup:upcoming_all"
            ),
        ],
        "review_budget": [
            InlineKeyboardButton(
                "💰 Открыть бюджеты",
                callback_data="nav:budgets"
            ),
        ],
        "improve_cashflow": [
            InlineKeyboardButton(
                "📈 Динамика за 3 месяца",
                callback_data="advisor_followup:trend"
            ),
        ],
    }
    
    context_buttons = contextual_map.get(action_type or "", [])
    
    rows = []
    if context_buttons:
        rows.append(context_buttons)
    rows.append([
        InlineKeyboardButton("📥 Скачать отчёт", callback_data="export:choose"),
    ])
    rows.append(base)
    
    return InlineKeyboardMarkup(inline_keyboard=rows)
```

**Файлы:** `backend/app/telegram/keyboards.py`, `backend/app/telegram/runtime.py`

---

## 5. Спринт 4 — Anti-loop и session memory

**Цель:** советник не должен повторять одну и ту же рекомендацию если пользователь уже на неё нажал.  
**Оценка:** 2–3 дня  
**Риск:** низкий

### 5.1 Отслеживание показанных рекомендаций

**Проблема:** пользователь нажимает "Где сократить?" → получает ответ → нажимает снова → получает тот же ответ. Это создаёт ощущение "тупого бота".

**Решение:**

```python
# bot_service.py или advisor-related handler

SHOWN_RECOMMENDATIONS_KEY = "shown_recommendation_types"
MAX_SESSION_RECOMMENDATIONS = 5  # после этого — сброс

def _track_shown_recommendation(
    context: CallbackContext, 
    action_type: str
) -> None:
    shown = context.user_data.get(SHOWN_RECOMMENDATIONS_KEY, [])
    if action_type not in shown:
        shown.append(action_type)
    context.user_data[SHOWN_RECOMMENDATIONS_KEY] = shown[-MAX_SESSION_RECOMMENDATIONS:]

def _was_recommendation_shown(
    context: CallbackContext, 
    action_type: str
) -> bool:
    shown = context.user_data.get(SHOWN_RECOMMENDATIONS_KEY, [])
    return action_type in shown
```

**В RecommendationService.build() добавить фильтрацию:**

```python
def build(
    self,
    snapshot: FinancialSnapshot,
    analytics: FinancialAnalyticsSnapshot,
    exclude_action_types: list[str] | None = None,
) -> RecommendationSnapshot:
    candidates = self._compute_all_candidates(snapshot, analytics)
    
    if exclude_action_types:
        candidates = [
            c for c in candidates 
            if c.action_type not in exclude_action_types
        ]
    
    # ... остальная логика без изменений
```

**Файлы:** `backend/app/services/recommendation_service.py`, `backend/app/telegram/bot_service.py`

---

### 5.2 Follow-up memory в сессии

**Проблема:** советник не помнит что уже обсуждалось в текущей сессии (кроме `advisor_history`).

**Решение — расширить advisor state:**

```python
# Добавить в context.user_data при входе в advisor:

{
    "advisor_history": [...],           # уже есть
    "advisor_last_active": timestamp,   # уже есть
    "last_advisor_recommendations": ..., # уже есть
    
    # НОВЫЕ ПОЛЯ:
    "advisor_session_topics": [],       # темы уже затронутые в сессии
    "advisor_actions_taken": [],        # какие follow-up кнопки нажаты
    "advisor_session_start": timestamp, # для определения длины сессии
}
```

**Использование в system prompt:**

```python
def _build_context_with_session(
    self,
    snapshot_context: str,
    session_state: dict
) -> str:
    topics = session_state.get("advisor_session_topics", [])
    
    session_note = ""
    if topics:
        session_note = (
            f"\nВ этой сессии уже обсуждали: {', '.join(topics)}. "
            "Не повторяй те же рекомендации — ищи следующий шаг."
        )
    
    return snapshot_context + session_note
```

**Файлы:** `backend/app/telegram/runtime.py`, `backend/app/services/financial_qa_service.py`

---

## 6. Спринт 5 — Action-specific rendering

**Цель:** разные follow-up сценарии должны рендериться по-разному — там где нужны цифры показывать цифры, там где нужно действие — показывать действие.  
**Оценка:** 3–4 дня  
**Риск:** низкий

### 6.1 Специализированные рендереры по action_type

```python
# formatter.py — новые методы

class AdvisorFormatter:
    
    def format_for_action_type(
        self,
        payload: AdvisorPayload,
        action_type: str | None
    ) -> str:
        renderers = {
            "cut_costs":        self._render_cut_costs,
            "prepare_payment":  self._render_payment_warning,
            "review_budget":    self._render_budget_status,
            "improve_cashflow": self._render_cashflow_trend,
        }
        renderer = renderers.get(action_type or "", self._render_default)
        return renderer(payload)
    
    def _render_cut_costs(self, payload: AdvisorPayload) -> str:
        # Акцент: показать конкретную категорию и сумму перерасхода
        lines = [payload.answer]
        if payload.basis:
            lines.append("📊 На чём основано:")
            for fact in payload.basis[:3]:  # max 3 факта
                lines.append(f"  • {fact}")
        if payload.recommendations:
            rec = payload.recommendations[0]
            lines.append(f"\n→ {rec.title}: {rec.detail}")
        return "\n".join(lines)
    
    def _render_payment_warning(self, payload: AdvisorPayload) -> str:
        # Акцент: даты и суммы ближайших платежей
        lines = [payload.answer]
        if payload.warnings:
            for w in payload.warnings:
                lines.append(f"⚠️ {w}")
        return "\n".join(lines)
    
    def _render_budget_status(self, payload: AdvisorPayload) -> str:
        # Акцент: процент использования бюджетов
        return payload.answer  # здесь достаточно answer — цифры уже внутри
    
    def _render_cashflow_trend(self, payload: AdvisorPayload) -> str:
        # Акцент: динамика, было/стало, тренд
        lines = [payload.answer]
        if payload.basis:
            lines.append("📈 Данные за период:")
            for fact in payload.basis:
                lines.append(f"  {fact}")
        return "\n".join(lines)
    
    def _render_default(self, payload: AdvisorPayload) -> str:
        return payload.answer
```

**Файлы:** `backend/app/telegram/formatter.py`

---

### 6.2 Inline-редактирование ответов советника

**Проблема:** сейчас при нажатии на follow-up кнопку бот отправляет новое сообщение. При активной сессии чат быстро засоряется.

**Решение:** follow-up ответы редактируют текущее сообщение советника, а не создают новое.

```python
# runtime.py — обработчик advisor follow-up callbacks

@dp.callback_query(F.data.startswith("advisor_followup:"))
async def handle_advisor_followup(
    callback: CallbackQuery, 
    context: CallbackContext
) -> None:
    action = callback.data.split(":", 1)[1]
    
    # Показать индикатор загрузки в том же сообщении
    await callback.message.edit_text(
        callback.message.text + "\n\n⏳ Загружаю...",
        reply_markup=None
    )
    
    # Получить ответ
    response = await _get_followup_response(action, callback.from_user.id, context)
    
    # Обновить то же сообщение — не создавать новое
    await callback.message.edit_text(
        response.text,
        reply_markup=response.keyboard,
        parse_mode="Markdown"
    )
    
    await callback.answer()
```

**Исключение:** если ответ принципиально другого типа (например, переход в другой раздел) — тогда новое сообщение оправдано.

**Файлы:** `backend/app/telegram/runtime.py`

---

## 7. Спринт 6 — Улучшение импорта и reconcile

**Цель:** импорт должен быть надёжным, понятным и защищённым от дублей.  
**Оценка:** 5–7 дней  
**Риск:** средний (изменение ImportService)

### 7.1 Дедупликация при импорте

**Проблема:** повторный импорт одного файла создаёт дублирующие транзакции.

**Решение:**

```python
# import_service.py — добавить дедуп-логику

@dataclass
class ImportRow:
    date: date
    amount: Decimal
    description: str
    category: str | None
    
    def dedup_key(self) -> str:
        # Уникальный ключ: дата + сумма + описание
        return f"{self.date}:{self.amount}:{self.description.lower().strip()}"

class ImportService:
    
    async def build_preview(
        self, 
        user_id: int, 
        rows: list[ImportRow]
    ) -> ImportPreview:
        
        # Получить хэши существующих транзакций за период
        existing_keys = await self._get_existing_transaction_keys(
            user_id,
            date_from=min(r.date for r in rows),
            date_to=max(r.date for r in rows),
        )
        
        to_import = []
        duplicates = []
        
        for row in rows:
            if row.dedup_key() in existing_keys:
                duplicates.append(row)
            else:
                to_import.append(row)
        
        return ImportPreview(
            rows_to_import=to_import,
            rows_skipped_duplicates=duplicates,
            rows_skipped_invalid=[],  # отдельная валидация
        )
    
    async def _get_existing_transaction_keys(
        self,
        user_id: int,
        date_from: date,
        date_to: date,
    ) -> set[str]:
        transactions = await self.repo.get_transactions_for_period(
            user_id, date_from, date_to
        )
        return {
            f"{t.date}:{t.amount}:{t.description.lower().strip()}"
            for t in transactions
        }
```

**Обновлённый preview для пользователя:**

```
📥 Предпросмотр импорта — expenses_march.xlsx

Будет импортировано: 47 транзакций
Пропущено дублей: 12 (уже есть в базе)
Пропущено невалидных: 2 (нет суммы)

Период: 01.03 — 27.03.2026
Общая сумма: 84 320 ₽

[✅ Подтвердить импорт]  [❌ Отмена]  [👁 Показать детали]
```

---

### 7.2 Лучшая валидация при импорте

**Добавить понятные сообщения об ошибках вместо технических:**

```python
# import_service.py — улучшенные сообщения валидации

VALIDATION_MESSAGES = {
    "missing_amount":   "нет суммы",
    "invalid_date":     "некорректная дата",
    "future_date":      "дата в будущем",
    "negative_amount":  "отрицательная сумма",
    "missing_desc":     "нет описания",
    "amount_too_large": "сумма > 10 000 000 ₽ (проверь)",
}

def _validate_row(self, row: dict) -> list[str]:
    errors = []
    
    if not row.get("amount"):
        errors.append(VALIDATION_MESSAGES["missing_amount"])
    
    try:
        amount = Decimal(str(row.get("amount", 0)))
        if amount < 0:
            errors.append(VALIDATION_MESSAGES["negative_amount"])
        if amount > 10_000_000:
            errors.append(VALIDATION_MESSAGES["amount_too_large"])
    except Exception:
        errors.append(VALIDATION_MESSAGES["missing_amount"])
    
    if not row.get("date"):
        errors.append(VALIDATION_MESSAGES["invalid_date"])
    
    return errors
```

**Файлы:** `backend/app/services/import_service.py`, `backend/app/telegram/formatter.py`

---

### 7.3 Улучшенный шаблон для экспорта/импорта

**Добавить команду `/export template`** — скачать правильный шаблон CSV/XLSX для импорта:

```python
# runtime.py

@dp.message(Command("export"))
async def export_command(message: Message) -> None:
    # Существующая логика...
    # Добавить новую опцию:
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton("📊 XLSX за месяц", callback_data="export:xlsx:month"),
            InlineKeyboardButton("📄 CSV за месяц", callback_data="export:csv:month"),
        ],
        [
            InlineKeyboardButton("📅 За всё время", callback_data="export:xlsx:all"),
        ],
        [
            # НОВАЯ КНОПКА
            InlineKeyboardButton(
                "📋 Шаблон для импорта", 
                callback_data="export:template"
            ),
        ],
    ])
    await message.reply("Выбери формат:", reply_markup=keyboard)
```

**Файлы:** `backend/app/telegram/runtime.py`, `backend/app/services/export_service.py`

---

## 8. Что не трогать сейчас

Следующие вещи намеренно исключены из этого плана — они либо преждевременны, либо несут высокий риск при текущей стадии:

| Что | Почему не сейчас |
|---|---|
| Vector DB / RAG для советника | Overengineering на текущем объёме данных |
| PDF import | Требует специализированного парсера под конкретный банк, иначе ненадёжно |
| Agent loop / task memory | Следующий крупный слой, отдельный план |
| Safe action execution (изменение бюджетов агентом) | Требует отдельного action layer — спринт 7+ |
| WebApp рефакторинг | Telegram-first, WebApp второстепенен |
| ML-прогнозирование | Детерминированная аналитика работает лучше при малом объёме данных |
| Многопользовательские счета | Требует архитектурных изменений в схеме БД |

---

## 9. Сводная таблица задач

| # | Задача | Спринт | Impact | Effort | Риск | Файлы |
|---|---|---|---|---|---|---|
| 1.1 | Сократить команды в BotFather | 1 | 🔴 Высокий | S | Низкий | `runtime.py` |
| 1.2 | Защита /deleteall двойным confirm | 1 | 🔴 Высокий | S | Низкий | `runtime.py`, `keyboards.py` |
| 1.3 | Таймаут на кнопки транзакций | 1 | 🟡 Средний | S | Низкий | `handlers.py`, `bot_service.py` |
| 1.4 | Edit вместо Send для статусов | 1 | 🟡 Средний | S | Низкий | `runtime.py`, `bot_service.py` |
| 2.1 | Трёхшаговый онбординг | 2 | 🔴 Высокий | M | Низкий | `onboarding.py` (новый) |
| 2.2 | Пустые состояния с подсказками | 2 | 🟡 Средний | S | Низкий | `formatter.py` |
| 3.1 | Адаптивная длина ответа советника | 3 | 🔴 Высокий | M | Средний | `financial_qa_service.py` |
| 3.2 | Улучшение system prompt | 3 | 🟡 Средний | S | Низкий | `financial_qa_service.py` |
| 3.3 | Контекстная клавиатура советника | 3 | 🟡 Средний | M | Низкий | `keyboards.py`, `runtime.py` |
| 4.1 | Anti-loop: трекинг рекомендаций | 4 | 🟡 Средний | S | Низкий | `recommendation_service.py` |
| 4.2 | Follow-up memory в сессии | 4 | 🟡 Средний | M | Низкий | `runtime.py`, `financial_qa_service.py` |
| 5.1 | Рендереры по action_type | 5 | 🟡 Средний | M | Низкий | `formatter.py` |
| 5.2 | Inline-редактирование follow-up | 5 | 🔴 Высокий | M | Низкий | `runtime.py` |
| 6.1 | Дедупликация при импорте | 6 | 🔴 Высокий | L | Средний | `import_service.py` |
| 6.2 | Лучшая валидация импорта | 6 | 🟡 Средний | S | Низкий | `import_service.py`, `formatter.py` |
| 6.3 | Шаблон для импорта (/export template) | 6 | 🟢 Низкий | S | Низкий | `runtime.py`, `export_service.py` |

**Обозначения:**  
S = до 1 дня · M = 2–3 дня · L = 4–5 дней

---

## Рекомендуемый порядок работ

```
Неделя 1
  Спринт 1 — чистка интерфейса     (2–3 дня)
  Спринт 2 — онбординг             (3–4 дня)

Неделя 2
  Спринт 3 — советник              (4–5 дней)

Неделя 3
  Спринт 4 — anti-loop             (2–3 дня)
  Спринт 5 — rendering             (3–4 дня)

Неделя 4
  Спринт 6 — импорт/reconcile      (5–7 дней)
```

Итого: ~4 недели для полного цикла улучшений.

---

*Следующий план после завершения этих улучшений: Agent v1 — action layer, task memory, safe confirmable actions.*
