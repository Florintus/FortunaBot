from bot.database.database import get_db
from bot.database.models import BotChannel


class ChannelService:
    """Сервис для управления каналами бота"""

    @staticmethod
    def add_channel(chat_id: str, title: str, chat_type: str):
        """Добавить или обновить канал"""
        with get_db() as db:
            channel = db.query(BotChannel).filter_by(chat_id=str(chat_id)).first()
            if channel:
                channel.title = title
                channel.chat_type = chat_type
            else:
                db.add(BotChannel(
                    chat_id=str(chat_id),
                    title=title,
                    chat_type=chat_type
                ))

    @staticmethod
    def remove_channel(chat_id: str):
        """Удалить канал"""
        with get_db() as db:
            channel = db.query(BotChannel).filter_by(chat_id=str(chat_id)).first()
            if channel:
                db.delete(channel)

    @staticmethod
    def get_all_channels() -> list:
        """Получить все каналы"""
        with get_db() as db:
            channels = db.query(BotChannel).order_by(BotChannel.added_at.desc()).all()
            return [
                {
                    'chat_id': c.chat_id,
                    'title': c.title,
                    'chat_type': c.chat_type,
                    'added_at': c.added_at,
                }
                for c in channels
            ]