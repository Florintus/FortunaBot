"""Разметка inline-клавиатур."""
from bot.keyboards.inline import (
    get_participate_button,
    get_confirm_delete_keyboard,
)


def test_participate_button_callback():
    m = get_participate_button(42)
    row = m.keyboard[0]
    assert len(row) == 1
    assert row[0].callback_data == "participate_42"


def test_confirm_delete_contains_giveaway_id():
    m = get_confirm_delete_keyboard(99)
    callbacks = [b.callback_data for row in m.keyboard for b in row]
    assert any("confirm_delete_99" == c for c in callbacks)
