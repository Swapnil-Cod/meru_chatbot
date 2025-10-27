import pymysql
from config import Config

# Connect to database
conn = pymysql.connect(**Config.DB_CONFIG, cursorclass=pymysql.cursors.DictCursor)

print("="*60)
print("VERIFYING DATABASE CONNECTION AND TABLE STRUCTURE")
print("="*60)

# Check database
with conn.cursor() as cur:
    cur.execute("SELECT DATABASE()")
    db = cur.fetchone()
    print(f"\nConnected to database: {db}")

# Check if table exists
with conn.cursor() as cur:
    cur.execute("SHOW TABLES")
    tables = cur.fetchall()
    print(f"\nTables in database: {tables}")

# Check table structure
with conn.cursor() as cur:
    cur.execute("DESCRIBE trading_all")
    columns = cur.fetchall()
    print(f"\nColumns in trading_all table:")
    for col in columns:
        print(f"  - {col['Field']} ({col['Type']})")

# Check row count
with conn.cursor() as cur:
    cur.execute("SELECT COUNT(*) as count FROM trading_all")
    count = cur.fetchone()
    print(f"\nTotal rows in trading_all: {count['count']}")

# Try the failing query
print("\n" + "="*60)
print("TESTING THE ACTUAL QUERY THAT FAILS IN FLASK")
print("="*60)

sql = "SELECT DATE(MIN(ordertime)) as first_day, SUM(total_pnl) as profit FROM trading_all WHERE DATE(ordertime) = (SELECT DATE(MIN(ordertime)) FROM trading_all)"
print(f"\nSQL: {sql}\n")

try:
    with conn.cursor() as cur:
        cur.execute(sql)
        result = cur.fetchone()
        print(f"✅ SUCCESS! Result: {result}")
except Exception as e:
    print(f"❌ FAILED! Error: {e}")

# Try a simple query
print("\n" + "="*60)
print("TESTING SIMPLE QUERY")
print("="*60)

sql2 = "SELECT * FROM trading_all LIMIT 1"
print(f"\nSQL: {sql2}\n")

try:
    with conn.cursor() as cur:
        cur.execute(sql2)
        result = cur.fetchone()
        print(f"✅ SUCCESS! Sample row columns:")
        for key in result.keys():
            print(f"  - {key}")
except Exception as e:
    print(f"❌ FAILED! Error: {e}")

conn.close()
