"""Парсинг ссылок и имён канала Twitch."""
import pytest

from bot.utils.twitch_parse import normalize_twitch_channel_login


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, ""),
        ("", ""),
        ("  ", ""),
        ("FlorinTus", "florintus"),
        ("@SomeOne", "someone"),
        ("https://www.twitch.tv/florintus", "florintus"),
        ("http://twitch.tv/x", "x"),
        ("twitch.tv/user_name", "user_name"),
        ("https://www.Twitch.tv/FOO?tab=about", "foo"),
    ],
)
def test_normalize_twitch_channel_login(raw, expected):
    assert normalize_twitch_channel_login(raw) == expected
