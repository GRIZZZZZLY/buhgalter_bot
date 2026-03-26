# UI/UX Prompt for Pencil.dev

## Project

Telegram Finance Bot WebApp

## Prompt

Design a **premium mobile-first Telegram Mini App** for a personal finance assistant.

This product is a **Telegram-first finance bot** where users record income and expenses through:

- text input in chat
- voice input in chat, with recognition and confirmation before saving

The **WebApp** is the companion product where users:

- review balance and period summaries
- browse recent transactions
- add a transaction directly in the WebApp
- edit and delete existing transactions
- review category analytics
- track budgets by category

The final result must feel like:

**a modern Telegram-native finance product with refined treasury / archival / ledger-inspired visual accents**

It must **not** feel like:

- a museum interface
- a folklore-themed parody
- historical cosplay
- a fantasy game UI
- an overloaded ornamental experiment

The design should be:

- mobile-native
- premium
- highly readable
- fast to scan
- elegant
- culturally distinctive in a restrained way

---

## Core Design Direction

The visual language should be built from **two layers**:

### 1. Product layer (primary)

- Telegram-native UX
- modern fintech clarity
- clean information hierarchy
- fast scanning of amounts and balances
- compact mobile layout
- one-handed usability

### 2. Cultural accent layer (secondary)

- subtle treasury / archive / manuscript cues
- refined ornamental dividers
- elegant serif display typography for headings and financial numbers
- restrained decorative rhythm
- accent details inspired by seals, ledgers, archival margins, editorial financial documents

Important:

- The **product layer must dominate**
- The **cultural layer must frame the experience**, not overwhelm it
- Decorative identity should appear only in selective moments

---

## Visual Positioning

The product should feel like:

- a refined digital ledger
- a modern treasury dashboard
- an elegant mobile finance companion
- a calm financial archive translated into a premium Telegram Mini App

The feeling should be:

- crafted
- noble
- understated
- editorial
- product-grade

The app should **not** feel:

- theatrical
- costume-heavy
- pseudo-medieval
- cartoonish
- kitschy
- overloaded with folk ornament

---

## Heritage Inspiration Rules

Use heritage inspiration as **accent logic**, not literal decoration.

Allowed inspiration sources:

- treasury ledgers
- archival books
- manuscript separators
- premium editorial design
- seal-like marks
- elegant Slavic decorative rhythm
- restrained references to Gzhel / Khokhloma color logic

Do **not** directly translate:

- folk patterns into full backgrounds
- heavy ornamental borders on every card
- pseudo-old Cyrillic text styles
- carved wood / old paper textures over content
- dense decorative patterns behind data

If using cultural references, apply them in:

- hero card
- section dividers
- section labels
- chart accents
- empty-state illustration mood

Do not apply them to:

- every list row
- every button
- every input
- every modal

---

## Platform Constraints

The design runs inside **Telegram Mini App** context.

It must be:

- **mobile-first**
- optimized for **small screens**
- optimized for **embedded Telegram viewport**
- touch-friendly
- lightweight
- visually stable in Telegram
- fast-loading and clear

Avoid:

- desktop dashboard behavior
- sidebars
- dense tables
- wide multi-column layouts
- hover-dependent interactions
- long navigation depth

Prefer:

- stacked cards
- lightweight routed mobile screens
- bottom-sheet behavior where appropriate
- clear CTA hierarchy
- thumb-friendly targets

---

## Product Screens to Design

Design the following screens / states.

### 1. Main Dashboard

Include:

- dominant current balance hero card
- total income
- total expense
- period switcher: `Сегодня / Неделя / Месяц / Всё`
- category breakdown chart
- category legend / top spending categories
- recent transactions preview
- floating action button or strong CTA to add transaction
- quick access to budgets

This screen should feel like:

- the refined opening page of a modern financial ledger
- premium, mobile, fast, and emotionally distinct

### 2. Transactions List / Recent Activity

Include:

- chronological transaction rows
- strong amount readability
- clear income / expense distinction
- category label
- date / time
- quick scan behavior
- tap to edit

Rows may have a slight ledger / register feel, but should remain minimal.

### 3. Add Transaction Screen

Include:

- amount input
- transaction type switch (`income / expense`)
- category selector
- description input
- strong save CTA

This should feel:

- fast
- lightweight
- frictionless
- modern first, styled second

### 4. Edit Transaction Screen / Sheet

Include:

- amount
- type
- category
- description
- save
- delete
- cancel / back

Destructive action must be clear and safe.

### 5. Budgets Screen

Include:

- category budget cards
- current spend vs budget
- progress bars
- over-budget state
- empty state when budgets are not configured

This screen should be clear and dense enough to be useful on mobile.

### 6. Empty / Error / Loading States

Create states for:

- no transactions yet
- no transactions in selected period
- no analytics data yet
- no budgets configured
- API unavailable / unauthorized / Telegram context missing
- loading skeletons

These states should still feel premium and intentional.

---

## UX Requirements

The UX must prioritize:

- balance visibility at first glance
- very fast transaction scanning
- easy thumb navigation
- lightweight editing
- clear positive / negative semantics
- obvious destructive actions
- elegant empty states
- minimal cognitive load

Also:

- design must feel good when there is **little data**
- design must feel stable when there is **a lot of repeated rows**
- avoid visual overload in high-frequency interactions

---

## Typography Direction

Typography should combine:

### Display typography

- elegant serif or editorial serif
- used for hero balance, key headings, financial emphasis
- refined, premium, restrained
- can hint at ledger / archive / chronicle mood

### Body typography

- highly readable modern sans-serif
- used for all lists, forms, labels, buttons, settings, metadata

Rules:

- financial values must remain crystal clear
- do not use pseudo-old Cyrillic
- do not over-style small text
- numbers must stay extremely readable
- serif should be used sparingly and with hierarchy

Possible direction:

- serif display for headings and amounts
- neutral system / modern sans for body

---

## Color Direction

Use a premium, restrained palette.

Primary direction:

### Treasury Manuscript / Editorial Ledger

- parchment cream / warm ivory backgrounds
- ink brown / deep graphite for text
- muted blue accents
- antique gold highlights
- subtle red / green semantics for expense / income

Alternative accent logic:

- restrained Gzhel-like cool blue for navigation and links
- restrained gold for section labels, separators, hero accent, chart accents

Do not use:

- loud folk color explosions
- carnival red/gold/black overload
- heavy black lacquer surfaces everywhere
- saturated ornamental color blocks

For semantics:

- income must still clearly read as positive
- expense must still clearly read as negative
- semantic meaning must win over theme aesthetics

---

## Decorative Usage Rules

Decorative elements must be **systematic, sparse, and reusable**.

Allowed decorative components:

- hero accent line
- ornamental divider
- section kicker label
- subtle seal-like mark in hero
- chart accent color treatment
- quiet empty-state illustration language

Avoid:

- decorating every component
- random flourishes
- dense borders on every card
- decorative patterns behind list rows
- highly textured surfaces behind text

Think like a real design system, not a one-off illustration.

---

## Component System to Define

Please define:

- color palette
- typography hierarchy
- display font rules
- body font rules
- spacing system
- hero card style
- standard surface card style
- transaction row style
- chart style
- budget card style
- button styles
- period tabs style
- input fields style
- bottom sheet / edit modal style
- icon style
- divider / ornament rules
- empty state rules
- loading state rules

---

## Telegram Mini App-Specific UX Guidance

Please account for:

- small viewport
- one-handed use
- embedded Telegram context
- safe area handling
- quick loading feel
- native-feeling overlays and sheets
- high readability under varying Telegram themes
- compact actions near the thumb zone

The interface should feel like it belongs inside Telegram, not like a transplanted desktop app.

---

## Technical Implementation Context

The final frontend will likely be implemented with:

- React
- TypeScript
- Vite
- `@tma.js/sdk-react`
- Tailwind CSS v4
- shadcn/ui
- Motion
- TanStack Query
- react-hook-form
- zod

Please make the design realistic for production implementation in this stack.

Avoid design ideas that depend on:

- heavy desktop charting patterns
- complex hover-only behavior
- non-mobile layout assumptions
- extreme ornament rendering

---

## Deliverables

Generate:

1. overall UX direction
2. main dashboard screen
3. transactions screen
4. add transaction screen
5. edit transaction screen / sheet
6. budgets screen
7. empty states
8. loading and error states
9. design system guidance
10. typography recommendations
11. color palette recommendations
12. ornament and icon usage guidance
13. Telegram Mini App-specific implementation notes

---

## Extra Instruction

The final visual result should feel like:

**"A Telegram-native finance product with the calm authority of a treasury ledger and the restraint of premium editorial design."**

Not parody. Not museum. Not fantasy. Not folklore cosplay.

It must be:

- beautiful
- memorable
- culturally nuanced
- usable
- premium
- fast
- mobile-native
