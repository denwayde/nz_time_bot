import requests
from datetime import datetime as dt, timedelta
import time

import pytz
import re

resp = requests.get(
    "http://api.aladhan.com/v1/calendarByCity/2023/3?city=Москва&country=Россия&method=14&school=1")

tz_moscow = pytz.timezone("Europe/Moscow")

# resp.json()['data'][21]['timings'] vremenena nz
# resp.json()['data'][21]['date']['gregorian']['date'] data kotoruy nuzno preobrazovat v nuznii format pered tem kak vstavlst v bd
# resp.json()['data'][21]['date']['gregorian']['month']['number'] nomer mesyatca
# resp.json()['data'][21]['date']['gregorian']['year']
# resp.json()['data'][21]['meta']['timezone'] timezonechik
# resp.json()['data'][21]['date']['hijri']['holidays']
dt_str = resp.json()['data'][21]['date']['gregorian']['date']
# preobrazovannaya data которую будем интегрировать в БД
dt_str_conv = dt.strptime(dt_str, '%d-%m-%Y')
# print(dt_str_conv.date() == dt.now().date())


timings = resp.json()['data'][21]['timings']
# print(timings)
tmings_arr = []
delta_time = dt.now(tz_moscow).hour-dt.now().hour

for x in timings:
    time_match = re.search(r'(\d\d)\:(\d\d)', timings[x])

    dt_obj = dt(dt.now().year, dt.now().month, dt.now().day +
                1, int(time_match[1]), int(time_match[2]))

    d = dt_obj + timedelta(hours=delta_time, minutes=0)
    # print(d.strftime('%H:%M'))
    tmings_arr.append(d.strftime('%H:%M'))

# СДЕЛАЛИ ВРЕМЕНА ДЛЯ ТАСКОВ СКОРЕЕ ВСЕГО ОБЪЕДИНЯТЬ ИХ В МАССИВ НЕ ОБЯЗАТЕЛЬНО
# print(tmings_arr)
