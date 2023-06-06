import logging
from aiogram import Bot, Dispatcher, executor, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.utils.exceptions import BotBlocked
from config_reader import config
from db import delete_or_insert_data as di_d, select_data, insert_many
import requests
from datetime import datetime as dt, timedelta
import json
import pytz
import re
import asyncio
import aioschedule
import random


class SetConfigsToBot(StatesGroup):
    waiting_for_choose_country = State()
    waiting_for_choose_city = State()
    waiting_for_choose_mazhab = State()
    waiting_for_choose_delta_time = State()
    waiting_for_send_message_to_admin = State()
    waiting_for_send_message_to_all = State()


API_TOKEN = config.bot_token.get_secret_value()

# Configure logging
logging.basicConfig(level=logging.INFO)
memstore = MemoryStorage()
# Initialize bot and dispatcher
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=memstore)

nz_times_names = ["Утренний", "Обеденный", "Послеобеденный", "Вечерний", "Ночной"]


@dp.message_handler(commands='start', state="*")
async def send_welcome(message: types.Message, state: FSMContext):
    user_exist = select_data("select*from users where telega_id = ?", (message.chat.id, ))
    if user_exist == []:
        await message.answer("Здравствуйте, этот бот напомнит вам о чтении намаза сообщением с хадисом.\nДавайте выполним первоначальные настройки. Напишите боту название страны, в которой вы проживаете.\n\nPS: Убедитесь в правильности написания названия")
        await bot.delete_message(message.chat.id, message["message_id"])
        await state.set_state(SetConfigsToBot.waiting_for_choose_country.state)
    else:
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        buttons = ["Времена намазов на сегодня", ]
        keyboard.add(*buttons)
        await message.answer("Вы инициализированный пользователь бота", reply_markup=keyboard)
        await bot.delete_message(message.chat.id, message["message_id"])


@dp.message_handler(state=SetConfigsToBot.waiting_for_choose_country)
async def choosen_country_handler(message: types.Message, state: FSMContext):
    await state.update_data(chosen_country=message.text)
    await message.answer(f"Вы выбрали страну {message.text}.\nНапишите боту город в котором Вы живете.")
    await bot.delete_message(message.chat.id, message["message_id"])
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
    await message.answer(f"Вы выбрали город {message.text}.\nНапишите боту мазхаб, которому Вы следуете.", reply_markup=keyb)
    await bot.delete_message(message.chat.id, message["message_id"])
    await state.set_state(SetConfigsToBot.waiting_for_choose_mazhab.state)
    # user_data = await state.get_data()
    # await message.answer(f"Вы выбрали город {message.text} и страну {user_data['chosen_country']}")
    # await state.finish()




async def choosen_mazhab_handler(call, state, message_data):
    btns = [
        types.InlineKeyboardButton(text='За полчаса до окончания', callback_data='-30'),
        types.InlineKeyboardButton(text='С заходом', callback_data='0'),
        types.InlineKeyboardButton(text='За час до окончания', callback_data='-60')
    ]
    keyb = types.InlineKeyboardMarkup(row_width=3)
    keyb.add(*btns)
    await state.update_data(chosen_mazhab=message_data)
    await call.message.answer(f"Вы выбрали мазхаб {message_data}. Выберите удобное для Вас время напоминания о выполнении намаза", reply_markup=keyb)
    await bot.delete_message(call.message.chat.id, call.message["message_id"])
    await bot.answer_callback_query(callback_query_id=call.id)
    await state.set_state(SetConfigsToBot.waiting_for_choose_delta_time.state)




@dp.callback_query_handler(lambda call: call.data == 'hanafi', state=SetConfigsToBot.waiting_for_choose_mazhab)
async def choose_hanafi_handler(call: types.CallbackQuery, state: FSMContext):  #esli vibrali hanafi
    await choosen_mazhab_handler(call, state, "Ханафи")



@dp.callback_query_handler(lambda call: call.data == 'shafii', state=SetConfigsToBot.waiting_for_choose_mazhab)
async def choose_shafii_handler(call: types.CallbackQuery, state: FSMContext):  #esli vibrali Шафии
    await choosen_mazhab_handler(call, state, "Шафии")



async def choose_delta_minutes_and_save_settings(call, state, delta_time):
    #reply_markup = types.ReplyKeyboardRemove()
    await state.update_data(chosen_delta=delta_time)
    user_data = await state.get_data()

    mazh = 1
    if user_data['chosen_mazhab'] == "Шафии":
        mazh = 0

    di_d("delete from users where telega_id=?",(call.message.chat.id, ))
    di_d("delete from user_timings where telega_id=?",(call.message.chat.id, ))

    di_d("insert into users(telega_id, name, country, city, mazhab, time_delta, nz_times_with_hadis) values(?,?,?,?,?,?, ?);", (call.message.chat.id, call.message.chat.username, user_data['chosen_country'], user_data['chosen_city'], mazh, int(delta_time), json.dumps(nz_times_names, ensure_ascii=False).encode("utf-8"), ))
    resp = requests.get(
        f"http://api.aladhan.com/v1/calendarByCity/{dt.now().date().year}/{dt.now().date().month}?city={user_data['chosen_city']}&country={user_data['chosen_country']}&method=14&school={mazh}")
    
    if resp.json()['code'] == 200:
        await correct_timings_insertor(call.message.chat.id, resp)
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        buttons = ["Времена намазов на сегодня", ]
        keyboard.add(*buttons)
        await call.message.answer(f"Настройки бота завершены, в течении 5 минут Ваши данные будут инициализированы.\nЕсли Вы передумайте использовать бота нажмите на /delete_user для удаления своего аккаунта из базы данных бота. Если Вы захотите изменить ранее инициализированные настройки местности или времени оповещения нажмите на /change_settings. Если Вы захотите убрать хадис из какого либо напоминания нажмите на /del_hadis_from_time. Если захотите написать администратору то нажмите на /send_message_to_admin. Эти команды есть в меню расположенное слева от поля ввода сообщения (синяя кнопка). \nВ нужное время бот иншАлла пришлет оповещение. \n🕌 Мир Вам 🕌", reply_markup=keyboard)

    else:
        await call.message.answer("Что-то пошло не так!\nВозможно вы опечатались в названии своей страны или города или сервер временно недоступен. Попробуйте повторить процедуру натройки, для этого нажмите на /start.")
    await bot.delete_message(call.message.chat.id, call.message["message_id"])
    await state.finish()


@dp.callback_query_handler(lambda call: call.data == '-30', state=SetConfigsToBot.waiting_for_choose_delta_time)
async def choose_delta_thirty(call: types.CallbackQuery, state: FSMContext):  #konec nastroek
    await choose_delta_minutes_and_save_settings(call, state, '-30')

@dp.callback_query_handler(lambda call: call.data == '0', state=SetConfigsToBot.waiting_for_choose_delta_time)
async def choose_delta_zero(call: types.CallbackQuery, state: FSMContext):  #konec nastroek
    await choose_delta_minutes_and_save_settings(call, state, '0')

@dp.callback_query_handler(lambda call: call.data == '-60', state=SetConfigsToBot.waiting_for_choose_delta_time)
async def choose_delta_sexty(call: types.CallbackQuery, state: FSMContext):  #konec nastroek
    await choose_delta_minutes_and_save_settings(call, state, '-60')



@dp.message_handler(commands=['delete_user'])
async def delete_user(message: types.Message,  state: FSMContext):
    user = select_data("select*from users where telega_id = ?", (message.chat.id, ))
    if user != []:
        di_d("delete from users where telega_id = ?",(message.chat.id, ))
        di_d("delete from user_timings where telega_id = ?",(message.chat.id, ))
        await bot.send_message(message.chat.id, "Вы удалили свои данные из базы пользователей бота.\nБольше бот не будет отправлять Вам сообщении. Если Вы передумаете нажмите на /start.\n🕌 Мир Вам 🕌")
    else:
        await bot.send_message(message.chat.id, "Вы не инициализированный пользователь бота. Если хотите пользоваться ботом нажмите на /start.")
    await state.finish()


@dp.message_handler(commands=['change_settings'],  state="*")
async def change_settings(message: types.Message, state: FSMContext):
    await message.answer("Напишите боту название страны в которой вы проживаете.\n\nPS:Обязательно убедитесь в правильности написания названия.")
    await state.set_state(SetConfigsToBot.waiting_for_choose_country.state)    


async def set_hadis_to_time(message, nz_time_arr): 
    keyb = types.InlineKeyboardMarkup(row_width=3)
    # ["Утренний", "Обеденный", "Послеобеденный", "Вечерний", "Ночной"]
    nz_times_list = nz_time_arr
    if nz_times_list == []:
        await bot.delete_message(message.chat.id, message.message_id)  
        await bot.send_message(message.chat.id, "Ни в одно из времен намаза Вам хадис не приходит. Если хотите добавить хадис в напоминание нажмите на /set_hadis_to_time")
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
        await bot.delete_message(message.chat.id, message.message_id)  
        await bot.send_message(message.chat.id, "Выберите времена намаза в которых напоминание будет приходить БЕЗ хадиса", reply_markup=keyb)




def nz_names_from_usr_bd_for_text(id):
    nz_names_from_user = json.loads(select_data("select nz_times_with_hadis from users where telega_id = ?", (id, ))[0][0])
    #print(nz_names_from_user[len(nz_names_from_user)-1])
    nz_names_text = ''
    for x in nz_names_from_user:
        if nz_names_from_user.index(x) != len(nz_names_from_user)-1:
            nz_names_text = nz_names_text+x + "," +" "
        else:
            nz_names_text = nz_names_text+x
    return nz_names_text

async def save_and_close(call, state, mes): #СОХРАНЕНИЕ СООБЩЕНИЕ 
    await bot.send_message(call.message.chat.id, mes)
    await state.finish()
    await bot.delete_message(call.message.chat.id, call.message.message_id)
    await bot.answer_callback_query(callback_query_id=call.id)

@dp.callback_query_handler(lambda call: re.fullmatch(r'save\_[0-9]+', call.data), state="*")
async def save_for_nz_without_hadis(call: types.CallbackQuery, state: FSMContext, ):
    await save_and_close(call, state, f"Настройки напоминании сохранены. Бот будет присылать хадисы при напоминании о следующих намазах: {nz_names_from_usr_bd_for_text(call.message.chat.id)}")

@dp.callback_query_handler(lambda call: re.fullmatch(r'otmena\_[0-9]+', call.data), state="*")  # ОТМЕНА СООБЩЕНИЯ
async def otmena(call: types.CallbackQuery, state: FSMContext):
    msg_id_del = call.data.split('_')[1]
    await bot.delete_message(call.message.chat.id, int(msg_id_del) + 1)
    await state.finish()
    await bot.answer_callback_query(callback_query_id=call.id)
    


@dp.callback_query_handler(lambda call: re.fullmatch(r'without\_([А-Яа-я]+)', call.data))
async def remove_nz_name(call: types.CallbackQuery):  #удаляем из списка намазом то название в котором хадис приходить не будет
    nz_wich_will_be_deleted = call.data.split('_')[1]
    nz_arr = select_data("select nz_times_with_hadis from users where telega_id = ?", (call.message.chat.id, ))
    nz_local = json.loads(nz_arr[0][0])
    nz_local.remove(nz_wich_will_be_deleted)
    #di_d("insert into users(nz_times_with_hadis) values(?)", (json.dumps(nz_local, ensure_ascii=False).encode("utf-8"), ))
    di_d("update users set nz_times_with_hadis = ? where telega_id = ?", (json.dumps(nz_local, ensure_ascii=False).encode("utf-8"), call.message.chat.id, ))
    await set_hadis_to_time(call.message, nz_local)
    await bot.answer_callback_query(callback_query_id=call.id)


@dp.message_handler(commands=["del_hadis_from_time"])
async def dhadis_to_time(message: types.Message):
    nz_arr = select_data("select nz_times_with_hadis from users where telega_id = ?", (message.chat.id, ))
    await set_hadis_to_time(message, json.loads(nz_arr[0][0]))


@dp.message_handler(commands=["set_hadis_to_time"])
async def shadis_to_time(message: types.Message):
    nz_arr = select_data("select nz_times_with_hadis from users where telega_id = ?", (message.chat.id, ))
    await insept_hadis_to_time(message, json.loads(nz_arr[0][0]))


async def insept_hadis_to_time(message, nz_time_arr):
    #global nz_times_names 
    sootvetstvie = 0
    keyb = types.InlineKeyboardMarkup(row_width=3)

    nz_times_names = ["Утренний", "Обеденный", "Послеобеденный", "Вечерний", "Ночной"]
    nz_times_list = nz_time_arr
    btns = []
    for x in nz_times_list:
        if x in nz_times_names:
            sootvetstvie = sootvetstvie +1
            nz_times_names.remove(x)
    
    if sootvetstvie == 5:
        await bot.delete_message(message.chat.id, message.message_id)  
        await bot.send_message(message.chat.id, "Хадисы Вам приходят во всех пяти временах намаза. Если хотите убрать хадис из напоминания нажмите на /del_hadis_from_time")
    else:
        for z in nz_times_names:
            btns.append(types.InlineKeyboardButton(text=z, callback_data=f'with_{z}'))
        keyb.add(*btns)
        commands_options = [
            types.InlineKeyboardButton(text="❌Отмена", callback_data=f"otmena_{message.message_id}"),
            types.InlineKeyboardButton(text="💾Сохранить", callback_data=f"save_{message.message_id}"),
        ]
        keyb.row(*commands_options)
        await bot.delete_message(message.chat.id, message.message_id)  
        await bot.send_message(message.chat.id, "Выберите времена намаза в которых напоминание будет приходить ВМЕСТЕ С хадисом", reply_markup=keyb)


@dp.callback_query_handler(lambda call: re.fullmatch(r'with\_([А-Яа-я]+)', call.data))
async def remove_nz_name(call: types.CallbackQuery):  #удаляем из списка намазом то название в котором хадис приходить не будет
    nz_wich_will_be_added = call.data.split('_')[1]
    nz_arr = select_data("select nz_times_with_hadis from users where telega_id = ?", (call.message.chat.id, ))
    nz_local = json.loads(nz_arr[0][0])
    nz_local.append(nz_wich_will_be_added)
    #di_d("insert into users(nz_times_with_hadis) values(?)", (json.dumps(nz_local, ensure_ascii=False).encode("utf-8"), ))
    di_d("update users set nz_times_with_hadis = ? where telega_id = ?", (json.dumps(nz_local, ensure_ascii=False).encode("utf-8"), call.message.chat.id, ))
    await insept_hadis_to_time(call.message, nz_local)
    await bot.answer_callback_query(callback_query_id=call.id)

#ОТПРАВКА СООБЩЕНИЯ АДМИНУ
@dp.message_handler(commands=["send_message_to_admin"], state="*")
async def message_init(message: types.Message, state:FSMContext):
    keyb = types.InlineKeyboardMarkup(row_width=3)
    otmena = [types.InlineKeyboardButton(text="❌Отмена", callback_data=f"otmena_{message.message_id}"), ]
    keyb.add(*otmena)
    # commands_options = [
    #     types.InlineKeyboardButton(text="❌Отмена", callback_data=f"otmena_{message.message_id}"),
    #     types.InlineKeyboardButton(text="💾Сохранить", callback_data=f"save_{message.message_id}"),
    # ]
    # keyb.row(*commands_options)
    await bot.send_message(message.chat.id, "Напишите сообщение администратору в ответ на это сообщение. Если вы хотите получить ответ, напишите email в сообщении.", reply_markup=keyb)
    await state.set_state(SetConfigsToBot.waiting_for_send_message_to_admin.state)

@dp.message_handler(state=SetConfigsToBot.waiting_for_send_message_to_admin)
async def send_message_to_admin(message: types.Message, state: FSMContext):
    await state.update_data(mes = message.text)
    user_message = await state.get_data()
    if len(user_message['mes']) >= 6:
        chat_id = message.chat.id
        button_url = f'tg://openmessage?user_id={chat_id}'
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(text="Open user", url=button_url))
        await bot.send_message(1949640271, f"Сообщение от пользователя: @{message.from_user.username if message.from_user.username!=None else message.chat.id}\n{user_message['mes']}", reply_markup=markup)
        await bot.send_message(message.chat.id, "Ваше сообщение отправлено администратору.")
    else:
        await bot.send_message(message.chat.id, "Ваше сообщение не корректно. Попробуйте повторить попытку: нажмите на /send_message_to_admin")
    await state.finish()
#ОТПРАВКА СООБЩЕНИЯ АДМИНУ


#ПРОСМОТР ВСЕХ ПОЛЬЗОВАТЕЛЕЙ
@dp.message_handler(commands=["users"])
async def show_all_users(message: types.Message):
    if message.chat.id == 1949640271:
        users_arr = select_data("select*from users")
        txt = ''
        num = 0
        for x in users_arr:
            num = num + 1
            txt = txt+ str(num)+') ' + str(x[1]) + ' ' + str(x[2])+ ' '+str(x[3])+' '+str(x[4])+'\n'
        await bot.send_message(message.chat.id, txt)
    else:
        await bot.send_message(message.chat.id, '))))')
#ПРОСМОТР ВСЕХ ПОЛЬЗОВАТЕЛЕЙ



#ОТПРАВИТЬ СООБЩЕНИЕ ВСЕМ ПОЛЬЗОВАТЕЛЯМ
@dp.message_handler(commands=["send_all"], state="*")
async def send_message_from_admin_init(message: types.Message, state: FSMContext):
    if message.chat.id == 1949640271:
        await bot.send_message(message.chat.id, "Напиши всем сообщение")
        await state.set_state(SetConfigsToBot.waiting_for_send_message_to_all.state)
    else:
        await bot.send_message(message.chat.id, ")))))")

@dp.message_handler(state=SetConfigsToBot.waiting_for_send_message_to_all)
async def send_message_from_admin(message: types.Message, state: FSMContext):
    await state.update_data(mes = message.text)
    admin_message = await state.get_data()
    users_arr = select_data("select*from users")
    for x in users_arr:
        try:
            rand_second_for_sleep = random.randint(1, 10)
            await asyncio.sleep(rand_second_for_sleep)#pered otpravkoi pust zasnet        
            await bot.send_message(x[1], admin_message['mes'])
        except BotBlocked:
            print(f"Блокировка юзером {x[1]} ты отправил всем сообщение")
            await asyncio.sleep(1)
    state.finish()
#ОТПРАВИТЬ СООБЩЕНИЕ ВСЕМ ПОЛЬЗОВАТЕЛЯМ




async def send_all_timings(city, telega_id, my_arr, message_obj):
    timings_in_arr_form = my_arr
    msg = f'<b>{city.capitalize()}. Сегодня: {dt.now().strftime("%d/%m/%Y")}</b>\n\n✨Утренний: <b>{timings_in_arr_form[0]}</b>\n✨Обеденный: <b>{timings_in_arr_form[2]}</b>\n✨Послеобеденный: <b>{timings_in_arr_form[3]}</b>\n✨Вечернии: <b>{timings_in_arr_form[4]}</b>\n✨Ночной: <b>{timings_in_arr_form[5]}</b>\n'
    await bot.send_message(telega_id, msg, parse_mode="HTML")
    await bot.delete_message(telega_id, message_obj["message_id"])#удаление отправленного сообщения


@dp.message_handler(content_types='text', state="*")
async def report_handler(message: types.Message, state: FSMContext):
    if message.text == 'Времена намазов на сегодня':
        await state.finish()
        user_info = select_data("select*from user_timings inner join users USING(telega_id) where date = ? and telega_id=?", (dt.now().date(), message.chat.id, ))
        #fetch_timings_from_bd = select_data("select*from user_timings where telega_id=? and date=?", (message.chat.id, dt.now().date(), ))
        if user_info != []:
            #timings_in_arr_form = fetch_timings_from_bd[0][2]
            await send_all_timings(user_info[0][-4], message.chat.id, json.loads(user_info[0][2]), message)
        else:
            resp = requests.get(f"http://api.aladhan.com/v1/calendarByCity/{dt.now().date().year}/{dt.now().date().month}?city={user_info[0][9]}&country={user_info[0][8]}&method=14&school={user_info[0][10]}")

            di_d("delete from user_timings where telega_id = ?", (user_info[0][1],))
            await correct_timings_insertor(user_info[0][1], resp)
            await report_handler(message)
        

async def correct_timings_insertor(chat_id, outside_resp):
    #ЕСЛИ ЧТО ТУТ ДОБАВИМ КЛАВИАТУРУ УПРАВЛЕНИЯ БОТОМ ДЛЯ ЧТЕНИЯ ХАДИСОВ!!!
    timings_data = []
    timezone = outside_resp.json()['data'][0]['meta']['timezone']

    for z in outside_resp.json()['data']:
        times_arr = []
        for v in z['timings']:
            if v != 'Imsak' and v != 'Firstthird' and v != 'Sunset' and v != "Lastthird":
                times_for_nz = z['timings'][v]
                
                obj_times_for_nz = re.search(r'(\d\d)\:(\d\d)', times_for_nz)

                dt_obj = dt(dt.now().year, dt.now().month, dt.now().day, int(obj_times_for_nz[1]), int(obj_times_for_nz[2]))

                times_arr.append(dt_obj.strftime('%H:%M'))

        # ОБРАБОТКА ДАТЫ В НУЖНЫЙ ФОРМАТ
        dt_str = z['date']['gregorian']['date']
        dt_str_conv = dt.strptime(dt_str, '%d-%m-%Y').date()

        # СОЗДАНИЕ СПИСКА ДЛЯ МАССИВА
        mem_tuple = (chat_id, json.dumps(times_arr), timezone, str(dt_str_conv), json.dumps(z['date']['hijri']['holidays']),)
        # ДОБАВЛЕНИЕ СПИСКА В МАССИВ
        timings_data.append(mem_tuple)
        mem_tuple = ()

    insert_many("INSERT INTO user_timings(telega_id, timings, timezone, date, holidays) VALUES(?, ?, ?, ?, ?);", timings_data)
    print("Inserted")


async def noon_print(telega_id, mes, hds):
    try:
        rand_second_for_sleep = random.randint(1, 10)
        await asyncio.sleep(rand_second_for_sleep)#pered otpravkoi pust zasnet 
        if len(hds)>4096:
            for x in range(0, len(hds), 4096):
                #print(some_string[x:x+100])
                if x>0:
                    await bot.send_message(telega_id, f"{hds[x:x+4096]}")
                else:
                    await bot.send_message(telega_id, f"{mes}{' '*28}🌹🌹🌹{' '*28}\n{hds[x:x+4096]}")
        else:
            await bot.send_message(telega_id, f"{mes}{' '*28}🌹🌹🌹{' '*28}\n{hds}")
    except BotBlocked:
        print("Chto to ili kto to tebya zablochil!!!!!")
        await asyncio.sleep(1)

def hadis(namaz, arr):
    if namaz in arr:
        return select_data('select khadis from khadisy order by RANDOM() LIMIT 1')[0][0]
    else:
        return 'Мир Вам'

def schedule_creator(outside_timings):
    for z in outside_timings:
        t_a = json.loads(z[2])
        #t_a = ["21:04", "21:07", "21:10", "21:12", "21:15", "21:17", "21:20"]
        tz_moscow = pytz.timezone(z[3])
        delta_time = dt.now().hour-dt.now(tz_moscow).hour
        delta_minutes = z[-2]
        nz_times_names_arr = json.loads(z[-1])
        #hadis = select_data('select khadis from khadisy order by () LIMIT 1')[0][0]
        #nz_times_names = ["Утренний", "Обеденный", "Послеобеденный", "Вечерний", "Ночной"]
        if delta_minutes == 0:
            for x in t_a:
                obj_times_for_nz = re.search(r'(\d\d)\:(\d\d)', x)
                dt_obj = dt(dt.now().year, dt.now().month, dt.now().day, int(obj_times_for_nz[1]), int(obj_times_for_nz[2]))
                d = dt_obj + timedelta(hours=delta_time, minutes=delta_minutes)
                if t_a.index(x) == 0:
                    aioschedule.every().day.at(d.strftime('%H:%M')).do(noon_print, z[1], f"🕌 Прочитай Фаджр (Утренний)!🕌\nОкончание в {t_a[1]}\n\n", hadis("Утренний", nz_times_names_arr))
                elif t_a.index(x) == 2:
                    aioschedule.every().day.at(d.strftime('%H:%M')).do(noon_print, z[1], f"🕌 Прочитай Зухр (Обеденный)!🕌\nОкончание в {t_a[3]}\n\n", hadis("Обеденный", nz_times_names_arr))
                elif t_a.index(x) == 3:
                    aioschedule.every().day.at(d.strftime('%H:%M')).do(noon_print, z[1], f"🕌 Прочитай Аср (Послеобеденный)!🕌\nОкончание в {t_a[4]}\n\n", hadis("Послеобеденный", nz_times_names_arr))
                elif t_a.index(x) == 4:
                    aioschedule.every().day.at(d.strftime('%H:%M')).do(noon_print, z[1], f"🕌 Прочитай Магриб (Вечернии)!🕌\nОкончание в {t_a[5]}\n\n", hadis("Вечерний", nz_times_names_arr))
                elif t_a.index(x) == 5:
                    aioschedule.every().day.at(d.strftime('%H:%M')).do(noon_print, z[1], f"🕌 Прочитай Иша (Ночной)!🕌\nОкончание в {t_a[0]}\n\n", hadis("Ночной", nz_times_names_arr))
        elif delta_minutes == -60:
            for x in t_a:
                obj_times_for_nz = re.search(r'(\d\d)\:(\d\d)', x)
                dt_obj = dt(dt.now().year, dt.now().month, dt.now().day, int(obj_times_for_nz[1]), int(obj_times_for_nz[2]))
                d = dt_obj + timedelta(hours=delta_time, minutes=delta_minutes)
                if t_a.index(x) == 1:
                    aioschedule.every().day.at(d.strftime('%H:%M')).do(noon_print, z[1], f"🕌 Через 60 минут закончится время выполнения намаза Фаджр (Утрении)!🕌\nОкончание в {t_a[1]}\n\n", hadis("Утренний", nz_times_names_arr))
                elif t_a.index(x) == 3:
                    aioschedule.every().day.at(d.strftime('%H:%M')).do(noon_print, z[1], f"🕌 Через 60 минут закончится время выполнения намаза Зухр (Обеденный)!🕌\nОкончание в {t_a[3]}\n\n", hadis("Обеденный", nz_times_names_arr))
                elif t_a.index(x) == 4:
                    aioschedule.every().day.at(d.strftime('%H:%M')).do(noon_print, z[1], f"🕌 Через 60 минут закончится время выполнения намаза Аср (Послеобеденный)!🕌\nОкончание в {t_a[4]}\n\n", hadis("Послеобеденный", nz_times_names_arr))
                elif t_a.index(x) == 5:
                    aioschedule.every().day.at(d.strftime('%H:%M')).do(noon_print, z[1], f"🕌 Через 60 минут закончится время выполнения намаза Магриб (Вечерний)!🕌\nОкончание в {t_a[5]}\nНочной намаз закончится в {t_a[0]}\n\n", hadis("Вечерний", nz_times_names_arr))
                elif t_a.index(x) == 6:
                    aioschedule.every().day.at(d.strftime('%H:%M')).do(noon_print, z[1], "🕌 Желательно прочитать Иша (Ночной), если Вы еще не прочитали. 🕌\n\n", hadis("Ночной", nz_times_names_arr))
        elif delta_minutes == -30:
            for x in t_a:
                obj_times_for_nz = re.search(r'(\d\d)\:(\d\d)', x)
                dt_obj = dt(dt.now().year, dt.now().month, dt.now().day, int(obj_times_for_nz[1]), int(obj_times_for_nz[2]))
                d = dt_obj + timedelta(hours=delta_time, minutes=delta_minutes)
                if t_a.index(x) == 1:
                    aioschedule.every().day.at(d.strftime('%H:%M')).do(noon_print, z[1], f"🕌 Через 30 минут закончится время выполнения намаза Фаджр (Утрении)!🕌\nОкончание в {t_a[1]}\n\n", hadis("Утренний", nz_times_names_arr))
                elif t_a.index(x) == 3:
                    aioschedule.every().day.at(d.strftime('%H:%M')).do(noon_print, z[1], f"🕌 Через 30 минут закончится время выполнения намаза Зухр (Обеденный)!🕌\nОкончание в {t_a[3]}\n\n", hadis("Обеденный", nz_times_names_arr))
                elif t_a.index(x) == 4:
                    aioschedule.every().day.at(d.strftime('%H:%M')).do(noon_print, z[1], f"🕌 Через 30 минут закончится время выполнения намаза Аср (Послеобеденный)!🕌\nОкончание в {t_a[4]}\n\n", hadis("Послеобеденный", nz_times_names_arr))
                elif t_a.index(x) == 5:
                    aioschedule.every().day.at(d.strftime('%H:%M')).do(noon_print, z[1], f"🕌 Через 30 минут закончится время выполнения намаза Магриб (Вечерний)!🕌\nОкончание в {t_a[5]}\nНочной намаз закончится в {t_a[0]}\n\n", hadis("Вечерний", nz_times_names_arr))
                elif t_a.index(x) == 6:
                    aioschedule.every().day.at(d.strftime('%H:%M')).do(noon_print, z[1], "🕌 Желательно прочитать Иша (Ночной), если Вы еще не прочитали. 🕌\n\n", hadis("Ночной", nz_times_names_arr))
            




async def timings_from_bd():
    aioschedule.clear()
    timings = select_data("select*from user_timings inner join users USING(telega_id) where date = ?", (dt.now().date(),))
    users = select_data("select*from users")
    if len(users)>len(timings):
        for x in timings:  #prohod po zapisyam v timingah prinadlejashim useram
            for j in users: #prohod po useram, ih bolshe, potomu probegaem po nim 
                if x[1]==j[1]: #esli user sovpadaet s zapisu v taimingah ego iz spiska udalaem
                    users.remove(j)
        for z in users: 
            di_d("delete from user_timings where telega_id = ?", (z[1],))
            resp = requests.get(f"http://api.aladhan.com/v1/calendarByCity/{dt.now().date().year}/{dt.now().date().month}?city={z[4]}&country={z[3]}&method=14&school={z[5]}")
            await correct_timings_insertor(z[1], resp)
            await asyncio.sleep(3)
            #await timings_from_bd() #vot eto zachem?
    if timings !=[]:
        schedule_creator(timings)
    aioschedule.every(3).minutes.do(timings_from_bd)
        



async def scheduler():
    aioschedule.every(3).minutes.do(timings_from_bd)
    while True:
        await aioschedule.run_pending()
        await asyncio.sleep(1)


async def on_strtp(_):
    asyncio.create_task(scheduler())


if __name__ == '__main__':

    executor.start_polling(
        dispatcher=dp,
        skip_updates=True,
        on_startup=on_strtp
    )

# https://aiogram.ru/?p=33 - ссыль на кнопки
