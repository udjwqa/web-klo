from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from admin import router as admin_router
from db import init_db
from decide import router as decide_router
from gate import GateMiddleware, nginx_404
from cloaker_api import cloaker_client
from ipinfo import ipinfo_client
from ipqs import ipqs_client
from burst import burst_window
from google_crawlers import google_crawlers
from ip_ranges import ip_range_checker
from lists import lists
from settings import BASE_DIR, PANEL_PATH, WEBKLO_ROLE
from store import seed_if_empty


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()
    lists.load()
    ip_range_checker.load()
    google_crawlers.load()
    burst_window.clear()
    if WEBKLO_ROLE == "edge":
        from edge import start_edge, stop_edge

        await start_edge()
    else:
        await seed_if_empty()
    yield
    if WEBKLO_ROLE == "edge":
        from edge import stop_edge

        await stop_edge()
    await ipqs_client.close()
    await ipinfo_client.close()
    await cloaker_client.close()


app = FastAPI(
    title="",
    version="1",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
app.add_middleware(GateMiddleware)
app.include_router(decide_router)
app.include_router(admin_router)

STATIC = BASE_DIR / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get(PANEL_PATH)
async def panel_page(request: Request):
    if not getattr(request.state, "serve_panel", False):
        return nginx_404()
    return FileResponse(STATIC / "admin" / "index.html")
