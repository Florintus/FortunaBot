from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
import calendar


# ─────────────────────────────────────────────
#  Календарь
# ─────────────────────────────────────────────

def get_calendar_keyboard(year: int, month: int, prefix: str) -> InlineKeyboardMarkup:
    """
    Инлайн-календарь для выбора даты.
    prefix: 'start' или 'end' — чтобы различать какую дату выбираем.
    """
    markup = InlineKeyboardMarkup(row_width=7)

    # Заголовок: месяц и год + стрелки
    month_names = [
        '', 'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
        'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
    ]
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    markup.row(
        InlineKeyboardButton("◀️", callback_data=f"cal_{prefix}_nav_{prev_year}_{prev_month}"),
        InlineKeyboardButton(f"📅 {month_names[month]} {year}", callback_data=f"cal_{prefix}_ignore"),
        InlineKeyboardButton("▶️", callback_data=f"cal_{prefix}_nav_{next_year}_{next_month}"),
    )

    # Дни недели
    markup.row(*[
        InlineKeyboardButton(d, callback_data=f"cal_{prefix}_ignore")
        for d in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    ])

    # Дни месяца
    today = datetime.utcnow().date()
    month_calendar = calendar.monthcalendar(year, month)
    for week in month_calendar:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(" ", callback_data=f"cal_{prefix}_ignore"))
            else:
                date = datetime(year, month, day).date()
                label = f"{day}" if date >= today else f"·{day}·"
                cb = f"cal_{prefix}_day_{year}_{month}_{day}" if date >= today else f"cal_{prefix}_ignore"
                row.append(InlineKeyboardButton(label, callback_data=cb))
        markup.row(*row)

    markup.add(InlineKeyboardButton("❌ Отмена", callback_data="cancel_giveaway"))
    return markup


def get_time_keyboard(year: int, month: int, day: int, prefix: str) -> InlineKeyboardMarkup:
    """Выбор времени после выбора даты."""
    markup = InlineKeyboardMarkup(row_width=4)

    markup.add(InlineKeyboardButton(
        f"🗓 {day:02d}.{month:02d}.{year} — выберите время:",
        callback_data=f"cal_{prefix}_ignore"
    ))

    # Быстрые варианты времени
    times = ["00:00", "06:00", "09:00", "10:00",
             "12:00", "15:00", "18:00", "20:00",
             "21:00", "22:00", "23:00", "23:59"]
    buttons = [
        InlineKeyboardButton(t, callback_data=f"cal_{prefix}_time_{year}_{month}_{day}_{t.replace(':', '_')}")
        for t in times
    ]
    markup.add(*buttons)

    # Ручной ввод
    markup.add(InlineKeyboardButton(
        "✏️ Ввести своё время (ЧЧ:ММ)",
        callback_data=f"cal_{prefix}_manual_{year}_{month}_{day}"
    ))
    markup.add(InlineKeyboardButton("◀️ Назад к календарю", callback_data=f"cal_{prefix}_nav_{year}_{month}"))
    return markup


def get_duration_keyboard(prefix: str = "end") -> InlineKeyboardMarkup:
    """Быстрый выбор длительности розыгрыша (для даты окончания)."""
    markup = InlineKeyboardMarkup(row_width=3)
    markup.add(
        InlineKeyboardButton("1 час",   callback_data=f"dur_{prefix}_1h"),
        InlineKeyboardButton("3 часа",  callback_data=f"dur_{prefix}_3h"),
        InlineKeyboardButton("12 часов",callback_data=f"dur_{prefix}_12h"),
    )
    markup.add(
        InlineKeyboardButton("1 день",  callback_data=f"dur_{prefix}_1d"),
        InlineKeyboardButton("3 дня",   callback_data=f"dur_{prefix}_3d"),
        InlineKeyboardButton("7 дней",  callback_data=f"dur_{prefix}_7d"),
    )
    markup.add(InlineKeyboardButton("📅 Выбрать дату вручную", callback_data=f"dur_{prefix}_custom"))
    markup.add(InlineKeyboardButton("◀️ Назад к старту",       callback_data=f"cal_start_back"))
    return markup


# ─────────────────────────────────────────────
#  Остальные клавиатуры
# ─────────────────────────────────────────────

def get_participate_button(giveaway_id: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🎉 Участвовать", callback_data=f"participate_{giveaway_id}"))
    return markup


def get_admin_menu() -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("➕ Создать розыгрыш", callback_data="create_giveaway"),
        InlineKeyboardButton("📋 Мои розыгрыши",    callback_data="my_giveaways")
    )
    markup.add(InlineKeyboardButton("⚙️ Настройки", callback_data="settings"))
    return markup


def get_confirm_keyboard() -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("✅ Опубликовать", callback_data="confirm_publish"),
        InlineKeyboardButton("❌ Отменить",     callback_data="cancel_giveaway")
    )
    return markup


def get_skip_button(callback_data: str) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("⏭ Пропустить", callback_data=callback_data))
    return markup


def get_giveaway_list_keyboard(giveaways: list) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    for g in giveaways:
        status = "✅" if g['is_finished'] else "🔄" if g['is_published'] else "⏳"
        title = g['title'][:40] + ('...' if len(g['title']) > 40 else '')
        markup.add(InlineKeyboardButton(
            f"{status} {title}",
            callback_data=f"view_giveaway_{g['id']}"
        ))
    markup.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu"))
    return markup


def get_giveaway_view_keyboard(giveaway_id: int) -> InlineKeyboardMarkup:
    """Клавиатура просмотра розыгрыша с кнопкой удаления"""
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton(
        "🗑 Удалить розыгрыш",
        callback_data=f"delete_giveaway_{giveaway_id}"
    ))
    markup.add(InlineKeyboardButton("🔙 К списку", callback_data="my_giveaways"))
    return markup


def get_confirm_delete_keyboard(giveaway_id: int) -> InlineKeyboardMarkup:
    """Подтверждение удаления"""
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_delete_{giveaway_id}"),
        InlineKeyboardButton("❌ Отмена",      callback_data=f"view_giveaway_{giveaway_id}")
    )
    return markup