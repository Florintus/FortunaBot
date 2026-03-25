import traceback
from html import escape
from telebot.types import CallbackQuery
from bot.services.giveaway_service import GiveawayService
from bot.services.subscription_checker import SubscriptionChecker
from bot.services.twitch_service import twitch_service
from bot.keyboards.inline import get_twitch_device_poll_keyboard
from bot.utils.twitch_parse import normalize_twitch_channel_login

bot = None


def register_user_handlers(telegram_bot):
    """Регистрация обработчиков пользователей"""
    global bot
    bot = telegram_bot

    @bot.callback_query_handler(func=lambda call: call.data == "twitch_auth_poll")
    def twitch_auth_poll(call: CallbackQuery):
        status, detail = twitch_service.poll_device_auth(call.from_user.id)
        if status == "success":
            bot.answer_callback_query(call.id, f"✅ Привязано: {detail}")
            bot.send_message(
                call.message.chat.id,
                f"✅ Twitch <b>{detail}</b> привязан. Можно участвовать в розыгрышах.",
                parse_mode="HTML",
            )
        elif status == "pending":
            bot.answer_callback_query(
                call.id,
                "Ещё не подтверждено на Twitch. Введите код на сайте и нажмите снова.",
                show_alert=True,
            )
        elif status == "wait":
            bot.answer_callback_query(
                call.id,
                f"Подождите ~{detail} с и нажмите снова.",
                show_alert=True,
            )
        elif status == "expired":
            bot.answer_callback_query(call.id, "Срок кода истёк. Отправьте /link_twitch снова.", show_alert=True)
        elif status == "denied":
            bot.answer_callback_query(call.id, "Авторизация отклонена.", show_alert=True)
        elif status == "no_session":
            bot.answer_callback_query(call.id, "Нет активной привязки. Отправьте /link_twitch", show_alert=True)
        else:
            bot.answer_callback_query(call.id, detail or "Ошибка", show_alert=True)

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

            # Проверяем Twitch (OAuth Device Flow + user:read:follows)
            if giveaway['twitch_channels']:
                if not twitch_service.is_configured():
                    bot.answer_callback_query(
                        call.id,
                        "❌ Проверка Twitch недоступна (бот не настроен).",
                        show_alert=True,
                    )
                    return

                if not twitch_service.has_oauth_link(user.id):
                    bot.answer_callback_query(
                        call.id,
                        "❌ Нужна привязка Twitch через сайт!",
                        show_alert=True,
                    )
                    bot.send_message(
                        user.id,
                        "🎮 Для участия привяжите Twitch через OAuth:\n\n"
                        "Отправьте команду <b>/link_twitch</b> (без аргументов) — "
                        "бот пришлёт ссылку и код для входа на twitch.tv.\n\n"
                        "Старая привязка только по нику без входа не даёт проверить подписки.",
                        parse_mode="HTML",
                    )
                    return

                missing_twitch = []
                for channel in giveaway['twitch_channels']:
                    if not twitch_service.check_follows_channel(user.id, channel):
                        missing_twitch.append(
                            normalize_twitch_channel_login(channel) or channel
                        )

                if missing_twitch:
                    missing_text = "\n".join([f"• https://twitch.tv/{ch}" for ch in missing_twitch])
                    bot.answer_callback_query(
                        call.id,
                        "❌ Необходимо подписаться на Twitch каналы!",
                        show_alert=True
                    )
                    bot.send_message(
                        user.id,
                        f"🎮 Подпишитесь (follow) на каналы в Twitch:\n\n{missing_text}"
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
        """Привязка Twitch: OAuth (без аргументов) или устаревший ввод ника."""
        try:
            parts = message.text.split(maxsplit=1)

            if len(parts) < 2:
                if not twitch_service.is_configured():
                    bot.send_message(
                        message.chat.id,
                        "❌ Twitch OAuth не настроен: нужны <b>TWITCH_CLIENT_ID</b> и "
                        "<b>TWITCH_CLIENT_SECRET</b> в окружении (или в .env для Docker Compose). "
                        "Явное выключение: <code>TWITCH_DISABLED=true</code> или "
                        "<code>TWITCH_ENABLED=false</code>.",
                        parse_mode="HTML",
                    )
                    return
                info = twitch_service.start_device_auth(message.from_user.id)
                if not info:
                    bot.send_message(
                        message.chat.id,
                        "❌ Не удалось начать привязку Twitch. Попробуйте позже.",
                    )
                    return
                uri = info["verification_uri"]
                code = info["user_code"]
                safe_uri = escape(uri)
                safe_code = escape(code)
                bot.send_message(
                    message.chat.id,
                    "🎮 <b>Привязка Twitch</b>\n\n"
                    f'1. Откройте: <a href="{safe_uri}">{safe_uri}</a>\n'
                    f"2. Введите код: <code>{safe_code}</code>\n\n"
                    "После входа на Twitch нажмите кнопку ниже.",
                    parse_mode="HTML",
                    reply_markup=get_twitch_device_poll_keyboard(),
                    disable_web_page_preview=True,
                )
                return

            twitch_username = parts[1].strip().replace('@', '')
            ok = twitch_service.link_account_manual(message.from_user.id, twitch_username)

            if ok:
                bot.send_message(
                    message.chat.id,
                    f"⚠️ Ник <b>{twitch_username}</b> сохранён, но для розыгрышей нужен вход через Twitch.\n\n"
                    "Отправьте <b>/link_twitch</b> без текста и пройдите авторизацию по коду.",
                    parse_mode="HTML",
                )
            else:
                bot.send_message(message.chat.id, "❌ Ошибка привязки аккаунта")

        except Exception as e:
            print(f"Ошибка привязки Twitch: {e}")
            traceback.print_exc()
            hint = ""
            err = str(e).lower()
            if "no such table" in err or "undefinedtable" in err or "does not exist" in err:
                hint = "\n\nПерезапустите бота (нужна таблица <code>twitch_device_auth</code> в БД)."
            detail = escape(str(e))[:400]
            bot.send_message(
                message.chat.id,
                "❌ Ошибка при привязке Twitch. См. логи сервера.\n"
                f"<code>{detail}</code>" + hint,
                parse_mode="HTML",
            )
