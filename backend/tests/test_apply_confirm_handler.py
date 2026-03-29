"""Tests for apply_confirm_handler — Agent v2 real execution."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.apply_action import ApplyAction, ApplyActionType


def _make_query(callback_data: str = "apply_confirm:set_budget") -> MagicMock:
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.data = callback_data
    return query


def _make_update(query, user_id: int = 555) -> MagicMock:
    update = MagicMock()
    update.callback_query = query
    update.effective_user = MagicMock()
    update.effective_user.id = user_id
    return update


def _make_context(pending_action=None) -> MagicMock:
    ctx = MagicMock()
    ctx.user_data = {}
    if pending_action:
        ctx.user_data["pending_action"] = pending_action
        ctx.user_data["pending_action_expires_at"] = 9999999999
    return ctx


@pytest.mark.asyncio
async def test_apply_confirm_executes_set_budget() -> None:
    """Unit test: apply_confirm_handler correctly wires to ActionService and shows result.message."""
    from app.telegram.runtime import apply_confirm_handler
    from app.services.action_service import ActionResult

    action = ApplyAction(
        action_type=ApplyActionType.SET_BUDGET,
        label="Бюджет еда 5000",
        payload={"category": "food", "suggested_limit": 5000.0},
        preview_text="Бюджет «еда»: 5000 ₽/мес",
        is_reversible=True,
    )
    query = _make_query("apply_confirm:set_budget")
    update = _make_update(query)
    ctx = _make_context(pending_action=action)

    with patch("app.telegram.runtime.SessionLocal") as mock_session_cls:
        mock_db = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

        with patch("app.services.action_service.ActionService.execute") as mock_execute:
            from app.services.action_service import ActionStatus
            mock_execute.return_value = ActionResult(status=ActionStatus.SUCCESS, action_type="set_budget", message="✅ Бюджет «food» установлен: 5000 ₽/мес")
            await apply_confirm_handler(update, ctx)

    query.edit_message_text.assert_called_once()
    call_args = query.edit_message_text.call_args
    text = call_args.args[0] if call_args.args else call_args.kwargs.get("text", "")
    assert "✅" in text
    assert "pending_action" not in ctx.user_data


@pytest.mark.asyncio
async def test_apply_confirm_no_pending_action_shows_expired_message() -> None:
    """apply_confirm_handler без pending_action показывает 'Действие устарело.'"""
    from app.telegram.runtime import apply_confirm_handler

    query = _make_query()
    update = _make_update(query)
    ctx = _make_context()  # нет pending_action

    await apply_confirm_handler(update, ctx)

    query.edit_message_text.assert_called_once()
    call_args = query.edit_message_text.call_args
    text = call_args.args[0] if call_args.args else call_args.kwargs.get("text", "")
    assert "устарело" in text.lower()


@pytest.mark.asyncio
async def test_apply_confirm_failure_result_shown_to_user() -> None:
    """При success=False сообщение об ошибке показывается пользователю."""
    from app.telegram.runtime import apply_confirm_handler
    from app.services.action_service import ActionResult

    action = ApplyAction(
        action_type=ApplyActionType.SET_TOTAL_BUDGET,
        label="Общий бюджет",
        payload={"amount": 50000.0},
        preview_text="...",
        is_reversible=True,
    )
    query = _make_query("apply_confirm:set_total_budget")
    update = _make_update(query)
    ctx = _make_context(pending_action=action)

    with patch("app.telegram.runtime.SessionLocal") as mock_session_cls:
        mock_db = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

        with patch("app.services.action_service.ActionService.execute") as mock_execute:
            from app.services.action_service import ActionStatus
            mock_execute.return_value = ActionResult(status=ActionStatus.FAILURE, action_type="set_total_budget", message="Установка общего бюджета пока не поддерживается.")
            await apply_confirm_handler(update, ctx)

    query.edit_message_text.assert_called_once()
    call_args = query.edit_message_text.call_args
    text = call_args.args[0] if call_args.args else call_args.kwargs.get("text", "")
    assert "поддерживается" in text
    assert "pending_action" not in ctx.user_data
