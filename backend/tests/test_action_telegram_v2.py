"""B5.3 — Additional Telegram action flow tests."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.apply_action import ApplyAction, ApplyActionType


def _make_query(callback_data: str = "action:undo") -> MagicMock:
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


def _make_context(**user_data) -> MagicMock:
    ctx = MagicMock()
    ctx.user_data = dict(user_data)
    return ctx


@pytest.mark.asyncio
async def test_apply_confirm_success_stores_last_action_result() -> None:
    """apply_confirm_handler сохраняет last_action_result если is_reversible."""
    from app.telegram.runtime import apply_confirm_handler
    from app.services.action_service import ActionResult, ActionStatus

    action = ApplyAction(
        action_type=ApplyActionType.SET_BUDGET,
        label="Бюджет еда 5000",
        payload={"category": "food", "suggested_limit": 5000.0},
        preview_text="...",
        is_reversible=True,
    )
    query = _make_query("apply_confirm:set_budget")
    update = _make_update(query)
    ctx = _make_context(
        pending_action=action,
        pending_action_expires_at=9999999999,
    )

    reversible_result = ActionResult(
        status=ActionStatus.SUCCESS,
        action_type="set_budget",
        message="✅ Бюджет установлен",
        is_reversible=True,
        undo_payload={"action_type": "set_budget", "category": "food", "old_amount": 0.0},
    )

    with patch("app.telegram.handlers.advisor.SessionLocal") as mock_session_cls:
        mock_db = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        with patch("app.services.action_service.ActionService.execute", return_value=reversible_result):
            await apply_confirm_handler(update, ctx)

    assert "last_action_result" in ctx.user_data
    assert "last_action_ts" in ctx.user_data
    assert "pending_action" not in ctx.user_data


@pytest.mark.asyncio
async def test_apply_confirm_failure_does_not_store_last_action() -> None:
    """apply_confirm_handler НЕ сохраняет last_action_result при failure."""
    from app.telegram.runtime import apply_confirm_handler
    from app.services.action_service import ActionResult, ActionStatus

    action = ApplyAction(
        action_type=ApplyActionType.SET_TOTAL_BUDGET,
        label="test",
        payload={"amount": 50000.0},
        preview_text="...",
        is_reversible=True,
    )
    query = _make_query("apply_confirm:set_total_budget")
    update = _make_update(query)
    ctx = _make_context(
        pending_action=action,
        pending_action_expires_at=9999999999,
    )

    failure_result = ActionResult(
        status=ActionStatus.FAILURE,
        action_type="set_total_budget",
        message="Не поддерживается.",
    )

    with patch("app.telegram.handlers.advisor.SessionLocal") as mock_session_cls:
        mock_db = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        with patch("app.services.action_service.ActionService.execute", return_value=failure_result):
            await apply_confirm_handler(update, ctx)

    assert "last_action_result" not in ctx.user_data


@pytest.mark.asyncio
async def test_second_undo_not_possible() -> None:
    """После первого undo повторный undo невозможен."""
    from app.telegram.runtime import undo_handler
    from app.services.action_service import ActionResult, ActionStatus

    last_result = ActionResult(
        status=ActionStatus.SUCCESS,
        action_type="set_budget",
        message="ok",
        is_reversible=True,
        undo_payload={"action_type": "set_budget", "category": "food", "old_amount": 0.0},
    )
    now = 1000000
    ctx = _make_context(last_action_result=last_result, last_action_ts=now - 5)

    with patch("app.telegram.handlers.advisor._time_now", return_value=now):
        with patch("app.telegram.handlers.advisor.SessionLocal") as mock_session_cls:
            mock_db = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            with patch("app.services.action_service.ActionService.undo") as mock_undo:
                mock_undo.return_value = ActionResult(
                    status=ActionStatus.SUCCESS,
                    action_type="set_budget",
                    message="↩ Отменено",
                )
                await undo_handler(_make_update(_make_query()), ctx)

    assert "last_action_result" not in ctx.user_data

    # Второй undo — должен показать "нечего отменять"
    query2 = _make_query()
    ctx2 = _make_context()
    await undo_handler(_make_update(query2), ctx2)

    call_args = query2.edit_message_text.call_args
    text = call_args.args[0] if call_args.args else call_args.kwargs.get("text", "")
    assert "нечего" in text.lower() or "отменять" in text.lower()
