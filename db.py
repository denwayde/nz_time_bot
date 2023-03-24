import sqlite3

conn = sqlite3.connect("nzt.db")
cur = conn.cursor()
cur.execute("ВАШ-SQL-ЗАПРОС-ЗДЕСЬ;")
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

conn.commit()
