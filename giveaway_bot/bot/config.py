import os
from pathlib import Path

from dotenv import load_dotenv

# Пакет: .../giveaway_bot/bot/config.py -> giveaway_bot и корень репозитория
_PKG_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _PKG_ROOT.parent


def _load_env_files() -> None:
    """
    Подхватывает .env при любом способе запуска.
    В Docker Compose переменные чаще приходят из env_file в os.environ, файла /app/.env может не быть.
    Локально помогает поиск в cwd, корне репо и каталоге giveaway_bot.
    """
    candidates = (
        Path.cwd() / ".env",
        _REPO_ROOT / ".env",
        _PKG_ROOT / ".env",
    )
    for path in candidates:
        if path.is_file():
            load_dotenv(path, override=True)


_load_env_files()


def _env_truthy(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _strip_secret(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip()
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        v = v[1:-1].strip()
    return v or None


_BOT_TOKEN_RAW = os.getenv("BOT_TOKEN", "").strip() or None
BOT_TOKEN = _strip_secret(_BOT_TOKEN_RAW) if _BOT_TOKEN_RAW else None
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip()]
CHANNEL_ID = os.getenv("CHANNEL_ID")
BOT_USERNAME = "testStmalina_bot"

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./bot.db").strip()  # fallback на SQLite для теста

TWITCH_CLIENT_ID = _strip_secret(os.getenv("TWITCH_CLIENT_ID"))
TWITCH_CLIENT_SECRET = _strip_secret(os.getenv("TWITCH_CLIENT_SECRET"))
_has_twitch_creds = bool(TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET)

# Логика «как лучше» для Docker (env_file) и локали:
# — достаточно пары CLIENT_ID + SECRET;
# — TWITCH_ENABLED=false / 0 явно выключает;
# — TWITCH_DISABLED=true явно выключает;
# — если TWITCH_ENABLED не задан в окружении, считаем включённым при наличии кредов.
_twitch_enabled_raw = os.getenv("TWITCH_ENABLED")
_twitch_flag_set = _twitch_enabled_raw is not None and str(_twitch_enabled_raw).strip() != ""

if _env_truthy("TWITCH_DISABLED", False):
    TWITCH_ENABLED = False
elif _twitch_flag_set:
    TWITCH_ENABLED = _env_truthy("TWITCH_ENABLED", False) and _has_twitch_creds
else:
    TWITCH_ENABLED = _has_twitch_creds
TWITCH_FOLLOW_SCOPE = 'user:read:follows'

MEDIA_DIR = '/app/media'

# Проверки
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN required!")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL required!")
