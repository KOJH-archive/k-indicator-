import sqlite3
import os

DB_PATH = os.path.join("data", "database.sqlite")
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("SELECT period, value FROM indicators WHERE indicator_key='unemployment_rate' ORDER BY period ASC")
rows = c.fetchall()
print("First 5:", rows[:5])
print("Middle 5:", rows[len(rows)//2 : len(rows)//2 + 5])
print("Last 5:", rows[-5:])
conn.close()
