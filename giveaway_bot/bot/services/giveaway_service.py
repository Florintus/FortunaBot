import json
import random

from bot.database.database import get_db
from bot.database.models import Giveaway, Participant, Winner


def _coerce_json_list(value) -> list:
    """Из FSM/БД иногда приходит JSON-массив строкой — для Column(JSON) нужен list."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass
        return [s]
    return []


class GiveawayService:
    """Сервис для работы с розыгрышами"""

    @staticmethod
    def _giveaway_to_dict(giveaway: Giveaway) -> dict:
        """Конвертирует ORM объект в словарь пока сессия открыта"""
        return {
            'id': giveaway.id,
            'creator_id': giveaway.creator_id,
            'title': giveaway.title,
            'description': giveaway.description,
            'photo_file_id': giveaway.photo_file_id,
            'document_file_id': giveaway.document_file_id,
            'start_time': giveaway.start_time,
            'end_time': giveaway.end_time,
            'required_channels': giveaway.required_channels,
            'twitch_channels': giveaway.twitch_channels,
            'winners_count': giveaway.winners_count,
            'is_published': giveaway.is_published,
            'is_finished': giveaway.is_finished,
            'message_id': giveaway.message_id,
            'channel_id': giveaway.channel_id,
            'participants_count': len(giveaway.participants),
        }

    @staticmethod
    def create_giveaway(data: dict) -> dict:
        """Создание розыгрыша"""
        row = dict(data)
        row["required_channels"] = _coerce_json_list(row.get("required_channels"))
        row["twitch_channels"] = _coerce_json_list(row.get("twitch_channels"))
        with get_db() as db:
            giveaway = Giveaway(**row)
            db.add(giveaway)
            db.flush()
            db.refresh(giveaway)
            return GiveawayService._giveaway_to_dict(giveaway)

    @staticmethod
    def add_participant(giveaway_id: int, user_id: int, username: str, full_name: str) -> bool:
        """Добавление участника"""
        with get_db() as db:
            existing = db.query(Participant).filter_by(
                giveaway_id=giveaway_id,
                user_id=user_id
            ).first()
            if existing:
                return False
            participant = Participant(
                giveaway_id=giveaway_id,
                user_id=user_id,
                username=username,
                full_name=full_name
            )
            db.add(participant)
            return True

    @staticmethod
    def is_participant(giveaway_id: int, user_id: int) -> bool:
        """Проверка, участвует ли пользователь"""
        with get_db() as db:
            return db.query(Participant).filter_by(
                giveaway_id=giveaway_id,
                user_id=user_id
            ).first() is not None

    @staticmethod
    def get_giveaway(giveaway_id: int) -> dict | None:
        """Получение розыгрыша по ID"""
        with get_db() as db:
            g = db.query(Giveaway).filter_by(id=giveaway_id).first()
            if not g:
                return None
            return GiveawayService._giveaway_to_dict(g)

    @staticmethod
    def get_active_giveaways() -> list:
        """Непубликованные розыгрыши (время публикации решает планировщик)."""
        with get_db() as db:
            giveaways = db.query(Giveaway).filter(
                Giveaway.is_published.is_(False)
            ).order_by(Giveaway.start_time.asc()).all()
            return [GiveawayService._giveaway_to_dict(g) for g in giveaways]

    @staticmethod
    def get_finished_giveaways() -> list:
        """Опубликованные, но ещё не завершённые (момент завершения решает планировщик)."""
        with get_db() as db:
            giveaways = db.query(Giveaway).filter(
                Giveaway.is_published.is_(True),
                Giveaway.is_finished.is_(False)
            ).order_by(Giveaway.end_time.asc()).all()
            return [GiveawayService._giveaway_to_dict(g) for g in giveaways]

    @staticmethod
    def select_winners(giveaway_id: int) -> list:
        """Случайный выбор победителей, возвращает список словарей"""
        with get_db() as db:
            giveaway = db.query(Giveaway).filter_by(id=giveaway_id).first()
            if not giveaway:
                return []

            participants = db.query(Participant).filter_by(giveaway_id=giveaway_id).all()
            if not participants:
                giveaway.is_finished = True
                return []

            winners_count = min(giveaway.winners_count, len(participants))
            selected = random.sample(participants, winners_count)

            winners = []
            for participant in selected:
                winner = Winner(
                    giveaway_id=giveaway_id,
                    user_id=participant.user_id,
                    username=participant.username,
                    full_name=participant.full_name
                )
                db.add(winner)
                winners.append({
                    'user_id': participant.user_id,
                    'username': participant.username,
                    'full_name': participant.full_name,
                })

            giveaway.is_finished = True
            return winners

    @staticmethod
    def get_user_giveaways(creator_id: int) -> list:
        """Получение розыгрышей пользователя"""
        with get_db() as db:
            giveaways = db.query(Giveaway).filter_by(creator_id=creator_id).order_by(
                Giveaway.created_at.desc()
            ).all()
            return [GiveawayService._giveaway_to_dict(g) for g in giveaways]

    @staticmethod
    def update_message_id(giveaway_id: int, message_id: int):
        """Обновление ID сообщения и статуса публикации"""
        with get_db() as db:
            giveaway = db.query(Giveaway).filter_by(id=giveaway_id).first()
            if giveaway:
                giveaway.message_id = message_id
                giveaway.is_published = True

    @staticmethod
    def mark_published(giveaway_id: int):
        """Пометить розыгрыш как опубликованный (без отправки сообщения)"""
        with get_db() as db:
            giveaway = db.query(Giveaway).filter_by(id=giveaway_id).first()
            if giveaway:
                giveaway.is_published = True

    @staticmethod
    def delete_giveaway(giveaway_id: int, creator_id: int) -> bool:
        """Удаление розыгрыша (только своего)"""
        with get_db() as db:
            giveaway = db.query(Giveaway).filter_by(
                id=giveaway_id, creator_id=creator_id
            ).first()
            if giveaway:
                db.delete(giveaway)
                return True
            return False
