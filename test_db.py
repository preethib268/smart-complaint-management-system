import pymysql

# Connect to the database
connection = pymysql.connect(
    host='localhost',
    user='root',
    password='',
    database='complaint_system',
    charset='utf8mb4',
    cursorclass=pymysql.cursors.DictCursor
)

try:
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM complaints")
        rows = cursor.fetchall()
        print("Connection successful!")
        print("Number of complaints found:", len(rows))
        print("Rows:", rows)
finally:
    connection.close()