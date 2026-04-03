"""Настройки бота маленьких побед."""
import os

# ── Токен Telegram бота ──────────────────────────────────────────
# Получить у @BotFather в Telegram
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")

# ── Ссылка на консультацию (продающий CTA) ───────────────────────
CONSULTANT_LINK = os.getenv("CONSULTANT_LINK", "https://t.me/elena_vasilenko")

# ── Период сводки (в днях) ───────────────────────────────────────
# Как часто отправлять итоговую сводку достижений
SUMMARY_DAYS = int(os.getenv("SUMMARY_DAYS", "3"))

# ── Порог низкой оценки для CTA ─────────────────────────────────
# Если пользователь ставит оценку <= этого числа → показать CTA консультации
LOW_RATING_THRESHOLD = int(os.getenv("LOW_RATING_THRESHOLD", "5"))

# ── Часы отправки сводки ────────────────────────────────────────
# Сводка отправляется если сейчас между этими часами (по времени пользователя)
SUMMARY_HOUR_FROM = int(os.getenv("SUMMARY_HOUR_FROM", "9"))
SUMMARY_HOUR_TO = int(os.getenv("SUMMARY_HOUR_TO", "12"))

# ── Часы напоминаний ────────────────────────────────────────────
REMINDER_HOUR_FROM = int(os.getenv("REMINDER_HOUR_FROM", "10"))
REMINDER_HOUR_TO = int(os.getenv("REMINDER_HOUR_TO", "22"))

# ── Путь к базе данных ───────────────────────────────────────────
DB_PATH = os.getenv("DB_PATH", "/data/achievements.db")

# ── Админ-панель ─────────────────────────────────────────────────
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "elena2026")
ADMIN_PORT = int(os.getenv("PORT", os.getenv("ADMIN_PORT", "8080")))

# ── ID администраторов (через запятую) ───────────────────────────
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "0").split(",") if x.strip() and x != "0"]
