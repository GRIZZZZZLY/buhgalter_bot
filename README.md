# buhgalter_bot

Telegram-first finance product in a single repo:
- `frontend/` style lives in the root Vite app
- `backend/` contains FastAPI API, Telegram bot runtime, parser, voice flow, tests

## Structure

- `src/` — Telegram WebApp frontend on React + Vite
- `backend/` — FastAPI backend, Telegram bot, Alembic, parser, tests

## Frontend local development

```bash
cd /home/zubr/.openclaw/workspace-coder/buhgalter_bot
npm install
npm run dev
```

Frontend runs on: `http://127.0.0.1:4173`

## Backend local development

```bash
cd /home/zubr/.openclaw/workspace-coder/buhgalter_bot/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Telegram bot runtime

```bash
cd /home/zubr/.openclaw/workspace-coder/buhgalter_bot/backend
source .venv/bin/activate
python run_bot.py
```

## Tests

```bash
cd /home/zubr/.openclaw/workspace-coder/buhgalter_bot/backend
pytest
```

## Notes

- Frontend and backend are now treated as one product and should live in this repo.
- Runtime data like local DB, audio artifacts, logs, and `.env` stay untracked.
