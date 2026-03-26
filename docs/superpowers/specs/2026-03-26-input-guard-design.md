# Input Guard — Design Spec
**Date:** 2026-03-26
**Status:** Approved by user

## Goal

Block obviously off-topic user messages before any LLM or parser call, returning a fixed rejection message. Reduces wasted API calls and keeps the bot clearly scoped to financial operations.

## Problem

Currently, a message like "расскажи анекдот" travels through:
1. `_looks_like_question()` → no match
2. Parser (fast path) → low confidence, no amount
3. LLM → classifies as `advisor`
4. `FinancialQAService` → rejects

Two API calls consumed for garbage input.

## Solution

Add an `InputGuard` service that runs at the **very start** of `handle_text`, before parser and LLM, using a combo of whitelist + blacklist logic.

## Architecture

### New file: `backend/app/services/input_guard.py`

```python
class InputGuard:
    def check(self, text: str) -> str | None:
        """Returns rejection message str, or None to pass through."""
```

**Logic (in order):**
1. **Blacklist check** — if text matches explicit off-topic patterns → reject immediately
2. **Whitelist check** — if text contains financial signals (digits, currency, financial keywords) → pass (return None)
3. **Default** — no signals on either side → reject

**Financial signals (whitelist):**
- Any digit (`\d`)
- Currency symbols: `₽`, `$`, `€`, `£`
- Financial verbs/nouns: `потратил`, `купил`, `заплатил`, `получил`, `доход`, `расход`, `зарплата`, `перевёл`, `перевел`, `стоит`, `рублей`, `копейк`, `бюджет`, `трат`, `плат`, `выплат`, `списал`, `снял`, `внёс`, `вернул`, `задолж`, `долг`, `кредит`, `депозит`, `налог`

**Off-topic blacklist patterns:**
- `анекдот`, `шутк`, `стих`, `поэм`, `песн`
- `привет`, `здравствуй`, `добрый день`, `добрый вечер`, `как дела`, `как ты`
- `расскажи` (without financial context — guarded by whitelist running second)
- `напиши` (same)
- `погода`, `новост`, `политик`, `спорт`, `рецепт`, `помоги с`

Note: blacklist runs **before** whitelist, so "расскажи анекдот про 100 рублей" — hits blacklist → rejected. "потратил 100" — not blacklisted, hits whitelist → passed.

**Rejection message:** `"Я работаю только с финансами — расходами, доходами и бюджетом."`

### Integration in `handlers.py`

```python
def handle_text(self, telegram_user_id: int, text: str) -> dict:
    normalized = self._normalize_incoming_text(text)

    # Guard: only run when user is NOT in pending category resolution flow.
    # _store_get returns None when there is no active pending state.
    if _store_get(telegram_user_id) is None:
        rejection = self._input_guard.check(normalized)
        if rejection:
            return {"action": "offtopic", "message": rejection}

    # ... existing logic unchanged
```

`InputGuard` initialized once in `TelegramTextFlow.__init__`:
```python
self._input_guard = InputGuard()
```

**Guard is bypassed when:**
- User has a pending category resolution (`_store_get(user_id) is not None`) — they're answering a bot prompt about category selection. In this case the guard call is skipped entirely.

**Guard is NOT applied to:**
- Voice messages (handled by `handle_voice`, separate flow)
- `/start`, `/summary` commands (handled by dedicated methods)

**Case-insensitivity:** `InputGuard` lowercases the incoming text before all pattern checks.

### New action type

`{"action": "offtopic", "message": "..."}` — handled by the catch-all branch in `runtime.py` (line ~2302): `await update.effective_message.reply_text(response["message"], ...)`. No changes to `runtime.py` or `bot_service.py` needed.

### Intentional rejection of short/ambiguous text

Messages like "ок", "хорошо", one-word acknowledgements without financial context are intentionally rejected with the same message. The bot is not a general conversational assistant — ambiguous text with no financial signals should not consume API calls.

### Blacklist-wins rationale

Blacklist is checked before whitelist to prevent prompt injection patterns like "расскажи анекдот про 100 рублей" from sneaking through by embedding a digit. If someone explicitly asks for jokes/poems/non-financial help, the explicit request intent wins regardless of incidental numbers.

## Testing

New file: `backend/tests/test_input_guard.py`

Coverage:
- Obvious off-topic → rejected (анекдот, приветствие, погода)
- Financial text with digits → passed
- Financial keywords without digits → passed
- Short ambiguous text (no signals) → rejected
- Edge: "расскажи анекдот про 100 рублей" → rejected (blacklist wins)
- Edge: "как дела с бюджетом?" → passed (whitelist: "бюджет")

## Files Changed

| File | Change |
|------|--------|
| `backend/app/services/input_guard.py` | New — InputGuard class |
| `backend/app/telegram/handlers.py` | Add guard call + `self._input_guard` init |
| `backend/tests/test_input_guard.py` | New — unit tests |

No DB, no mocks of external services needed in tests.
