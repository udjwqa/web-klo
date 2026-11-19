from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from settings import DATABASE_URL

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_async_engine(DATABASE_URL, echo=False, connect_args=connect_args)
Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if DATABASE_URL.startswith("sqlite"):
            await conn.run_sync(_migrate_columns)


def _migrate_columns(sync_conn) -> None:
    logs = {row[1] for row in sync_conn.exec_driver_sql("PRAGMA table_info(request_logs)").fetchall()}
    for name, ddl in (
        ("isp", "VARCHAR(200) DEFAULT ''"),
        ("referer", "TEXT DEFAULT ''"),
        ("language", "VARCHAR(80) DEFAULT ''"),
    ):
        if name not in logs:
            sync_conn.exec_driver_sql(f"ALTER TABLE request_logs ADD COLUMN {name} {ddl}")
    camps = {row[1] for row in sync_conn.exec_driver_sql("PRAGMA table_info(campaigns)").fetchall()}
    if "bridge_url" not in camps:
        sync_conn.exec_driver_sql("ALTER TABLE campaigns ADD COLUMN bridge_url TEXT DEFAULT ''")
    bans = {row[1] for row in sync_conn.exec_driver_sql("PRAGMA table_info(banned_ips)").fetchall()}
    if "expires_at" not in bans:
        sync_conn.exec_driver_sql("ALTER TABLE banned_ips ADD COLUMN expires_at DATETIME")
