"""FSM-состояния в БД."""
from datetime import datetime

from bot.utils.states import FSMContext


def test_set_get_clear_state_roundtrip():
    uid = 900001
    FSMContext.set_state(uid, "waiting_title", {"key": "v", "when": datetime(2024, 1, 15, 12, 0, 0)})
    state, data = FSMContext.get_state(uid)
    assert state == "waiting_title"
    assert data["key"] == "v"
    assert isinstance(data["when"], datetime)
    FSMContext.clear_state(uid)
    s2, d2 = FSMContext.get_state(uid)
    assert s2 is None
    assert d2 == {}


def test_update_data_merges():
    uid = 900002
    FSMContext.set_state(uid, "s", {"a": 1})
    FSMContext.update_data(uid, {"b": 2})
    _, data = FSMContext.get_state(uid)
    assert data == {"a": 1, "b": 2}
