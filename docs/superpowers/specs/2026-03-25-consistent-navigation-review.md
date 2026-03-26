# Review: Consistent Navigation Design Spec

**Reviewer:** Code Review Agent
**Date:** 2026-03-25
**Spec:** `docs/superpowers/specs/2026-03-25-consistent-navigation-design.md`

---

## Overall Assessment

The spec is well-structured, with a clear design principle ("every bot message must contain an inline keyboard") and clean keyboard abstractions (`done_keyboard`, `advisor_keyboard`). The two new helper functions fit naturally alongside the existing `_btn`, `_menu_btn`, `_back_btn` helpers in `keyboards.py`. The decision to keep `handlers.py` untouched is correct -- keyboards belong at the send layer in `runtime.py`.

However, the spec covers only **~19 of ~95+ dead-end sends**. It addresses the most obvious ones but misses entire subsystems.

---

## Critical: Missed Dead-End Screens

### 1. Edit flow (L600, L630, L645, L660, L662, L674, L692)

The spec covers L660 ("Udali zapis") but misses:
- **L600** `"Zapisey dlya redaktirovaniya net."` -- needs `done_keyboard()`
- **L630** `"Zapisey net."` -- needs `done_keyboard()`
- **L645** `"Ne nashyol zapis."` -- needs `done_keyboard("edit:select")`
- **L662** `"Ne nashyol zapis. Vozmozhno, ona uzhe udalena."` -- needs `done_keyboard()`
- **L674** `"Ne nashyol zapis."` (edit amount/type) -- needs `done_keyboard("edit:select")`
- **L692** `"Vvedi novuyu summu..."` -- input prompt, arguable skip but user is stranded if they change their mind

### 2. Undo callback (L913, L930, L932)

- **L913** `"Ne udalos' otmenit': ID ne nayden."` -- needs `done_keyboard()`
- **L930** `"Otmeneno."` -- needs `done_keyboard()`
- **L932** `"Zapis' uzhe byla udalena ili ne naydena."` -- needs `done_keyboard()`

### 3. Category resolution / catres (L962, L967, L975, L986, L993)

- **L962** `"Sessiya istekla."` -- needs `done_keyboard()`
- **L967** `"Zapis' otmenena."` -- needs `done_keyboard()`
- **L993** `"Ne udalos' obrabotat' vybor."` -- needs `done_keyboard()`

### 4. Low confidence / lowconf (L1060, L1064)

- **L1060** evening check-in result -- needs `done_keyboard()`
- **L1064** `"Ne udalos' obrabotat' vybor."` -- needs `done_keyboard()`

### 5. Evening check-in (L1084, L1126, L1136, L1139)

- **L1084** `"Khorosho, pustoy den'."` -- needs `done_keyboard()`
- **L1126** check-in saved result -- needs `done_keyboard()`
- **L1139** `"Khorosho!"` -- needs `done_keyboard()`
- **L1136** `"Vvedi summu:"` -- input prompt, needs cancel button

### 6. Budget command (L1408, L1414, L1418, L1437, L1447, L1449, L1454, L1463)

Entire `/budget` command is missed:
- **L1414** budget report -- needs `done_keyboard("nav:budgets")`
- **L1437** `"Ne ponyal summu"` -- needs `done_keyboard("nav:budgets")`
- **L1447** `"Byudzhet udalen"` -- needs `done_keyboard("nav:budgets")`
- **L1454** `"Byudzhet ... rub/mes"` -- needs `done_keyboard("nav:budgets")`
- **L1463** budget alert -- arguably a notification, but still a dead end

### 7. Recurring commands (L1478, L1496, L1512, L1530, L1536, L1542, L1566, L1571, L1577, L1585, L1587)

Entire `/recurring` and recurring callback flow is missed:
- **L1478** recurring list -- needs `done_keyboard()`
- **L1512** recurring created -- needs `done_keyboard()`
- **L1566** recurring callback response -- needs `done_keyboard()`
- **L1585** `"Tranzaktsiya udalena"` -- needs `done_keyboard()`
- **L1587** `"Tranzaktsiya ne naydena"` -- needs `done_keyboard()`

### 8. Settings callbacks (L1607, L1613, L1619, L1625, L1636)

All settings input prompts are dead ends:
- **L1607-L1625** "Enter time/timezone" prompts -- need cancel buttons back to `nav:settings`
- **L1636** `"Vse napominaniya otklyucheny"` -- needs `done_keyboard("nav:settings")`

### 9. Planned/recurring input handlers (L1674-L1695, L1757, L1765, L1844, L1857, L1878, L1891, L1902, L1920, L1931)

Free-form input error and confirmation responses -- all dead ends.

### 10. Category rename/emoji (L1945, L1949, L1964, L1968, L1970, L1978, L1986)

Category management text input responses -- all dead ends.

### 11. Voice handler errors (L2173, L2206, L2211)

- **L2173** `"Ne nashyol voice payload."` -- needs `done_keyboard()`
- **L2206/L2211** voice processing errors -- need `done_keyboard()`

### 12. Delete callback (L2363)

- **L2363** delete response -- needs `done_keyboard()`

### 13. Budget input handlers (L2454, L2481)

Budget total/category input responses -- dead ends.

---

## Important: Incorrect or Imprecise back_target Values

### L341 missing from spec
The spec lists L330 with `back_target="nav:categories"` but L341 (`"categories:set_type"` error during category creation) also needs `back_target="nav:categories"`. It is absent.

### L281 missing from spec
`"Kategoriya ne naydena"` at L281 -- dead end in the categories callback handler. Needs `done_keyboard("nav:categories")`.

### L2053 listed as "contextual" with no definition
The spec says `back_target` is "contextual" for L2053 but does not explain what that means or how to determine it. This needs clarification -- what context determines the back target? Likely should be `None` (just menu button).

---

## Important: `context.bot.send_message` and `effective_chat.send_message`

The spec mentions `context.bot.send_message` as an edge case but does not address two actual instances:
- **L1267** `effective_chat.send_message("Oshibka pri otkrytii razdela")` -- needs `done_keyboard()`
- **L1255** `effective_chat.send_message(...)` in the nav router -- context-dependent

These use `send_message` rather than `edit_message_text`, so they create new messages. The `done_keyboard()` approach still works, but the spec should explicitly note this difference (new message vs. editing existing).

---

## Important: Input Prompts Need Cancel Buttons

Several "awaiting input" prompts leave users stranded:
- **L692** "Enter new amount" (edit flow)
- **L842** "Enter new amount" (planned expense)
- **L848** "Enter new date" (planned expense)
- **L1536** "Enter new amount" (recurring)
- **L1542** "Enter new period" (recurring)
- **L1607-L1625** Settings input prompts (morning/evening/timezone)
- **L1136** Evening check-in "enter amount"

These are not confirmations or errors -- they are input prompts where the user may want to cancel. They need a cancel/back inline button. `done_keyboard(back_target)` does not fit semantically; a third keyboard type like `cancel_keyboard(back_target)` would be cleaner.

**Recommendation:** Add a third helper:
```python
def cancel_keyboard(back_target: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[_btn("Otmena", back_target)]])
```

---

## Suggestion: L184 and L212 (improve_categories results)

- **L184** result from `/improve_categories` -- has navigation context but no keyboard
- **L207** "Predlozheniy net" -- needs `done_keyboard()`
- **L203** "Oshibka pri analize" -- needs `done_keyboard()`
- **L212** suggestion text with approval keyboard is sent separately, but if suggestions list is displayed first, that message is a dead end

---

## Suggestion: Batch the Changes by Subsystem

The spec organizes changes by keyboard type (confirmations, errors, advisor). For a 2643-line file with ~95 edits needed, organizing by **subsystem** would be safer:

1. Category management (L281, L330, L341, L343, L354, L388, L390, L395, L405, L407)
2. Edit flow (L600, L630, L645, L660, L662, L674, L692)
3. Undo (L913, L930, L932)
4. Category resolution (L962, L967, L975, L986, L993)
5. Low confidence (L1060, L1064)
6. Evening check-in (L1084, L1126, L1136, L1139)
7. Budget (L1408-L1463, L2454, L2481)
8. Recurring (L1478-L1587)
9. Settings (L1607-L1636)
10. Planned/recurring input (L1674-L1931)
11. Category rename/emoji (L1945-L1986)
12. Advisor/QA (L525, L2282)
13. Voice (L2173, L2206, L2211)
14. Delete (L2363)
15. Misc nav errors (L1267, L2301)

This makes it easier to verify correctness of `back_target` values within each subsystem.

---

## Suggestion: Consider a Lint Rule

After implementation, add a simple grep-based CI check:
```bash
# Fail if any send without reply_markup (excluding known placeholders)
grep -nP '(edit_message_text|reply_text|send_message)\(' runtime.py \
  | grep -v 'reply_markup' | grep -v 'placeholder' | grep -v 'Analyzing'
```
This prevents future regressions.

---

## Summary

| Category | Count |
|----------|-------|
| Spec covers | ~19 lines |
| Missed dead ends | ~76 lines |
| Spec accuracy on covered lines | Good -- back_target values are correct |
| Missed subsystems | Edit, Undo, CatRes, LowConf, CheckIn, Budget, Recurring, Settings, Planned input, Category edit, Voice, Delete |

**Verdict:** The design approach (two helper functions, point edits in runtime.py, no handler changes) is sound and should be kept. But the spec needs a second pass to cover the full set of dead-end screens before implementation begins. The current coverage is roughly 20% of what is needed.
