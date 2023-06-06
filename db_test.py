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

# from fake_headers import Headers
# header = Headers(
#         browser="chrome",  # Generate only Chrome UA
#         os="win",  # Generate ony Windows platform
#         headers=True  # generate misc headers
#     )
# for i in range(0,10):
#     print(header.generate())
#     print()
#     print()
# API_TOKEN = config.bot_token.get_secret_value()

# memstore = MemoryStorage()
# Initialize bot and dispatcher
# bot = Bot(token=API_TOKEN)
# dp = Dispatcher(bot, storage=memstore)


resp = requests.get(
    "http://api.aladhan.com/v1/calendarByCity/2023/4?city=Уфа&country=Россия&method=14&school=1")


# resp.json()['status'] doljno bit OK
# resp.json()['code'] doljno bit 200
# tim = select_data("select*from user_timings inner join users USING(telega_id) where date = ?", (dt.now().date(),))
users = select_data("select*from users")

async def send_by_partials(my_arr):
    num = 0
    for x in my_arr:
        num = num +1
        my_arr.remove(x)
        if num == 5 or len(my_arr)!=0:
            print(my_arr)
            await asyncio.sleep(1)
            await send_by_partials(my_arr)

'''
loop = asyncio.get_event_loop()
task1 = loop.create_task(send_by_partials(users))
loop.run_until_complete(asyncio.wait([task1,])) '''
# for x in tim:
#     for j in users:
#         if x[1]==j[1]:
#             users.remove(j)
# for z in users:
#     print(z)
#     print()
#     print()
# import random
# print(random.randint(1,10))
some_string = 'Всем привет. Подскажите пожалуйста как можно обойти лимит на ограничение длинны сообщений, который установлен в размере 4096 символов?Использую библиотеку TeleBot и когда в ответ пользователю формируется длинное сообщение, он падает с ошибкой Bad Request: message is too long.Можно ли как то разделить это сообщение на несколько, что бы оно пришло частями?'

# if len(some_string)>100:
#     for x in range(0, len(some_string), 100):
#         print(some_string[x:x+100])
#         print()
#         print()
user_info = select_data("select*from user_timings inner join users USING(telega_id) where date = ? and telega_id=?", (dt.now().date(), 1949640271, ))
print(len(user_info[0]))
