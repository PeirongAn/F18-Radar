import sqlite3

def get_remaining_tables(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 获取所有表名
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    
    # 显示剩余的表（从第6个开始）
    remaining_tables = tables[5:]  # 从索引5开始
    
    for i, table in enumerate(remaining_tables, 6):
        table_name = table[0]
        print(f"\n{i}. 表名: {table_name}")
        print("-" * 50)
        
        # 获取表结构
        cursor.execute(f"PRAGMA table_info({table_name});")
        columns = cursor.fetchall()
        
        print("字段信息:")
        for col in columns:
            col_id, col_name, col_type, not_null, default_val, pk = col
            print(f"  {col_name:25s} ({col_type:10s})")
        
        # 获取记录数
        cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
        count = cursor.fetchone()[0]
        print(f"\n记录数: {count}")
        
        if i < len(tables):
            print("\n" + "="*60)
    
    conn.close()

if __name__ == "__main__":
    get_remaining_tables("task_performance_data.db")

