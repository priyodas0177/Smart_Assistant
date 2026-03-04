import psycopg2
def get_connection():
    return psycopg2.connect(
        dbname="samsung_db",
        user="postgres",
        password="pri123",
        host="localhost",
        port="5432",
    )
conn=get_connection()
cursor=conn.cursor()

# cursor.execute("""CREATE TABLE phones(
#             id SERIAL PRIMARY KEY,
#             model_name TEXT UNIQUE,
#             release_date DATE,
#             display TEXT,
#             battery INT,
#             camera INT,
#             ram INT,
#             storage INT,
#             price INT
              
#             )""")
# conn.commit()
# cursor.close()
# conn.close
# print("Table Create success.")

