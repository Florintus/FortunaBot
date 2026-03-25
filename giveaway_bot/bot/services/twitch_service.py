import traceback
from datetime import datetime, timedelta, timezone

import requests

from bot.config import (
    TWITCH_CLIENT_ID,
    TWITCH_CLIENT_SECRET,
    TWITCH_ENABLED,
    TWITCH_FOLLOW_SCOPE,
)
from bot.database.database import get_db
from bot.database.models import TwitchDeviceAuth, TwitchLink
from bot.utils.twitch_parse import normalize_twitch_channel_login

TWITCH_DEVICE_URL = "https://id.twitch.tv/oauth2/device"
TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_HELIX = "https://api.twitch.tv/helix"


def _dt_utc_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class TwitchService:
    """Twitch API: app-токен, Device Flow привязка, проверка фолловов через user token."""

    def __init__(self):
        self.client_id = TWITCH_CLIENT_ID
        self.client_secret = TWITCH_CLIENT_SECRET
        self._app_token: str | None = None
        self._app_token_expires: datetime | None = None

    def is_configured(self) -> bool:
        return bool(
            TWITCH_ENABLED and self.client_id and self.client_secret
        )

    def get_app_access_token(self) -> str | None:
        if not self.is_configured():
            return None
        now = datetime.now(timezone.utc)
        if (
            self._app_token
            and self._app_token_expires
            and now < self._app_token_expires - timedelta(seconds=60)
        ):
            return self._app_token
        try:
            r = requests.post(
                TWITCH_TOKEN_URL,
                params={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "client_credentials",
                },
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            self._app_token = data["access_token"]
            self._app_token_expires = now + timedelta(
                seconds=int(data.get("expires_in", 3600))
            )
            return self._app_token
        except Exception as e:
            print(f"Ошибка получения Twitch app-токена: {e}")
            return None

    def _helix_headers_user(self, user_access_token: str) -> dict:
        return {
            "Client-Id": self.client_id,
            "Authorization": f"Bearer {user_access_token}",
        }

    def _helix_headers_app(self, app_token: str) -> dict:
        return {
            "Client-Id": self.client_id,
            "Authorization": f"Bearer {app_token}",
        }

    def _fetch_login_user_id(self, login: str, app_token: str) -> str | None:
        login = login.strip().lstrip("@").lower()
        if not login:
            return None
        try:
            r = requests.get(
                f"{TWITCH_HELIX}/users",
                headers=self._helix_headers_app(app_token),
                params={"login": login},
                timeout=15,
            )
            r.raise_for_status()
            data = r.json().get("data") or []
            return str(data[0]["id"]) if data else None
        except Exception as e:
            print(f"Twitch users lookup: {e}")
            return None

    def start_device_auth(self, telegram_id: int) -> dict | None:
        """Старт Device Flow. Возвращает user_code, verification_uri, message или None."""
        if not self.is_configured():
            return None
        try:
            r = requests.post(
                TWITCH_DEVICE_URL,
                data={
                    "client_id": self.client_id,
                    "scopes": TWITCH_FOLLOW_SCOPE.strip(),
                },
                timeout=15,
            )
            r.raise_for_status()
            payload = r.json()
            device_code = payload.get("device_code") or ""
            user_code = payload.get("user_code") or ""
            verification_uri = payload.get("verification_uri") or "https://www.twitch.tv/activate"
            interval = max(int(payload.get("interval", 5)), 1)
            expires_in = int(payload.get("expires_in", 0))
            if not device_code or not user_code or expires_in <= 0:
                return None
            # Naive UTC: иначе PostgreSQL/SQLAlchemy часто падают на TIMESTAMP WITHOUT TIME ZONE
            expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            with get_db() as db:
                row = db.query(TwitchDeviceAuth).filter_by(
                    telegram_id=telegram_id
                ).first()
                if row:
                    row.device_code = device_code
                    row.poll_interval = interval
                    row.expires_at = expires_at
                    row.last_poll_at = None
                else:
                    db.add(
                        TwitchDeviceAuth(
                            telegram_id=telegram_id,
                            device_code=device_code,
                            poll_interval=interval,
                            expires_at=expires_at,
                        )
                    )
            return {
                "user_code": user_code,
                "verification_uri": verification_uri,
                "expires_in": expires_in,
                "interval": interval,
            }
        except Exception as e:
            print(f"Twitch device auth start: {e}")
            traceback.print_exc()
            return None

    def _delete_device_session(self, telegram_id: int):
        with get_db() as db:
            row = db.query(TwitchDeviceAuth).filter_by(
                telegram_id=telegram_id
            ).first()
            if row:
                db.delete(row)

    def poll_device_auth(self, telegram_id: int) -> tuple[str, str | None]:
        """
        Опрос завершения Device Flow.
        Возвращает (статус, детали): success+login, pending, wait+N сек, expired, denied, error, no_session.
        """
        if not self.is_configured():
            return ("error", "Twitch не настроен")

        now = datetime.now(timezone.utc)
        device_code = None
        with get_db() as db:
            pending = db.query(TwitchDeviceAuth).filter_by(
                telegram_id=telegram_id
            ).first()
            if not pending:
                return ("no_session", None)

            exp = _dt_utc_aware(pending.expires_at)
            if exp and now >= exp:
                db.delete(pending)
                return ("expired", None)

            last = pending.last_poll_at
            if last is not None:
                elapsed = (now - _dt_utc_aware(last)).total_seconds()
                wait_need = max(pending.poll_interval, 1)
                if elapsed < wait_need:
                    return ("wait", str(int(wait_need - elapsed) + 1))

            device_code = pending.device_code

        try:
            r = requests.post(
                TWITCH_TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": device_code,
                },
                timeout=15,
            )
        except Exception as e:
            return ("error", str(e))

        with get_db() as db:
            pending = db.query(TwitchDeviceAuth).filter_by(
                telegram_id=telegram_id
            ).first()
            if pending:
                pending.last_poll_at = datetime.utcnow()

        if r.status_code == 200:
            data = r.json()
            access = data.get("access_token")
            refresh = data.get("refresh_token")
            expires_in = int(data.get("expires_in", 0))
            if not access:
                return ("error", "Нет access_token")
            try:
                ur = requests.get(
                    f"{TWITCH_HELIX}/users",
                    headers=self._helix_headers_user(access),
                    timeout=15,
                )
                ur.raise_for_status()
                udata = ur.json().get("data") or []
                if not udata:
                    return ("error", "Не удалось получить профиль Twitch")
                twitch_user_id = str(udata[0]["id"])
                twitch_login = str(udata[0]["login"])
                token_exp = datetime.utcnow() + timedelta(
                    seconds=max(expires_in - 120, 60)
                )
                with get_db() as db:
                    sess = db.query(TwitchDeviceAuth).filter_by(
                        telegram_id=telegram_id
                    ).first()
                    if sess:
                        db.delete(sess)
                    link = db.query(TwitchLink).filter_by(
                        telegram_id=telegram_id
                    ).first()
                    if link:
                        link.twitch_username = twitch_login
                        link.twitch_user_id = twitch_user_id
                        link.access_token = access
                        link.refresh_token = refresh
                        link.token_expires_at = token_exp
                    else:
                        db.add(
                            TwitchLink(
                                telegram_id=telegram_id,
                                twitch_username=twitch_login,
                                twitch_user_id=twitch_user_id,
                                access_token=access,
                                refresh_token=refresh,
                                token_expires_at=token_exp,
                            )
                        )
                return ("success", twitch_login)
            except Exception as e:
                return ("error", str(e))

        try:
            err = r.json()
        except Exception:
            err = {}
        err_type = err.get("message", "") or err.get("error", "")

        if r.status_code == 400:
            low = str(err_type).lower()
            if "authorization_pending" in low or "slow_down" in low:
                return ("pending", None)
            if "expired" in low or "invalid_grant" in low:
                self._delete_device_session(telegram_id)
                return ("expired", None)
            if "denied" in low:
                self._delete_device_session(telegram_id)
                return ("denied", None)

        return ("error", str(err_type or r.text[:200]))

    def get_valid_user_access_token(self, telegram_id: int) -> str | None:
        """Access token пользователя с авто-обновлением по refresh_token."""
        if not self.is_configured():
            return None
        with get_db() as db:
            link = db.query(TwitchLink).filter_by(telegram_id=telegram_id).first()
            if not link or not link.access_token:
                return None
            now = datetime.now(timezone.utc)
            exp = link.token_expires_at
            if exp is not None:
                exp_aware = _dt_utc_aware(exp)
                if exp_aware and exp_aware > now + timedelta(seconds=90):
                    return link.access_token
            if not link.refresh_token:
                return link.access_token
            try:
                r = requests.post(
                    TWITCH_TOKEN_URL,
                    data={
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "grant_type": "refresh_token",
                        "refresh_token": link.refresh_token,
                    },
                    timeout=15,
                )
                r.raise_for_status()
                data = r.json()
                access = data.get("access_token")
                refresh = data.get("refresh_token", link.refresh_token)
                expires_in = int(data.get("expires_in", 0))
                if not access:
                    return None
                new_exp = datetime.now(timezone.utc) + timedelta(
                    seconds=max(expires_in - 120, 60)
                )
                link.access_token = access
                link.refresh_token = refresh
                link.token_expires_at = new_exp.replace(tzinfo=None)
                return access
            except Exception as e:
                print(f"Twitch refresh token: {e}")
                return None

    def check_follows_channel(self, telegram_id: int, channel_login: str) -> bool:
        """Проверка, что пользователь (OAuth) фолловит указанный канал."""
        channel_login = normalize_twitch_channel_login(channel_login) or ""
        if not channel_login:
            return False
        user_token = self.get_valid_user_access_token(telegram_id)
        app_token = self.get_app_access_token()
        if not user_token or not app_token:
            return False

        with get_db() as db:
            link = db.query(TwitchLink).filter_by(telegram_id=telegram_id).first()
            if not link or not link.twitch_user_id:
                return False
            uid = link.twitch_user_id

        bid = self._fetch_login_user_id(channel_login, app_token)
        if not bid:
            return False

        try:
            r = requests.get(
                f"{TWITCH_HELIX}/channels/followed",
                headers=self._helix_headers_user(user_token),
                params={"user_id": uid, "broadcaster_id": bid, "first": 1},
                timeout=15,
            )
            if r.status_code == 401:
                self._invalidate_user_tokens(telegram_id)
                return False
            r.raise_for_status()
            data = r.json().get("data") or []
            return len(data) > 0
        except Exception as e:
            print(f"Twitch channels/followed: {e}")
            return False

    def _invalidate_user_tokens(self, telegram_id: int):
        with get_db() as db:
            link = db.query(TwitchLink).filter_by(telegram_id=telegram_id).first()
            if link:
                link.access_token = None
                link.refresh_token = None
                link.token_expires_at = None

    def check_subscription(self, telegram_id: int, channel_name: str) -> bool:
        """Совместимость: проверка условия «подписка» = фоллов на канал (user:read:follows)."""
        return self.check_follows_channel(telegram_id, channel_name)

    @staticmethod
    def link_account_manual(telegram_id: int, twitch_username: str) -> bool:
        """Ручная привязка логина без OAuth (проверка Twitch для розыгрышей не сработает)."""
        twitch_username = twitch_username.strip().lstrip("@").lower()
        try:
            with get_db() as db:
                link = db.query(TwitchLink).filter_by(
                    telegram_id=telegram_id
                ).first()
                if link:
                    link.twitch_username = twitch_username
                    link.twitch_user_id = None
                    link.access_token = None
                    link.refresh_token = None
                    link.token_expires_at = None
                else:
                    db.add(
                        TwitchLink(
                            telegram_id=telegram_id,
                            twitch_username=twitch_username,
                        )
                    )
            return True
        except Exception as e:
            print(f"Ошибка привязки Twitch: {e}")
            return False

    @staticmethod
    def get_linked_twitch(telegram_id: int) -> str | None:
        with get_db() as db:
            link = db.query(TwitchLink).filter_by(telegram_id=telegram_id).first()
            return link.twitch_username if link else None

    def has_oauth_link(self, telegram_id: int) -> bool:
        with get_db() as db:
            link = db.query(TwitchLink).filter_by(telegram_id=telegram_id).first()
            return bool(link and link.access_token and link.twitch_user_id)


twitch_service = TwitchService()
