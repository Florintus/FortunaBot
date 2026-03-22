import telebot
from bot.config import BOT_TOKEN
from bot.database.database import init_db
from bot.handlers import admin, user
from bot.utils.scheduler import start_scheduler

def main():
    """Главная функция запуска бота"""
    print("🤖 Запуск бота для розыгрышей...")
    
    # Инициализация базы данных
    init_db()
    
    # Создание бота
    bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML')
    
    # Регистрация обработчиков
    admin.register_admin_handlers(bot)
    user.register_user_handlers(bot)
    
    # Запуск планировщика
    start_scheduler()
    
    print("✅ Бот запущен и готов к работе!")
    
    # Запуск polling
    bot.infinity_polling(timeout=60, long_polling_timeout=60)


if __name__ == '__main__':
    main()
