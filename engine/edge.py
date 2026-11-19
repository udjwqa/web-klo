from __future__ import annotations

import asyncio
import logging

import httpx

from settings import ENGINE_SECRET, HUB_URL, PANEL_HOST, SYNC_SEC
from store import apply_snapshot, read_outbox, replace_outbox

logger = logging.getLogger("webklo.edge")
_tasks: list[asyncio.Task] = []


async def start_edge() -> list[asyncio.Task]:
    await sync_once()
    _tasks.append(asyncio.create_task(_loop(), name="webklo-edge"))
    return _tasks


async def stop_edge() -> None:
    for task in _tasks:
        task.cancel()
    _tasks.clear()


async def sync_once() -> bool:
    headers = {"X-Klo-Key": ENGINE_SECRET, "Host": PANEL_HOST}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            res = await client.get(HUB_URL + "/v1/sync", headers=headers)
            res.raise_for_status()
            await apply_snapshot(res.json())
            await flush_outbox(client, headers)
        return True
    except Exception as exc:
        logger.warning("edge sync failed: %s", exc)
        return False


async def flush_outbox(client: httpx.AsyncClient, headers: dict) -> None:
    rows = read_outbox()
    if not rows:
        return
    try:
        res = await client.post(HUB_URL + "/v1/ingest", headers=headers, json={"logs": rows[:400]})
        res.raise_for_status()
        left = rows[400:]
        replace_outbox(left)
    except Exception as exc:
        logger.warning("edge ingest failed: %s", exc)


async def _loop() -> None:
    delay = max(15, SYNC_SEC)
    while True:
        await asyncio.sleep(delay)
        await sync_once()
