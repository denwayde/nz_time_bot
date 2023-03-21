import requests
import json

resp = requests.get(
    "http://api.aladhan.com/v1/calendarByCity/2023/3?city=уфа&country=россия&method=14&school=1")

print(json.dumps(resp.json()['data'][20]))
