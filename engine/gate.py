import ipaddress
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from auth import check_admin_login, sign_admin, valid_admin_cookie
from settings import PANEL_HOST, PANEL_PATH

NGINX_404 = """<html>
<head><title>404 Not Found</title></head>
<body>
<center><h1>404 Not Found</h1></center>
<hr><center>nginx</center>
</body>
</html>
"""

LOGIN_HTML = """<!doctype html>
<meta charset="utf-8">
<title>Вход</title>
<style>
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#f4efe6;color:#1c1914;font:18px Georgia,serif}}
form{{width:min(360px,92vw);display:grid;gap:10px}}
input{{padding:10px 12px;border:1px solid #e3d9c8;border-radius:10px;font:inherit;background:#fffdf8}}
button{{padding:10px 12px;border:0;border-radius:999px;background:#1d5c3a;color:#f7f3ea;font:inherit}}
p{{margin:0;color:#8e3a2f}}
</style>
<form method="post" action="{action}">
<input name="username" autocomplete="username" placeholder="Логин" required>
<input name="password" type="password" autocomplete="current-password" placeholder="Пароль" required>
<button type="submit">Войти</button>
{error}
</form>
"""

def nginx_404() -> HTMLResponse:
    return HTMLResponse(
        NGINX_404,
        status_code=404,
        headers={"cache-control": "no-store", "server": "nginx"},
    )


def _host_name(request: Request) -> str:
    host = (request.headers.get("host") or "").split(":")[0].strip().lower()
    return host


def _is_ip(host: str) -> bool:
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def _client_host(request: Request) -> str:
    if request.client is None:
        return ""
    return request.client.host or ""


def _local_call(request: Request) -> bool:
    return _client_host(request) in {"127.0.0.1", "::1", "testclient"}


def _engine_path(path: str) -> bool:
    return path in {
        "/v1/decide",
        "/v1/collect",
        "/v1/challenge",
        "/v1/pay",
        "/v1/sync",
        "/v1/ingest",
    } or path.startswith("/v1/challenge/")


def _cookie_ok(request: Request) -> bool:
    return valid_admin_cookie(request.cookies.get("klo_admin", ""))


class GateMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = urlparse(str(request.url)).path or "/"
        if path != "/" and path.endswith("/"):
            path = path[:-1]
        host = _host_name(request)

        if _engine_path(path):
            if not _local_call(request) or request.method not in {"GET", "POST", "HEAD"}:
                return nginx_404()
            if path == "/v1/decide" and request.method != "POST":
                return nginx_404()
            if path == "/v1/collect" and request.method != "POST":
                return nginx_404()
            if path == "/v1/pay" and request.method not in {"GET", "POST"}:
                return nginx_404()
            if path == "/v1/sync" and request.method != "GET":
                return nginx_404()
            if path == "/v1/ingest" and request.method != "POST":
                return nginx_404()
            response = await call_next(request)
            return _quiet(response)

        if _is_ip(host) or host != PANEL_HOST:
            return nginx_404()

        if path == "/static/tracker.js" and request.method == "GET":
            return _quiet(await call_next(request))

        if path.startswith("/static/admin") and request.method == "GET" and _cookie_ok(request):
            return _quiet(await call_next(request))

        if path.startswith("/admin/api") and _cookie_ok(request):
            return _quiet(await call_next(request))

        if path == PANEL_PATH and request.method == "GET":
            if _cookie_ok(request):
                request.state.serve_panel = True
                return _quiet(await call_next(request))
            return HTMLResponse(LOGIN_HTML.format(action=PANEL_PATH + "/login", error=""), status_code=200)

        if path == PANEL_PATH + "/login" and request.method == "POST":
            return await _login(request)

        return nginx_404()


async def _login(request: Request) -> Response:
    form = await request.form()
    username = str(form.get("username") or "")
    password = str(form.get("password") or "")
    if not check_admin_login(username, password):
        page = LOGIN_HTML.format(action=PANEL_PATH + "/login", error="<p>Не подошло.</p>")
        return HTMLResponse(page, status_code=200, headers={"cache-control": "no-store", "server": "nginx"})
    response = RedirectResponse(PANEL_PATH, status_code=303)
    response.set_cookie(
        "klo_admin",
        sign_admin(),
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 12,
        path="/",
    )
    response.headers["server"] = "nginx"
    response.headers["cache-control"] = "no-store"
    return response


def _quiet(response: Response) -> Response:
    if response.status_code in {401, 403, 404, 405}:
        return nginx_404()
    response.headers["server"] = "nginx"
    if "x-powered-by" in response.headers:
        del response.headers["x-powered-by"]
    return response
