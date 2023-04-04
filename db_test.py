import requests
from datetime import datetime as dt, timedelta
import time
from db import delete_or_insert_data as di_d, insert_many, select_data
import json

import pytz
import re

resp = requests.get(
    "http://api.aladhan.com/v1/calendarByCity/2023/4?city=Уфа&country=Россия&method=14&school=1")


timings_data = []

# resp.json()['status'] doljno bit OK
# resp.json()['code'] doljno bit 200
telega_id = 123456789

for z in resp.json()['data']:
    # print(z['date']['hijri']['holidays'])
    dt_str = z['date']['gregorian']['date']
    dt_str_conv = dt.strptime(dt_str, '%d-%m-%Y').date()
    # print(dt_str_conv)
    mem_tuple = tuple((telega_id, str(z['timings']), z['meta']
                      ['timezone'], str(dt_str_conv), str(z['date']['hijri']['holidays'])))
    # print(mem_tuple)
    timings_data.append(mem_tuple)

    mem_tuple = ()

# print(timings_data)

# insert_many("INSERT INTO user_timings(telega_id, timings, timezone, date, holidays) VALUES(?, ?, ?, ?, ?);", timings_data)

out = select_data("select*from user_timings where date = ?",
                  (str(dt.now().date()),))

# print(dict(out[0][2]))
