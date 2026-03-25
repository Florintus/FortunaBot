"""Twitch-сервис: локальная логика без сети (кроме явно замоканных вызовов)."""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from bot.services.twitch_service import TwitchService, _dt_utc_aware


def test_dt_utc_aware_naive():

    n = datetime(2024, 1, 1, 12, 0, 0)
    rly = _dt_utc_aware(n)
    assert rly.tzinfo == timezone.utc


def test_is_configured_false_when_disabled():
    svc = TwitchService()
    assert svc.is_configured() is False


def test_get_app_token_returns_none_when_not_configured():
    svc = TwitchService()
    assert svc.get_app_access_token() is None


def test_check_follows_empty_login():
    svc = TwitchService()
    assert svc.check_follows_channel(1, "  ") is False


def test_link_manual_and_get():
    assert TwitchService.link_account_manual(88001, "  MyLogin  ") is True
    assert TwitchService.get_linked_twitch(88001) == "mylogin"


def test_has_oauth_link_false_for_manual_only():
    TwitchService.link_account_manual(88002, "x")
    svc = TwitchService()
    assert svc.has_oauth_link(88002) is False


@patch("bot.services.twitch_service.TWITCH_CLIENT_SECRET", "sec")
@patch("bot.services.twitch_service.TWITCH_CLIENT_ID", "cid")
@patch("bot.services.twitch_service.TWITCH_ENABLED", True)
@patch("bot.services.twitch_service.requests.post")
def test_get_app_access_token_caches(mock_post):
    from bot.services.twitch_service import TwitchService

    svc = TwitchService()
    mock_post.return_value.json.return_value = {
        "access_token": "tok",
        "expires_in": 3600,
    }
    mock_post.return_value.raise_for_status = MagicMock()

    assert svc.get_app_access_token() == "tok"
    assert svc.get_app_access_token() == "tok"
    assert mock_post.call_count == 1
