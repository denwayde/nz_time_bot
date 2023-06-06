import sqlite3
from datetime import datetime as dt, timedelta
conn = sqlite3.connect("nzt.db")
# cur = conn.cursor()
# cur.execute("ВАШ-SQL-ЗАПРОС-ЗДЕСЬ;")
# conn.commit()


# cur.execute("INSERT INTO users VALUES(?, ?, ?, ?);", user)
# more_users = [('00003', 'Peter', 'Parker', 'Male'), ('00004', 'Bruce', 'Wayne', 'male')]
# cur.executemany("INSERT INTO users VALUES(?, ?, ?, ?);", more_users)
#
#
# cur.execute("SELECT * FROM users;")
# three_results = cur.fetchmany(3)
# print(three_results)
#
#
# cur.execute("SELECT * FROM users;")
# one_result = cur.fetchone()
# print(one_result)


def delete_or_insert_data(delete_or_insert_query, tup=()):
    global conn
    cur = conn.cursor()
    cur.execute(delete_or_insert_query, tup)
    conn.commit()


def insert_many(insert_many_query, mas):
    global conn
    cur = conn.cursor()
    cur.executemany(insert_many_query, mas)
    conn.commit()


def select_data(selection_query, tup=()):
    global conn
    cur = conn.cursor()
    cur.execute(selection_query, tup)
    return cur.fetchall()

# out = select_data(
#         "select*from user_timings inner join users USING(telega_id) where date = ?", (dt.now().date(),))
# print(out)
# print()
# for j in out:
#     print(j)
# khadis = select_data("select khadis from khadisy order by RANDOM() LIMIT 1")[0][0]
# print(str(khadis))
# users = select_data("select*from users")
# print(users)