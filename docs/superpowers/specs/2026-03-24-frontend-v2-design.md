# Frontend V2 Design

## Goal

Спроектировать новую версию Telegram Mini App как полноценный второй интерфейс продукта: не просто дашборд, а **workspace-first companion** к Telegram-боту.

Бот остаётся лучшим для быстрого ввода и подтверждений. WebApp V2 становится лучшим местом для:

- обзора состояния,
- управления операциями,
- работы с planned expenses,
- управления recurring rules,
- бюджетов,
- настроек и категорий.

---

## Product Thesis

**Telegram bot = capture-first**  
**WebApp V2 = workspace-first**

Пользователь:

- быстро фиксирует события в боте;
- управляет структурой, историей, будущими тратами и правилами — в WebApp.

---

## Information Architecture

### Bottom navigation

1. **Главная**
2. **Операции**
3. **Планы**
4. **Бюджеты**
5. **Ещё**

### Inside “Ещё”

- Регулярное
- Категории
- Настройки
- Помощь
- Экспорт / удаление данных

Это даёт короткую и понятную мобильную IA без перегруженной нижней навигации.

---

## Screen Map

### 1. Главная

Назначение: быстро понять текущее состояние и увидеть ближайшие действия.

Содержимое:

- balance hero;
- доход / расход за период;
- period switcher;
- блок `Требует внимания`;
- быстрые действия;
- переходы в planned / recurring / budgets.

### 2. Операции

Назначение: рабочий реестр фактических транзакций.

Содержимое:

- список операций;
- фильтр периода;
- фильтр типа;
- поиск;
- edit/delete action flow.

### 3. Планы

Назначение: управление planned expenses.

Секции:

- Сегодня
- Ближайшие
- Просроченные

Действия:

- учесть;
- изменить сумму и учесть;
- перенести дату;
- отменить.

### 4. Бюджеты

Назначение: контроль лимитов и перерасходов.

Содержимое:

- общий бюджет;
- category budgets;
- over-budget states;
- edit budget actions.

### 5. Ещё → Регулярное

Назначение: управление recurring rules.

Содержимое:

- список правил;
- период;
- сумма;
- следующая planned generation;
- edit amount/category/schedule;
- deactivate.

### 6. Ещё → Категории

Назначение: пользовательские категории.

Содержимое:

- список категорий;
- add custom;
- rename;
- change emoji;
- delete custom with reassignment.

### 7. Ещё → Настройки

Назначение: системные пользовательские параметры.

Содержимое:

- timezone;
- reminders;
- budget settings;
- budget start day;
- privacy/system actions.

---

## Visual Direction

### Core direction

**Product Workspace with strong editorial character**

Это не generic dashboard и не themed costume UI.  
Это строгий мобильный финансовый workspace с ярким first screen, сильной типографикой и сдержанным treasury/editorial character.

### Visual rules

- сильный first viewport;
- balance как доминирующий visual anchor;
- списки — строгие и сканируемые, не “карточная мозаика”;
- decorative identity — дозированно;
- core UI — быстрый и utilitarian.

### Typography

- display serif для hero balance, headings, key amounts;
- neutral sans for body / forms / controls / lists.

### Color

- светлая премиальная база;
- графитовый текст;
- сапфировый/ink blue для navigation and actions;
- restrained gold/brass accent для headers / separators / hero accents;
- subdued income / expense semantics.

---

## Interaction Model

### Patterns

- bottom navigation for top-level movement;
- bottom sheets for editing and actions;
- compact action rows for planned / recurring;
- light shared transitions between sections;
- visible success / status feedback after state-changing actions.

### Important UX principles

- one-handed use first;
- lists over dashboards where repeated entities dominate;
- no deep nesting;
- no desktop metaphors (sidebars, dense tables, multi-column admin layout).

---

## Backend/API Gap

Чтобы V2 покрывал текущий продукт, frontend needs API for:

1. **Planned expenses**

- list
- create
- confirm
- confirm with amount
- cancel
- reschedule

2. **Recurring rules**

- list
- create
- update amount/category/schedule
- deactivate

3. **Settings**

- read
- update

4. **Categories**

- list
- create custom
- rename
- change emoji
- delete/reassign

The frontend V2 is therefore not “just redesign”, but a product-surface expansion that depends on new API contracts.

---

## Delivery Strategy

### Phase 1 — Core

- App shell
- Bottom navigation
- Dashboard
- Transactions
- Budgets
- Shared design system V2

### Phase 2 — Product parity

- Planned
- Recurring
- Settings
- Categories
- required backend APIs

### Phase 3 — Polish

- refined motion
- richer empty/error states
- higher action quality
- more expressive feedback patterns

---

## Recommended Implementation Approach

Строить V2 как **phased product rewrite**, а не как “перерисовку старых экранов”.

Потому что:

- продукт уже сильно вырос за пределы текущего фронта;
- старый WebApp покрывает лишь часть backend/domain возможностей;
- нужен новый IA layer, а не просто новая skin.

---

## Acceptance Criteria

Дизайн V2 считается корректно зафиксированным, если:

- bottom nav покрывает core flow продукта;
- planned / recurring / budgets / settings / categories встроены в общую IA;
- visual direction остаётся characterful, но product-first;
- фазы delivery позволяют безопасно выпускать V2 итеративно;
- backend API gap явно зафиксирован.
