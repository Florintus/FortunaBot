from datetime import datetime, timedelta
from html import escape
import logging
import telebot
from telebot.types import Message, CallbackQuery
from bot.config import ADMIN_IDS
from bot.keyboards.inline import (
    get_admin_menu, get_confirm_keyboard, get_skip_button,
    get_giveaway_list_keyboard, get_calendar_keyboard,
    get_time_keyboard, get_duration_keyboard,
    get_giveaway_view_keyboard, get_confirm_delete_keyboard,
    wizard_back_only_keyboard, get_media_step_keyboard,
    get_early_end_confirm_keyboard,
)
from bot.utils.states import FSMContext, States
from bot.utils.twitch_parse import normalize_twitch_channel_login
from bot.services.giveaway_service import GiveawayService
from bot.utils.scheduler import run_finish_giveaway_now

bot = None

# Шаг 5 (Twitch): текст в двух местах — переход с шага 4 и возврат «Назад» с шага 6
_MSG_STEP5_TWITCH = (
    "🎮 <b>Шаг 5 из 8</b> — Twitch каналы\n\n"
    "Укажите каналы: <b>логин</b> или целиком ссылку "
    "<code>https://www.twitch.tv/ник</code> — <b>по одному на строку</b>.\n"
    "Из ссылки бот возьмёт только логин (ссылки в посте и при проверке будут верными).\n\n"
    "Если Twitch не нужен — «Пропустить»."
)


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def _callback_answer_text(text: str, max_len: int = 200) -> str:
    """Telegram answerCallbackQuery: не более 200 символов."""
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def register_admin_handlers(telegram_bot):
    global bot
    bot = telegram_bot

    def _parse_time_input(text: str, fallback_date: str = None) -> tuple:
        """
        Парсит ввод времени в разных форматах.
        Возвращает (hh, mm, year, month, day) или бросает ValueError.
        Поддерживает: 'ЧЧ:ММ', 'ДД.ММ.ГГГГ ЧЧ:ММ', 'ДД,ММ,ГГГГ ЧЧ:ММ'
        """
        text = text.strip().replace(',', '.')
        # Полный формат: ДД.ММ.ГГГГ ЧЧ:ММ
        for fmt in ('%d.%m.%Y %H:%M', '%d.%m.%y %H:%M'):
            try:
                dt = __import__('datetime').datetime.strptime(text, fmt)
                return dt.hour, dt.minute, dt.year, dt.month, dt.day
            except ValueError:
                pass
        # Только время: ЧЧ:ММ
        if ':' in text and len(text) <= 5:
            hh, mm = map(int, text.split(':'))
            if not (0 <= hh <= 23 and 0 <= mm <= 59):
                raise ValueError
            if fallback_date:
                year, month, day = map(int, fallback_date.split('_'))
            else:
                raise ValueError("no date")
            return hh, mm, year, month, day
        raise ValueError("unknown format")

    # ─────────────────────────────────────────
    #  Меню
    # ─────────────────────────────────────────

    @bot.message_handler(commands=['start', 'menu'])
    def start_command(message: Message):
        if not is_admin(message.from_user.id):
            bot.send_message(message.chat.id, "❌ У вас нет доступа к этому боту.")
            return
        bot.send_message(
            message.chat.id,
            "👋 Добро пожаловать в панель управления розыгрышами!\n\nВыберите действие:",
            reply_markup=get_admin_menu()
        )

    # ─────────────────────────────────────────
    #  Шаг 1: Канал публикации
    # ─────────────────────────────────────────

    @bot.callback_query_handler(func=lambda call: call.data == "create_giveaway")
    def create_giveaway_start(call: CallbackQuery):
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Нет доступа")
            return
        FSMContext.set_state(call.from_user.id, States.WAITING_CHANNEL)
        bot.edit_message_text(
            "📢 <b>Шаг 1 из 8</b> — Канал публикации\n\n"
            "В какой канал/группу публиковать розыгрыш?\n\n"
            "Введите @username или ID канала:\n"
            "Например: <code>@my_channel</code> или <code>-1001234567890</code>\n\n"
            "⚠️ Бот должен быть администратором в канале!",
            call.message.chat.id,
            call.message.message_id,
            parse_mode='HTML'
        )

    @bot.message_handler(func=lambda msg: FSMContext.get_state(msg.from_user.id)[0] == States.WAITING_CHANNEL)
    def get_channel(message: Message):
        channel = message.text.strip()
        try:
            chat = bot.get_chat(channel)
            bot_member = bot.get_chat_member(channel, bot.get_me().id)
            if bot_member.status not in ['administrator', 'creator']:
                bot.send_message(
                    message.chat.id,
                    "❌ Бот не является администратором в этом канале!\n"
                    "Добавьте бота как администратора и попробуйте снова."
                )
                return
            FSMContext.update_data(message.from_user.id, {
                'channel_id': channel,
                'channel_title': chat.title or channel
            })
            FSMContext.set_state(message.from_user.id, States.WAITING_TITLE)
            bot.send_message(
                message.chat.id,
                f"✅ Канал <b>{chat.title or channel}</b> выбран!\n\n"
                f"📝 <b>Шаг 2 из 8</b> — Введите название розыгрыша:",
                parse_mode='HTML',
                reply_markup=wizard_back_only_keyboard(),
            )
        except Exception as e:
            bot.send_message(
                message.chat.id,
                f"❌ Не удалось получить доступ к каналу.\n"
                f"Проверьте @username и права бота.\n\nОшибка: <code>{e}</code>",
                parse_mode='HTML'
            )

    # ─────────────────────────────────────────
    #  Шаг 2: Название
    # ─────────────────────────────────────────

    @bot.message_handler(func=lambda msg: FSMContext.get_state(msg.from_user.id)[0] == States.WAITING_TITLE)
    def get_title(message: Message):
        FSMContext.update_data(message.from_user.id, {'title': message.text})
        FSMContext.set_state(message.from_user.id, States.WAITING_DESCRIPTION)
        bot.send_message(
            message.chat.id,
            "📄 <b>Шаг 3 из 8</b> — Введите описание розыгрыша:",
            parse_mode='HTML',
            reply_markup=wizard_back_only_keyboard(),
        )

    # ─────────────────────────────────────────
    #  Шаг 3: Описание
    # ─────────────────────────────────────────

    @bot.message_handler(func=lambda msg: FSMContext.get_state(msg.from_user.id)[0] == States.WAITING_DESCRIPTION)
    def get_description(message: Message):
        FSMContext.update_data(message.from_user.id, {'description': message.text})
        FSMContext.set_state(message.from_user.id, States.WAITING_CHANNELS)
        bot.send_message(
            message.chat.id,
            "📺 <b>Шаг 4 из 8</b> — Обязательные каналы для подписки\n\n"
            "Введите список каналов по одному на строку:\n"
            "Формат: <code>@channel_username</code> или <code>-100123456789</code>\n\n"
            "Например:\n<code>@my_channel\n@another_channel</code>",
            parse_mode='HTML',
            reply_markup=wizard_back_only_keyboard(),
        )

    # ─────────────────────────────────────────
    #  Шаг 4: Каналы подписки
    # ─────────────────────────────────────────

    @bot.message_handler(func=lambda msg: FSMContext.get_state(msg.from_user.id)[0] == States.WAITING_CHANNELS)
    def get_channels(message: Message):
        channels = [ch.strip() for ch in message.text.split('\n') if ch.strip()]
        if not channels:
            bot.send_message(message.chat.id, "❌ Нужно указать хотя бы один канал!")
            return
        FSMContext.update_data(message.from_user.id, {'required_channels': channels})
        FSMContext.set_state(message.from_user.id, States.WAITING_TWITCH)
        bot.send_message(
            message.chat.id,
            _MSG_STEP5_TWITCH,
            parse_mode="HTML",
            reply_markup=get_skip_button("skip_twitch", with_wizard_back=True),
        )

    # ─────────────────────────────────────────
    #  Шаг 5: Twitch
    # ─────────────────────────────────────────

    @bot.callback_query_handler(func=lambda call: call.data == "skip_twitch")
    def skip_twitch(call: CallbackQuery):
        state, _ = FSMContext.get_state(call.from_user.id)
        if state != States.WAITING_TWITCH:
            bot.answer_callback_query(call.id)
            return
        bot.answer_callback_query(call.id)
        FSMContext.update_data(call.from_user.id, {'twitch_channels': []})
        FSMContext.set_state(call.from_user.id, States.WAITING_WINNERS)
        bot.send_message(
            call.message.chat.id,
            "🏆 <b>Шаг 6 из 8</b> — Введите количество победителей:",
            parse_mode='HTML',
            reply_markup=wizard_back_only_keyboard(),
        )

    @bot.message_handler(func=lambda msg: FSMContext.get_state(msg.from_user.id)[0] == States.WAITING_TWITCH)
    def get_twitch(message: Message):
        raw_lines = [ch.strip() for ch in message.text.split("\n") if ch.strip()]
        seen: set[str] = set()
        channels: list[str] = []
        for line in raw_lines:
            login = normalize_twitch_channel_login(line)
            if login and login not in seen:
                seen.add(login)
                channels.append(login)
        if raw_lines and not channels:
            bot.send_message(
                message.chat.id,
                "❌ Не удалось распознать каналы. Укажите логин или полную ссылку "
                "<code>https://www.twitch.tv/ник</code> — по одному на строку.",
                parse_mode="HTML",
            )
            return
        FSMContext.update_data(message.from_user.id, {"twitch_channels": channels})
        FSMContext.set_state(message.from_user.id, States.WAITING_WINNERS)
        bot.send_message(
            message.chat.id,
            "🏆 <b>Шаг 6 из 8</b> — Введите количество победителей:",
            parse_mode='HTML',
            reply_markup=wizard_back_only_keyboard(),
        )

    # ─────────────────────────────────────────
    #  Шаг 6: Победители
    # ─────────────────────────────────────────

    @bot.message_handler(func=lambda msg: FSMContext.get_state(msg.from_user.id)[0] == States.WAITING_WINNERS)
    def get_winners_count(message: Message):
        try:
            count = int(message.text)
            if count < 1:
                raise ValueError
            FSMContext.update_data(message.from_user.id, {'winners_count': count})
            FSMContext.set_state(message.from_user.id, States.WAITING_MEDIA)
            bot.send_message(
                message.chat.id,
                "🖼 <b>Шаг 7 из 8</b> — Медиа\n\n"
                "Отправьте <b>одно фото</b> или <b>один файл</b> в этот чат "
                "(в клиенте Telegram нажмите 📎 рядом с полем ввода).\n\n"
                "Кнопка ниже открывает подсказку, если не видно, как прикрепить файл.\n"
                "Или нажмите «Пропустить», если медиа не нужно.",
                parse_mode="HTML",
                reply_markup=get_media_step_keyboard(with_wizard_back=True),
            )
        except ValueError:
            bot.send_message(message.chat.id, "❌ Введите целое число больше 0!")

    # ─────────────────────────────────────────
    #  Шаг 7: Медиа
    # ─────────────────────────────────────────

    @bot.callback_query_handler(func=lambda call: call.data == "media_help")
    def media_help(call: CallbackQuery):
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id)
            return
        state, _ = FSMContext.get_state(call.from_user.id)
        if state != States.WAITING_MEDIA:
            bot.answer_callback_query(call.id)
            return
        bot.answer_callback_query(call.id)
        bot.send_message(
            call.message.chat.id,
            "📎 <b>Как прикрепить фото или файл</b>\n\n"
            "1. Нажмите значок <b>скрепки</b> (📎) слева от поля ввода сообщения.\n"
            "2. Выберите «Фото» или «Файл» и отправьте одно вложение боту.\n\n"
            "В веб-версии Telegram: кнопка вложения обычно рядом с полем чата.\n\n"
            "Бот не может открыть галерею по кнопке — только так.",
            parse_mode="HTML",
        )

    @bot.callback_query_handler(func=lambda call: call.data == "skip_media")
    def skip_media(call: CallbackQuery):
        state, _ = FSMContext.get_state(call.from_user.id)
        if state != States.WAITING_MEDIA:
            bot.answer_callback_query(call.id)
            return
        bot.answer_callback_query(call.id)
        _ask_start_time(call.from_user.id, call.message.chat.id)

    @bot.message_handler(content_types=['photo'], func=lambda msg: FSMContext.get_state(msg.from_user.id)[0] == States.WAITING_MEDIA)
    def get_photo(message: Message):
        FSMContext.update_data(message.from_user.id, {'photo_file_id': message.photo[-1].file_id})
        _ask_start_time(message.from_user.id, message.chat.id)

    @bot.message_handler(content_types=['document'], func=lambda msg: FSMContext.get_state(msg.from_user.id)[0] == States.WAITING_MEDIA)
    def get_document(message: Message):
        FSMContext.update_data(message.from_user.id, {'document_file_id': message.document.file_id})
        _ask_start_time(message.from_user.id, message.chat.id)

    # ─────────────────────────────────────────
    #  Шаг 8а: Дата начала — календарь
    # ─────────────────────────────────────────

    def _ask_start_time(user_id: int, chat_id: int):
        FSMContext.set_state(user_id, States.WAITING_START_TIME)
        now = datetime.utcnow()
        bot.send_message(
            chat_id,
            "📅 <b>Шаг 8 из 8</b> — Дата и время начала\n\nВыберите дату:",
            parse_mode='HTML',
            reply_markup=get_calendar_keyboard(now.year, now.month, 'start')
        )

    # Навигация по календарю
    @bot.callback_query_handler(func=lambda call: call.data.startswith("cal_start_nav_"))
    def calendar_start_nav(call: CallbackQuery):
        # cal_start_nav_YEAR_MONTH
        _, _, _, year, month = call.data.split('_')
        bot.edit_message_reply_markup(
            call.message.chat.id,
            call.message.message_id,
            reply_markup=get_calendar_keyboard(int(year), int(month), 'start')
        )
        bot.answer_callback_query(call.id)

    # Выбор дня начала
    @bot.callback_query_handler(func=lambda call: call.data.startswith("cal_start_day_"))
    def calendar_start_day(call: CallbackQuery):
        _, _, _, year, month, day = call.data.split('_')
        bot.edit_message_reply_markup(
            call.message.chat.id,
            call.message.message_id,
            reply_markup=get_time_keyboard(int(year), int(month), int(day), 'start')
        )
        bot.answer_callback_query(call.id)

    # Выбор времени начала (кнопкой)
    @bot.callback_query_handler(func=lambda call: call.data.startswith("cal_start_time_"))
    def calendar_start_time(call: CallbackQuery):
        parts = call.data.split('_')
        # cal_start_time_YEAR_MONTH_DAY_HH_MM
        year, month, day, hh, mm = int(parts[3]), int(parts[4]), int(parts[5]), int(parts[6]), int(parts[7])
        start_time = datetime(year, month, day, hh, mm)
        FSMContext.update_data(call.from_user.id, {'start_time': start_time})
        bot.answer_callback_query(call.id, f"✅ Начало: {start_time.strftime('%d.%m.%Y %H:%M')}")
        _ask_end_time(call.from_user.id, call.message.chat.id, call.message.message_id, start_time)

    # Ручной ввод времени начала
    @bot.callback_query_handler(func=lambda call: call.data.startswith("cal_start_manual_"))
    def calendar_start_manual(call: CallbackQuery):
        parts = call.data.split('_')
        year, month, day = int(parts[3]), int(parts[4]), int(parts[5])
        FSMContext.update_data(call.from_user.id, {'_pending_start_date': f"{year}_{month}_{day}"})
        FSMContext.set_state(call.from_user.id, States.WAITING_START_MANUAL)
        bot.edit_message_text(
            f"✏️ Введите время начала для <b>{day:02d}.{month:02d}.{year}</b>\n\n"
            f"Формат: <code>ЧЧ:ММ</code> (например: <code>15:30</code>)",
            call.message.chat.id,
            call.message.message_id,
            parse_mode='HTML',
            reply_markup=wizard_back_only_keyboard(),
        )
        bot.answer_callback_query(call.id)

    @bot.message_handler(func=lambda msg: FSMContext.get_state(msg.from_user.id)[0] == States.WAITING_START_MANUAL)
    def get_start_manual(message: Message):
        _, data = FSMContext.get_state(message.from_user.id)
        try:
            hh, mm, year, month, day = _parse_time_input(message.text, data.get('_pending_start_date'))
            start_time = datetime(year, month, day, hh, mm)
            FSMContext.update_data(message.from_user.id, {'start_time': start_time})
            FSMContext.set_state(message.from_user.id, States.WAITING_END_TIME)
            bot.send_message(
                message.chat.id,
                f"✅ Начало: <b>{start_time.strftime('%d.%m.%Y %H:%M')}</b>\n\n"
                f"Теперь выберите дату и время окончания:",
                parse_mode='HTML',
                reply_markup=get_duration_keyboard()
            )
        except (ValueError, KeyError):
            bot.send_message(
                message.chat.id,
                "❌ Не распознал формат!\n\n"
                "Введите только время: <code>15:30</code>\n"
                "или дату и время: <code>21.03.2026 15:30</code>",
                parse_mode='HTML'
            )

    # Возврат к календарю начала
    @bot.callback_query_handler(func=lambda call: call.data == "cal_start_back")
    def calendar_start_back(call: CallbackQuery):
        now = datetime.utcnow()
        FSMContext.set_state(call.from_user.id, States.WAITING_START_TIME)
        bot.edit_message_text(
            "📅 Выберите дату начала:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=get_calendar_keyboard(now.year, now.month, 'start')
        )
        bot.answer_callback_query(call.id)

    # ─────────────────────────────────────────
    #  Шаг 8б: Дата окончания
    # ─────────────────────────────────────────

    def _ask_end_time(user_id: int, chat_id: int, message_id: int, start_time: datetime):
        FSMContext.set_state(user_id, States.WAITING_END_TIME)
        bot.edit_message_text(
            f"✅ Начало: <b>{start_time.strftime('%d.%m.%Y %H:%M')}</b>\n\n"
            f"⏱ Выберите длительность розыгрыша или укажите дату окончания вручную:",
            chat_id,
            message_id,
            parse_mode='HTML',
            reply_markup=get_duration_keyboard()
        )

    # Быстрый выбор длительности
    @bot.callback_query_handler(func=lambda call: call.data.startswith("dur_end_") and call.data != "dur_end_custom")
    def duration_quick(call: CallbackQuery):
        _, data = FSMContext.get_state(call.from_user.id)
        start_time = data.get('start_time')
        if not start_time:
            bot.answer_callback_query(call.id, "❌ Сначала выберите дату начала")
            return

        delta_map = {
            'dur_end_1h':  timedelta(hours=1),
            'dur_end_3h':  timedelta(hours=3),
            'dur_end_12h': timedelta(hours=12),
            'dur_end_1d':  timedelta(days=1),
            'dur_end_3d':  timedelta(days=3),
            'dur_end_7d':  timedelta(days=7),
        }
        delta = delta_map.get(call.data)
        if not delta:
            return

        end_time = start_time + delta
        FSMContext.update_data(call.from_user.id, {'end_time': end_time})
        bot.answer_callback_query(call.id, f"✅ Конец: {end_time.strftime('%d.%m.%Y %H:%M')}")
        _finish_dates(call.from_user.id, call.message.chat.id, call.message.message_id, start_time, end_time)

    # Ручной выбор даты окончания через календарь
    @bot.callback_query_handler(func=lambda call: call.data == "dur_end_custom")
    def duration_custom(call: CallbackQuery):
        _, data = FSMContext.get_state(call.from_user.id)
        start_time = data.get('start_time', datetime.utcnow())
        bot.edit_message_text(
            "📅 Выберите дату окончания:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=get_calendar_keyboard(start_time.year, start_time.month, 'end')
        )
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("cal_end_nav_"))
    def calendar_end_nav(call: CallbackQuery):
        # cal_end_nav_YEAR_MONTH
        _, _, _, year, month = call.data.split('_')
        bot.edit_message_reply_markup(
            call.message.chat.id,
            call.message.message_id,
            reply_markup=get_calendar_keyboard(int(year), int(month), 'end')
        )
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("cal_end_day_"))
    def calendar_end_day(call: CallbackQuery):
        _, _, _, year, month, day = call.data.split('_')
        bot.edit_message_reply_markup(
            call.message.chat.id,
            call.message.message_id,
            reply_markup=get_time_keyboard(int(year), int(month), int(day), 'end')
        )
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("cal_end_time_"))
    def calendar_end_time(call: CallbackQuery):
        parts = call.data.split('_')
        year, month, day, hh, mm = int(parts[3]), int(parts[4]), int(parts[5]), int(parts[6]), int(parts[7])
        end_time = datetime(year, month, day, hh, mm)
        _, data = FSMContext.get_state(call.from_user.id)
        start_time = data.get('start_time')

        if start_time and end_time <= start_time:
            bot.answer_callback_query(call.id, "❌ Дата окончания должна быть позже начала!", show_alert=True)
            return

        FSMContext.update_data(call.from_user.id, {'end_time': end_time})
        bot.answer_callback_query(call.id, f"✅ Конец: {end_time.strftime('%d.%m.%Y %H:%M')}")
        _finish_dates(call.from_user.id, call.message.chat.id, call.message.message_id, start_time, end_time)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("cal_end_manual_"))
    def calendar_end_manual(call: CallbackQuery):
        parts = call.data.split('_')
        year, month, day = int(parts[3]), int(parts[4]), int(parts[5])
        FSMContext.update_data(call.from_user.id, {'_pending_end_date': f"{year}_{month}_{day}"})
        FSMContext.set_state(call.from_user.id, States.WAITING_END_MANUAL)
        bot.edit_message_text(
            f"✏️ Введите время окончания для <b>{day:02d}.{month:02d}.{year}</b>\n\n"
            f"Формат: <code>ЧЧ:ММ</code> (например: <code>23:59</code>)",
            call.message.chat.id,
            call.message.message_id,
            parse_mode='HTML',
            reply_markup=wizard_back_only_keyboard(),
        )
        bot.answer_callback_query(call.id)

    @bot.message_handler(func=lambda msg: FSMContext.get_state(msg.from_user.id)[0] == States.WAITING_END_MANUAL)
    def get_end_manual(message: Message):
        _, data = FSMContext.get_state(message.from_user.id)
        try:
            hh, mm, year, month, day = _parse_time_input(message.text, data.get('_pending_end_date'))
            end_time = datetime(year, month, day, hh, mm)
            start_time = data.get('start_time')

            if start_time and end_time <= start_time:
                bot.send_message(message.chat.id, "❌ Дата окончания должна быть позже начала!")
                return

            FSMContext.update_data(message.from_user.id, {'end_time': end_time})
            _, data = FSMContext.get_state(message.from_user.id)
            show_confirmation(message.chat.id, message.from_user.id, data)
        except (ValueError, KeyError):
            bot.send_message(
                message.chat.id,
                "❌ Не распознал формат!\n\n"
                "Введите только время: <code>23:59</code>\n"
                "или дату и время: <code>25.03.2026 23:59</code>",
                parse_mode='HTML'
            )

    def _finish_dates(user_id: int, chat_id: int, message_id: int, start_time: datetime, end_time: datetime):
        """Даты выбраны — показываем подтверждение."""
        _, data = FSMContext.get_state(user_id)
        bot.edit_message_text(
            f"✅ Начало: <b>{start_time.strftime('%d.%m.%Y %H:%M')}</b>\n"
            f"✅ Конец: <b>{end_time.strftime('%d.%m.%Y %H:%M')}</b>\n\n"
            f"Формирую подтверждение...",
            chat_id,
            message_id,
            parse_mode='HTML'
        )
        show_confirmation(chat_id, user_id, data)

    # ─────────────────────────────────────────
    #  Подтверждение и публикация
    # ─────────────────────────────────────────

    def show_confirmation(chat_id: int, user_id: int, data: dict):
        FSMContext.set_state(user_id, States.CONFIRM, data)

        text = "📋 <b>Проверьте данные розыгрыша:</b>\n\n"
        text += f"📢 <b>Канал:</b> {data.get('channel_title', data.get('channel_id', '—'))}\n"
        text += f"📝 <b>Название:</b> {data['title']}\n"
        text += f"📄 <b>Описание:</b> {data['description']}\n"
        text += f"🕐 <b>Начало:</b> {data['start_time'].strftime('%d.%m.%Y %H:%M')} UTC\n"
        text += f"🕐 <b>Конец:</b> {data['end_time'].strftime('%d.%m.%Y %H:%M')} UTC\n"
        text += f"🏆 <b>Победителей:</b> {data['winners_count']}\n\n"
        text += "<b>📺 Обязательные каналы:</b>\n"
        for ch in data['required_channels']:
            text += f"• {ch}\n"
        if data.get('twitch_channels'):
            text += "\n<b>🎮 Twitch каналы:</b>\n"
            for ch in data['twitch_channels']:
                text += f"• {ch}\n"

        bot.send_message(chat_id, text, parse_mode='HTML', reply_markup=get_confirm_keyboard())

    @bot.callback_query_handler(func=lambda call: call.data == "confirm_publish")
    def confirm_publish(call: CallbackQuery):
        state, data = FSMContext.get_state(call.from_user.id)
        if state != States.CONFIRM:
            return
        try:
            giveaway_data = {
                'creator_id': call.from_user.id,
                'title': data['title'],
                'description': data['description'],
                'start_time': data['start_time'],
                'end_time': data['end_time'],
                'required_channels': data['required_channels'],
                'twitch_channels': data.get('twitch_channels', []),
                'winners_count': data['winners_count'],
                'photo_file_id': data.get('photo_file_id'),
                'document_file_id': data.get('document_file_id'),
                'channel_id': data['channel_id'],
            }
            giveaway = GiveawayService.create_giveaway(giveaway_data)
            FSMContext.clear_state(call.from_user.id)
            bot.edit_message_text(
                f"✅ Розыгрыш создан!\n\n"
                f"ID: {giveaway['id']}\n"
                f"Канал: {data.get('channel_title', data['channel_id'])}\n"
                f"Публикация: {giveaway['start_time'].strftime('%d.%m.%Y %H:%M')} UTC\n"
                f"Завершение: {giveaway['end_time'].strftime('%d.%m.%Y %H:%M')} UTC",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=get_admin_menu()
            )
        except Exception as e:
            logging.exception("confirm_publish")
            bot.answer_callback_query(
                call.id,
                _callback_answer_text(f"❌ Ошибка: {e}"),
                show_alert=True,
            )

    @bot.callback_query_handler(func=lambda call: call.data == "cancel_giveaway")
    def cancel_giveaway(call: CallbackQuery):
        FSMContext.clear_state(call.from_user.id)
        bot.edit_message_text(
            "❌ Создание розыгрыша отменено",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=get_admin_menu()
        )

    @bot.callback_query_handler(func=lambda call: call.data == "dur_end_back")
    def dur_end_back(call: CallbackQuery):
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id)
            return
        _, data = FSMContext.get_state(call.from_user.id)
        start_time = data.get("start_time")
        if not start_time:
            bot.answer_callback_query(call.id, "Сначала выберите дату начала", show_alert=True)
            return
        FSMContext.set_state(call.from_user.id, States.WAITING_END_TIME)
        bot.edit_message_text(
            f"✅ Начало: <b>{start_time.strftime('%d.%m.%Y %H:%M')}</b>\n\n"
            f"⏱ Выберите длительность розыгрыша или укажите дату окончания вручную:",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="HTML",
            reply_markup=get_duration_keyboard(),
        )
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data == "wizard_back")
    def wizard_back_handler(call: CallbackQuery):
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Нет доступа")
            return

        state, data = FSMContext.get_state(call.from_user.id)
        chat_id = call.message.chat.id
        uid = call.from_user.id
        bot.answer_callback_query(call.id)

        if state in (None, States.WAITING_CHANNEL):
            bot.send_message(
                chat_id,
                "Это первый шаг. Укажите канал сообщением выше или откройте /menu.",
            )
            return

        if state == States.WAITING_TITLE:
            FSMContext.set_state(uid, States.WAITING_CHANNEL)
            bot.send_message(
                chat_id,
                "📢 <b>Шаг 1 из 8</b> — Канал публикации\n\n"
                "В какой канал/группу публиковать розыгрыш?\n\n"
                "Введите @username или ID канала:\n"
                "Например: <code>@my_channel</code> или <code>-1001234567890</code>\n\n"
                "⚠️ Бот должен быть администратором в канале!",
                parse_mode="HTML",
            )
            return

        if state == States.WAITING_DESCRIPTION:
            FSMContext.set_state(uid, States.WAITING_TITLE)
            bot.send_message(
                chat_id,
                "📝 <b>Шаг 2 из 8</b> — Введите название розыгрыша:",
                parse_mode="HTML",
                reply_markup=wizard_back_only_keyboard(),
            )
            return

        if state == States.WAITING_CHANNELS:
            FSMContext.set_state(uid, States.WAITING_DESCRIPTION)
            bot.send_message(
                chat_id,
                "📄 <b>Шаг 3 из 8</b> — Введите описание розыгрыша:",
                parse_mode="HTML",
                reply_markup=wizard_back_only_keyboard(),
            )
            return

        if state == States.WAITING_TWITCH:
            FSMContext.set_state(uid, States.WAITING_CHANNELS)
            bot.send_message(
                chat_id,
                "📺 <b>Шаг 4 из 8</b> — Обязательные каналы для подписки\n\n"
                "Введите список каналов по одному на строку:\n"
                "Формат: <code>@channel_username</code> или <code>-100123456789</code>\n\n"
                "Например:\n<code>@my_channel\n@another_channel</code>",
                parse_mode="HTML",
                reply_markup=wizard_back_only_keyboard(),
            )
            return

        if state == States.WAITING_WINNERS:
            FSMContext.set_state(uid, States.WAITING_TWITCH)
            bot.send_message(
                chat_id,
                _MSG_STEP5_TWITCH,
                parse_mode="HTML",
                reply_markup=get_skip_button("skip_twitch", with_wizard_back=True),
            )
            return

        if state == States.WAITING_MEDIA:
            FSMContext.set_state(uid, States.WAITING_WINNERS)
            bot.send_message(
                chat_id,
                "🏆 <b>Шаг 6 из 8</b> — Введите количество победителей:",
                parse_mode="HTML",
                reply_markup=wizard_back_only_keyboard(),
            )
            return

        if state == States.WAITING_START_TIME:
            FSMContext.update_data(
                uid,
                {
                    "start_time": None,
                    "end_time": None,
                    "_pending_start_date": None,
                    "_pending_end_date": None,
                },
            )
            FSMContext.set_state(uid, States.WAITING_MEDIA)
            bot.send_message(
                chat_id,
                "🖼 <b>Шаг 7 из 8</b> — Медиа\n\n"
                "Отправьте <b>одно фото</b> или <b>один файл</b> в этот чат "
                "(в клиенте Telegram нажмите 📎 рядом с полем ввода).\n\n"
                "Кнопка ниже открывает подсказку, если не видно, как прикрепить файл.\n"
                "Или нажмите «Пропустить», если медиа не нужно.",
                parse_mode="HTML",
                reply_markup=get_media_step_keyboard(with_wizard_back=True),
            )
            return

        if state == States.WAITING_START_MANUAL:
            FSMContext.update_data(uid, {"_pending_start_date": None})
            FSMContext.set_state(uid, States.WAITING_START_TIME)
            now = datetime.utcnow()
            bot.send_message(
                chat_id,
                "📅 <b>Шаг 8 из 8</b> — Дата и время начала\n\nВыберите дату:",
                parse_mode="HTML",
                reply_markup=get_calendar_keyboard(now.year, now.month, "start"),
            )
            return

        if state == States.WAITING_END_TIME:
            FSMContext.update_data(uid, {"end_time": None, "_pending_end_date": None})
            FSMContext.set_state(uid, States.WAITING_START_TIME)
            now = datetime.utcnow()
            bot.send_message(
                chat_id,
                "📅 Выберите дату и время <b>начала</b> розыгрыша:",
                parse_mode="HTML",
                reply_markup=get_calendar_keyboard(now.year, now.month, "start"),
            )
            return

        if state == States.WAITING_END_MANUAL:
            FSMContext.update_data(uid, {"_pending_end_date": None})
            FSMContext.set_state(uid, States.WAITING_END_TIME)
            st = data.get("start_time") or datetime.utcnow()
            bot.send_message(
                chat_id,
                f"✅ Начало: <b>{st.strftime('%d.%m.%Y %H:%M')}</b>\n\n"
                f"⏱ Выберите длительность розыгрыша или укажите дату окончания вручную:",
                parse_mode="HTML",
                reply_markup=get_duration_keyboard(),
            )
            return

        if state == States.CONFIRM:
            FSMContext.set_state(uid, States.WAITING_END_TIME)
            st = data.get("start_time")
            if not st:
                now = datetime.utcnow()
                FSMContext.set_state(uid, States.WAITING_START_TIME)
                bot.send_message(
                    chat_id,
                    "📅 Выберите дату начала:",
                    parse_mode="HTML",
                    reply_markup=get_calendar_keyboard(now.year, now.month, "start"),
                )
                return
            bot.send_message(
                chat_id,
                f"✅ Начало: <b>{st.strftime('%d.%m.%Y %H:%M')}</b>\n\n"
                f"⏱ Выберите длительность или дату окончания:",
                parse_mode="HTML",
                reply_markup=get_duration_keyboard(),
            )
            return

        bot.send_message(chat_id, "Назад из этого шага недоступен. Используйте /menu.")

    # ─────────────────────────────────────────
    #  Игнор пустых кнопок календаря
    # ─────────────────────────────────────────

    @bot.callback_query_handler(func=lambda call: "cal_" in call.data and "_ignore" in call.data)
    def calendar_ignore(call: CallbackQuery):
        bot.answer_callback_query(call.id)

    # ─────────────────────────────────────────
    #  Мои розыгрыши
    # ─────────────────────────────────────────

    @bot.callback_query_handler(func=lambda call: call.data == "my_giveaways")
    def my_giveaways(call: CallbackQuery):
        giveaways = GiveawayService.get_user_giveaways(call.from_user.id)
        if not giveaways:
            bot.answer_callback_query(call.id, "У вас пока нет розыгрышей")
            return
        bot.edit_message_text(
            "📋 Ваши розыгрыши:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=get_giveaway_list_keyboard(giveaways)
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("view_giveaway_"))
    def view_giveaway(call: CallbackQuery):
        giveaway_id = int(call.data.split('_')[2])
        giveaway = GiveawayService.get_giveaway(giveaway_id)
        if not giveaway:
            bot.answer_callback_query(call.id, "Розыгрыш не найден")
            return

        status = "✅ Завершён" if giveaway['is_finished'] else "🔄 Активен" if giveaway['is_published'] else "⏳ Ожидает"
        text = (
            f"🎉 <b>{giveaway['title']}</b>\n\n"
            f"📄 {giveaway['description']}\n\n"
            f"📢 Канал: {giveaway.get('channel_id', '—')}\n"
            f"🕐 Начало: {giveaway['start_time'].strftime('%d.%m.%Y %H:%M')} UTC\n"
            f"🕐 Конец: {giveaway['end_time'].strftime('%d.%m.%Y %H:%M')} UTC\n"
            f"🏆 Победителей: {giveaway['winners_count']}\n"
            f"👥 Участников: {giveaway['participants_count']}\n\n"
            f"Статус: {status}"
        )
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="HTML",
            reply_markup=get_giveaway_view_keyboard(
                giveaway_id,
                is_finished=giveaway["is_finished"],
            ),
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("early_end_giveaway_"))
    def early_end_giveaway_prompt(call: CallbackQuery):
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id)
            return
        giveaway_id = int(call.data.rsplit("_", 1)[-1])
        giveaway = GiveawayService.get_giveaway(giveaway_id)
        if not giveaway or giveaway["creator_id"] != call.from_user.id:
            bot.answer_callback_query(call.id, "❌ Нет доступа", show_alert=True)
            return
        if giveaway["is_finished"]:
            bot.answer_callback_query(call.id, "Розыгрыш уже завершён", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "⏹ <b>Досрочное завершение</b>\n\n"
            "Будут выбраны победители (если есть участники), итоги отправятся в канал "
            "и победителям в личные сообщения (если бот может им написать).\n\n"
            "Подтвердите:",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="HTML",
            reply_markup=get_early_end_confirm_keyboard(giveaway_id),
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_early_end_"))
    def early_end_giveaway_run(call: CallbackQuery):
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id)
            return
        giveaway_id = int(call.data.rsplit("_", 1)[-1])
        giveaway = GiveawayService.get_giveaway(giveaway_id)
        if not giveaway or giveaway["creator_id"] != call.from_user.id:
            bot.answer_callback_query(call.id, "❌ Нет доступа", show_alert=True)
            return
        if giveaway["is_finished"]:
            bot.answer_callback_query(call.id, "Уже завершён", show_alert=True)
            return
        bot.answer_callback_query(call.id, "Завершаем…")
        run_finish_giveaway_now(giveaway_id)
        bot.edit_message_text(
            f"✅ Розыгрыш <b>{escape(giveaway['title'])}</b> завершён досрочно.\n"
            "Проверьте канал и логи бота при необходимости.",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="HTML",
            reply_markup=get_admin_menu(),
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("delete_giveaway_"))
    def delete_giveaway_confirm(call: CallbackQuery):
        giveaway_id = int(call.data.split('_')[2])
        bot.edit_message_text(
            "🗑 <b>Удалить розыгрыш?</b>\n\nЭто действие необратимо.",
            call.message.chat.id, call.message.message_id,
            parse_mode='HTML',
            reply_markup=get_confirm_delete_keyboard(giveaway_id)
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_delete_"))
    def delete_giveaway_execute(call: CallbackQuery):
        giveaway_id = int(call.data.split('_')[2])
        success = GiveawayService.delete_giveaway(giveaway_id, call.from_user.id)
        if success:
            bot.edit_message_text(
                "✅ Розыгрыш удалён.",
                call.message.chat.id, call.message.message_id,
                reply_markup=get_admin_menu()
            )
        else:
            bot.answer_callback_query(call.id, "❌ Не удалось удалить", show_alert=True)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_menu")
    def back_to_menu(call: CallbackQuery):
        bot.edit_message_text(
            "👋 Панель управления розыгрышами\n\nВыберите действие:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=get_admin_menu()
        )