import json
import telebot
from tool import language_check, create_inlineKeyboard

def get_menu_keyboard(user_id):
	buttons = language_check(user_id)[1]['menu']['menu_buttons']
	menu_keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
	menu_keyboard.row(buttons[0], buttons[1])
	menu_keyboard.row(buttons[2])
	menu_keyboard.row(buttons[3])
	menu_keyboard.row(buttons[4], buttons[5])
	return menu_keyboard

	
def get_draw_keyboard(user_id):
	buttons = language_check(user_id)[1]['draw']['draw_buttons']
	draw_keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
	for i in range(0, len(buttons), 2):
		chunk = buttons[i:i+2]
		draw_keyboard.row(*chunk)
	return draw_keyboard
	

def back_button(user_id):
	buttons = language_check(user_id)[1]['draw']['back']
	back_button = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
	back_button.row(buttons)
	return back_button


