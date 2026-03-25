"""Проверка подписок в Telegram (мок API)."""
from unittest.mock import MagicMock, patch

from bot.services.subscription_checker import SubscriptionChecker


def test_format_missing_channels():
    text = SubscriptionChecker.format_missing_channels(["@a", "@b"])
    assert text == "• @a\n• @b"


@patch.object(SubscriptionChecker, "_get_bot")
def test_check_subscription_true(mock_get_bot):
    bot = MagicMock()
    member = MagicMock()
    member.status = "member"
    bot.get_chat_member.return_value = member
    mock_get_bot.return_value = bot

    assert SubscriptionChecker.check_subscription(1, "@channel") is True
    bot.get_chat_member.assert_called_once_with("@channel", 1)


@patch.object(SubscriptionChecker, "_get_bot")
def test_check_subscription_false_on_exception(mock_get_bot):
    bot = MagicMock()
    bot.get_chat_member.side_effect = RuntimeError("API")
    mock_get_bot.return_value = bot

    assert SubscriptionChecker.check_subscription(1, "@channel") is False


@patch.object(SubscriptionChecker, "check_subscription", side_effect=[True, False])
def test_check_all_subscriptions(_mock_check):
    ok, missing = SubscriptionChecker.check_all_subscriptions(5, ["@x", "@y"])
    assert ok is False
    assert missing == ["@y"]
