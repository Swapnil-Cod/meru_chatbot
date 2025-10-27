import pymysql
from config import Config

# Connect to database
conn = pymysql.connect(**Config.DB_CONFIG)

print("Checking for trading_all tables in all databases...\n")

with conn.cursor() as cur:
    cur.execute("SHOW DATABASES")
    databases = cur.fetchall()

    for db in databases:
        db_name = db[0]
        try:
            cur.execute(f"USE `{db_name}`")
            cur.execute("SHOW TABLES LIKE 'trading_all'")
            result = cur.fetchone()
            if result:
                print(f"Found trading_all in database: {db_name}")
                cur.execute("DESCRIBE trading_all")
                columns = cur.fetchall()
                print(f"  Columns: {[col[0] for col in columns][:10]}")  # First 10 columns
        except:
            pass

conn.close()
