import os
import sqlite3

# База лежит рядом с db.py, а не в текущей рабочей директории:
# тогда бот находит её независимо от того, откуда он запущен.
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nzt.db")

conn = sqlite3.connect(DB_PATH)
# Строки можно индексировать как по номеру, так и по имени колонки:
# row["telega_id"], row["city"] и т.д. Это защищает от ошибок с перепутанными индексами.
conn.row_factory = sqlite3.Row


def init_db():
    """Создаёт таблицы, если их ещё нет.

    Выполняется при каждом импорте db, поэтому после клонирования репозитория
    бот запускается без ручной инициализации базы, а существующие данные
    (если nzt.db уже был с таблицами) не затрагиваются.
    """
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        telega_id           INTEGER PRIMARY KEY,
        name                TEXT,
        country             TEXT,
        city                TEXT,
        mazhab              INTEGER NOT NULL DEFAULT 1,
        time_delta          INTEGER NOT NULL DEFAULT 0,
        nz_times_with_hadis TEXT
    );

    CREATE TABLE IF NOT EXISTS user_timings (
        telega_id INTEGER NOT NULL REFERENCES users(telega_id),
        timings   TEXT,
        timezone  TEXT,
        date      TEXT,
        holidays  TEXT
    );

    CREATE TABLE IF NOT EXISTS khadisy (
        khadis TEXT
    );
    """)
    conn.commit()


init_db()


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
