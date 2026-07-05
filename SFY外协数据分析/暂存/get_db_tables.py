import sqlite3

def get_table_info(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 获取所有表名
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    
    print(f"数据库: {db_path}")
    print(f"表数量: {len(tables)}")
    print("\n" + "="*60)
    
    for table in tables:
        table_name = table[0]
        print(f"\n表名: {table_name}")
        print("-" * 40)
        
        # 获取表结构
        cursor.execute(f"PRAGMA table_info({table_name});")
        columns = cursor.fetchall()
        
        print("字段信息:")
        for col in columns:
            col_id, col_name, col_type, not_null, default_val, pk = col
            print(f"  {col_name:20s} ({col_type:10s})")
        
        # 获取记录数
        cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
        count = cursor.fetchone()[0]
        print(f"\n记录数: {count}")
        print("="*60)
    
    conn.close()

if __name__ == "__main__":
    get_table_info("task_performance_data.db")

