"""Точка запуска: бот достижений + планировщик + админ-панель."""

import asyncio
import logging

from bot import create_bot_and_dispatcher
from admin_panel import start_admin
from scheduler import run_scheduler
from storage import Storage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


async def main():
    db = Storage()

    # Получаем username бота (нужен для определения упоминаний в группах)
    from aiogram import Bot as _Bot
    from config import TG_BOT_TOKEN
    _tmp_bot = _Bot(token=TG_BOT_TOKEN)
    bot_info = await _tmp_bot.get_me()
    bot_username = bot_info.username
    await _tmp_bot.session.close()
    log.info("Бот запущен как @%s", bot_username)

    bot, dp = create_bot_and_dispatcher(db, bot_username=bot_username)

    # Запускаем веб-панель администратора
    admin_runner = await start_admin(db)
    log.info("Админ-панель запущена")

    # Запускаем планировщик как фоновую задачу
    scheduler_task = asyncio.create_task(run_scheduler(bot, db))
    log.info("Планировщик напоминаний запущен")

    try:
        log.info("Бот запущен, слушаем обновления...")
        await dp.start_polling(bot, drop_pending_updates=True)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        scheduler_task.cancel()
        await admin_runner.cleanup()
        await bot.session.close()
        log.info("Бот остановлен")


if __name__ == "__main__":
    asyncio.run(main())
