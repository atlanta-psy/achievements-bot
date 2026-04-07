"""
Планировщик задач: напоминания и сводки достижений.
Запускается как фоновая задача вместе с ботом.
"""

import asyncio
import logging
import random
import time
from datetime import datetime, timezone, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

from config import (
    SUMMARY_DAYS, LOW_RATING_THRESHOLD, CONSULTANT_LINK,
    SUMMARY_HOUR_FROM, SUMMARY_HOUR_TO,
    REMINDER_HOUR_FROM, REMINDER_HOUR_TO,
)
from messages import REMINDERS, build_summary, NO_ACHIEVEMENTS_SKIP
from storage import Storage

log = logging.getLogger(__name__)

CHECK_REMINDERS_INTERVAL = 30 * 60   # проверяем напоминания каждые 30 минут
CHECK_SUMMARIES_INTERVAL = 60 * 60   # проверяем сводки каждый час


def _user_hour(utc_offset: int) -> int:
    """Текущий час в часовом поясе пользователя."""
    now_utc = datetime.now(timezone.utc)
    user_time = now_utc + timedelta(hours=utc_offset)
    return user_time.hour


async def _safe_send(bot: Bot, user_id: int, text: str, **kwargs) -> bool:
    """Отправляет сообщение, игнорирует заблокированных пользователей."""
    try:
        await bot.send_message(user_id, text, **kwargs)
        return True
    except TelegramForbiddenError:
        log.info("Пользователь %s заблокировал бота", user_id)
        return False
    except TelegramBadRequest as e:
        log.warning("Ошибка отправки %s: %s", user_id, e)
        return False
    except Exception as e:
        log.error("Неожиданная ошибка при отправке %s: %s", user_id, e)
        return False


async def check_reminders(bot: Bot, db: Storage):
    """Отправляет напоминания пользователям, у которых подошёл интервал."""
    now = time.time()
    users = db.get_all_active_users()

    for user in users:
        if not user["is_active"]:
            continue

        hour = _user_hour(user["utc_offset"])
        if not (REMINDER_HOUR_FROM <= hour < REMINDER_HOUR_TO):
            continue

        interval_seconds = user["interval_hours"] * 3600
        if now - user["last_notification_at"] < interval_seconds:
            continue

        text = random.choice(REMINDERS)
        sent = await _safe_send(bot, user["user_id"], text)
        if sent:
            db.update_user(user["user_id"], last_notification_at=now)
            log.info("Напоминание отправлено → %s", user["user_id"])


async def check_summaries(bot: Bot, db: Storage):
    """Отправляет сводку достижений раз в SUMMARY_DAYS дней."""
    now = time.time()
    summary_period = 60  # ТЕСТ: 1 минута (вернуть: SUMMARY_DAYS * 86400)

    users = db.get_all_active_users()
    for user in users:
        # Только для пользователей в состоянии 'active'
        if user["state"] != "active":
            continue

        # Проверяем, что прошло нужное количество дней
        last_summary = user["last_summary_at"]
        if now - last_summary < summary_period:
            continue

        # ТЕСТ: окно отключено (вернуть: раскомментировать 2 строки ниже)
        # hour = _user_hour(user["utc_offset"])
        # if not (SUMMARY_HOUR_FROM <= hour < SUMMARY_HOUR_TO): continue

        # Период для достижений
        period_start = last_summary if last_summary > 0 else user["created_at"]
        achievements = db.get_achievements(user["user_id"], since=period_start)

        if not achievements:
            # Нет достижений — пропускаем, но обновляем таймер
            days_text = str(SUMMARY_DAYS)
            await _safe_send(
                bot, user["user_id"],
                NO_ACHIEVEMENTS_SKIP.format(days=days_text)
            )
            db.update_user(user["user_id"], last_summary_at=now)
            # Сохраняем период для оценки позже
            db.update_user(
                user["user_id"],
                last_summary_at=now,
            )
            continue

        # Строим текст сводки
        text = build_summary(
            goal=user["goal"] or "не указана",
            achievements=achievements,
            days=SUMMARY_DAYS,
        )

        sent = await _safe_send(bot, user["user_id"], text, parse_mode="MarkdownV2")
        if sent:
            # Переводим в состояние ожидания оценки
            db.update_user(
                user["user_id"],
                state="waiting_rating",
                last_summary_at=now,
            )
            # Сохраняем в extra информацию о периоде (для записи оценки)
            # Используем отдельное поле через update_user
            # period_start будет вычислен из last_summary_at при получении оценки
            log.info("Сводка отправлена → %s (%d достижений)", user["user_id"], len(achievements))


async def run_scheduler(bot: Bot, db: Storage):
    """Главный цикл планировщика. Запускается как asyncio задача."""
    log.info("Планировщик запущен")
    last_reminder_check = 0.0
    last_summary_check = 0.0

    while True:
        try:
            now = time.time()
            if now - last_reminder_check >= CHECK_REMINDERS_INTERVAL:
                await check_reminders(bot, db)
                last_reminder_check = now

            if now - last_summary_check >= CHECK_SUMMARIES_INTERVAL:
                await check_summaries(bot, db)
                last_summary_check = now

        except Exception as e:
            log.error("Ошибка в планировщике: %s", e, exc_info=True)

        await asyncio.sleep(60)  # проверяем каждую минуту
