import requests
from datetime import datetime as dt
import time

import pytz
import re

resp = requests.get(
    "http://api.aladhan.com/v1/calendarByCity/2023/3?city=Москва&country=Россия&method=14&school=1")

# resp.json()['data'][21]['timings'] vremenena nz
# resp.json()['data'][21]['date']['gregorian']['date'] data kotoruy nuzno preobrazovat v nuznii format pered sohraneniem v bd
# resp.json()['data'][21]['date']['gregorian']['month']['number'] nomer mesyatca
# resp.json()['data'][21]['date']['gregorian']['year']
# resp.json()['data'][21]['meta']['timezone'] timezonechik


timings = resp.json()['data'][21]['timings']

for x in timings:
    time_match = re.search(r'\d\d\:\d\d', timings[x])
    print(time_match[0])
