"""
Бот маленьких побед — обработчики команд и сообщений.
"""

import logging
import random
import time
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardRemove, Voice, VideoNote, FSInputFile,
)
from aiogram.enums import ParseMode

from config import TG_BOT_TOKEN, CONSULTANT_LINK, LOW_RATING_THRESHOLD, SUMMARY_DAYS
from messages import (
    WELCOME, GOAL_SAVED, TIMEZONE_SAVED, SETUP_COMPLETE, ALREADY_SETUP,
    REMINDERS, ACHIEVEMENT_SAVED, PAUSED, RESUMED, NOT_PAUSED, ALREADY_PAUSED,
    HELP, GOAL_CHANGE_PROMPT, GOAL_CHANGED, NO_ACHIEVEMENTS, NOT_REGISTERED,
    ASK_RATING_AGAIN, build_summary, rating_response_low, rating_response_high,
    GROUP_NOT_REGISTERED, GROUP_EMPTY_MENTION, GROUP_ACHIEVEMENT_SAVED,
)
from storage import Storage

log = logging.getLogger(__name__)


# ── Клавиатуры ───────────────────────────────────────────────────

def tz_keyboard() -> InlineKeyboardMarkup:
    """Выбор часового пояса — самые популярные для русскоязычной аудитории."""
    buttons = [
        [
            InlineKeyboardButton(text="UTC+2 Калининград", callback_data="tz:2"),
            InlineKeyboardButton(text="UTC+3 Москва", callback_data="tz:3"),
        ],
        [
            InlineKeyboardButton(text="UTC+4 Самара, Баку", callback_data="tz:4"),
            InlineKeyboardButton(text="UTC+5 Екатеринбург", callback_data="tz:5"),
        ],
        [
            InlineKeyboardButton(text="UTC+6 Омск", callback_data="tz:6"),
            InlineKeyboardButton(text="UTC+7 Новосибирск", callback_data="tz:7"),
        ],
        [
            InlineKeyboardButton(text="UTC+8 Иркутск", callback_data="tz:8"),
            InlineKeyboardButton(text="UTC+9 Якутск", callback_data="tz:9"),
        ],
        [
            InlineKeyboardButton(text="UTC+10 Владивосток", callback_data="tz:10"),
            InlineKeyboardButton(text="UTC+11 Магадан", callback_data="tz:11"),
        ],
        [
            InlineKeyboardButton(text="UTC+12 Камчатка", callback_data="tz:12"),
            InlineKeyboardButton(text="UTC+1 Европа Запад", callback_data="tz:1"),
        ],
        [
            InlineKeyboardButton(text="UTC+0 Лондон", callback_data="tz:0"),
            InlineKeyboardButton(text="UTC-5 Нью-Йорк", callback_data="tz:-5"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def interval_keyboard() -> InlineKeyboardMarkup:
    buttons = [[
        InlineKeyboardButton(text="Каждые 2 часа", callback_data="interval:2"),
        InlineKeyboardButton(text="Каждые 3 часа", callback_data="interval:3"),
    ]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ── Регистрация хендлеров ────────────────────────────────────────

def _extract_group_text(message: Message, bot_username: str) -> str | None:
    """Возвращает текст без упоминания бота, или None если бот не упомянут."""
    if not message.entities or not message.text:
        return None

    text = message.text
    removals = []
    for entity in message.entities:
        if entity.type == "mention":
            mention = text[entity.offset: entity.offset + entity.length]
            if mention.lstrip("@").lower() == bot_username.lower():
                removals.append((entity.offset, entity.offset + entity.length))

    if not removals:
        return None

    # Вырезаем упоминания справа налево, чтобы не сдвигать смещения
    for start, end in sorted(removals, reverse=True):
        text = text[:start] + text[end:]

    return text.strip()


def setup_handlers(dp: Dispatcher, db: Storage, bot_username: str = ""):

    # /start
    @dp.message(CommandStart())
    async def cmd_start(message: Message):
        user_id = message.from_user.id
        user = db.get_user(user_id)

        if user and user["state"] not in ("setup_goal", "setup_timezone", "setup_interval"):
            await message.answer(ALREADY_SETUP)
            return

        db.create_user(
            user_id,
            username=message.from_user.username or "",
            first_name=message.from_user.first_name or "",
        )
        db.update_user(user_id, state="setup_goal")

        photo = FSInputFile("media/intro.png")
        await message.answer_photo(photo=photo)
        await message.answer(WELCOME)

    # /help
    @dp.message(Command("help"))
    async def cmd_help(message: Message):
        user = db.get_user(message.from_user.id)
        if not user:
            await message.answer(NOT_REGISTERED)
            return
        await message.answer(HELP, parse_mode=ParseMode.MARKDOWN_V2)

    # /pause
    @dp.message(Command("pause"))
    async def cmd_pause(message: Message):
        user = db.get_user(message.from_user.id)
        if not user:
            await message.answer(NOT_REGISTERED)
            return
        if not user["is_active"]:
            await message.answer(ALREADY_PAUSED)
            return
        db.update_user(message.from_user.id, is_active=0)
        await message.answer(PAUSED)

    # /resume
    @dp.message(Command("resume"))
    async def cmd_resume(message: Message):
        user = db.get_user(message.from_user.id)
        if not user:
            await message.answer(NOT_REGISTERED)
            return
        if user["is_active"]:
            await message.answer(NOT_PAUSED)
            return
        db.update_user(message.from_user.id, is_active=1)
        await message.answer(RESUMED)

    # /achievements
    @dp.message(Command("achievements"))
    async def cmd_achievements(message: Message):
        user = db.get_user(message.from_user.id)
        if not user:
            await message.answer(NOT_REGISTERED)
            return
        items = db.get_recent_achievements(message.from_user.id, days=7)
        if not items:
            await message.answer(NO_ACHIEVEMENTS)
            return

        lines = ["📋 *Твои записи за последние 7 дней:*\n"]
        for i, a in enumerate(items, 1):
            dt = datetime.fromtimestamp(a["created_at"]).strftime("%d\\.%m")
            text = a["text"].replace(".", "\\.").replace("!", "\\!").replace("-", "\\-").replace("(", "\\(").replace(")", "\\)").replace("_", "\\_")
            lines.append(f"{i}\\. {text} _\\({dt}\\)_")

        await message.answer("\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2)

    # /goal
    @dp.message(Command("goal"))
    async def cmd_goal(message: Message):
        user = db.get_user(message.from_user.id)
        if not user:
            await message.answer(NOT_REGISTERED)
            return
        db.update_user(message.from_user.id, state="change_goal")
        await message.answer(GOAL_CHANGE_PROMPT)

    # Callback: выбор часового пояса
    @dp.callback_query(F.data.startswith("tz:"))
    async def cb_timezone(callback: CallbackQuery):
        user_id = callback.from_user.id
        user = db.get_user(user_id)
        if not user:
            await callback.answer()
            return

        offset = int(callback.data.split(":")[1])
        db.update_user(user_id, utc_offset=offset, state="setup_interval")
        await callback.message.edit_text(TIMEZONE_SAVED)
        await callback.message.answer(
            "Выбери, как часто ты хочешь получать напоминания 👇",
            reply_markup=interval_keyboard()
        )
        await callback.answer()

    # Callback: выбор интервала
    @dp.callback_query(F.data.startswith("interval:"))
    async def cb_interval(callback: CallbackQuery):
        user_id = callback.from_user.id
        user = db.get_user(user_id)
        if not user:
            await callback.answer()
            return

        interval = int(callback.data.split(":")[1])
        db.update_user(user_id, interval_hours=interval, state="active")
        await callback.message.edit_text(
            SETUP_COMPLETE.format(interval=interval)
        )
        await callback.answer()

    # ── Групповой чат: тег бота ───────────────────────────────────
    @dp.message(F.chat.type.in_({"group", "supergroup"}), F.text)
    async def handle_group_text(message: Message):
        achievement_text = _extract_group_text(message, bot_username)
        if achievement_text is None:
            return  # Бот не упомянут — игнорируем

        user_id = message.from_user.id
        name = message.from_user.first_name or "друг"
        user = db.get_user(user_id)

        # Не зарегистрирован или ещё в процессе настройки
        if not user or user["state"] in ("setup_goal", "setup_timezone", "setup_interval"):
            await message.reply(
                GROUP_NOT_REGISTERED.format(name=name, bot_username=bot_username)
            )
            return

        # Упомянул бота но ничего не написал
        if not achievement_text:
            await message.reply(GROUP_EMPTY_MENTION.format(name=name))
            return

        db.save_achievement(user_id, achievement_text)
        response = random.choice(GROUP_ACHIEVEMENT_SAVED).format(name=name)
        await message.reply(response)

    # ── Вспомогательная функция: сохранить любое достижение ──────
    async def _save_any_achievement(message: Message, achievement_text: str):
        """Единая логика сохранения достижения для текста, голоса и видео."""
        user_id = message.from_user.id
        user = db.get_user(user_id)
        if not user:
            await message.answer(NOT_REGISTERED)
            return

        state = user["state"]

        # В состоянии ожидания оценки — просим цифру
        if state == "waiting_rating":
            await message.answer(
                "Сейчас мне нужна цифра от 1 до 10 для оценки 🙂\n"
                "После этого снова сможешь записывать шаги!"
            )
            return

        # В состоянии настройки — не принимаем
        if state in ("setup_goal", "setup_timezone", "setup_interval"):
            await message.answer("Давай сначала закончим настройку 😊")
            return

        # В состоянии смены цели — голос/видео не подходит
        if state == "change_goal":
            await message.answer("Для смены цели напиши её текстом 🎯")
            return

        # Обычное состояние active
        if state == "active":
            if not user["is_active"]:
                await message.answer(
                    "Напоминания на паузе. Отправь /resume чтобы возобновить.\n\n"
                    "Но я всё равно сохранила твой шаг! 🌟"
                )
            db.save_achievement(user_id, achievement_text)
            response = random.choice(ACHIEVEMENT_SAVED)
            await message.answer(response)
            return

        await message.answer(NOT_REGISTERED)

    # Голосовые сообщения
    @dp.message(F.voice)
    async def handle_voice(message: Message):
        duration = message.voice.duration
        mins = duration // 60
        secs = duration % 60
        if mins > 0:
            dur_str = f"{mins} мин {secs} сек"
        else:
            dur_str = f"{secs} сек"
        achievement_text = f"🎤 Голосовое сообщение ({dur_str})"
        await _save_any_achievement(message, achievement_text)

    # Видеокружочки
    @dp.message(F.video_note)
    async def handle_video_note(message: Message):
        duration = message.video_note.duration
        dur_str = f"{duration} сек"
        achievement_text = f"🎥 Видеосообщение ({dur_str})"
        await _save_any_achievement(message, achievement_text)

    # Все текстовые сообщения
    @dp.message(F.text)
    async def handle_text(message: Message):
        user_id = message.from_user.id
        text = message.text.strip()

        user = db.get_user(user_id)
        if not user:
            await message.answer(NOT_REGISTERED)
            return

        state = user["state"]

        # ── Онбординг: ввод цели ──────────────────────────────
        if state == "setup_goal":
            db.update_user(user_id, goal=text, state="setup_timezone")
            await message.answer(GOAL_SAVED, reply_markup=tz_keyboard())
            return

        # ── Онбординг: ждём выбор часового пояса (текст не принимаем) ──
        if state == "setup_timezone":
            await message.answer(
                "Пожалуйста, выбери часовой пояс из кнопок выше 👆",
                reply_markup=tz_keyboard()
            )
            return

        # ── Онбординг: ждём выбор интервала ──────────────────
        if state == "setup_interval":
            await message.answer(
                "Пожалуйста, выбери интервал из кнопок выше 👆",
                reply_markup=interval_keyboard()
            )
            return

        # ── Изменение цели ────────────────────────────────────
        if state == "change_goal":
            db.update_user(user_id, goal=text, state="active")
            await message.answer(GOAL_CHANGED)
            return

        # ── Ожидание оценки (после сводки) ───────────────────
        if state == "waiting_rating":
            try:
                rating = int(text)
                if not (1 <= rating <= 10):
                    raise ValueError
            except ValueError:
                await message.answer(ASK_RATING_AGAIN)
                return

            # Находим достижения за период сводки
            period_start = user["last_summary_at"] - SUMMARY_DAYS * 86400
            achievements = db.get_achievements(user_id, since=period_start)
            count = len(achievements)

            db.save_rating(
                user_id=user_id,
                rating=rating,
                period_start=period_start,
                period_end=user["last_summary_at"],
                achievements_count=count,
            )
            db.update_user(user_id, state="active")

            if rating <= LOW_RATING_THRESHOLD:
                link = CONSULTANT_LINK.replace(".", "\\.").replace("-", "\\-")
                response = rating_response_low(count, CONSULTANT_LINK)
            else:
                response = rating_response_high(rating)

            await message.answer(response, parse_mode=ParseMode.MARKDOWN_V2)
            return

        # ── Обычное состояние active: сохраняем достижение ────
        await _save_any_achievement(message, text)


def create_bot_and_dispatcher(db: Storage, bot_username: str = ""):
    bot = Bot(token=TG_BOT_TOKEN)
    dp = Dispatcher()
    setup_handlers(dp, db, bot_username)
    return bot, dp
