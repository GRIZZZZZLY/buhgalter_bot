# buhgalter_bot

Telegram Finance Bot WebApp with Ancient Rus inspired premium mobile UI.

## Current status
- React + TypeScript + Vite frontend scaffold
- Telegram WebApp SDK initialization
- Dashboard with balance, periods, chart, transactions, edit sheet
- API-ready wiring for summary, transactions, update, delete
- Russian labels for categories in UI
- Mock fallback when backend API is unavailable

## Local development

### 1. Start backend
The frontend expects the finance bot backend from:
`/home/zubr/.openclaw/workspace/finance-bot-mvp/backend`

Run it locally on port 8000:

```bash
cd /home/zubr/.openclaw/workspace/finance-bot-mvp/backend
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Start frontend

```bash
cd /home/zubr/.openclaw/workspace-coder/buhgalter_bot
npm install
npm run dev
```

Frontend runs on:
- `http://127.0.0.1:4173`

Vite proxy forwards:
- `/api-proxy/*` -> `http://127.0.0.1:8000/*`

By default `.env.example` uses:

```env
VITE_API_BASE=/api-proxy
```

### 3. Production build

```bash
npm run build
```

## UX direction
1. Treasury hero card
2. Period switch
3. Category analytics
4. Ledger-like transaction list
5. Mobile edit bottom sheet
6. Calm empty states

## Design note
Visual language should feel like a modern treasury ledger influenced by Ancient Rus aesthetics, Gzhel, Khokhloma, manuscript ornament, and premium editorial fintech design.
