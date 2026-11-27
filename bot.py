import asyncio
import json
import logging
import random
import re
from datetime import datetime as dt, timedelta

import aioschedule
import pytz
import requests
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils.exceptions import BotBlocked

from config_reader import config
from db import delete_or_insert_data as di_d, insert_many, select_data

logging.basicConfig(level=logging.INFO)


class SetConfigsToBot(StatesGroup):
    waiting_for_choose_country = State()
    waiting_for_choose_city = State()
    waiting_for_choose_mazhab = State()
    waiting_for_choose_delta_time = State()
    waiting_for_send_message_to_admin = State()
    waiting_for_send_message_to_all = State()


API_TOKEN = config.bot_token.get_secret_value()
ADMIN_ID = config.admin_id

memstore = MemoryStorage()
# Initialize bot and dispatcher
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=memstore)

# Names of the five daily prayers. They are stored in the database as JSON
# (users.nz_times_with_hadis) and are used as button texts, so they must stay
# in sync with the callback_data regexes below.
nz_times_names = ["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]

# Reply keyboard button that shows today's prayer times.
# report_handler matches incoming messages against this exact text.
TODAY_BUTTON = "Today's prayer times"

# Madhhab names: shown on buttons and compared in choose_delta_minutes_and_save_settings
MAZHAB_HANAFI = "Hanafi"
MAZHAB_SHAFII = "Shafi'i"

# The order of prayer times in the stored array matches the key order in the aladhan API response:
# Fajr, Sunrise, Dhuhr, Asr, Maghrib, Isha, Midnight (Imsak/Sunset/Firstthird/Lastthird are dropped)
FAJR, SUNRISE, DHUHR, ASR, MAGHRIB, ISHA, MIDNIGHT = range(7)
PRAYER_KEYS = ("Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha", "Midnight")

# The API sometimes returns times with spaces after the colon: "21: 16 (+05)"
TIME_RE = re.compile(r'(\d{1,2})\s*:\s*(\d{1,2})')

API_URL = ("http://api.aladhan.com/v1/calendarByCity/{year}/{month}"
           "?city={city}&country={country}&method=14&school={school}")


# ============================ HELPER FUNCTIONS ============================

def parse_hhmm(text):
    """Parses a time string like '05:22 (+05)' or '21: 16 (+05)'."""
    m = TIME_RE.search(text)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


async def safe_delete(chat_id, message_id):
    """Deletes a message without failing if it is already deleted or too old."""
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


def fetch_calendar(city, country, school):
    """Synchronous monthly prayer calendar request (runs in an executor)."""
    url = API_URL.format(year=dt.now().year, month=dt.now().month,
                         city=city, country=country, school=school)
    resp = requests.get(url, timeout=30)
    data = resp.json()
    if data.get("code") != 200 or not data.get("data"):
        raise ValueError(f"aladhan API returned an error for {country}/{city}: {data.get('code')}")
    return data


async def get_calendar(city, country, school):
    """Does not block the event loop: the API request runs in a separate thread."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fetch_calendar, city, country, school)


def local_to_server_time(tz_name, hh, mm):
    """Converts the user's local prayer time into the server's local time.

    Correctly handles time zones, DST and crossing midnight
    (unlike the hour difference dt.now().hour - dt.now(tz).hour).
    """
    tz = pytz.timezone(tz_name)
    naive = dt.now(tz).replace(tzinfo=None, hour=hh, minute=mm, second=0, microsecond=0)
    return tz.localize(naive).astimezone()


def get_user_nz_names(telega_id):
    """Returns the list of the user's prayer names with hadiths (None - not initialized)."""
    rows = select_data("select nz_times_with_hadis from users where telega_id = ?", (telega_id,))
    if not rows:
        return None
    return json.loads(rows[0][0])


# ============================ HANDLERS ============================

@dp.message_handler(commands='start', state="*")
async def send_welcome(message: types.Message, state: FSMContext):
    user_exist = select_data("select*from users where telega_id = ?", (message.chat.id,))
    if user_exist == []:
        await message.answer("Hello! This bot will remind you to perform your prayers with a message "
                             "containing a hadith.\nLet's run the initial setup. Write the bot the name "
                             "of the country you live in.\n\nPS: Make sure the name is spelled correctly")
        await safe_delete(message.chat.id, message.message_id)
        await state.set_state(SetConfigsToBot.waiting_for_choose_country.state)
    else:
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        buttons = [TODAY_BUTTON, ]
        keyboard.add(*buttons)
        await message.answer("You are already set up with this bot", reply_markup=keyboard)
        await safe_delete(message.chat.id, message.message_id)


@dp.message_handler(state=SetConfigsToBot.waiting_for_choose_country)
async def choosen_country_handler(message: types.Message, state: FSMContext):
    await state.update_data(chosen_country=message.text)
    await message.answer(f"You chose the country {message.text}.\n"
                         f"Now write the bot the name of the city you live in.")
    await safe_delete(message.chat.id, message.message_id)
    await state.set_state(SetConfigsToBot.waiting_for_choose_city.state)


@dp.message_handler(state=SetConfigsToBot.waiting_for_choose_city)
async def choosen_city_handler(message: types.Message, state: FSMContext):
    btns = [
        types.InlineKeyboardButton(text=MAZHAB_HANAFI, callback_data='hanafi'),
        types.InlineKeyboardButton(text=MAZHAB_SHAFII, callback_data='shafii')
    ]
    keyb = types.InlineKeyboardMarkup(row_width=2)
    keyb.add(*btns)
    await state.update_data(chosen_city=message.text)
    await message.answer(f"You chose the city {message.text}.\nNow choose the madhhab you follow.",
                         reply_markup=keyb)
    await safe_delete(message.chat.id, message.message_id)
    await state.set_state(SetConfigsToBot.waiting_for_choose_mazhab.state)


async def choosen_mazhab_handler(call, state, message_data):
    btns = [
        types.InlineKeyboardButton(text='30 minutes before it ends', callback_data='-30'),
        types.InlineKeyboardButton(text='When the prayer time starts', callback_data='0'),
        types.InlineKeyboardButton(text='1 hour before it ends', callback_data='-60')
    ]
    keyb = types.InlineKeyboardMarkup(row_width=3)
    keyb.add(*btns)
    await state.update_data(chosen_mazhab=message_data)
    await call.message.answer(f"You chose the {message_data} madhhab. "
                              f"Now choose a convenient time for your prayer reminders",
                              reply_markup=keyb)
    await safe_delete(call.message.chat.id, call.message.message_id)
    await bot.answer_callback_query(callback_query_id=call.id)
    await state.set_state(SetConfigsToBot.waiting_for_choose_delta_time.state)


@dp.callback_query_handler(lambda call: call.data == 'hanafi', state=SetConfigsToBot.waiting_for_choose_mazhab)
async def choose_hanafi_handler(call: types.CallbackQuery, state: FSMContext):  # Hanafi was chosen
    await choosen_mazhab_handler(call, state, MAZHAB_HANAFI)


@dp.callback_query_handler(lambda call: call.data == 'shafii', state=SetConfigsToBot.waiting_for_choose_mazhab)
async def choose_shafii_handler(call: types.CallbackQuery, state: FSMContext):  # Shafi'i was chosen
    await choosen_mazhab_handler(call, state, MAZHAB_SHAFII)


async def choose_delta_minutes_and_save_settings(call, state, delta_time):
    await bot.answer_callback_query(callback_query_id=call.id)
    user_data = await state.get_data()

    mazh = 1
    if user_data['chosen_mazhab'] == MAZHAB_SHAFII:
        mazh = 0

    try:
        # First we check that the API accepts this country/city,
        # and only after that do we save the user to the database
        calendar = await get_calendar(user_data['chosen_city'], user_data['chosen_country'], mazh)
    except Exception:
        logging.exception("Could not fetch the calendar for %s/%s",
                          user_data['chosen_country'], user_data['chosen_city'])
        await call.message.answer("Something went wrong!\nPerhaps you misspelled the name of your country or city, "
                                  "or the server is temporarily unavailable. Please run the setup again, "
                                  "for that press /start.")
        await safe_delete(call.message.chat.id, call.message.message_id)
        await state.finish()
        return

    di_d("delete from users where telega_id=?", (call.message.chat.id,))
    di_d("delete from user_timings where telega_id=?", (call.message.chat.id,))
    di_d("insert into users(telega_id, name, country, city, mazhab, time_delta, nz_times_with_hadis) "
         "values(?,?,?,?,?,?,?);",
         (call.message.chat.id, call.message.chat.username, user_data['chosen_country'], user_data['chosen_city'],
          mazh, int(delta_time), json.dumps(nz_times_names, ensure_ascii=False)))
    await correct_timings_insertor(call.message.chat.id, calendar)

    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = [TODAY_BUTTON, ]
    keyboard.add(*buttons)
    await call.message.answer("The bot setup is complete. Your data will be initialized within 5 minutes.\n"
                              "If you change your mind about using the bot, press /delete_user to remove your "
                              "account from the bot's database. If you want to change the location or the "
                              "reminder time you have set, press /change_settings. If you want to remove the "
                              "hadith from some of the reminders, press /del_hadis_from_time. If you want to "
                              "write to the administrator, press /send_message_to_admin. These commands are in "
                              "the menu to the left of the message input field (the blue button). \nAt the right "
                              "time the bot will send you a reminder, in sha'Allah. "
                              "\n🕌 Peace be upon you 🕌", reply_markup=keyboard)
    await safe_delete(call.message.chat.id, call.message.message_id)
    await state.finish()


@dp.callback_query_handler(lambda call: call.data == '-30', state=SetConfigsToBot.waiting_for_choose_delta_time)
async def choose_delta_thirty(call: types.CallbackQuery, state: FSMContext):  # end of the setup
    await choose_delta_minutes_and_save_settings(call, state, '-30')


@dp.callback_query_handler(lambda call: call.data == '0', state=SetConfigsToBot.waiting_for_choose_delta_time)
async def choose_delta_zero(call: types.CallbackQuery, state: FSMContext):  # end of the setup
    await choose_delta_minutes_and_save_settings(call, state, '0')


@dp.callback_query_handler(lambda call: call.data == '-60', state=SetConfigsToBot.waiting_for_choose_delta_time)
async def choose_delta_sixty(call: types.CallbackQuery, state: FSMContext):  # end of the setup
    await choose_delta_minutes_and_save_settings(call, state, '-60')


@dp.message_handler(commands=['delete_user'])
async def delete_user(message: types.Message, state: FSMContext):
    user = select_data("select*from users where telega_id = ?", (message.chat.id,))
    if user != []:
        di_d("delete from users where telega_id = ?", (message.chat.id,))
        di_d("delete from user_timings where telega_id = ?", (message.chat.id,))
        await bot.send_message(message.chat.id, "You have deleted your data from the bot's user database.\n"
                                                "The bot will not send you messages anymore. "
                                                "If you change your mind, press /start.\n🕌 Peace be upon you 🕌")
    else:
        await bot.send_message(message.chat.id, "You are not set up with this bot. "
                                                "If you want to use it, press /start.")
    await state.finish()


@dp.message_handler(commands=['change_settings'], state="*")
async def change_settings(message: types.Message, state: FSMContext):
    await message.answer("Write the bot the name of the country you live in.\n\n"
                         "PS: Make sure the name is spelled correctly.")
    await state.set_state(SetConfigsToBot.waiting_for_choose_country.state)


async def set_hadis_to_time(message, nz_time_arr):
    keyb = types.InlineKeyboardMarkup(row_width=3)
    nz_times_list = nz_time_arr
    if nz_times_list == []:
        await safe_delete(message.chat.id, message.message_id)
        await bot.send_message(message.chat.id, "You do not receive a hadith with any of the prayer reminders. "
                                                "If you want to add a hadith to a reminder, press "
                                                "/set_hadis_to_time")
    else:
        btns = []
        for x in nz_times_list:
            btns.append(types.InlineKeyboardButton(text=x, callback_data=f'without_{x}'))
        keyb.add(*btns)
        commands_options = [
            types.InlineKeyboardButton(text="❌ Cancel", callback_data=f"otmena_{message.message_id}"),
            types.InlineKeyboardButton(text="💾 Save", callback_data=f"save_{message.message_id}")
        ]
        keyb.row(*commands_options)
        await safe_delete(message.chat.id, message.message_id)
        await bot.send_message(message.chat.id,
                               "Choose the prayer times for which the reminder will come WITHOUT a hadith",
                               reply_markup=keyb)


def nz_names_from_usr_bd_for_text(telega_id):
    nz_names = get_user_nz_names(telega_id)
    if not nz_names:
        return ""
    return ", ".join(nz_names)


async def save_and_close(call, state, mes):  # SAVING THE MESSAGE
    await bot.send_message(call.message.chat.id, mes)
    await state.finish()
    await safe_delete(call.message.chat.id, call.message.message_id)
    await bot.answer_callback_query(callback_query_id=call.id)


@dp.callback_query_handler(lambda call: re.fullmatch(r'save\_[0-9]+', call.data), state="*")
async def save_for_nz_without_hadis(call: types.CallbackQuery, state: FSMContext):
    await save_and_close(call, state, f"Reminder settings saved. The bot will send hadiths with the reminders "
                                      f"for the following prayers: {nz_names_from_usr_bd_for_text(call.message.chat.id)}")


@dp.callback_query_handler(lambda call: re.fullmatch(r'otmena\_[0-9]+', call.data), state="*")  # CANCEL
async def otmena(call: types.CallbackQuery, state: FSMContext):
    await state.finish()
    await safe_delete(call.message.chat.id, call.message.message_id)
    await bot.answer_callback_query(callback_query_id=call.id)


@dp.callback_query_handler(lambda call: re.fullmatch(r'without\_([A-Za-z]+)', call.data))
async def remove_nz_name(call: types.CallbackQuery):
    """Removes from the list of prayers the name for which a hadith will no longer be sent."""
    nz_wich_will_be_deleted = call.data.split('_')[1]
    nz_local = get_user_nz_names(call.message.chat.id)
    if nz_local is None:
        await bot.answer_callback_query(callback_query_id=call.id)
        return
    if nz_wich_will_be_deleted in nz_local:
        nz_local.remove(nz_wich_will_be_deleted)
        di_d("update users set nz_times_with_hadis = ? where telega_id = ?",
             (json.dumps(nz_local, ensure_ascii=False), call.message.chat.id))
    await set_hadis_to_time(call.message, nz_local)
    await bot.answer_callback_query(callback_query_id=call.id)


@dp.message_handler(commands=["del_hadis_from_time"])
async def dhadis_to_time(message: types.Message):
    nz_names = get_user_nz_names(message.chat.id)
    if nz_names is None:
        await message.answer("You are not set up with this bot. "
                             "If you want to use it, press /start.")
        return
    await set_hadis_to_time(message, nz_names)


@dp.message_handler(commands=["set_hadis_to_time"])
async def shadis_to_time(message: types.Message):
    nz_names = get_user_nz_names(message.chat.id)
    if nz_names is None:
        await message.answer("You are not set up with this bot. "
                             "If you want to use it, press /start.")
        return
    await insept_hadis_to_time(message, nz_names)


async def insept_hadis_to_time(message, nz_time_arr):
    matched = 0
    keyb = types.InlineKeyboardMarkup(row_width=3)

    # All five prayer names; we remove the ones that already come with a hadith
    nz_times_names_local = list(nz_times_names)
    nz_times_list = nz_time_arr
    for x in nz_times_list:
        if x in nz_times_names_local:
            matched = matched + 1
            nz_times_names_local.remove(x)

    if matched == 5:
        await safe_delete(message.chat.id, message.message_id)
        await bot.send_message(message.chat.id, "You receive hadiths with all five prayer reminders. "
                                                "If you want to remove the hadith from a reminder, press "
                                                "/del_hadis_from_time")
    else:
        btns = []
        for z in nz_times_names_local:
            btns.append(types.InlineKeyboardButton(text=z, callback_data=f'with_{z}'))
        keyb.add(*btns)
        commands_options = [
            types.InlineKeyboardButton(text="❌ Cancel", callback_data=f"otmena_{message.message_id}"),
            types.InlineKeyboardButton(text="💾 Save", callback_data=f"save_{message.message_id}"),
        ]
        keyb.row(*commands_options)
        await safe_delete(message.chat.id, message.message_id)
        await bot.send_message(message.chat.id,
                               "Choose the prayer times for which the reminder will come WITH a hadith",
                               reply_markup=keyb)


@dp.callback_query_handler(lambda call: re.fullmatch(r'with\_([A-Za-z]+)', call.data))
async def add_nz_name(call: types.CallbackQuery):
    """Adds to the list of prayers the name for which a hadith will be sent."""
    nz_wich_will_be_added = call.data.split('_')[1]
    nz_local = get_user_nz_names(call.message.chat.id)
    if nz_local is None:
        await bot.answer_callback_query(callback_query_id=call.id)
        return
    if nz_wich_will_be_added not in nz_local:
        nz_local.append(nz_wich_will_be_added)
        di_d("update users set nz_times_with_hadis = ? where telega_id = ?",
             (json.dumps(nz_local, ensure_ascii=False), call.message.chat.id))
    await insept_hadis_to_time(call.message, nz_local)
    await bot.answer_callback_query(callback_query_id=call.id)


# SENDING A MESSAGE TO THE ADMIN
@dp.message_handler(commands=["send_message_to_admin"], state="*")
async def message_init(message: types.Message, state: FSMContext):
    keyb = types.InlineKeyboardMarkup(row_width=3)
    cancel = [types.InlineKeyboardButton(text="❌ Cancel", callback_data=f"otmena_{message.message_id}"), ]
    keyb.add(*cancel)
    await bot.send_message(message.chat.id,
                           "Write your message to the administrator in a reply to this message. "
                           "If you want to get an answer, include your email in the message.", reply_markup=keyb)
    await state.set_state(SetConfigsToBot.waiting_for_send_message_to_admin.state)


@dp.message_handler(state=SetConfigsToBot.waiting_for_send_message_to_admin)
async def send_message_to_admin(message: types.Message, state: FSMContext):
    if len(message.text or "") >= 6:
        chat_id = message.chat.id
        button_url = f'tg://openmessage?user_id={chat_id}'
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(text="Open user", url=button_url))
        await bot.send_message(ADMIN_ID,
                               f"Message from user: "
                               f"@{message.from_user.username if message.from_user.username is not None else message.chat.id}"
                               f"\n{message.text}", reply_markup=markup)
        await bot.send_message(message.chat.id, "Your message has been sent to the administrator.")
    else:
        await bot.send_message(message.chat.id,
                               "Your message is incorrect. Please try again: "
                               "press /send_message_to_admin")
    await state.finish()
# SENDING A MESSAGE TO THE ADMIN


# VIEWING ALL USERS
@dp.message_handler(commands=["users"])
async def show_all_users(message: types.Message):
    if message.chat.id == ADMIN_ID:
        users_arr = select_data("select*from users")
        txt = ''
        num = 0
        for user in users_arr:
            num = num + 1
            txt = txt + str(num) + ') ' + str(user["name"]) + ' ' + str(user["country"]) + ' ' \
                  + str(user["city"]) + ' ' + str(user["mazhab"]) + '\n'
        # splitting into parts so as not to hit the message length limit
        for i in range(0, len(txt), 4000):
            await bot.send_message(message.chat.id, txt[i:i + 4000])
    else:
        await bot.send_message(message.chat.id, 'This command is available to the administrator only.')
# VIEWING ALL USERS


# SEND A MESSAGE TO ALL USERS
@dp.message_handler(commands=["send_all"], state="*")
async def send_message_from_admin_init(message: types.Message, state: FSMContext):
    if message.chat.id == ADMIN_ID:
        await bot.send_message(message.chat.id, "Write the message to send to all users")
        await state.set_state(SetConfigsToBot.waiting_for_send_message_to_all.state)
    else:
        await bot.send_message(message.chat.id, 'This command is available to the administrator only.')


@dp.message_handler(state=SetConfigsToBot.waiting_for_send_message_to_all)
async def send_message_from_admin(message: types.Message, state: FSMContext):
    admin_message = message.text
    users_arr = select_data("select*from users")
    sent = 0
    for user in users_arr:
        try:
            await asyncio.sleep(random.randint(1, 10))  # sleep before sending
            await bot.send_message(user["telega_id"], admin_message)
            sent += 1
        except BotBlocked:
            logging.info("Blocked by user %s, you have sent the message to everyone", user["telega_id"])
            await asyncio.sleep(1)
        except Exception:
            logging.exception("Failed to send the message to user %s", user["telega_id"])
            await asyncio.sleep(1)
    await bot.send_message(message.chat.id, f"The mailing has finished. Delivered {sent} of {len(users_arr)} messages.")
    await state.finish()
# SEND A MESSAGE TO ALL USERS


async def send_all_timings(city, telega_id, timings, message_obj):
    msg = (f'<b>{city.capitalize()}. Today: {dt.now().strftime("%d/%m/%Y")}</b>\n\n'
           f'✨ Fajr: <b>{timings[FAJR]}</b>\n'
           f'✨ Dhuhr: <b>{timings[DHUHR]}</b>\n'
           f'✨ Asr: <b>{timings[ASR]}</b>\n'
           f'✨ Maghrib: <b>{timings[MAGHRIB]}</b>\n'
           f'✨ Isha: <b>{timings[ISHA]}</b>\n')
    await bot.send_message(telega_id, msg, parse_mode="HTML")
    await safe_delete(telega_id, message_obj["message_id"])  # deleting the sent message


@dp.message_handler(content_types='text', state="*")
async def report_handler(message: types.Message, state: FSMContext):
    if message.text != TODAY_BUTTON:
        return
    await state.finish()

    def fetch_rows():
        return select_data("select*from user_timings inner join users USING(telega_id) "
                           "where date = ? and telega_id=?", (dt.now().date(), message.chat.id,))

    rows = fetch_rows()
    if rows:
        await send_all_timings(rows[0]["city"], message.chat.id, json.loads(rows[0]["timings"]), message)
        return

    # There is no schedule for today - we pull the calendar from the user's settings
    user_rows = select_data("select*from users where telega_id = ?", (message.chat.id,))
    if not user_rows:
        await message.answer("You are not set up with this bot. Press /start to set it up.")
        return
    user = user_rows[0]
    try:
        calendar = await get_calendar(user["city"], user["country"], user["mazhab"])
    except Exception:
        logging.exception("Could not fetch the calendar for telega_id=%s", message.chat.id)
        await message.answer("Could not fetch the prayer times. Perhaps you misspelled your location during the "
                             "setup (check it via /change_settings) or the server is temporarily unavailable. "
                             "Please try again later.")
        return
    di_d("delete from user_timings where telega_id = ?", (message.chat.id,))
    await correct_timings_insertor(message.chat.id, calendar)
    rows = fetch_rows()
    if rows:
        await send_all_timings(rows[0]["city"], message.chat.id, json.loads(rows[0]["timings"]), message)
    else:
        await message.answer("Could not fetch today's prayer times. Please try again later.")


async def correct_timings_insertor(chat_id, calendar):
    timings_data = []
    timezone = calendar["data"][0]["meta"]["timezone"]

    for day in calendar["data"]:
        times_arr = []
        for key in PRAYER_KEYS:
            parsed = parse_hhmm(day["timings"][key])
            if parsed is None:
                raise ValueError(f"Could not parse the time '{key}': {day['timings'][key]}")
            hh, mm = parsed
            times_arr.append(f"{hh:02d}:{mm:02d}")

        # CONVERTING THE DATE INTO THE REQUIRED FORMAT
        day_date = dt.strptime(day["date"]["gregorian"]["date"], '%d-%m-%Y').date()

        timings_data.append((
            chat_id,
            json.dumps(times_arr),
            timezone,
            str(day_date),
            json.dumps(day["date"]["hijri"].get("holidays", [])),
        ))

    insert_many("INSERT INTO user_timings(telega_id, timings, timezone, date, holidays) VALUES(?, ?, ?, ?, ?);",
                timings_data)
    logging.info("Schedule saved for telega_id=%s", chat_id)


async def noon_print(telega_id, mes, hds):
    try:
        await asyncio.sleep(random.randint(1, 10))  # sleep before sending
        full = f"{mes}{' ' * 28}🌹🌹🌹{' ' * 28}\n{hds}"
        if len(full) <= 4096:
            await bot.send_message(telega_id, full)
        else:
            # long messages are split into parts respecting the Telegram limit
            for i in range(0, len(full), 4096):
                await bot.send_message(telega_id, full[i:i + 4096])
                await asyncio.sleep(0.5)
    except BotBlocked:
        logging.info("Someone blocked the bot: %s", telega_id)
        await asyncio.sleep(1)
    except Exception:
        logging.exception("Failed to send the reminder to user %s", telega_id)


def hadis(namaz, arr):
    if namaz in arr:
        rows = select_data('select khadis from khadisy order by RANDOM() LIMIT 1')
        if rows:
            return rows[0][0]
        # the khadisy table is empty (main.py was never run with a hadith file) - send the text without a hadith
    return 'Peace be upon you'


def schedule_creator(outside_timings):
    seen_ids = set()
    for row in outside_timings:
        telega_id = row["telega_id"]
        if telega_id in seen_ids:
            continue  # protection against duplicated schedules of one user
        seen_ids.add(telega_id)

        t_a = json.loads(row["timings"])
        tz_name = row["timezone"]
        delta_minutes = row["time_delta"]
        nz_times_names_arr = json.loads(row["nz_times_with_hadis"])

        if delta_minutes == 0:
            # reminder at the moment the prayer time starts
            jobs = [
                (FAJR, f"🕌 It's time to perform the Fajr (Morning) prayer! 🕌\nEnds at {t_a[SUNRISE]}\n\n", "Fajr"),
                (DHUHR, f"🕌 It's time to perform the Dhuhr (Midday) prayer! 🕌\nEnds at {t_a[ASR]}\n\n", "Dhuhr"),
                (ASR, f"🕌 It's time to perform the Asr (Afternoon) prayer! 🕌\nEnds at {t_a[MAGHRIB]}\n\n", "Asr"),
                (MAGHRIB, f"🕌 It's time to perform the Maghrib (Evening) prayer! 🕌\nEnds at {t_a[ISHA]}\n\n", "Maghrib"),
                (ISHA, f"🕌 It's time to perform the Isha (Night) prayer! 🕌\nEnds at {t_a[FAJR]}\n\n", "Isha"),
            ]
            for index, text, nz_name in jobs:
                parsed = parse_hhmm(t_a[index])
                if parsed is None:
                    continue
                hh, mm = parsed
                at = local_to_server_time(tz_name, hh, mm).strftime('%H:%M')
                aioschedule.every().day.at(at).do(noon_print, telega_id, text, hadis(nz_name, nz_times_names_arr))
        else:
            # reminder N minutes before the prayer time ends
            minutes = abs(delta_minutes)
            jobs = [
                (SUNRISE, f"🕌 The time for the Fajr (Morning) prayer ends in {minutes} minutes! 🕌\n"
                          f"Ends at {t_a[SUNRISE]}\n\n", "Fajr"),
                (ASR, f"🕌 The time for the Dhuhr (Midday) prayer ends in {minutes} minutes! 🕌\n"
                      f"Ends at {t_a[ASR]}\n\n", "Dhuhr"),
                (MAGHRIB, f"🕌 The time for the Asr (Afternoon) prayer ends in {minutes} minutes! 🕌\n"
                          f"Ends at {t_a[MAGHRIB]}\n\n", "Asr"),
                (ISHA, f"🕌 The time for the Maghrib (Evening) prayer ends in {minutes} minutes! 🕌\n"
                       f"Ends at {t_a[ISHA]}\nThe Isha (Night) prayer time ends at {t_a[FAJR]}\n\n", "Maghrib"),
                (MIDNIGHT, "🕌 If you have not performed the Isha (Night) prayer yet, it is recommended "
                           "to do so now. 🕌\n\n", "Isha"),
            ]
            for index, text, nz_name in jobs:
                parsed = parse_hhmm(t_a[index])
                if parsed is None:
                    continue
                hh, mm = parsed
                at = (local_to_server_time(tz_name, hh, mm) - timedelta(minutes=minutes)).strftime('%H:%M')
                aioschedule.every().day.at(at).do(noon_print, telega_id, text, hadis(nz_name, nz_times_names_arr))


async def timings_from_bd():
    aioschedule.clear()
    today = dt.now().date()

    # clean up the schedules of users who are no longer in the database
    di_d("delete from user_timings where telega_id not in (select telega_id from users)")

    timings = select_data("select*from user_timings inner join users USING(telega_id) where date = ?", (today,))
    users = select_data("select*from users")

    ids_with_today = {row["telega_id"] for row in timings}
    for user in users:
        if user["telega_id"] in ids_with_today:
            continue
        try:
            di_d("delete from user_timings where telega_id = ?", (user["telega_id"],))
            calendar = await get_calendar(user["city"], user["country"], user["mazhab"])
            await correct_timings_insertor(user["telega_id"], calendar)
        except Exception:
            logging.exception("Could not update the schedule for telega_id=%s", user["telega_id"])
        await asyncio.sleep(2)  # so as not to overload the API

    fresh_timings = select_data("select*from user_timings inner join users USING(telega_id) where date = ?", (today,))
    if fresh_timings:
        schedule_creator(fresh_timings)
    aioschedule.every(3).minutes.do(timings_from_bd)


async def scheduler():
    aioschedule.every(3).minutes.do(timings_from_bd)
    while True:
        try:
            await aioschedule.run_pending()
        except Exception:
            # an error in one of the jobs must not kill the whole scheduler
            logging.exception("Error while running the scheduled jobs")
        await asyncio.sleep(1)


async def on_start(_):
    asyncio.create_task(scheduler())


if __name__ == '__main__':

    executor.start_polling(
        dispatcher=dp,
        skip_updates=True,
        on_startup=on_start
    )
