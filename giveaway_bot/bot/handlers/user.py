import traceback
from telebot.types import CallbackQuery
from bot.services.giveaway_service import GiveawayService
from bot.services.subscription_checker import SubscriptionChecker
from bot.services.twitch_service import twitch_service

bot = None


def register_user_handlers(telegram_bot):
    """Регистрация обработчиков пользователей"""
    global bot
    bot = telegram_bot

    @bot.callback_query_handler(func=lambda call: call.data.startswith("participate_"))
    def participate_handler(call: CallbackQuery):
        """Обработка участия в розыгрыше"""
        try:
            giveaway_id = int(call.data.split('_')[1])
            user = call.from_user

            giveaway = GiveawayService.get_giveaway(giveaway_id)
            if not giveaway:
                bot.answer_callback_query(call.id, "❌ Розыгрыш не найден")
                return

            if giveaway['is_finished']:
                bot.answer_callback_query(call.id, "❌ Розыгрыш уже завершён")
                return

            if GiveawayService.is_participant(giveaway_id, user.id):
                bot.answer_callback_query(call.id, "✅ Вы уже участвуете!")
                return

            # Проверяем подписки на Telegram каналы
            all_subscribed, missing_channels = SubscriptionChecker.check_all_subscriptions(
                user.id,
                giveaway['required_channels']
            )

            if not all_subscribed:
                missing_text = SubscriptionChecker.format_missing_channels(missing_channels)
                bot.answer_callback_query(
                    call.id,
                    "❌ Необходимо подписаться на все каналы!",
                    show_alert=True
                )
                bot.send_message(
                    user.id,
                    f"❌ Для участия подпишитесь на все обязательные каналы:\n\n{missing_text}",
                    parse_mode='HTML'
                )
                return

            # Проверяем Twitch подписки (если есть)
            if giveaway['twitch_channels']:
                twitch_username = twitch_service.get_linked_twitch(user.id)

                if not twitch_username:
                    bot.answer_callback_query(
                        call.id,
                        "❌ Необходимо привязать Twitch аккаунт!",
                        show_alert=True
                    )
                    bot.send_message(
                        user.id,
                        "🎮 Для участия нужно привязать Twitch аккаунт.\n\n"
                        "Отправьте команду /link_twitch <ваш_ник_twitch>\n"
                        "Например: /link_twitch my_username"
                    )
                    return

                missing_twitch = []
                for channel in giveaway['twitch_channels']:
                    if not twitch_service.check_subscription(twitch_username, channel):
                        missing_twitch.append(channel)

                if missing_twitch:
                    missing_text = "\n".join([f"• https://twitch.tv/{ch}" for ch in missing_twitch])
                    bot.answer_callback_query(
                        call.id,
                        "❌ Необходимо подписаться на Twitch каналы!",
                        show_alert=True
                    )
                    bot.send_message(
                        user.id,
                        f"🎮 Для участия подпишитесь на Twitch каналы:\n\n{missing_text}"
                    )
                    return

            success = GiveawayService.add_participant(
                giveaway_id,
                user.id,
                user.username,
                user.full_name
            )

            if success:
                bot.answer_callback_query(call.id, "🎉 Вы участвуете в розыгрыше!")
                bot.send_message(
                    user.id,
                    f"✅ Вы успешно зарегистрированы в розыгрыше:\n"
                    f"<b>{giveaway['title']}</b>\n\n"
                    f"Итоги будут подведены {giveaway['end_time'].strftime('%d.%m.%Y в %H:%M')} UTC",
                    parse_mode='HTML'
                )
            else:
                bot.answer_callback_query(call.id, "❌ Ошибка регистрации")

        except Exception as e:
            print(f"Ошибка участия: {e}")
            print(traceback.format_exc())
            bot.answer_callback_query(call.id, "❌ Произошла ошибка")

    @bot.message_handler(commands=['link_twitch'])
    def link_twitch_command(message):
        """Привязка Twitch аккаунта"""
        try:
            parts = message.text.split(maxsplit=1)
            if len(parts) < 2:
                bot.send_message(
                    message.chat.id,
                    "❌ Использование: /link_twitch <ваш_ник_twitch>\n"
                    "Например: /link_twitch my_username"
                )
                return

            twitch_username = parts[1].strip().replace('@', '')
            success = twitch_service.link_account(message.from_user.id, twitch_username)

            if success:
                bot.send_message(
                    message.chat.id,
                    f"✅ Twitch аккаунт <b>{twitch_username}</b> успешно привязан!",
                    parse_mode='HTML'
                )
            else:
                bot.send_message(message.chat.id, "❌ Ошибка привязки аккаунта")

        except Exception as e:
            print(f"Ошибка привязки Twitch: {e}")
            bot.send_message(message.chat.id, "❌ Произошла ошибка")