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
    bot, dp = create_bot_and_dispatcher(db)

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
