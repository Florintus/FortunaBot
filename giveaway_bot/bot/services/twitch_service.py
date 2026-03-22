import requests
from datetime import datetime, timedelta
from bot.config import TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET
from bot.database.database import get_db
from bot.database.models import TwitchLink


class TwitchService:
    """Сервис для работы с Twitch API"""
    
    def __init__(self):
        self.client_id = TWITCH_CLIENT_ID
        self.client_secret = TWITCH_CLIENT_SECRET
        self.access_token = None
        self.token_expires = None
    
    def get_access_token(self) -> str:
        """Получение OAuth токена Twitch"""
        if self.access_token and self.token_expires and datetime.now() < self.token_expires:
            return self.access_token
        
        url = "https://id.twitch.tv/oauth2/token"
        params = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'client_credentials'
        }
        
        try:
            response = requests.post(url, params=params)
            data = response.json()
            self.access_token = data['access_token']
            self.token_expires = datetime.now() + timedelta(seconds=data['expires_in'] - 300)
            return self.access_token
        except Exception as e:
            print(f"Ошибка получения Twitch токена: {e}")
            return None
    
    def check_subscription(self, twitch_username: str, channel_name: str) -> bool:
        """
        Проверяет, подписан ли пользователь на Twitch канал
        
        :param twitch_username: Имя пользователя Twitch
        :param channel_name: Имя канала для проверки
        :return: True если подписан
        """
        token = self.get_access_token()
        if not token:
            return False
        
        headers = {
            'Client-ID': self.client_id,
            'Authorization': f'Bearer {token}'
        }
        
        try:
            # Получаем ID пользователя
            user_response = requests.get(
                'https://api.twitch.tv/helix/users',
                headers=headers,
                params={'login': twitch_username}
            )
            user_data = user_response.json()
            if not user_data.get('data'):
                return False
            user_id = user_data['data'][0]['id']
            
            # Получаем ID канала
            channel_response = requests.get(
                'https://api.twitch.tv/helix/users',
                headers=headers,
                params={'login': channel_name}
            )
            channel_data = channel_response.json()
            if not channel_data.get('data'):
                return False
            channel_id = channel_data['data'][0]['id']
            
            # Проверяем подписку
            sub_response = requests.get(
                'https://api.twitch.tv/helix/subscriptions/user',
                headers=headers,
                params={
                    'broadcaster_id': channel_id,
                    'user_id': user_id
                }
            )
            
            return sub_response.status_code == 200 and bool(sub_response.json().get('data'))
        
        except Exception as e:
            print(f"Ошибка проверки Twitch подписки: {e}")
            return False
    
    @staticmethod
    def link_account(telegram_id: int, twitch_username: str) -> bool:
        """Связывает Telegram аккаунт с Twitch"""
        try:
            with get_db() as db:
                link = TwitchLink(telegram_id=telegram_id, twitch_username=twitch_username)
                db.merge(link)
            return True
        except Exception as e:
            print(f"Ошибка привязки Twitch: {e}")
            return False
    
    @staticmethod
    def get_linked_twitch(telegram_id: int) -> str:
        """Получает привязанный Twitch аккаунт"""
        with get_db() as db:
            link = db.query(TwitchLink).filter_by(telegram_id=telegram_id).first()
            return link.twitch_username if link else None


twitch_service = TwitchService()
