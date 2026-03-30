"""
persistence.py — кастомная SQLAlchemy-backed persistence для PTB.

Реализует BasePersistence поверх таблицы telegram_persistence (key/value JSON).
Работает с SQLite (dev) и PostgreSQL (prod) через тот же DATABASE_URL.
Таблица создаётся автоматически при первом старте бота (create_all).
"""
import json
import logging
from collections import defaultdict
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import Column, MetaData, String, Table, Text, create_engine
from telegram.ext import BasePersistence, PersistenceInput

logger = logging.getLogger("finance_bot.persistence")

_KEY_USER = "user_data"
_KEY_CHAT = "chat_data"
_KEY_BOT = "bot_data"
_KEY_CONV = "conversations"


class SQLAlchemyPersistence(BasePersistence):
    """PTB BasePersistence backed by SQLAlchemy (SQLite / PostgreSQL).

    Данные хранятся в таблице ``telegram_persistence`` как JSON-строки,
    по одной строке на тип данных (user_data, chat_data, bot_data, conversations).
    Все update_* методы пишут сразу в БД; flush() является no-op.
    """

    def __init__(self, url: str) -> None:
        super().__init__(
            store_data=PersistenceInput(
                user_data=True,
                chat_data=True,
                bot_data=True,
                callback_data=False,
            )
        )
        self._engine = create_engine(url, pool_pre_ping=True)
        meta = MetaData()
        self._table = Table(
            "telegram_persistence",
            meta,
            Column("key", String(64), primary_key=True),
            Column("value", Text, nullable=False),
        )
        meta.create_all(self._engine)

        self._user_data: Dict[int, Dict] = {}
        self._chat_data: Dict[int, Dict] = {}
        self._bot_data: Dict = {}
        self._conversations: Dict[str, Dict[Tuple, Any]] = {}
        self._loaded = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._engine.connect() as conn:
            rows = conn.execute(self._table.select()).fetchall()
        raw: Dict[str, Any] = {r.key: json.loads(r.value) for r in rows}

        self._user_data = {int(k): v for k, v in raw.get(_KEY_USER, {}).items()}
        self._chat_data = {int(k): v for k, v in raw.get(_KEY_CHAT, {}).items()}
        self._bot_data = raw.get(_KEY_BOT, {})

        # Conversation keys хранятся как "uid,cid" → восстанавливаем кортежи
        for name, entries in raw.get(_KEY_CONV, {}).items():
            self._conversations[name] = {
                tuple(int(x) for x in k.split(",")): v
                for k, v in entries.items()
            }

        self._loaded = True
        logger.info("persistence: loaded from db (users=%d)", len(self._user_data))

    def _upsert(self, key: str, value: Any) -> None:
        payload = json.dumps(value, ensure_ascii=False)
        with self._engine.begin() as conn:
            exists = conn.execute(
                self._table.select().where(self._table.c.key == key)
            ).fetchone()
            if exists:
                conn.execute(
                    self._table.update()
                    .where(self._table.c.key == key)
                    .values(value=payload)
                )
            else:
                conn.execute(self._table.insert().values(key=key, value=payload))

    # ------------------------------------------------------------------
    # BasePersistence interface — getters
    # ------------------------------------------------------------------

    async def get_user_data(self) -> Dict[int, Dict]:
        self._ensure_loaded()
        return defaultdict(dict, self._user_data)

    async def get_chat_data(self) -> Dict[int, Dict]:
        self._ensure_loaded()
        return defaultdict(dict, self._chat_data)

    async def get_bot_data(self) -> Dict:
        self._ensure_loaded()
        return self._bot_data

    async def get_callback_data(self) -> None:
        return None

    async def get_conversations(self, name: str) -> Dict:
        self._ensure_loaded()
        return dict(self._conversations.get(name, {}))

    # ------------------------------------------------------------------
    # BasePersistence interface — updaters
    # ------------------------------------------------------------------

    async def update_user_data(self, user_id: int, data: Dict) -> None:
        self._user_data[user_id] = data
        self._upsert(_KEY_USER, {str(k): v for k, v in self._user_data.items()})

    async def update_chat_data(self, chat_id: int, data: Dict) -> None:
        self._chat_data[chat_id] = data
        self._upsert(_KEY_CHAT, {str(k): v for k, v in self._chat_data.items()})

    async def update_bot_data(self, data: Dict) -> None:
        self._bot_data = data
        self._upsert(_KEY_BOT, self._bot_data)

    async def update_callback_data(self, data: Any) -> None:
        pass  # callback_data persistence отключена

    async def update_conversation(
        self, name: str, key: Tuple[int, ...], new_state: Optional[Any]
    ) -> None:
        bucket = self._conversations.setdefault(name, {})
        if new_state is None:
            bucket.pop(key, None)
        else:
            bucket[key] = new_state
        serialized = {
            conv_name: {
                ",".join(str(x) for x in k): v for k, v in entries.items()
            }
            for conv_name, entries in self._conversations.items()
        }
        self._upsert(_KEY_CONV, serialized)

    async def drop_chat_data(self, chat_id: int) -> None:
        self._chat_data.pop(chat_id, None)
        self._upsert(_KEY_CHAT, {str(k): v for k, v in self._chat_data.items()})

    async def drop_user_data(self, user_id: int) -> None:
        self._user_data.pop(user_id, None)
        self._upsert(_KEY_USER, {str(k): v for k, v in self._user_data.items()})

    # ------------------------------------------------------------------
    # BasePersistence interface — refresh / flush
    # ------------------------------------------------------------------

    async def refresh_bot_data(self, bot_data: Dict) -> None:
        pass  # in-memory кэш является источником истины

    async def refresh_chat_data(self, chat_id: int, chat_data: Dict) -> None:
        pass

    async def refresh_user_data(self, user_id: int, user_data: Dict) -> None:
        pass

    async def flush(self) -> None:
        # Все записи выполняются немедленно в update_* — flush является no-op
        logger.debug("persistence: flush (no-op)")
