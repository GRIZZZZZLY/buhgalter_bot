"""Tests for undo_handler — Agent v2 undo flow."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_query() -> MagicMock:
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.data = "action:undo"
    return query


def _make_update(query, user_id: int = 555) -> MagicMock:
    update = MagicMock()
    update.callback_query = query
    update.effective_user = MagicMock()
    update.effective_user.id = user_id
    return update


def _make_context(last_action_result=None, last_ts=None) -> MagicMock:
    ctx = MagicMock()
    ctx.user_data = {}
    if last_action_result is not None:
        ctx.user_data["last_action_result"] = last_action_result
    if last_ts is not None:
        ctx.user_data["last_action_ts"] = last_ts
    return ctx


@pytest.mark.asyncio
async def test_undo_within_ttl_succeeds() -> None:
    """undo_handler выполняет undo если TTL не истёк."""
    from app.telegram.runtime import undo_handler
    from app.services.action_service import ActionResult, ActionStatus

    last_result = ActionResult(
        status=ActionStatus.SUCCESS,
        action_type="set_budget",
        message="✅ Бюджет установлен",
        is_reversible=True,
        undo_payload={"action_type": "set_budget", "category": "food", "old_amount": 0.0},
    )
    query = _make_query()
    update = _make_update(query)
    now = 1000000
    ctx = _make_context(last_action_result=last_result, last_ts=now - 10)  # 10 сек назад — в пределах TTL=60

    with patch("app.telegram.handlers.advisor._time_now", return_value=now):
        with patch("app.telegram.handlers.advisor.SessionLocal") as mock_session_cls:
            mock_db = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

            with patch("app.services.action_service.ActionService.undo") as mock_undo:
                mock_undo.return_value = ActionResult(
                    status=ActionStatus.SUCCESS,
                    action_type="set_budget",
                    message="↩ Бюджет «food» удалён",
                )
                await undo_handler(update, ctx)

    query.edit_message_text.assert_called_once()
    call_args = query.edit_message_text.call_args
    text = call_args.args[0] if call_args.args else call_args.kwargs.get("text", "")
    assert "↩" in text
    assert "last_action_result" not in ctx.user_data


@pytest.mark.asyncio
async def test_undo_after_ttl_shows_expired() -> None:
    """undo_handler показывает сообщение об истечении TTL."""
    from app.telegram.runtime import undo_handler
    from app.services.action_service import ActionResult, ActionStatus

    last_result = ActionResult(
        status=ActionStatus.SUCCESS,
        action_type="set_budget",
        message="ok",
        is_reversible=True,
        undo_payload={"action_type": "set_budget"},
    )
    query = _make_query()
    update = _make_update(query)
    ctx = _make_context(last_action_result=last_result, last_ts=0)  # ts=0 = expired

    await undo_handler(update, ctx)

    query.edit_message_text.assert_called_once()
    call_args = query.edit_message_text.call_args
    text = call_args.args[0] if call_args.args else call_args.kwargs.get("text", "")
    assert "истекло" in text.lower() or "60" in text
    assert "last_action_result" not in ctx.user_data


@pytest.mark.asyncio
async def test_undo_no_last_action_shows_nothing_to_undo() -> None:
    """undo_handler без last_action_result показывает соответствующее сообщение."""
    from app.telegram.runtime import undo_handler

    query = _make_query()
    update = _make_update(query)
    ctx = _make_context()  # нет last_action_result

    await undo_handler(update, ctx)

    query.edit_message_text.assert_called_once()
    call_args = query.edit_message_text.call_args
    text = call_args.args[0] if call_args.args else call_args.kwargs.get("text", "")
    assert "нечего" in text.lower() or "отменять" in text.lower()
