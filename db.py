import os
import sqlite3

# The database lives next to db.py, not in the current working directory:
# this way the bot finds it no matter where the bot is launched from.
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nzt.db")

conn = sqlite3.connect(DB_PATH)
# Rows can be indexed both by number and by column name:
# row["telega_id"], row["city"], etc. This protects against mistakes with mixed-up indexes.
conn.row_factory = sqlite3.Row


def init_db():
    """Creates the tables if they do not exist yet.

    Runs on every import of db, so after cloning the repository the bot starts
    without any manual database initialization, while existing data
    (if nzt.db already has the tables) is left untouched.
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
