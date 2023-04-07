from aiogram import Bot, Dispatcher, executor, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from config_reader import config
import requests
from datetime import datetime as dt, timedelta
import time
from db import delete_or_insert_data as di_d, insert_many, select_data
import json
import pytz
import re

import asyncio
import aioschedule
from aiogram.utils.exceptions import BotBlocked

API_TOKEN = config.bot_token.get_secret_value()

memstore = MemoryStorage()
# Initialize bot and dispatcher
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=memstore)


resp = requests.get(
    "http://api.aladhan.com/v1/calendarByCity/2023/4?city=Уфа&country=Россия&method=14&school=1")


# resp.json()['status'] doljno bit OK
# resp.json()['code'] doljno bit 200
telega_id = 123456789
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
    mem_tuple = tuple((telega_id, json.dumps(times_arr), z['meta']
                      ['timezone'], str(dt_str_conv), json.dumps(z['date']['hijri']['holidays'])))
    # ДОБАВЛЕНИЕ СПИСКА В МАССИВ
    timings_data.append(mem_tuple)

    mem_tuple = ()


# insert_many("INSERT INTO user_timings(telega_id, timings, timezone, date, holidays) VALUES(?, ?, ?, ?, ?);", timings_data)
# print("Inserted")

# TUT DOSTAEM IZ DB VREMENA I TIMEZON I VIPOLNYAEM PEREVOD NA CHASOVOI POYAS KOTORII NUJEN
out = select_data("select*from user_timings where date = ?",
                  (str(dt.now().date()),))

timings_arr_from_db = json.loads(out[0][2])  # ВРЕМЕНА ИЗ БД

# print(timings_arr_from_db) #здесь те времена что извлечены из БД

tz_moscow = pytz.timezone(out[0][-3])
tmings_arr = []
delta_time = dt.now(tz_moscow).hour-dt.now().hour

for x in timings_arr_from_db:
    time_match = re.search(r'(\d\d)\:(\d\d)', x)

    dt_obj = dt(dt.now().year, dt.now().month, dt.now().day +
                1, int(time_match[1]), int(time_match[2]))

    d = dt_obj + timedelta(hours=delta_time, minutes=0)

    tmings_arr.append(d.strftime('%H:%M'))

# print(tmings_arr) # здесь те времена что преобразованы окончательно !!!НУЖНО ЕЩЕ ПОРАБОТАТЬ С TIMEDELTA ЕСЛИ ЮЗЕР РЕШИТ ЗА ОПРЕДЕЛЕННОЕ ВРЕМЯ ПРОСИТЬ ПРЕДУПРЕЖДЕНИЕ

'''
async def noon_print():
    d = datetime.datetime.now().strftime("%Y-%m-%d")
    ids = db_handler.get_data("SELECT telega_id FROM teachers")
    kur_ids = db_handler.get_data(
        "SELECT DISTINCT telega_id FROM kuramshin_otchet WHERE date = ?", (d,))
    for x in ids:
        for v in kur_ids:
            if x == v:
                ids.remove(v)
    for z in ids:
        try:
            await bot.send_message(z[0], "Доброго времени суток, отправьте пожалуйста отчет посещаемости")
        except BotBlocked:
            await asyncio.sleep(1)
'''


print(users[0])

'''
async def scheduler():
    aioschedule.every().day.at("08:17").do(noon_print)
    aioschedule.every().day.at("09:13").do(noon_print)
    aioschedule.every().day.at("17:47").do(noon_print)
    while True:
        await aioschedule.run_pending()
        await asyncio.sleep(1)
'''


async def on_strtp(_):
    users = select_data(
        "select*from user_timings inner join users USING(telega_id) where date = ?", (dt.now().date(),))
    asyncio.create_task(scheduler())

if __name__ == '__main__':

    executor.start_polling(
        dispatcher=dp,
        skip_updates=True,
        on_startup=on_strtp
    )
