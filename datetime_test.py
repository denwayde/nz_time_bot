from datetime import datetime as dt, timedelta
import time

import pytz
import re


# ДОСТАЕМ ТАЙМЗОН ИЗ БД СРАВНИВАЕМ ТЕКУЩИЕ ВРЕМЕНА ПОЛУЧАЕМ ДЕЛЬТА В ЧАСАХ ---) ЭТУ ДЕЛЬТА БУДЕМ ПРИБАВЛЯТЬ ИЛИ ВЫЧИТАТЬ В ТЕ ТАЙМЗОНЫ ЧТО ЛЕЖАТ В БД для конкретного пользователя

tz_moscow = pytz.timezone("Europe/Moscow")
full_msk_time = str(dt.now(tz_moscow).time())
# ВОТ ТАК ВЫКОВЫРИВАЛИ ВРЕМЯ
msk_time_match = re.search(r'\d\d\:\d\d', full_msk_time)


# print(dt.now(tz_moscow).hour-dt.now().hour) ###---TIMEDELTA
delta_time = dt.now(tz_moscow).hour-dt.now().hour

stringed_time = "17-03-2023"
date_obj = dt.strptime(stringed_time, "%d-%m-%Y")
# print(date_obj.date())#так можно преобразовывать в формат дат который обычно в питоне

# print(dt.today().date())#так можно получить сегодняшнюю дату

# print(dt.now().day)#так можно получить сеголняшнее число. возврат в формате интеджер

# так можно манипулировать датами(так мы прибавили один день к текушей дате)
dt_obj = dt(dt.now().year, dt.now().month, dt.now().day +
            1, dt.now().hour + delta_time, dt.now().minute)

# print(dt_obj.date())
# print()
# print(dt_obj.time())


# КУДА ТО НУЖНО СОХРАНЯТЬ ТЕКУЩУЮ ДАТУ И КАЖДЫЙ ДЕНЬ СРАВНИВАТЬ ЕЕ
# СКОРЕЕ ВСЕГО МЫ БУДЕМ СРАВНИВАТЬ ТЕКУЩУЮ ДАТУ с учетом таймзон С ТЕМ ЧТО СОХРАНИЛИ В БД С ТАЙМИНГАМИ ИЗ НАЧАЛЬНОЙ КОНФИГУРАЦИИ!!!!!!!!

# ТЕПЕРЬ НУЖНО ПРИДУМАТЬ КАК МОЖНО ВЫЧИТАТЬ ВРЕМЕНА!!!!ПРИДУМАНО СМОТРИ НИЖЕ
# ----- dt(dt.now().year, dt.now().month, dt.now().day+1, dt.now().hour, dt.now().minute, )
a = time.ctime(time.time()-2400)
# ПРЕОБРАЗОВАННОЕ ВРЕМЯ ПРИДЕТСЯ ВЫКОВЫРИВАТЬ ТОКа ТАК!
match_time = re.search(r'\s\d\d\:\d\d', a)

# print(match_time[0])

# ТЕПЕРЬ НУЖНО ПРОВЕРИТЬ РАБОТУ НАПОМИНАТЕЛЯ !!!!!


d = dt.now() + timedelta(hours=0, minutes=-30)
print(d.time().strftime('%H:%M'))  # VIPOLNILI VICHET MINUT!!!!TEPER NUJNO PRIDUMAT OTPRAVKU SMISLOVOGO SOOBSHENIA V NUJNOE VREMIA!!!V BD NEOBHODIMO VNOSIT VREMYA VICHETA - TIMEDELTA #SEGODNYA SDELAY SOHRANENIE POLZOVATELYA SO VSEM NEOBHODIMIM
