import sqlite3

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
    return cur.fetchmany()
