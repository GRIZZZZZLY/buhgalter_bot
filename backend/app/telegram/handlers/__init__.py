# Re-export legacy symbols needed by tests and other modules.
from app.telegram.handlers_legacy import (  # noqa: F401
    _pending_store,
    TelegramTextFlow,
    PendingCategoryResolution,
    _store_set,
    _store_get,
    _store_pop,
)
