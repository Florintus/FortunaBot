import telebot
from bot.config import BOT_TOKEN


class SubscriptionChecker:
    
    _bot = None

    @classmethod
    def _get_bot(cls):
        if cls._bot is None:
            cls._bot = telebot.TeleBot(BOT_TOKEN)
        return cls._bot

    @staticmethod
    def check_subscription(user_id: int, channel: str) -> bool:
        try:
            bot = SubscriptionChecker._get_bot()
            member = bot.get_chat_member(channel, user_id)
            return member.status in ['creator', 'administrator', 'member']
        except Exception as e:
            print(f"Ошибка проверки подписки на {channel}: {e}")
            return False
    
    @staticmethod
    def check_all_subscriptions(user_id: int, channels: list) -> tuple:
        """
        Проверяет подписки на все указанные каналы
        
        :return: (all_subscribed: bool, missing_channels: list)
        """
        missing = []
        
        for channel in channels:
            if not SubscriptionChecker.check_subscription(user_id, channel):
                missing.append(channel)
        
        return len(missing) == 0, missing
    
    @staticmethod
    def format_missing_channels(channels: list) -> str:
        """Форматирует список каналов для сообщения"""
        return "\n".join([f"• {channel}" for channel in channels])
