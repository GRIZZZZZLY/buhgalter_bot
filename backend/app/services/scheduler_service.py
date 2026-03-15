"""APScheduler-based scheduler that sends morning briefings and evening check-ins."""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from telegram.ext import Application

from app.db.session import SessionLocal
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.reminder_service import ReminderService, CATEGORY_EMOJI
from app.telegram.formatter import TreasuryFormatter
from app.telegram.keyboards import evening_checkin_keyboard

logger = logging.getLogger("finance_bot.scheduler")
formatter = TreasuryFormatter()


class SchedulerService:
    """Manages periodic reminder jobs using APScheduler."""

    def __init__(self, application: Application) -> None:
        self.application = application
        self.scheduler = AsyncIOScheduler()

    def start(self) -> None:
        """Start the scheduler with periodic check jobs."""
        # Check every minute which users need reminders
        self.scheduler.add_job(
            self._check_morning_reminders,
            trigger=IntervalTrigger(minutes=1),
            id="morning_check",
            replace_existing=True,
            max_instances=1,
        )
        self.scheduler.add_job(
            self._check_evening_reminders,
            trigger=IntervalTrigger(minutes=1),
            id="evening_check",
            replace_existing=True,
            max_instances=1,
        )
        self.scheduler.add_job(
            self._check_streak_resets,
            trigger=IntervalTrigger(minutes=60),
            id="streak_check",
            replace_existing=True,
            max_instances=1,
        )
        self.scheduler.add_job(
            self._check_weekly_digest,
            trigger=IntervalTrigger(minutes=30),
            id="weekly_digest_check",
            replace_existing=True,
            max_instances=1,
        )
        self.scheduler.add_job(
            self._check_first_week_summary,
            trigger=IntervalTrigger(hours=6),
            id="first_week_check",
            replace_existing=True,
            max_instances=1,
        )
        self.scheduler.start()
        logger.info("scheduler started with morning/evening/streak/digest/first-week jobs")

    def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("scheduler stopped")

    # ------------------------------------------------------------------
    # Morning reminders
    # ------------------------------------------------------------------
    async def _check_morning_reminders(self) -> None:
        """Check all users and send morning briefings to those whose local time matches."""
        try:
            with SessionLocal() as db:
                user_repo = UserRepository(db)
                users = user_repo.get_all_with_morning_reminder()

                for user in users:
                    if self._is_time_to_send(user, user.reminder_morning):
                        reminder_service = ReminderService(db)
                        message = reminder_service.build_morning_briefing(user)
                        if message:
                            await self._send_message(user.telegram_user_id, message)
                            logger.info("morning briefing sent: user=%s", user.telegram_user_id)

                db.commit()
        except Exception:
            logger.exception("morning reminder check failed")

    # ------------------------------------------------------------------
    # Evening reminders
    # ------------------------------------------------------------------
    async def _check_evening_reminders(self) -> None:
        """Check all users and send evening check-ins to those whose local time matches."""
        try:
            with SessionLocal() as db:
                user_repo = UserRepository(db)
                users = user_repo.get_all_with_evening_reminder()

                for user in users:
                    if self._is_time_to_send(user, user.reminder_evening):
                        reminder_service = ReminderService(db)
                        message, top_categories = reminder_service.build_evening_checkin(user)
                        if message:
                            keyboard = evening_checkin_keyboard(top_categories)
                            await self._send_message(
                                user.telegram_user_id, message, reply_markup=keyboard
                            )
                            user_repo.increment_ignored_evening_reminders(user)
                            logger.info("evening checkin sent: user=%s", user.telegram_user_id)

                db.commit()
        except Exception:
            logger.exception("evening reminder check failed")

    # ------------------------------------------------------------------
    # Streak resets
    # ------------------------------------------------------------------
    async def _check_streak_resets(self) -> None:
        """Check for users who lost their streak and notify them."""
        try:
            with SessionLocal() as db:
                user_repo = UserRepository(db)
                reminder_service = ReminderService(db)

                # Get all users with active streaks
                from sqlalchemy import select
                from app.models.user import User as UserModel
                stmt = select(UserModel).where(UserModel.streak_days > 0, UserModel.streak_last_date.isnot(None))
                users = list(db.scalars(stmt).all())

                for user in users:
                    try:
                        tz = ZoneInfo(user.timezone)
                    except Exception:
                        tz = ZoneInfo("Europe/Moscow")

                    now_local = datetime.now(tz)
                    today_str = now_local.date().isoformat()

                    if user.streak_last_date and user.streak_last_date < (now_local.date() - timedelta(days=1)).isoformat():
                        # Streak is broken — user missed yesterday
                        previous_streak = user.streak_days
                        user.streak_days = 0
                        db.flush()

                        message = reminder_service.build_streak_loss_message(user, previous_streak)
                        if message:
                            await self._send_message(user.telegram_user_id, message)
                            logger.info(
                                "streak loss notification: user=%s previous=%d",
                                user.telegram_user_id, previous_streak,
                            )

                db.commit()
        except Exception:
            logger.exception("streak reset check failed")

    # ------------------------------------------------------------------
    # Weekly digest (Sunday evening)
    # ------------------------------------------------------------------
    async def _check_weekly_digest(self) -> None:
        """Send weekly digest to users on Sunday evening."""
        try:
            with SessionLocal() as db:
                from sqlalchemy import select
                from app.models.user import User as UserModel
                stmt = select(UserModel)
                users = list(db.scalars(stmt).all())

                for user in users:
                    try:
                        tz = ZoneInfo(user.timezone)
                    except Exception:
                        tz = ZoneInfo("Europe/Moscow")

                    now_local = datetime.now(tz)
                    # Only send on Sunday between 19:00-19:29
                    if now_local.weekday() != 6 or now_local.hour != 19 or now_local.minute >= 30:
                        continue

                    from app.services.analytics_service import AnalyticsService
                    analytics = AnalyticsService(db)
                    digest = analytics.build_weekly_digest(user)
                    if digest:
                        await self._send_message(user.telegram_user_id, digest)
                        logger.info("weekly digest sent: user=%s", user.telegram_user_id)

        except Exception:
            logger.exception("weekly digest check failed")

    # ------------------------------------------------------------------
    # First week summary ("aha moment")
    # ------------------------------------------------------------------
    async def _check_first_week_summary(self) -> None:
        """Send first-week summary to users who have been active for ~7 days."""
        try:
            with SessionLocal() as db:
                from sqlalchemy import select
                from app.models.user import User as UserModel
                # Find users created 7-8 days ago who haven't received this yet
                now = datetime.now(timezone.utc)
                seven_days_ago = now - timedelta(days=8)
                six_days_ago = now - timedelta(days=6)

                stmt = select(UserModel).where(
                    UserModel.created_at >= seven_days_ago,
                    UserModel.created_at <= six_days_ago,
                )
                users = list(db.scalars(stmt).all())

                for user in users:
                    from app.services.analytics_service import AnalyticsService
                    analytics = AnalyticsService(db)
                    summary = analytics.build_first_week_summary(user)
                    if summary:
                        await self._send_message(user.telegram_user_id, summary)
                        logger.info("first week summary sent: user=%s", user.telegram_user_id)

        except Exception:
            logger.exception("first week summary check failed")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _is_time_to_send(self, user: User, reminder_time_str: str | None) -> bool:
        """Check if the current minute matches the user's configured reminder time."""
        if not reminder_time_str:
            return False

        try:
            tz = ZoneInfo(user.timezone)
        except Exception:
            tz = ZoneInfo("Europe/Moscow")

        now_local = datetime.now(tz)
        try:
            hour, minute = map(int, reminder_time_str.split(":"))
            target = time(hour, minute)
        except (ValueError, AttributeError):
            return False

        # Match current hour:minute (1-minute window)
        return now_local.hour == target.hour and now_local.minute == target.minute

    async def _send_message(self, telegram_user_id: int, text: str, **kwargs) -> None:
        """Send a message via the bot application."""
        try:
            await self.application.bot.send_message(
                chat_id=telegram_user_id,
                text=text,
                **kwargs,
            )
        except Exception:
            logger.exception("failed to send message to user=%s", telegram_user_id)
