import logging
from aiogram import Bot, Dispatcher, executor, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from config_reader import config
from db import delete_or_insert_data as di_d, select_data, insert_many
import requests
from datetime import datetime as dt, timedelta
import time
import json
import pytz
import re


class SetConfigsToBot(StatesGroup):
    waiting_for_choose_country = State()
    waiting_for_choose_city = State()
    waiting_for_choose_mazhab = State()
    waiting_for_choose_delta_time = State()


API_TOKEN = config.bot_token.get_secret_value()

# Configure logging
logging.basicConfig(level=logging.INFO)
memstore = MemoryStorage()
# Initialize bot and dispatcher
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=memstore)


@dp.message_handler(commands='start', state="*")
async def send_welcome(message: types.Message, state: FSMContext):
    # buttons = [
    #     types.InlineKeyboardButton(text="", callback_data="")
    # ]
    # reply_markup=buttons
    await message.answer("Здравствуйте это бот для напоминания об НЗ. Тут рассказываем что бот делает, как работает и тд. Давайте выполним первоначальные настройки. Напишите боту страну в которой вы проживаете")
    await state.set_state(SetConfigsToBot.waiting_for_choose_country.state)


@dp.message_handler(state=SetConfigsToBot.waiting_for_choose_country)
async def choosen_country_handler(message: types.Message, state: FSMContext):
    await state.update_data(chosen_country=message.text)
    await message.answer(f"Вы выбрали страну {message.text}. Теперь выберите город в котором Вы проживаете. ")
    await state.set_state(SetConfigsToBot.waiting_for_choose_city.state)


@dp.message_handler(state=SetConfigsToBot.waiting_for_choose_city)
async def choosen_city_handler(message: types.Message, state: FSMContext):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = ["Ханафи", "Шафии"]
    keyboard.add(*buttons)
    await state.update_data(chosen_city=message.text)
    await message.answer(f"Вы выбрали город {message.text}. Теперь выберите мзхб", reply_markup=keyboard)
    await state.set_state(SetConfigsToBot.waiting_for_choose_mazhab.state)
    # user_data = await state.get_data()
    # await message.answer(f"Вы выбрали город {message.text} и страну {user_data['chosen_country']}")
    # await state.finish()


@dp.message_handler(state=SetConfigsToBot.waiting_for_choose_mazhab)
async def choosen_mazhab_handler(message: types.Message, state: FSMContext):
    # reply_markup=types.ReplyKeyboardRemove() чтобы удалить клавиатуру
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = ["С заходом", "За час до окончания", "За полчаса до окончания"]
    keyboard.add(*buttons)
    await state.update_data(chosen_mazhab=message.text)
    await message.answer(f"Вы выбрали мазхаб {message.text}. Теперь выберите удобное для Вас время напоминания о выполнении намаза", reply_markup=keyboard)
    await state.set_state(SetConfigsToBot.waiting_for_choose_delta_time.state)


@dp.message_handler(state=SetConfigsToBot.waiting_for_choose_delta_time)
async def choosen_mazhab_handler(message: types.Message, state: FSMContext):
    reply_markup = types.ReplyKeyboardRemove()
    await state.update_data(chosen_delta=message.text)
    user_data = await state.get_data()

    time_delta_minutes = 0
    if user_data["chosen_delta"] == "За час до окончания":
        time_delta_minutes = 60
    elif user_data["chosen_delta"] == "За полчаса до окончания":
        time_delta_minutes = 30

    mazh = 1
    if user_data['chosen_mazhab'] == "Шафии":
        mazh = 0

    di_d("insert into users(telega_id, name, country, city, mazhab, time_delta) values(?,?,?,?,?,?);", (message.chat.id,
         message.from_user.first_name, user_data['chosen_country'], user_data['chosen_city'], mazh, time_delta_minutes,))
    resp = requests.get(
        f"http://api.aladhan.com/v1/calendarByCity/{dt.now().date().year}/{dt.now().date().month}?city={user_data['chosen_city']}&country={user_data['chosen_country']}&method=14&school={mazh}")

    if resp.json()['code'] == 200:
        await message.answer(f"Вы выбрали напоминание {message.text}. Настройки завершены. Бот будет напоминать ", reply_markup=types.ReplyKeyboardRemove())
        timings_data = []
        for z in resp.json()['data']:
            times_arr = []
            for v in z['timings']:
                if v != 'Sunrise' and v != 'Imsak' and v != 'Midnight' and v != 'Firstthird':
                    times_for_nz = z['timings'][v]
                    obj_times_for_nz = re.search(r'\d\d\:\d\d', times_for_nz)
                    times_arr.append(obj_times_for_nz[0])

            # ОБРАБОТКА ДАТЫ В НУЖНЫЙ ФОРМАТ
            dt_str = z['date']['gregorian']['date']
            dt_str_conv = dt.strptime(dt_str, '%d-%m-%Y').date()

            # СОЗДАНИЕ СПИСКА ДЛЯ МАССИВА
            mem_tuple = tuple((message.chat.id, json.dumps(times_arr), z['meta']
                               ['timezone'], str(dt_str_conv), json.dumps(z['date']['hijri']['holidays'])))
            # ДОБАВЛЕНИЕ СПИСКА В МАССИВ
            timings_data.append(mem_tuple)
            mem_tuple = ()

        insert_many(
            "INSERT INTO user_timings(telega_id, timings, timezone, date, holidays) VALUES(?, ?, ?, ?, ?);", timings_data)
        print("Inserted")
    else:
        await message.answer("Что-то пошло не так. Возможно вы опечатались в названии своей страны или города или сервер временно недоступен. Попробуйте повторить процедуру натройки.")

    await state.finish()
    print(user_data)

'''@dp.callback_query(text="random_value")
async def send_random_value(callback: types.CallbackQuery):'''

# @dp.message_handler()
# async def echo(message: types.Message):
#     await message.answer(message.text)


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
# https://aiogram.ru/?p=33 - ссыль на кнопки
