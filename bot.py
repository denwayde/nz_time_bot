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

nz_times_names = ["Утренний", "Обеденный", "Послеобеденный", "Вечерний", "Ночной"]

# Порядок времён намаза в сохраняемом массиве соответствует порядку ключей в ответе API aladhan:
# Fajr, Sunrise, Dhuhr, Asr, Maghrib, Isha, Midnight (Imsak/Sunset/Firstthird/Lastthird отбрасываются)
FAJR, SUNRISE, DHUHR, ASR, MAGHRIB, ISHA, MIDNIGHT = range(7)
PRAYER_KEYS = ("Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha", "Midnight")

# API иногда возвращает время с пробелами после двоеточия: "21: 16 (+05)"
TIME_RE = re.compile(r'(\d{1,2})\s*:\s*(\d{1,2})')

API_URL = ("http://api.aladhan.com/v1/calendarByCity/{year}/{month}"
           "?city={city}&country={country}&method=14&school={school}")


# ============================ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ============================

def parse_hhmm(text):
    """Разбирает строку времени вида '05:22 (+05)' или '21: 16 (+05)'."""
    m = TIME_RE.search(text)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


async def safe_delete(chat_id, message_id):
    """Удаляет сообщение, не падая, если сообщение уже удалено или слишком старое."""
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


def fetch_calendar(city, country, school):
    """Синхронный запрос месячного календаря намазов (выполняется в executor)."""
    url = API_URL.format(year=dt.now().year, month=dt.now().month,
                         city=city, country=country, school=school)
    resp = requests.get(url, timeout=30)
    data = resp.json()
    if data.get("code") != 200 or not data.get("data"):
        raise ValueError(f"aladhan API вернул ошибку для {country}/{city}: {data.get('code')}")
    return data


async def get_calendar(city, country, school):
    """Не блокирует event loop: запрос к API выполняется в отдельном потоке."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fetch_calendar, city, country, school)


def local_to_server_time(tz_name, hh, mm):
    """Переводит локальное время намаза пользователя в серверное локальное время.

    Корректно обрабатывает часовые пояса, DST и переход через полночь
    (в отличие от разницы часов dt.now().hour - dt.now(tz).hour).
    """
    tz = pytz.timezone(tz_name)
    naive = dt.now(tz).replace(tzinfo=None, hour=hh, minute=mm, second=0, microsecond=0)
    return tz.localize(naive).astimezone()


def get_user_nz_names(telega_id):
    """Возвращает список времён намаза пользователя с хадисами (None - не инициализирован)."""
    rows = select_data("select nz_times_with_hadis from users where telega_id = ?", (telega_id,))
    if not rows:
        return None
    return json.loads(rows[0][0])


# ============================ ХЕНДЛЕРЫ ============================

@dp.message_handler(commands='start', state="*")
async def send_welcome(message: types.Message, state: FSMContext):
    user_exist = select_data("select*from users where telega_id = ?", (message.chat.id,))
    if user_exist == []:
        await message.answer("Здравствуйте, этот бот напомнит вам о чтении намаза сообщением с хадисом.\n"
                             "Давайте выполним первоначальные настройки. Напишите боту название страны, "
                             "в которой вы проживаете.\n\nPS: Убедитесь в правильности написания названия")
        await safe_delete(message.chat.id, message.message_id)
        await state.set_state(SetConfigsToBot.waiting_for_choose_country.state)
    else:
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        buttons = ["Времена намазов на сегодня", ]
        keyboard.add(*buttons)
        await message.answer("Вы инициализированный пользователь бота", reply_markup=keyboard)
        await safe_delete(message.chat.id, message.message_id)


@dp.message_handler(state=SetConfigsToBot.waiting_for_choose_country)
async def choosen_country_handler(message: types.Message, state: FSMContext):
    await state.update_data(chosen_country=message.text)
    await message.answer(f"Вы выбрали страну {message.text}.\nНапишите боту город в котором Вы живете.")
    await safe_delete(message.chat.id, message.message_id)
    await state.set_state(SetConfigsToBot.waiting_for_choose_city.state)


@dp.message_handler(state=SetConfigsToBot.waiting_for_choose_city)
async def choosen_city_handler(message: types.Message, state: FSMContext):
    btns = [
        types.InlineKeyboardButton(text='Ханафи', callback_data='hanafi'),
        types.InlineKeyboardButton(text='Шафии', callback_data='shafii')
    ]
    keyb = types.InlineKeyboardMarkup(row_width=2)
    keyb.add(*btns)
    await state.update_data(chosen_city=message.text)
    await message.answer(f"Вы выбрали город {message.text}.\nНапишите боту мазхаб, которому Вы следуете.",
                         reply_markup=keyb)
    await safe_delete(message.chat.id, message.message_id)
    await state.set_state(SetConfigsToBot.waiting_for_choose_mazhab.state)


async def choosen_mazhab_handler(call, state, message_data):
    btns = [
        types.InlineKeyboardButton(text='За полчаса до окончания', callback_data='-30'),
        types.InlineKeyboardButton(text='С заходом', callback_data='0'),
        types.InlineKeyboardButton(text='За час до окончания', callback_data='-60')
    ]
    keyb = types.InlineKeyboardMarkup(row_width=3)
    keyb.add(*btns)
    await state.update_data(chosen_mazhab=message_data)
    await call.message.answer(f"Вы выбрали мазхаб {message_data}. "
                              f"Выберите удобное для Вас время напоминания о выполнении намаза",
                              reply_markup=keyb)
    await safe_delete(call.message.chat.id, call.message.message_id)
    await bot.answer_callback_query(callback_query_id=call.id)
    await state.set_state(SetConfigsToBot.waiting_for_choose_delta_time.state)


@dp.callback_query_handler(lambda call: call.data == 'hanafi', state=SetConfigsToBot.waiting_for_choose_mazhab)
async def choose_hanafi_handler(call: types.CallbackQuery, state: FSMContext):  # если выбрали ханафи
    await choosen_mazhab_handler(call, state, "Ханафи")


@dp.callback_query_handler(lambda call: call.data == 'shafii', state=SetConfigsToBot.waiting_for_choose_mazhab)
async def choose_shafii_handler(call: types.CallbackQuery, state: FSMContext):  # если выбрали Шафии
    await choosen_mazhab_handler(call, state, "Шафии")


async def choose_delta_minutes_and_save_settings(call, state, delta_time):
    await bot.answer_callback_query(callback_query_id=call.id)
    user_data = await state.get_data()

    mazh = 1
    if user_data['chosen_mazhab'] == "Шафии":
        mazh = 0

    try:
        # Сначала проверяем, что API принимает такую страну/город,
        # и только после этого сохраняем пользователя в базу
        calendar = await get_calendar(user_data['chosen_city'], user_data['chosen_country'], mazh)
    except Exception:
        logging.exception("Не удалось получить календарь для %s/%s",
                          user_data['chosen_country'], user_data['chosen_city'])
        await call.message.answer("Что-то пошло не так!\nВозможно вы опечатались в названии своей страны или города "
                                  "или сервер временно недоступен. Попробуйте повторить процедуру настройки, "
                                  "для этого нажмите на /start.")
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
    buttons = ["Времена намазов на сегодня", ]
    keyboard.add(*buttons)
    await call.message.answer("Настройки бота завершены, в течении 5 минут Ваши данные будут инициализированы.\n"
                              "Если Вы передумаете использовать бота нажмите на /delete_user для удаления своего "
                              "аккаунта из базы данных бота. Если Вы захотите изменить ранее инициализированные "
                              "настройки местности или времени оповещения нажмите на /change_settings. "
                              "Если Вы захотите убрать хадис из какого либо напоминания нажмите на "
                              "/del_hadis_from_time. Если захотите написать администратору то нажмите на "
                              "/send_message_to_admin. Эти команды есть в меню расположенное слева от поля ввода "
                              "сообщения (синяя кнопка). \nВ нужное время бот иншАлла пришлет оповещение. "
                              "\n🕌 Мир Вам 🕌", reply_markup=keyboard)
    await safe_delete(call.message.chat.id, call.message.message_id)
    await state.finish()


@dp.callback_query_handler(lambda call: call.data == '-30', state=SetConfigsToBot.waiting_for_choose_delta_time)
async def choose_delta_thirty(call: types.CallbackQuery, state: FSMContext):  # конец настроек
    await choose_delta_minutes_and_save_settings(call, state, '-30')


@dp.callback_query_handler(lambda call: call.data == '0', state=SetConfigsToBot.waiting_for_choose_delta_time)
async def choose_delta_zero(call: types.CallbackQuery, state: FSMContext):  # конец настроек
    await choose_delta_minutes_and_save_settings(call, state, '0')


@dp.callback_query_handler(lambda call: call.data == '-60', state=SetConfigsToBot.waiting_for_choose_delta_time)
async def choose_delta_sixty(call: types.CallbackQuery, state: FSMContext):  # конец настроек
    await choose_delta_minutes_and_save_settings(call, state, '-60')


@dp.message_handler(commands=['delete_user'])
async def delete_user(message: types.Message, state: FSMContext):
    user = select_data("select*from users where telega_id = ?", (message.chat.id,))
    if user != []:
        di_d("delete from users where telega_id = ?", (message.chat.id,))
        di_d("delete from user_timings where telega_id = ?", (message.chat.id,))
        await bot.send_message(message.chat.id, "Вы удалили свои данные из базы пользователей бота.\n"
                                                "Больше бот не будет отправлять Вам сообщении. "
                                                "Если Вы передумаете нажмите на /start.\n🕌 Мир Вам 🕌")
    else:
        await bot.send_message(message.chat.id, "Вы не инициализированный пользователь бота. "
                                                "Если хотите пользоваться ботом нажмите на /start.")
    await state.finish()


@dp.message_handler(commands=['change_settings'], state="*")
async def change_settings(message: types.Message, state: FSMContext):
    await message.answer("Напишите боту название страны в которой вы проживаете.\n\n"
                         "PS:Обязательно убедитесь в правильности написания названия.")
    await state.set_state(SetConfigsToBot.waiting_for_choose_country.state)


async def set_hadis_to_time(message, nz_time_arr):
    keyb = types.InlineKeyboardMarkup(row_width=3)
    nz_times_list = nz_time_arr
    if nz_times_list == []:
        await safe_delete(message.chat.id, message.message_id)
        await bot.send_message(message.chat.id, "Ни в одно из времен намаза Вам хадис не приходит. "
                                                "Если хотите добавить хадис в напоминание нажмите на "
                                                "/set_hadis_to_time")
    else:
        btns = []
        for x in nz_times_list:
            btns.append(types.InlineKeyboardButton(text=x, callback_data=f'without_{x}'))
        keyb.add(*btns)
        commands_options = [
            types.InlineKeyboardButton(text="❌Отмена", callback_data=f"otmena_{message.message_id}"),
            types.InlineKeyboardButton(text="💾Сохранить", callback_data=f"save_{message.message_id}")
        ]
        keyb.row(*commands_options)
        await safe_delete(message.chat.id, message.message_id)
        await bot.send_message(message.chat.id,
                               "Выберите времена намаза в которых напоминание будет приходить БЕЗ хадиса",
                               reply_markup=keyb)


def nz_names_from_usr_bd_for_text(telega_id):
    nz_names = get_user_nz_names(telega_id)
    if not nz_names:
        return ""
    return ", ".join(nz_names)


async def save_and_close(call, state, mes):  # СОХРАНЕНИЕ СООБЩЕНИЯ
    await bot.send_message(call.message.chat.id, mes)
    await state.finish()
    await safe_delete(call.message.chat.id, call.message.message_id)
    await bot.answer_callback_query(callback_query_id=call.id)


@dp.callback_query_handler(lambda call: re.fullmatch(r'save\_[0-9]+', call.data), state="*")
async def save_for_nz_without_hadis(call: types.CallbackQuery, state: FSMContext):
    await save_and_close(call, state, f"Настройки напоминании сохранены. Бот будет присылать хадисы при напоминании "
                                      f"о следующих намазах: {nz_names_from_usr_bd_for_text(call.message.chat.id)}")


@dp.callback_query_handler(lambda call: re.fullmatch(r'otmena\_[0-9]+', call.data), state="*")  # ОТМЕНА
async def otmena(call: types.CallbackQuery, state: FSMContext):
    await state.finish()
    await safe_delete(call.message.chat.id, call.message.message_id)
    await bot.answer_callback_query(callback_query_id=call.id)


@dp.callback_query_handler(lambda call: re.fullmatch(r'without\_([А-Яа-я]+)', call.data))
async def remove_nz_name(call: types.CallbackQuery):
    """Удаляем из списка намазов то название, в котором хадис приходить больше не будет."""
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
        await message.answer("Вы не инициализированный пользователь бота. "
                             "Если хотите пользоваться ботом нажмите /start.")
        return
    await set_hadis_to_time(message, nz_names)


@dp.message_handler(commands=["set_hadis_to_time"])
async def shadis_to_time(message: types.Message):
    nz_names = get_user_nz_names(message.chat.id)
    if nz_names is None:
        await message.answer("Вы не инициализированный пользователь бота. "
                             "Если хотите пользоваться ботом нажмите /start.")
        return
    await insept_hadis_to_time(message, nz_names)


async def insept_hadis_to_time(message, nz_time_arr):
    sootvetstvie = 0
    keyb = types.InlineKeyboardMarkup(row_width=3)

    nz_times_names_local = ["Утренний", "Обеденный", "Послеобеденный", "Вечерний", "Ночной"]
    nz_times_list = nz_time_arr
    for x in nz_times_list:
        if x in nz_times_names_local:
            sootvetstvie = sootvetstvie + 1
            nz_times_names_local.remove(x)

    if sootvetstvie == 5:
        await safe_delete(message.chat.id, message.message_id)
        await bot.send_message(message.chat.id, "Хадисы Вам приходят во всех пяти временах намаза. "
                                                "Если хотите убрать хадис из напоминания нажмите на "
                                                "/del_hadis_from_time")
    else:
        btns = []
        for z in nz_times_names_local:
            btns.append(types.InlineKeyboardButton(text=z, callback_data=f'with_{z}'))
        keyb.add(*btns)
        commands_options = [
            types.InlineKeyboardButton(text="❌Отмена", callback_data=f"otmena_{message.message_id}"),
            types.InlineKeyboardButton(text="💾Сохранить", callback_data=f"save_{message.message_id}"),
        ]
        keyb.row(*commands_options)
        await safe_delete(message.chat.id, message.message_id)
        await bot.send_message(message.chat.id,
                               "Выберите времена намаза в которых напоминание будет приходить ВМЕСТЕ С хадисом",
                               reply_markup=keyb)


@dp.callback_query_handler(lambda call: re.fullmatch(r'with\_([А-Яа-я]+)', call.data))
async def add_nz_name(call: types.CallbackQuery):
    """Добавляем в список намазов название, в котором хадис будет приходить."""
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


# ОТПРАВКА СООБЩЕНИЯ АДМИНУ
@dp.message_handler(commands=["send_message_to_admin"], state="*")
async def message_init(message: types.Message, state: FSMContext):
    keyb = types.InlineKeyboardMarkup(row_width=3)
    otmena = [types.InlineKeyboardButton(text="❌Отмена", callback_data=f"otmena_{message.message_id}"), ]
    keyb.add(*otmena)
    await bot.send_message(message.chat.id,
                           "Напишите сообщение администратору в ответ на это сообщение. "
                           "Если вы хотите получить ответ, напишите email в сообщении.", reply_markup=keyb)
    await state.set_state(SetConfigsToBot.waiting_for_send_message_to_admin.state)


@dp.message_handler(state=SetConfigsToBot.waiting_for_send_message_to_admin)
async def send_message_to_admin(message: types.Message, state: FSMContext):
    if len(message.text or "") >= 6:
        chat_id = message.chat.id
        button_url = f'tg://openmessage?user_id={chat_id}'
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(text="Open user", url=button_url))
        await bot.send_message(ADMIN_ID,
                               f"Сообщение от пользователя: "
                               f"@{message.from_user.username if message.from_user.username is not None else message.chat.id}"
                               f"\n{message.text}", reply_markup=markup)
        await bot.send_message(message.chat.id, "Ваше сообщение отправлено администратору.")
    else:
        await bot.send_message(message.chat.id,
                               "Ваше сообщение не корректно. Попробуйте повторить попытку: "
                               "нажмите на /send_message_to_admin")
    await state.finish()
# ОТПРАВКА СООБЩЕНИЯ АДМИНУ


# ПРОСМОТР ВСЕХ ПОЛЬЗОВАТЕЛЕЙ
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
        # разбиение на части, чтобы не упереться в лимит длины сообщения
        for i in range(0, len(txt), 4000):
            await bot.send_message(message.chat.id, txt[i:i + 4000])
    else:
        await bot.send_message(message.chat.id, '))))')
# ПРОСМОТР ВСЕХ ПОЛЬЗОВАТЕЛЕЙ


# ОТПРАВИТЬ СООБЩЕНИЕ ВСЕМ ПОЛЬЗОВАТЕЛЯМ
@dp.message_handler(commands=["send_all"], state="*")
async def send_message_from_admin_init(message: types.Message, state: FSMContext):
    if message.chat.id == ADMIN_ID:
        await bot.send_message(message.chat.id, "Напиши всем сообщение")
        await state.set_state(SetConfigsToBot.waiting_for_send_message_to_all.state)
    else:
        await bot.send_message(message.chat.id, ")))))")


@dp.message_handler(state=SetConfigsToBot.waiting_for_send_message_to_all)
async def send_message_from_admin(message: types.Message, state: FSMContext):
    admin_message = message.text
    users_arr = select_data("select*from users")
    sent = 0
    for user in users_arr:
        try:
            await asyncio.sleep(random.randint(1, 10))  # перед отправкой пусть заснет
            await bot.send_message(user["telega_id"], admin_message)
            sent += 1
        except BotBlocked:
            logging.info("Блокировка юзером %s, ты отправил всем сообщение", user["telega_id"])
            await asyncio.sleep(1)
        except Exception:
            logging.exception("Не удалось отправить сообщение пользователю %s", user["telega_id"])
            await asyncio.sleep(1)
    await bot.send_message(message.chat.id, f"Рассылка завершена. Доставлено сообщений: {sent} из {len(users_arr)}.")
    await state.finish()
# ОТПРАВИТЬ СООБЩЕНИЕ ВСЕМ ПОЛЬЗОВАТЕЛЯМ


async def send_all_timings(city, telega_id, timings, message_obj):
    msg = (f'<b>{city.capitalize()}. Сегодня: {dt.now().strftime("%d/%m/%Y")}</b>\n\n'
           f'✨Утренний: <b>{timings[FAJR]}</b>\n'
           f'✨Обеденный: <b>{timings[DHUHR]}</b>\n'
           f'✨Послеобеденный: <b>{timings[ASR]}</b>\n'
           f'✨Вечерний: <b>{timings[MAGHRIB]}</b>\n'
           f'✨Ночной: <b>{timings[ISHA]}</b>\n')
    await bot.send_message(telega_id, msg, parse_mode="HTML")
    await safe_delete(telega_id, message_obj["message_id"])  # удаление отправленного сообщения


@dp.message_handler(content_types='text', state="*")
async def report_handler(message: types.Message, state: FSMContext):
    if message.text != 'Времена намазов на сегодня':
        return
    await state.finish()

    def fetch_rows():
        return select_data("select*from user_timings inner join users USING(telega_id) "
                           "where date = ? and telega_id=?", (dt.now().date(), message.chat.id,))

    rows = fetch_rows()
    if rows:
        await send_all_timings(rows[0]["city"], message.chat.id, json.loads(rows[0]["timings"]), message)
        return

    # Расписания на сегодня нет - подтягиваем календарь из настроек пользователя
    user_rows = select_data("select*from users where telega_id = ?", (message.chat.id,))
    if not user_rows:
        await message.answer("Вы не инициализированный пользователь бота. Нажмите /start для настройки.")
        return
    user = user_rows[0]
    try:
        calendar = await get_calendar(user["city"], user["country"], user["mazhab"])
    except Exception:
        logging.exception("Не удалось получить календарь для telega_id=%s", message.chat.id)
        await message.answer("Не удалось получить времена намазов. Возможно, вы опечатались при настройке "
                             "(проверьте через /change_settings) или сервер временно недоступен. Попробуйте позже.")
        return
    di_d("delete from user_timings where telega_id = ?", (message.chat.id,))
    await correct_timings_insertor(message.chat.id, calendar)
    rows = fetch_rows()
    if rows:
        await send_all_timings(rows[0]["city"], message.chat.id, json.loads(rows[0]["timings"]), message)
    else:
        await message.answer("Не удалось получить времена намазов на сегодня. Попробуйте позже.")


async def correct_timings_insertor(chat_id, calendar):
    timings_data = []
    timezone = calendar["data"][0]["meta"]["timezone"]

    for day in calendar["data"]:
        times_arr = []
        for key in PRAYER_KEYS:
            parsed = parse_hhmm(day["timings"][key])
            if parsed is None:
                raise ValueError(f"Не удалось разобрать время '{key}': {day['timings'][key]}")
            hh, mm = parsed
            times_arr.append(f"{hh:02d}:{mm:02d}")

        # ОБРАБОТКА ДАТЫ В НУЖНЫЙ ФОРМАТ
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
    logging.info("Расписание сохранено для telega_id=%s", chat_id)


async def noon_print(telega_id, mes, hds):
    try:
        await asyncio.sleep(random.randint(1, 10))  # перед отправкой пусть заснет
        full = f"{mes}{' ' * 28}🌹🌹🌹{' ' * 28}\n{hds}"
        if len(full) <= 4096:
            await bot.send_message(telega_id, full)
        else:
            # длинные сообщения режем на части с учётом лимита Telegram
            for i in range(0, len(full), 4096):
                await bot.send_message(telega_id, full[i:i + 4096])
                await asyncio.sleep(0.5)
    except BotBlocked:
        logging.info("Кто-то заблокировал бота: %s", telega_id)
        await asyncio.sleep(1)
    except Exception:
        logging.exception("Ошибка отправки напоминания пользователю %s", telega_id)


def hadis(namaz, arr):
    if namaz in arr:
        return select_data('select khadis from khadisy order by RANDOM() LIMIT 1')[0][0]
    else:
        return 'Мир Вам'


def schedule_creator(outside_timings):
    seen_ids = set()
    for row in outside_timings:
        telega_id = row["telega_id"]
        if telega_id in seen_ids:
            continue  # защита от дублей расписаний одного пользователя
        seen_ids.add(telega_id)

        t_a = json.loads(row["timings"])
        tz_name = row["timezone"]
        delta_minutes = row["time_delta"]
        nz_times_names_arr = json.loads(row["nz_times_with_hadis"])

        if delta_minutes == 0:
            # напоминание в момент наступления времени намаза
            jobs = [
                (FAJR, f"🕌 Прочитай Фаджр (Утренний)!🕌\nОкончание в {t_a[SUNRISE]}\n\n", "Утренний"),
                (DHUHR, f"🕌 Прочитай Зухр (Обеденный)!🕌\nОкончание в {t_a[ASR]}\n\n", "Обеденный"),
                (ASR, f"🕌 Прочитай Аср (Послеобеденный)!🕌\nОкончание в {t_a[MAGHRIB]}\n\n", "Послеобеденный"),
                (MAGHRIB, f"🕌 Прочитай Магриб (Вечерний)!🕌\nОкончание в {t_a[ISHA]}\n\n", "Вечерний"),
                (ISHA, f"🕌 Прочитай Иша (Ночной)!🕌\nОкончание в {t_a[FAJR]}\n\n", "Ночной"),
            ]
            for index, text, nz_name in jobs:
                parsed = parse_hhmm(t_a[index])
                if parsed is None:
                    continue
                hh, mm = parsed
                at = local_to_server_time(tz_name, hh, mm).strftime('%H:%M')
                aioschedule.every().day.at(at).do(noon_print, telega_id, text, hadis(nz_name, nz_times_names_arr))
        else:
            # напоминание за N минут до окончания времени намаза
            minutes = abs(delta_minutes)
            jobs = [
                (SUNRISE, f"🕌 Через {minutes} минут закончится время выполнения намаза Фаджр (Утренний)!🕌\n"
                          f"Окончание в {t_a[SUNRISE]}\n\n", "Утренний"),
                (ASR, f"🕌 Через {minutes} минут закончится время выполнения намаза Зухр (Обеденный)!🕌\n"
                      f"Окончание в {t_a[ASR]}\n\n", "Обеденный"),
                (MAGHRIB, f"🕌 Через {minutes} минут закончится время выполнения намаза Аср (Послеобеденный)!🕌\n"
                          f"Окончание в {t_a[MAGHRIB]}\n\n", "Послеобеденный"),
                (ISHA, f"🕌 Через {minutes} минут закончится время выполнения намаза Магриб (Вечерний)!🕌\n"
                       f"Окончание в {t_a[ISHA]}\nНочной намаз закончится в {t_a[FAJR]}\n\n", "Вечерний"),
                (MIDNIGHT, "🕌 Желательно прочитать Иша (Ночной), если Вы еще не прочитали. 🕌\n\n", "Ночной"),
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

    # чистим расписания пользователей, которых больше нет в базе
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
            logging.exception("Не удалось обновить расписание для telega_id=%s", user["telega_id"])
        await asyncio.sleep(2)  # чтобы не перегружать API

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
            # ошибка в одной из задач не должна убивать весь планировщик
            logging.exception("Ошибка при выполнении запланированных задач")
        await asyncio.sleep(1)


async def on_strtp(_):
    asyncio.create_task(scheduler())


if __name__ == '__main__':

    executor.start_polling(
        dispatcher=dp,
        skip_updates=True,
        on_startup=on_strtp
    )
