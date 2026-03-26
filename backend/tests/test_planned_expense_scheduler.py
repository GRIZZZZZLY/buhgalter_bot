from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.repositories.user_repository import UserRepository
from app.services.planned_expense_service import PlannedExpenseService
from app.services.scheduler_service import SchedulerService


class DummyApplication:
    def __init__(self) -> None:
        self.bot = MagicMock()


@patch("app.services.scheduler_service.SessionLocal")
@patch.object(SchedulerService, "_is_time_to_send", return_value=True)
@pytest.mark.asyncio
async def test_scheduler_sends_planned_expense_due_message(_mock_time, mock_session_local, db_session) -> None:
    user = UserRepository(db_session).get_or_create(555, "User")
    db_session.commit()
    PlannedExpenseService(db_session).create_manual(555, "Маникюр", 2100, "beauty", date.today())

    mock_session_local.return_value.__enter__.return_value = db_session
    mock_session_local.return_value.__exit__.return_value = None

    app = DummyApplication()
    scheduler = SchedulerService(app)

    sent = []

    async def fake_send(user_id: int, text: str, **kwargs) -> None:
        sent.append((user_id, text, kwargs))

    scheduler._send_message = fake_send

    await scheduler._check_planned_expense_reminders()

    assert len(sent) == 1
    assert sent[0][0] == 555
    assert "Маникюр" in sent[0][1]
    assert sent[0][2].get("reply_markup") is not None


@patch("app.services.scheduler_service.SessionLocal")
@patch.object(SchedulerService, "_is_time_to_send", return_value=True)
@pytest.mark.asyncio
async def test_scheduler_does_not_send_same_planned_expense_twice(_mock_time, mock_session_local, db_session) -> None:
    user = UserRepository(db_session).get_or_create(555, "User")
    db_session.commit()
    PlannedExpenseService(db_session).create_manual(555, "Маникюр", 2100, "beauty", date.today())

    mock_session_local.return_value.__enter__.return_value = db_session
    mock_session_local.return_value.__exit__.return_value = None

    app = DummyApplication()
    scheduler = SchedulerService(app)
    sent = []

    async def fake_send(user_id: int, text: str, **kwargs) -> None:
        sent.append((user_id, text))

    scheduler._send_message = fake_send

    await scheduler._check_planned_expense_reminders()
    await scheduler._check_planned_expense_reminders()

    assert len(sent) == 1


@patch("app.services.scheduler_service.SessionLocal")
@pytest.mark.asyncio
async def test_scheduler_sends_weekly_planned_digest(mock_session_local, db_session) -> None:
    user = UserRepository(db_session).get_or_create(555, "User")
    user.timezone = "Europe/Moscow"
    db_session.commit()

    PlannedExpenseService(db_session).create_manual(555, "Маникюр", 2100, "beauty", date(2030, 4, 15))
    PlannedExpenseService(db_session).create_manual(555, "Зал", 3000, "health", date(2030, 4, 19))

    mock_session_local.return_value.__enter__.return_value = db_session
    mock_session_local.return_value.__exit__.return_value = None

    app = DummyApplication()
    scheduler = SchedulerService(app)
    sent = []

    async def fake_send(user_id: int, text: str, **kwargs) -> None:
        sent.append((user_id, text))

    scheduler._send_message = fake_send

    class FakeDateTime:
        @classmethod
        def now(cls, tz=None):
            from datetime import datetime
            return datetime(2030, 4, 14, 19, 10, 0, tzinfo=tz)

    with patch("app.services.scheduler_service.datetime", FakeDateTime):
        await scheduler._check_weekly_planned_digest()

    assert len(sent) == 1
    assert "следующую неделю" in sent[0][1]
    assert "Маникюр" in sent[0][1]


@patch("app.services.scheduler_service.SessionLocal")
@pytest.mark.asyncio
async def test_scheduler_does_not_send_weekly_planned_digest_twice(mock_session_local, db_session) -> None:
    user = UserRepository(db_session).get_or_create(555, "User")
    user.timezone = "Europe/Moscow"
    db_session.commit()

    PlannedExpenseService(db_session).create_manual(555, "Маникюр", 2100, "beauty", date(2030, 4, 15))

    mock_session_local.return_value.__enter__.return_value = db_session
    mock_session_local.return_value.__exit__.return_value = None

    app = DummyApplication()
    scheduler = SchedulerService(app)
    sent = []

    async def fake_send(user_id: int, text: str, **kwargs) -> None:
        sent.append((user_id, text))

    scheduler._send_message = fake_send

    class FakeDateTime:
        @classmethod
        def now(cls, tz=None):
            from datetime import datetime
            return datetime(2030, 4, 14, 19, 10, 0, tzinfo=tz)

    with patch("app.services.scheduler_service.datetime", FakeDateTime):
        await scheduler._check_weekly_planned_digest()
        await scheduler._check_weekly_planned_digest()

    assert len(sent) == 1
