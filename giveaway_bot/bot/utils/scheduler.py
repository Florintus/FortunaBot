from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from html import escape
import telebot
from bot.config import BOT_TOKEN
from bot.services.giveaway_service import GiveawayService
from bot.keyboards.inline import get_participate_button
from bot.utils.twitch_parse import normalize_twitch_channel_login

bot = telebot.TeleBot(BOT_TOKEN)
scheduler = BackgroundScheduler()


def _safe_text(value) -> str:
    """Экранирует пользовательский текст для Telegram HTML."""
    return escape(str(value or ""))


def publish_giveaway(giveaway_id: int):
    """Публикация розыгрыша в канале"""
    try:
        giveaway = GiveawayService.get_giveaway(giveaway_id)
        if not giveaway or giveaway['is_published']:
            return

        channel_id = giveaway.get('channel_id')
        if not channel_id:
            print(f"❌ Розыгрыш {giveaway_id}: не указан канал публикации")
            return

        text = f"🎉 <b>{_safe_text(giveaway['title'])}</b>\n\n"
        text += f"{_safe_text(giveaway['description'])}\n\n"
        text += f"👥 Победителей: {giveaway['winners_count']}\n"
        text += f"⏰ Окончание: {giveaway['end_time'].strftime('%d.%m.%Y %H:%M')} UTC\n\n"
        text += "📋 <b>Условия участия:</b>\n"
        for channel in giveaway['required_channels']:
            text += f"• Подписаться на {_safe_text(channel)}\n"

        if giveaway['twitch_channels']:
            text += "\n🎮 <b>Twitch (follow):</b>\n"
            for channel in giveaway['twitch_channels']:
                login = normalize_twitch_channel_login(channel) or channel
                url = f"https://twitch.tv/{login}"
                text += f'• <a href="{escape(url)}">{_safe_text(login)}</a>\n'

        markup = get_participate_button(giveaway['id'])

        if giveaway['photo_file_id']:
            msg = bot.send_photo(
                channel_id,
                giveaway['photo_file_id'],
                caption=text,
                parse_mode='HTML',
                reply_markup=markup
            )
        elif giveaway['document_file_id']:
            msg = bot.send_document(
                channel_id,
                giveaway['document_file_id'],
                caption=text,
                parse_mode='HTML',
                reply_markup=markup
            )
        else:
            msg = bot.send_message(
                channel_id,
                text,
                parse_mode='HTML',
                reply_markup=markup
            )

        GiveawayService.update_message_id(giveaway['id'], msg.message_id)
        print(f"✅ Розыгрыш {giveaway_id} опубликован в {channel_id}")

    except Exception as e:
        print(f"❌ Ошибка публикации розыгрыша {giveaway_id}: {e}")


def finish_giveaway(giveaway_id: int):
    """Подведение итогов розыгрыша"""
    try:
        giveaway = GiveawayService.get_giveaway(giveaway_id)
        if not giveaway or giveaway['is_finished']:
            return

        channel_id = giveaway.get('channel_id')
        winners = GiveawayService.select_winners(giveaway_id)

        text = f"🏆 <b>Итоги розыгрыша: {_safe_text(giveaway['title'])}</b>\n\n"

        if winners:
            text += "🎊 <b>Победители:</b>\n\n"
            for i, winner in enumerate(winners, 1):
                username = (
                    f"@{_safe_text(winner['username'])}"
                    if winner['username']
                    else _safe_text(winner['full_name'])
                )
                text += f"{i}. {username}\n"
            text += "\n✉️ Победители будут уведомлены в личных сообщениях!"
        else:
            text += "😔 К сожалению, не было участников."

        if channel_id:
            bot.send_message(channel_id, text, parse_mode='HTML')

        for winner in winners:
            try:
                bot.send_message(
                    winner['user_id'],
                    f"🎉 <b>Поздравляем!</b>\n\n"
                    f"Вы выиграли в розыгрыше:\n<b>{_safe_text(giveaway['title'])}</b>\n\n"
                    f"Организатор свяжется с вами в ближайшее время!",
                    parse_mode='HTML'
                )
            except Exception:
                pass

        print(f"✅ Розыгрыш {giveaway_id} завершён, победителей: {len(winners)}")

    except Exception as e:
        print(f"❌ Ошибка завершения розыгрыша {giveaway_id}: {e}")


def check_giveaways():
    """Проверка розыгрышей для публикации и завершения"""
    try:
        now = datetime.utcnow()

        for giveaway in GiveawayService.get_active_giveaways():
            job_id = f"publish_{giveaway['id']}"
            if scheduler.get_job(job_id):
                continue
            run_date = giveaway['start_time']
            # Если время уже прошло — публикуем немедленно
            if run_date <= now:
                print(f"⚡ Розыгрыш {giveaway['id']}: время начала прошло, публикуем сразу")
                publish_giveaway(giveaway['id'])
            else:
                scheduler.add_job(
                    publish_giveaway,
                    'date',
                    run_date=run_date,
                    args=[giveaway['id']],
                    id=job_id,
                    replace_existing=True,
                    misfire_grace_time=3600
                )

        for giveaway in GiveawayService.get_finished_giveaways():
            job_id = f"finish_{giveaway['id']}"
            if scheduler.get_job(job_id):
                continue
            run_date = giveaway['end_time']
            if run_date <= now:
                print(f"⚡ Розыгрыш {giveaway['id']}: время конца прошло, завершаем сразу")
                finish_giveaway(giveaway['id'])
            else:
                scheduler.add_job(
                    finish_giveaway,
                    'date',
                    run_date=run_date,
                    args=[giveaway['id']],
                    id=job_id,
                    replace_existing=True,
                    misfire_grace_time=3600
                )

    except Exception as e:
        print(f"❌ Ошибка check_giveaways: {e}")


def cancel_giveaway_jobs(giveaway_id: int):
    """Снимает отложенные publish/finish для розыгрыша (например перед досрочным завершением)."""
    for jid in (f"publish_{giveaway_id}", f"finish_{giveaway_id}"):
        try:
            if scheduler.get_job(jid):
                scheduler.remove_job(jid)
        except Exception:
            pass


def run_finish_giveaway_now(giveaway_id: int):
    """Досрочно подвести итоги: отменить задачи планировщика и вызвать finish_giveaway."""
    cancel_giveaway_jobs(giveaway_id)
    finish_giveaway(giveaway_id)


def start_scheduler():
    """Запуск планировщика"""
    scheduler.add_job(check_giveaways, 'interval', minutes=1, id='check_giveaways')
    scheduler.start()
    print("✅ Планировщик запущен")
    # Сразу проверяем при старте не дожидаясь первой минуты
    check_giveaways()
