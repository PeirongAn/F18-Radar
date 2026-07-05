import sqlite3
import pandas as pd

# 连接到数据库
conn = sqlite3.connect('all_data.db')

# 查看所有表名
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
print("数据库中的表:")
for table in tables:
    print(f"- {table[0]}")

# 查看questionaire_statistics表的结构
print("\nquestionaire_statistics表结构:")
cursor.execute("PRAGMA table_info(questionaire_statistics);")
columns = cursor.fetchall()
for col in columns:
    print(f"- {col[1]} ({col[2]})")

# 查看前几行数据
print("\nquestionaire_statistics表前5行数据:")
df = pd.read_sql_query("SELECT * FROM questionaire_statistics LIMIT 5", conn)
print(df)

# 查看q6_score字段的分布
print("\nq6_score字段的分布:")
df_q6 = pd.read_sql_query("SELECT q6_score, COUNT(*) as count FROM questionaire_statistics GROUP BY q6_score", conn)
print(df_q6)

conn.close()
