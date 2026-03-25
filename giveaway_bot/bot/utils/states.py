import json
from datetime import datetime
from bot.database.database import get_db
from bot.database.models import UserState


def _json_serializer(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def _json_deserializer(data: dict) -> dict:
    _list_keys = frozenset({"required_channels", "twitch_channels"})
    for key, value in data.items():
        if isinstance(value, str) and key in _list_keys:
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    data[key] = parsed
                    continue
            except json.JSONDecodeError:
                pass
        if isinstance(value, str):
            try:
                data[key] = datetime.fromisoformat(value)
            except ValueError:
                pass
    return data


class FSMContext:
    """Управление состояниями пользователя"""

    @staticmethod
    def set_state(user_id: int, state: str, data: dict = None):
        with get_db() as db:
            user_state = db.query(UserState).filter_by(user_id=user_id).first()
            if user_state:
                user_state.state = state
                if data is not None:
                    user_state.data = json.dumps(data, default=_json_serializer)
            else:
                user_state = UserState(
                    user_id=user_id,
                    state=state,
                    data=json.dumps(data or {}, default=_json_serializer)
                )
                db.add(user_state)

    @staticmethod
    def get_state(user_id: int) -> tuple:
        """Возвращает (state, data)"""
        with get_db() as db:
            user_state = db.query(UserState).filter_by(user_id=user_id).first()
            if user_state:
                data = _json_deserializer(json.loads(user_state.data)) if user_state.data else {}
                return user_state.state, data
            return None, {}

    @staticmethod
    def update_data(user_id: int, new_data: dict):
        with get_db() as db:
            user_state = db.query(UserState).filter_by(user_id=user_id).first()
            if user_state:
                data = _json_deserializer(json.loads(user_state.data)) if user_state.data else {}
                data.update(new_data)
                user_state.data = json.dumps(data, default=_json_serializer)
            else:
                user_state = UserState(
                    user_id=user_id,
                    state=None,
                    data=json.dumps(new_data, default=_json_serializer)
                )
                db.add(user_state)

    @staticmethod
    def clear_state(user_id: int):
        with get_db() as db:
            user_state = db.query(UserState).filter_by(user_id=user_id).first()
            if user_state:
                db.delete(user_state)


# Состояния для создания розыгрыша
class States:
    WAITING_CHANNEL      = "waiting_channel"
    WAITING_TITLE        = "waiting_title"
    WAITING_DESCRIPTION  = "waiting_description"
    WAITING_CHANNELS     = "waiting_channels"
    WAITING_TWITCH       = "waiting_twitch"
    WAITING_WINNERS      = "waiting_winners"
    WAITING_MEDIA        = "waiting_media"
    WAITING_START_TIME   = "waiting_start_time"
    WAITING_START_MANUAL = "waiting_start_manual"  # ручной ввод времени начала
    WAITING_END_TIME     = "waiting_end_time"
    WAITING_END_MANUAL   = "waiting_end_manual"    # ручной ввод времени конца
    CONFIRM              = "confirm"