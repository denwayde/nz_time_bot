import requests
import json

resp = requests.get(
    "http://api.aladhan.com/v1/calendarByCity/2023/3?city=london&country=united&kingdom&method=14&school=1")

# resp.json()['data'][21]['timings'] vremenena nz
# resp.json()['data'][21]['date']['gregorian']['date'] data kotoruy nuzno preobrazovat v nuznii format pered sohraneniem v bd
# resp.json()['data'][21]['date']['gregorian']['month']['number'] nomer mesyatca
# resp.json()['data'][21]['date']['gregorian']['year']
# resp.json()['data'][21]['meta']['timezone'] timezonechik


print(resp.json()['data'][21]['meta']['timezone'])
