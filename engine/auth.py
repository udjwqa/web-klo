import hashlib
import hmac
import time
from typing import Optional

from fastapi import Cookie, HTTPException, Request

from settings import ADMIN_COOKIE, ADMIN_PASSWORD, ENGINE_SECRET, PANEL_USER


def _same(left: str, right: str) -> bool:
    return hmac.compare_digest(
        hashlib.sha256(left.encode()).digest(),
        hashlib.sha256(right.encode()).digest(),
    )


def check_engine_key(request: Request) -> None:
    key = request.headers.get("x-klo-key", "")
    if not _same(key, ENGINE_SECRET):
        raise HTTPException(status_code=404, detail="Not Found")


def check_admin_login(username: str, password: str) -> bool:
    return _same(username, PANEL_USER) and _same(password, ADMIN_PASSWORD)


def sign_admin(ts: Optional[int] = None) -> str:
    ts = ts or int(time.time())
    raw = f"{ts}".encode()
    sig = hmac.new(ADMIN_COOKIE.encode(), raw, hashlib.sha256).hexdigest()
    return f"{ts}.{sig}"


def valid_admin_cookie(token: str) -> bool:
    try:
        ts_s, sig = token.split(".", 1)
        ts = int(ts_s)
    except Exception:
        return False
    if abs(time.time() - ts) > 60 * 60 * 24 * 7:
        return False
    expected = hmac.new(ADMIN_COOKIE.encode(), ts_s.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


def check_admin_password(password: str) -> bool:
    return _same(password, ADMIN_PASSWORD)


async def require_admin(klo_admin: str = Cookie(default="")) -> None:
    if not valid_admin_cookie(klo_admin):
        raise HTTPException(status_code=401, detail="auth")
