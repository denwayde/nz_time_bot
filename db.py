import sqlite3

conn = sqlite3.connect("nzt.db")
# Строки можно индексировать как по номеру, так и по имени колонки:
# row["telega_id"], row["city"] и т.д. Это защищает от ошибок с перепутанными индексами.
conn.row_factory = sqlite3.Row


def delete_or_insert_data(delete_or_insert_query, tup=()):
    cur = conn.cursor()
    cur.execute(delete_or_insert_query, tup)
    conn.commit()


def insert_many(insert_many_query, mas):
    cur = conn.cursor()
    cur.executemany(insert_many_query, mas)
    conn.commit()


def select_data(selection_query, tup=()):
    cur = conn.cursor()
    cur.execute(selection_query, tup)
    return cur.fetchall()
