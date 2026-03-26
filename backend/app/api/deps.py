import hashlib
import hmac
import json
import logging
from urllib.parse import parse_qsl

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.settings import Settings, get_settings
from app.db.session import get_db

logger = logging.getLogger(__name__)


def _verify_telegram_init_data(init_data: str, bot_token: str) -> dict:
    """Verify Telegram WebApp initData HMAC-SHA256 signature.

    Algorithm: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

    Returns parsed fields dict on success.
    Raises HTTPException 401 on invalid or missing signature.
    """
    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=True))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed initData",
        )

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing hash in initData",
        )

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid initData signature",
        )

    return parsed


def _extract_user_id_from_parsed(parsed: dict) -> int:
    """Extract telegram user id from parsed initData fields."""
    user_raw = parsed.get("user")
    if not user_raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No user field in initData",
        )
    try:
        user_data = json.loads(user_raw)
        return int(user_data["id"])
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Cannot parse user id from initData",
        )


def get_telegram_user_id(
    x_telegram_init_data: str | None = Header(default=None),
    x_telegram_user_id: int | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> int:
    """Dependency: authenticate request and return verified telegram_user_id.

    Production: requires X-Telegram-Init-Data header with valid HMAC-SHA256 signature.
    Dev fallback: if TELEGRAM_BOT_TOKEN is empty, accepts X-Telegram-User-Id directly
                  (allows running tests and local dev without a real bot token).
    """

    # Dev/test mode: no bot token configured → accept plain user id header
    if not settings.telegram_bot_token:
        if x_telegram_user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing X-Telegram-User-Id header (dev mode, no bot token configured)",
            )
        logger.debug("Auth: dev mode, trusting X-Telegram-User-Id=%s", x_telegram_user_id)
        return x_telegram_user_id

    # Production mode: require initData with valid signature
    if x_telegram_init_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Telegram-Init-Data header",
        )

    parsed = _verify_telegram_init_data(x_telegram_init_data, settings.telegram_bot_token)
    user_id = _extract_user_id_from_parsed(parsed)
    logger.debug("Auth: verified initData for user_id=%s", user_id)
    return user_id


DBSession = Session
DBDependency = get_db
