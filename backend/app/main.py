from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: nothing to do — schema is managed exclusively by Alembic migrations.
    # Run `alembic upgrade head` before starting the server.
    yield
    # Shutdown: nothing to clean up at the moment.


app = FastAPI(title="Telegram Finance Bot", lifespan=lifespan)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
settings = get_settings()

# In production set CORS_ORIGINS in .env, e.g.:
#   CORS_ORIGINS=https://your-domain.com,https://t.me
# In dev (empty) → allow all origins so the Vite dev server works out of the box.
_raw_origins = getattr(settings, "cors_origins", "") or ""
_allowed_origins: list[str] = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
