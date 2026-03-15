from fastapi import FastAPI

from app.api.router import api_router
from app.db.init_db import init_db

app = FastAPI(title="Telegram Finance Bot MVP")
app.include_router(api_router)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
