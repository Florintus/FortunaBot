import time
import models
import random
import config
import requests
import re
import threading
import keyboard
from tool import language_check, create_inlineKeyboard, create_inlineKeyboard_url
from app import middleware_base, bot, post_base, end_base 
from datetime import datetime
from datetime import timedelta

TIME_FORMAT = '%Y-%m-%d %H:%M'


TWITCH_DEVICE_URL = 'https://id.twitch.tv/oauth2/device'
TWITCH_TOKEN_URL = 'https://id.twitch.tv/oauth2/token'
TWITCH_USERS_URL = 'https://api.twitch.tv/helix/users'
TWITCH_FOLLOWED_URL = 'https://api.twitch.tv/helix/channels/followed'

_TWITCH_APP_TOKEN = {
	'token': '',
	'expires_at': 0
}


def _unix_now():
	return int(time.time())


def _bot_username():
	try:
		cfg = str(getattr(config, 'BOT_USERNAME', '')).strip()
		if cfg != '':
			return cfg.lstrip('@')
	except:
		pass
	try:
		return str(bot.get_me().username).strip().lstrip('@')
	except:
		return ''


def _join_deeplink_url(draw_id):
	username = _bot_username()
	if username == '':
		return ''
	return f"https://t.me/{username}?start=join_{int(draw_id)}"


def utc_now_dt():
	return datetime.utcnow().replace(second=0, microsecond=0)


def utc_now_str():
	return utc_now_dt().strftime(TIME_FORMAT)


def parse_utc_time(value):
	try:
		return datetime.strptime(str(value).strip(), TIME_FORMAT)
	except:
		return None


def _twitch_ready():
	try:
		if bool(getattr(config, 'TWITCH_ENABLED', True)) == False:
			return False
	except:
		pass
	return bool(config.TWITCH_CLIENT_ID and config.TWITCH_CLIENT_SECRET)


def _request_twitch(method, url, headers=None, params=None, data=None):
	try:
		response = requests.request(method=method, url=url, headers=headers, params=params, data=data, timeout=15)
	except requests.RequestException:
		return (False, 0, {})

	try:
		payload = response.json()
	except ValueError:
		payload = {}
	return (response.ok, response.status_code, payload)


def _get_twitch_app_token(force=False):
	if _twitch_ready() == False:
		return ''

	now = _unix_now()
	if force == False and _TWITCH_APP_TOKEN['token'] != '' and _TWITCH_APP_TOKEN['expires_at'] > now + 60:
		return _TWITCH_APP_TOKEN['token']

	ok, _, payload = _request_twitch('POST', TWITCH_TOKEN_URL, data={
		'client_id': config.TWITCH_CLIENT_ID,
		'client_secret': config.TWITCH_CLIENT_SECRET,
		'grant_type': 'client_credentials'
	})
	if ok == False:
		return ''

	access_token = payload.get('access_token', '')
	expires_in = int(payload.get('expires_in', 0))
	if access_token == '':
		return ''

	_TWITCH_APP_TOKEN['token'] = access_token
	_TWITCH_APP_TOKEN['expires_at'] = now + expires_in
	return access_token


def _normalize_twitch_login(raw_value):
	if raw_value == None:
		return ''

	login = str(raw_value).strip().lower()
	if login == '':
		return ''

	if login.startswith('https://') or login.startswith('http://'):
		parts = login.rstrip('/').split('/')
		if len(parts) > 0:
			login = parts[-1]

	if '?' in login:
		login = login.split('?')[0]
	if login.startswith('@'):
		login = login[1:]

	if re.fullmatch(r'[a-z0-9_]{4,25}', login) == None:
		return ''
	return login


def _get_twitch_user_by_login(login):
	app_token = _get_twitch_app_token()
	if app_token == '':
		return None

	headers = {
		'Client-Id': config.TWITCH_CLIENT_ID,
		'Authorization': f"Bearer {app_token}"
	}
	ok, status_code, payload = _request_twitch('GET', TWITCH_USERS_URL, headers=headers, params={'login': login})
	if status_code == 401:
		app_token = _get_twitch_app_token(force=True)
		if app_token == '':
			return None
		headers['Authorization'] = f"Bearer {app_token}"
		ok, _, payload = _request_twitch('GET', TWITCH_USERS_URL, headers=headers, params={'login': login})

	if ok == False:
		return None

	users = payload.get('data', [])
	if len(users) == 0:
		return None

	user = users[0]
	return {
		'id': user.get('id', ''),
		'login': user.get('login', login)
	}


def _upsert_twitch_device_auth(telegram_user_id, device_code, user_code, verification_uri, interval, expires_at):
	current = middleware_base.get_one(models.TwitchDeviceAuth, telegram_user_id=str(telegram_user_id))
	if current == None:
		middleware_base.new(models.TwitchDeviceAuth, str(telegram_user_id), device_code, user_code, verification_uri, int(interval), int(expires_at))
	else:
		middleware_base.update(models.TwitchDeviceAuth, {
			'device_code': device_code,
			'user_code': user_code,
			'verification_uri': verification_uri,
			'interval': int(interval),
			'expires_at': int(expires_at)
		}, telegram_user_id=str(telegram_user_id))


def _upsert_twitch_user(telegram_user_id, twitch_user_id, twitch_login, access_token, refresh_token, expires_at):
	current = middleware_base.get_one(models.TwitchUser, telegram_user_id=str(telegram_user_id))
	if current == None:
		middleware_base.new(models.TwitchUser, str(telegram_user_id), str(twitch_user_id), twitch_login, access_token, refresh_token, int(expires_at))
	else:
		middleware_base.update(models.TwitchUser, {
			'twitch_user_id': str(twitch_user_id),
			'twitch_login': twitch_login,
			'access_token': access_token,
			'refresh_token': refresh_token,
			'expires_at': int(expires_at)
		}, telegram_user_id=str(telegram_user_id))


def _refresh_twitch_user_token(telegram_user_id):
	twitch_user = middleware_base.get_one(models.TwitchUser, telegram_user_id=str(telegram_user_id))
	if twitch_user == None or twitch_user.refresh_token in ['', None]:
		return ''

	ok, _, payload = _request_twitch('POST', TWITCH_TOKEN_URL, data={
		'client_id': config.TWITCH_CLIENT_ID,
		'client_secret': config.TWITCH_CLIENT_SECRET,
		'grant_type': 'refresh_token',
		'refresh_token': twitch_user.refresh_token
	})
	if ok == False:
		return ''

	access_token = payload.get('access_token', '')
	refresh_token = payload.get('refresh_token', twitch_user.refresh_token)
	expires_in = int(payload.get('expires_in', 0))
	if access_token == '':
		return ''

	middleware_base.update(models.TwitchUser, {
		'access_token': access_token,
		'refresh_token': refresh_token,
		'expires_at': _unix_now() + expires_in
	}, telegram_user_id=str(telegram_user_id))
	return access_token


def _get_valid_twitch_user_token(telegram_user_id):
	twitch_user = middleware_base.get_one(models.TwitchUser, telegram_user_id=str(telegram_user_id))
	if twitch_user == None:
		return (None, '')

	try:
		expires_at = int(twitch_user.expires_at)
	except:
		expires_at = 0

	if twitch_user.access_token not in ['', None] and expires_at > _unix_now() + 60:
		return (twitch_user, twitch_user.access_token)

	access_token = _refresh_twitch_user_token(telegram_user_id)
	if access_token == '':
		return (twitch_user, '')

	twitch_user = middleware_base.get_one(models.TwitchUser, telegram_user_id=str(telegram_user_id))
	return (twitch_user, access_token)


def _is_following_broadcaster(telegram_user_id, broadcaster_id):
	twitch_user, access_token = _get_valid_twitch_user_token(telegram_user_id)
	if twitch_user == None:
		return 'no_link'
	if access_token == '':
		return 'token_error'

	headers = {
		'Client-Id': config.TWITCH_CLIENT_ID,
		'Authorization': f"Bearer {access_token}"
	}
	params = {
		'user_id': twitch_user.twitch_user_id,
		'broadcaster_id': str(broadcaster_id)
	}
	ok, status_code, payload = _request_twitch('GET', TWITCH_FOLLOWED_URL, headers=headers, params=params)

	if status_code == 401:
		access_token = _refresh_twitch_user_token(telegram_user_id)
		if access_token == '':
			return 'token_error'
		headers['Authorization'] = f"Bearer {access_token}"
		ok, _, payload = _request_twitch('GET', TWITCH_FOLLOWED_URL, headers=headers, params=params)

	if ok == False:
		return 'api_error'

	if len(payload.get('data', [])) == 0:
		return 'not_following'
	return 'following'


def twitch_enabled():
	return _twitch_ready()


def start_twitch_device_auth(telegram_user_id):
	if _twitch_ready() == False:
		return ('not_configured', {})

	ok, _, payload = _request_twitch('POST', TWITCH_DEVICE_URL, data={
		'client_id': config.TWITCH_CLIENT_ID,
		'scopes': config.TWITCH_FOLLOW_SCOPE
	})
	if ok == False:
		return ('failed', {})

	device_code = payload.get('device_code', '')
	user_code = payload.get('user_code', '')
	verification_uri = payload.get('verification_uri', '')
	expires_in = int(payload.get('expires_in', 0))
	interval = int(payload.get('interval', 5))
	if device_code == '' or user_code == '' or verification_uri == '' or expires_in <= 0:
		return ('failed', {})

	expires_at = _unix_now() + expires_in
	_upsert_twitch_device_auth(telegram_user_id, device_code, user_code, verification_uri, interval, expires_at)

	return ('ok', {
		'user_code': user_code,
		'verification_uri': verification_uri,
		'expires_in': expires_in,
		'interval': interval
	})


def complete_twitch_device_auth(telegram_user_id):
	if _twitch_ready() == False:
		return ('not_configured', '')

	pending = middleware_base.get_one(models.TwitchDeviceAuth, telegram_user_id=str(telegram_user_id))
	if pending == None:
		return ('missing', '')

	if int(pending.expires_at) <= _unix_now():
		middleware_base.delete(models.TwitchDeviceAuth, telegram_user_id=str(telegram_user_id))
		return ('expired', '')

	ok, _, payload = _request_twitch('POST', TWITCH_TOKEN_URL, data={
		'client_id': config.TWITCH_CLIENT_ID,
		'client_secret': config.TWITCH_CLIENT_SECRET,
		'grant_type': 'urn:ietf:params:oauth:grant-type:device_code',
		'device_code': pending.device_code
	})

	if ok == False:
		error_code = payload.get('message', payload.get('error', ''))
		if error_code in ['authorization_pending', 'slow_down']:
			return ('pending', '')
		if error_code in ['access_denied']:
			middleware_base.delete(models.TwitchDeviceAuth, telegram_user_id=str(telegram_user_id))
			return ('denied', '')
		if error_code in ['expired_token', 'invalid_grant']:
			middleware_base.delete(models.TwitchDeviceAuth, telegram_user_id=str(telegram_user_id))
			return ('expired', '')
		return ('failed', '')

	access_token = payload.get('access_token', '')
	refresh_token = payload.get('refresh_token', '')
	expires_in = int(payload.get('expires_in', 0))
	if access_token == '' or expires_in <= 0:
		return ('failed', '')

	headers = {
		'Client-Id': config.TWITCH_CLIENT_ID,
		'Authorization': f"Bearer {access_token}"
	}
	ok, _, user_payload = _request_twitch('GET', TWITCH_USERS_URL, headers=headers)
	if ok == False:
		return ('failed', '')

	users = user_payload.get('data', [])
	if len(users) == 0:
		return ('failed', '')

	user = users[0]
	twitch_user_id = user.get('id', '')
	twitch_login = user.get('login', '')
	if twitch_user_id == '' or twitch_login == '':
		return ('failed', '')

	_upsert_twitch_user(
		telegram_user_id=telegram_user_id,
		twitch_user_id=twitch_user_id,
		twitch_login=twitch_login,
		access_token=access_token,
		refresh_token=refresh_token,
		expires_at=_unix_now() + expires_in
	)
	middleware_base.delete(models.TwitchDeviceAuth, telegram_user_id=str(telegram_user_id))
	return ('linked', twitch_login)


def get_twitch_linked_login(telegram_user_id):
	twitch_user = middleware_base.get_one(models.TwitchUser, telegram_user_id=str(telegram_user_id))
	if twitch_user == None:
		return ''
	return twitch_user.twitch_login


def add_twitch_channel_to_draw(draw_id, user_id, raw_channel_login):
	if _twitch_ready() == False:
		return ('not_configured', '')

	channel_login = _normalize_twitch_login(raw_channel_login)
	if channel_login == '':
		return ('invalid', '')

	twitch_user = _get_twitch_user_by_login(channel_login)
	if twitch_user == None or twitch_user.get('id', '') == '':
		return ('not_found', '')

	broadcaster_id = str(twitch_user['id'])
	existing = middleware_base.get_one(models.SubscribeTwitchChannel, draw_id=int(draw_id), broadcaster_id=broadcaster_id)
	if existing != None:
		return ('exists', existing.channel_login)

	middleware_base.new(models.SubscribeTwitchChannel, int(draw_id), str(user_id), twitch_user['login'], broadcaster_id)
	return ('added', twitch_user['login'])


def _cleanup_draw_requirements(draw_id):
	middleware_base.delete(models.SubscribeChannel, draw_id=int(draw_id))
	middleware_base.delete(models.SubscribeTwitchChannel, draw_id=int(draw_id))


def reset_draw_progress(user_id):
	tmp = middleware_base.get_one(models.DrawProgress, user_id=str(user_id))
	if tmp != None:
		_cleanup_draw_requirements(tmp.id)
	middleware_base.delete(models.DrawProgress, user_id=str(user_id))
	middleware_base.delete(models.State, user_id=str(user_id))


def _draw_requirements_text(draw_id, text):
	channels = middleware_base.select_all(models.SubscribeChannel, draw_id=int(draw_id))
	twitch_channels = []
	try:
		if _twitch_ready():
			twitch_channels = middleware_base.select_all(models.SubscribeTwitchChannel, draw_id=int(draw_id))
	except:
		twitch_channels = []

	lines = []
	if len(channels) > 0:
		lines.append(f"{text['required_tg_channels']} {', '.join([i.channel_id for i in channels])}")
	if len(twitch_channels) > 0:
		lines.append(f"{text['required_twitch_channels']} {', '.join([f'@{i.channel_login}' for i in twitch_channels])}")

	if len(lines) == 0:
		return ''
	return "\n" + "\n".join(lines)




def check_user(user_id):
	user = middleware_base.get_one(models.User, user_id=str(user_id))
	if user != None:
		return user
	else:
		return False


def create_draw_progress(user_id, tmp):
    old_progress = middleware_base.get_one(models.DrawProgress, user_id=str(user_id))
    if old_progress is not None:
        _cleanup_draw_requirements(old_progress.id)

    middleware_base.delete(models.DrawProgress, user_id=str(user_id))
    progress = middleware_base.new(
        models.DrawProgress,
        str(user_id),
        tmp['chanel_id'],
        tmp['chanel_name'],
        tmp['draw_text'],
        tmp['file_type'],
        tmp['file_id'],
        int(tmp['winers_count']),
        tmp['start_time'],
        tmp['end_time']
    )
    middleware_base.delete(models.State, user_id=str(user_id))

    report_lines = []
    parsed_tg = tmp.get('parsed_tg_channels', [])
    parsed_twitch = tmp.get('parsed_twitch_logins', [])

    # === Auto-add Telegram requirements from description (упрощённая версия) ===
    if isinstance(parsed_tg, list) and len(parsed_tg) > 0:
        added = []
        for ch in parsed_tg:
            ch_ref = str(ch).strip()
            if ch_ref == '':
                continue
            # нормализуем ссылку в @username
            if ch_ref.startswith('https://t.me/') or ch_ref.startswith('http://t.me/'):
                ch_ref = '@' + ch_ref.split('/')[-1]
            elif ch_ref.startswith('t.me/'):
                ch_ref = '@' + ch_ref.split('/')[-1]

            existing = middleware_base.get_one(
                models.SubscribeChannel,
                draw_id=int(progress.id),
                channel_id=ch_ref
            )
            if existing is not None:
                continue

            middleware_base.new(
                models.SubscribeChannel,
                int(progress.id),
                str(user_id),
                ch_ref
            )
            added.append(ch_ref)

        if len(added) > 0:
            report_lines.append(
                f"Автоматически добавлены TG-каналы в условия: {', '.join(added)}"
            )

    # === Auto-add Twitch requirements from description (как было) ===
    if isinstance(parsed_twitch, list) and len(parsed_twitch) > 0:
        if _twitch_ready() is False:
            try:
                if bool(getattr(config, 'TWITCH_ENABLED', True)) is False:
                    report_lines.append(
                        "Twitch-каналы из описания не добавлены: Twitch отключён"
                    )
            except Exception:
                report_lines.append(
                    "Twitch-каналы из описания не добавлены: Twitch API не настроен"
                )
        else:
            added = []
            skipped = []
            for login in parsed_twitch:
                status, channel_login = add_twitch_channel_to_draw(
                    progress.id, user_id, login
                )
                if status in ['added', 'exists']:
                    added.append(f"@{channel_login}")
                    continue
                if status in ['not_found', 'invalid']:
                    skipped.append(str(login))
                    continue
                if status == 'not_configured':
                    report_lines.append(
                        "Twitch-каналы из описания не добавлены: Twitch API не настроен"
                    )
                    skipped = []
                    break
                skipped.append(str(login))
            if len(added) > 0:
                report_lines.append(
                    f"Автоматически добавлены Twitch-каналы в условия: {', '.join(added)}"
                )
            if len(skipped) > 0:
                report_lines.append(
                    f"Twitch-каналы НЕ добавлены: {', '.join(skipped)}"
                )

    return {
        'text': draw_info(user_id),
        'report': "\n".join(report_lines)
    }






def draw_info(user_id):
	tmp = check_post(str(user_id))
	if tmp == None:
		return ''
	text = language_check(user_id)[1]['draw']
	requirements_text = _draw_requirements_text(tmp.id, text)
	draw_text = f"{text['change_text']}\n{text['post_time_text']} {tmp.post_time}\n{text['over_time_text']} {tmp.end_time}\n{text['chanel/chat']} {tmp.chanel_name}\n{text['count_text']} {tmp.winers_count}\n{text['text']} {tmp.text}{requirements_text}"
	return draw_text


def check_post(user_id):
	data = middleware_base.get_one(models.DrawProgress, user_id=str(user_id))
	return data

def send_draw_info(user_id):
	tmp = check_post(str(user_id))
	if tmp == None:
		return
	text = language_check(user_id)[1]['draw']
	requirements_text = _draw_requirements_text(tmp.id, text)
	draw_text = f"{text['change_text']}\n{text['post_time_text']} {tmp.post_time}\n{text['over_time_text']} {tmp.end_time}\n{text['chanel/chat']} {tmp.chanel_name}\n{text['count_text']} {tmp.winers_count}\n{text['text']} {tmp.text}{requirements_text}"
	if tmp.file_type == 'photo':
		bot.send_photo(user_id, tmp.file_id, draw_text, reply_markup=keyboard.get_draw_keyboard(user_id))
	elif tmp.file_type == 'document':
		bot.send_document(user_id, tmp.file_id, caption=draw_text, reply_markup=keyboard.get_draw_keyboard(user_id))
	else:
		bot.send_message(user_id, draw_text, reply_markup=keyboard.get_draw_keyboard(user_id))
	middleware_base.delete(models.State, user_id=user_id)



def my_draw_info(user_id, row=0):
	if row < 0:
		return 'first'

	text = language_check(user_id)[1]['my_draw']
	entries = _my_draw_entries(user_id)
	if len(entries) == 0:
		bot.send_message(user_id, text['no_draw'])
		return 'empty'

	if row >= len(entries):
		return 'last'

	entry = entries[row]
	draw = entry['draw']
	status_text = text['status_pending']
	action_label = text['cancel_pending_button']
	action_callback = f"cancel_pending_{draw.id}"
	edit_label = text.get('edit_pending_button', '')
	edit_callback = f"edit_pending_{draw.id}"
	if entry['type'] == 'active':
		status_text = text['status_active']
		action_label = text['finish_now_button']
		action_callback = f"finish_now_{draw.id}"

	draw_text = (
		f"{text['your_draw']}\n"
		f"{text['status']}: {status_text}\n"
		f"{text['post_time_text']} {draw.post_time}\n"
		f"{text['over_time_text']} {draw.end_time}\n"
		f"{text['chanel/chat']} {draw.chanel_name}\n"
		f"{text['count_text']} {draw.winers_count}\n"
		f"{text['text']} {draw.text}"
	)
	keyboard_map = {
		action_label: action_callback,
		text['back']: "back",
		text['next']: "next"
	}
	if entry['type'] == 'pending' and edit_label != '':
		keyboard_map[edit_label] = edit_callback
	inline_keyboard = create_inlineKeyboard(keyboard_map, 2)
	if draw.file_type == 'photo':
		bot.send_photo(user_id, draw.file_id, draw_text, reply_markup=inline_keyboard)
	elif draw.file_type == 'document':
		bot.send_document(user_id, draw.file_id, caption=draw_text, reply_markup=inline_keyboard)
	else:
		bot.send_message(user_id, draw_text, reply_markup=inline_keyboard)
	return True


def _my_draw_entries(user_id):
	entries = []
	not_posted = middleware_base.select_all(models.DrawNot, user_id=str(user_id))
	for i in not_posted:
		entries.append({'type': 'pending', 'draw': i})

	active = middleware_base.select_all(models.Draw, user_id=str(user_id))
	for i in active:
		entries.append({'type': 'active', 'draw': i})

	def _sort_key(entry):
		dt = parse_utc_time(entry['draw'].post_time)
		if dt == None:
			return datetime.max
		return dt

	entries.sort(key=_sort_key)
	return entries


def cancel_pending_draw(user_id, draw_id):
	draw = middleware_base.get_one(models.DrawNot, id=int(draw_id))
	if draw == None:
		return 'not_found'
	if str(draw.user_id) != str(user_id):
		return 'forbidden'

	_cleanup_draw_requirements(draw.id)
	middleware_base.delete(models.DrawNot, id=int(draw_id))
	return 'cancelled'


def _draw_winners_text(draw):
	text = language_check(draw.user_id)[1]['draw']
	players = end_base.select_all(models.DrawPlayer, draw_id=str(draw.id))
	if players == []:
		return (f"{draw.text}\n*****\n{text['no_winers']}", f"{text['no_winers']}")

	winners_text = f"{draw.text}\n*****\n{text['winers']}\n"
	owner_winners = f"{text['winers']}\n"
	for random_player in random.sample(players, min(int(draw.winers_count), len(players))):
		winners_text += f"<a href='tg://user?id={random_player.user_id}'>{random_player.user_name}</a>\n"
		owner_winners += f"<a href='tg://user?id={random_player.user_id}'>{random_player.user_name}</a>\n"

	return (winners_text, owner_winners)


def _finalize_draw(draw_id, forced=False):
	draw = end_base.get_one(models.Draw, id=int(draw_id))
	if draw == None:
		return 'not_found'

	text = language_check(draw.user_id)[1]['draw']
	winers, owner_winners = _draw_winners_text(draw)
	try:
		bot.send_message(chat_id=str(draw.chanel_id), text=winers, parse_mode='HTML')
	except:
		end_base.delete(models.Draw, id=draw.id)
		bot.send_message(draw.user_id, text['failed_post'])
		return 'failed_post'

	owner_title = text['your_draw_over']
	if forced == True:
		owner_title = text['draw_finished_early']
	bot.send_message(draw.user_id, f"{owner_title}\n{owner_winners}", parse_mode='HTML')

	end_base.new(models.DrawEnded, draw.id, draw.user_id, draw.message_id, draw.chanel_id, draw.chanel_name, draw.text, draw.file_type, draw.file_id, draw.winers_count, draw.post_time, draw.end_time, winers)
	end_base.delete(models.Draw, id=draw.id)
	return 'ended'


def finish_draw_now(user_id, draw_id):
	draw = middleware_base.get_one(models.Draw, id=int(draw_id))
	if draw == None:
		return 'not_found'
	if str(draw.user_id) != str(user_id):
		return 'forbidden'

	return _finalize_draw(draw.id, forced=True)





def start_draw_timer():
	def timer():
		while 1:
			for i in post_base.select_all(models.DrawNot):
				now_dt = utc_now_dt()
				post_dt = parse_utc_time(i.post_time)
				if post_dt != None and now_dt >= post_dt:
					text = language_check(i.user_id)[1]['draw']
					requirements_text = _draw_requirements_text(i.id, text)
					post_text = f"{i.text}{requirements_text}"
					join_url = _join_deeplink_url(i.id)
					if join_url != '':
						markup = create_inlineKeyboard_url({text['get_on']: join_url}, 1)
					else:
						markup = create_inlineKeyboard({text['get_on']:f'geton_{i.id}'}, 1)
					if i.file_type == 'photo':
						tmz = bot.send_photo(i.chanel_id, i.file_id, post_text, reply_markup=markup)
					elif i.file_type == 'document':
						tmz = bot.send_document(i.chanel_id, i.file_id, caption=post_text, reply_markup=markup)
					else:
						tmz = bot.send_message(i.chanel_id, post_text, reply_markup=markup)
					post_base.new(models.Draw, i.id, i.user_id, tmz.message_id, i.chanel_id, i.chanel_name, i.text, i.file_type, i.file_id, i.winers_count, i.post_time, i.end_time)
					post_base.delete(models.DrawNot, id=str(i.id))
			time.sleep(5)
	rT = threading.Thread(target = timer)
	rT.start()


def end_draw_timer():
	def end_timer():
		while 1:
			for i in end_base.select_all(models.Draw):
				now_dt = utc_now_dt()
				end_dt = parse_utc_time(i.end_time)
				if end_dt != None and now_dt >= end_dt:
					_finalize_draw(i.id)
					time.sleep(1)

			time.sleep(5)
	rT = threading.Thread(target = end_timer)
	rT.start()


def _channel_link(chanel_id):
	if chanel_id and str(chanel_id).startswith('@'):
		return f"https://t.me/{str(chanel_id)[1:]}"
	return False


def my_part_info(user_id, mode='active', row=0):
	if row < 0:
		return 'first'

	text = language_check(user_id)[1]['my_part']
	players = middleware_base.select_all(models.DrawPlayer, user_id=str(user_id))

	draws = []
	for p in players:
		if mode == 'active':
			d = middleware_base.get_one(models.Draw, id=int(p.draw_id))
		else:
			d = middleware_base.get_one(models.DrawEnded, id=int(p.draw_id))
		if d != None:
			draws.append(d)

	if len(draws) == 0:
		bot.send_message(user_id, text['no_draw'])
		return 'empty'

	if row >= len(draws):
		return 'last'

	d = draws[row]
	link = _channel_link(d.chanel_id)
	if link == False:
		link = str(d.chanel_id)

	draw_text = f"{text['your_draw']}\n{text['winners_time']} {d.end_time}\n{text['link']} {link}\n{language_check(user_id)[1]['draw']['chanel/chat']} {d.chanel_name}\n{language_check(user_id)[1]['draw']['text']} {d.text}"

	switch = create_inlineKeyboard({text['active']: "ptype_active", text['ended']: "ptype_ended"}, 2)
	nav = create_inlineKeyboard({text['back']: "pback", text['next']: "pnext"}, 2)

	if d.file_type == 'photo':
		bot.send_photo(user_id, d.file_id, draw_text, reply_markup=switch)
		bot.send_message(user_id, ".", reply_markup=nav)
	elif d.file_type == 'document':
		bot.send_document(user_id, d.file_id, caption=draw_text, reply_markup=switch)
		bot.send_message(user_id, ".", reply_markup=nav)
	else:
		bot.send_message(user_id, draw_text, reply_markup=switch)
		bot.send_message(user_id, ".", reply_markup=nav)


def _is_telegram_subscription_valid(channel_id, user_id):
	valid_status = ['member', 'administrator', 'creator', 'restricted']
	try:
		member = bot.get_chat_member(chat_id=channel_id, user_id=user_id)
	except:
		return False

	return str(member.status) in valid_status


def join_draw(draw_id, user_id, username=''):
	try:
		draw_id_int = int(draw_id)
	except:
		draw_id_int = 0
	if draw_id_int <= 0:
		return {'status': 'draw_not_found'}

	tmp = middleware_base.get_one(models.Draw, id=draw_id_int)
	if tmp == None:
		return {'status': 'draw_not_found'}

	channels = middleware_base.select_all(models.SubscribeChannel, draw_id=int(tmp.id))
	not_subscribed = []
	for i in channels:
		if _is_telegram_subscription_valid(i.channel_id, int(user_id)) == False:
			not_subscribed.append(str(i.channel_id))

	if len(not_subscribed) > 0:
		return {'status': 'not_subscribe_tg', 'channels': not_subscribed}

	if _twitch_ready():
		twitch_channels = middleware_base.select_all(models.SubscribeTwitchChannel, draw_id=int(tmp.id))
		if len(twitch_channels) > 0:
			linked_twitch = middleware_base.get_one(models.TwitchUser, telegram_user_id=str(user_id))
			if linked_twitch == None:
				return {'status': 'need_twitch_link'}

			not_followed = []
			for i in twitch_channels:
				follow_status = _is_following_broadcaster(int(user_id), i.broadcaster_id)
				if follow_status == 'no_link':
					return {'status': 'need_twitch_link'}
				if follow_status in ['token_error', 'api_error']:
					return {'status': 'twitch_check_error'}
				if follow_status == 'not_following':
					not_followed.append(f"@{i.channel_login}")

			if len(not_followed) > 0:
				return {'status': 'not_follow_twitch', 'channels': not_followed}

	players = middleware_base.get_one(models.DrawPlayer, draw_id=str(tmp.id), user_id=str(user_id))
	if players != None:
		return {'status': 'already_in'}

	middleware_base.new(models.DrawPlayer, int(tmp.id), str(user_id), str(username))
	tmz = middleware_base.select_all(models.DrawPlayer, draw_id=int(tmp.id))
	return {
		'status': 'joined',
		'count': len(tmz),
		'label': language_check(tmp.user_id)[1]['draw']['play']
	}


def new_player(call):
	id = int(call.data.split('_')[1])
	return join_draw(id, call.from_user.id, getattr(call.from_user, 'username', ''))

