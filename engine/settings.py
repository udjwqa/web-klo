import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("WEBKLO_DATA", BASE_DIR.parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite+aiosqlite:///{DATA_DIR / 'webklo.db'}",
)

ENGINE_SECRET = os.getenv("ENGINE_SECRET", "change-me-engine-secret")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change-me-admin")
ADMIN_COOKIE = os.getenv("ADMIN_COOKIE_SECRET", "change-me-cookie")
PANEL_HOST = os.getenv("PANEL_HOST", "klo.local").strip().lower()
PANEL_USER = os.getenv("PANEL_USER", "operator")
PANEL_PATH = "/" + os.getenv("PANEL_PATH", "entry").strip().strip("/")

IPQS_API_KEY = os.getenv("IPQS_API_KEY", "")
IPINFO_TOKEN = os.getenv("IPINFO_TOKEN", "")
CLOAKER_API_URL = os.getenv("CLOAKER_API_URL", "").strip()
CLOAKER_API_KEY = os.getenv("CLOAKER_API_KEY", "").strip()
CLOAKER_CAMPAIGN_ID = os.getenv("CLOAKER_CAMPAIGN_ID", "").strip()

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8088"))
WEBKLO_ROLE = os.getenv("WEBKLO_ROLE", "hub").strip().lower()
HUB_URL = os.getenv("HUB_URL", "https://prostoydomen.info").rstrip("/")
SYNC_SEC = int(os.getenv("SYNC_SEC", "60"))

DEFAULT_THRESHOLD = int(os.getenv("DEFAULT_THRESHOLD", "100"))
CHALLENGE_BAND = int(os.getenv("CHALLENGE_BAND", "20"))
DECISION_TTL_SEC = int(os.getenv("DECISION_TTL_SEC", "900"))
COLLECT_DELAY_MS = int(os.getenv("COLLECT_DELAY_MS", "1500"))
