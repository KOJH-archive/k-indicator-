import sqlite3
import os

DB_PATH = os.path.join("data", "database.sqlite")
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("DELETE FROM indicators WHERE indicator_key IN ('housing_index', 'unemployment_rate')")
conn.commit()
print("Deleted mock data.")
conn.close()
