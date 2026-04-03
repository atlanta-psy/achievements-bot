"""
Веб-админ-панель для просмотра статистики бота.
Доступна по адресу: http://your-railway-url/admin
Пароль задаётся в переменной окружения ADMIN_SECRET (по умолчанию elena2026)
"""

import time
from datetime import datetime

from aiohttp import web

from config import ADMIN_SECRET, ADMIN_PORT
from storage import Storage

HTML_STYLE = """
<style>
  body { font-family: Arial, sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; color: #333; }
  h1 { color: #6a5acd; }
  h2 { color: #888; font-size: 1rem; margin-top: 2rem; }
  .stats { display: flex; gap: 20px; flex-wrap: wrap; margin-bottom: 2rem; }
  .card { background: #f5f3ff; border-radius: 12px; padding: 20px; min-width: 140px; text-align: center; }
  .card .num { font-size: 2rem; font-weight: bold; color: #6a5acd; }
  .card .label { font-size: 0.85rem; color: #888; margin-top: 4px; }
  table { border-collapse: collapse; width: 100%; margin-bottom: 2rem; }
  th { background: #6a5acd; color: white; padding: 10px; text-align: left; font-weight: normal; }
  td { padding: 8px 10px; border-bottom: 1px solid #eee; font-size: 0.9rem; }
  tr:hover td { background: #f9f7ff; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 20px; font-size: 0.78rem; }
  .active { background: #d4edda; color: #155724; }
  .paused { background: #fff3cd; color: #856404; }
  .setup { background: #cce5ff; color: #004085; }
  .logout { float: right; color: #888; font-size: 0.85rem; text-decoration: none; }
  .logout:hover { color: #333; }
</style>
"""

LOGIN_PAGE = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="UTF-8"><title>Вход — Бот Достижений</title>
{style}
</head><body>
<h1>🌟 Бот Маленьких Побед</h1>
<h2>Вход в панель управления</h2>
<form method="POST" action="/admin/login">
  <input type="password" name="password" placeholder="Пароль" style="padding:10px;font-size:1rem;border:1px solid #ccc;border-radius:8px;margin-right:10px">
  <button type="submit" style="padding:10px 20px;background:#6a5acd;color:white;border:none;border-radius:8px;cursor:pointer;font-size:1rem">Войти</button>
</form>
{error}
</body></html>"""


def _fmt_time(ts: float) -> str:
    if not ts:
        return "—"
    return datetime.fromtimestamp(ts).strftime("%d.%m %H:%M")


def _state_badge(state: str, is_active: int) -> str:
    if state in ("setup_goal", "setup_timezone", "setup_interval"):
        return '<span class="badge setup">настройка</span>'
    if not is_active:
        return '<span class="badge paused">пауза</span>'
    if state == "waiting_rating":
        return '<span class="badge active">⭐ ждёт оценки</span>'
    return '<span class="badge active">активен</span>'


def build_dashboard(db: Storage) -> str:
    users = db.get_all_users()
    total = db.count_users()
    active = db.count_active_users()
    achievements = db.count_achievements()
    ratings = db.count_ratings()
    avg_r = db.avg_rating()
    recent = db.get_recent_all_achievements(limit=15)

    rows = []
    for u in users:
        name = u["first_name"] or "—"
        uname = f"@{u['username']}" if u["username"] else "—"
        badge = _state_badge(u["state"], u["is_active"])
        rows.append(f"""<tr>
          <td>{name}</td><td>{uname}</td>
          <td>{badge}</td>
          <td>UTC+{u["utc_offset"]}</td>
          <td>каждые {u["interval_hours"]}ч</td>
          <td>{_fmt_time(u["last_notification_at"])}</td>
          <td>{_fmt_time(u["last_summary_at"])}</td>
          <td>{_fmt_time(u["created_at"])}</td>
        </tr>""")

    ach_rows = []
    for a in recent:
        name = a.get("first_name") or "—"
        text = str(a["text"])[:80]
        ach_rows.append(f"<tr><td>{name}</td><td>{text}</td><td>{_fmt_time(a['created_at'])}</td></tr>")

    return f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="UTF-8"><title>Панель — Бот Достижений</title>
{HTML_STYLE}
</head><body>
<a class="logout" href="/admin/logout">Выйти</a>
<h1>🌟 Бот Маленьких Побед</h1>

<div class="stats">
  <div class="card"><div class="num">{total}</div><div class="label">всего пользователей</div></div>
  <div class="card"><div class="num">{active}</div><div class="label">активных сейчас</div></div>
  <div class="card"><div class="num">{achievements}</div><div class="label">достижений записано</div></div>
  <div class="card"><div class="num">{ratings}</div><div class="label">оценок получено</div></div>
  <div class="card"><div class="num">{avg_r}</div><div class="label">средняя оценка</div></div>
</div>

<h2>ПОЛЬЗОВАТЕЛИ</h2>
<table>
  <tr>
    <th>Имя</th><th>Username</th><th>Статус</th>
    <th>Часовой пояс</th><th>Интервал</th>
    <th>Посл. напомин.</th><th>Посл. сводка</th><th>Регистрация</th>
  </tr>
  {"".join(rows) if rows else "<tr><td colspan='8'>Нет пользователей</td></tr>"}
</table>

<h2>ПОСЛЕДНИЕ ЗАПИСАННЫЕ ДОСТИЖЕНИЯ</h2>
<table>
  <tr><th>Пользователь</th><th>Текст</th><th>Время</th></tr>
  {"".join(ach_rows) if ach_rows else "<tr><td colspan='3'>Нет записей</td></tr>"}
</table>

</body></html>"""


def setup_admin(app: web.Application, db: Storage):
    SESSIONS: set = set()

    async def login_get(request):
        html = LOGIN_PAGE.format(style=HTML_STYLE, error="")
        return web.Response(text=html, content_type="text/html")

    async def login_post(request):
        data = await request.post()
        if data.get("password") == ADMIN_SECRET:
            response = web.HTTPFound("/admin")
            response.set_cookie("auth", ADMIN_SECRET, max_age=86400 * 7, httponly=True)
            raise response
        html = LOGIN_PAGE.format(
            style=HTML_STYLE,
            error='<p style="color:red;margin-top:1rem">Неверный пароль</p>'
        )
        return web.Response(text=html, content_type="text/html", status=401)

    async def dashboard(request):
        if request.cookies.get("auth") != ADMIN_SECRET:
            raise web.HTTPFound("/admin/login")
        html = build_dashboard(db)
        return web.Response(text=html, content_type="text/html")

    async def logout(request):
        response = web.HTTPFound("/admin/login")
        response.del_cookie("auth")
        raise response

    async def health(request):
        return web.Response(text="ok")

    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    app.router.add_get("/admin/login", login_get)
    app.router.add_post("/admin/login", login_post)
    app.router.add_get("/admin", dashboard)
    app.router.add_get("/admin/logout", logout)


async def start_admin(db: Storage):
    app = web.Application()
    setup_admin(app, db)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", ADMIN_PORT)
    await site.start()
    return runner
