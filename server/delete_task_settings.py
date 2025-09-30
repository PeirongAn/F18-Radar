#!/usr/bin/env python3
"""
删除 task_settings 表中指定范围的数据
"""

import sqlite3
import os

def delete_task_settings_data(min_task_id=None, max_task_id=None):
    """
    删除 task_settings 表中指定范围的数据
    
    Args:
        min_task_id: 最小task_id (None表示无下限)
        max_task_id: 最大task_id (None表示无上限)
    """
    # 数据库路径
    db_path = os.path.join(os.path.dirname(__file__), 'data', 'radar_operations.db')
    
    if not os.path.exists(db_path):
        print(f"数据库文件不存在: {db_path}")
        return
    
    # 连接数据库
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 构建查询条件
        conditions = []
        params = []
        
        if min_task_id is not None:
            conditions.append("task_id >= ?")
            params.append(min_task_id)
        
        if max_task_id is not None:
            conditions.append("task_id <= ?")
            params.append(max_task_id)
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        # 先查询要删除的记录数和范围
        query_sql = f"SELECT COUNT(*), MIN(task_id), MAX(task_id) FROM task_settings WHERE {where_clause}"
        cursor.execute(query_sql, params)
        result = cursor.fetchone()
        count, min_id, max_id = result
        
        print(f"准备删除的记录信息:")
        print(f"  记录数量: {count}")
        print(f"  task_id 范围: {min_id} - {max_id}")
        
        if count == 0:
            print("没有符合条件的记录需要删除")
            return
        
        # 显示一些示例记录
        sample_sql = f"SELECT task_id, event_owner, difficulty_name, ai_level_name FROM task_settings WHERE {where_clause} ORDER BY task_id LIMIT 5"
        cursor.execute(sample_sql, params)
        samples = cursor.fetchall()
        
        print(f"\n示例记录 (前5条):")
        for task_id, event_owner, difficulty_name, ai_level_name in samples:
            print(f"  task_id={task_id}, owner={event_owner}, difficulty={difficulty_name}, ai_level={ai_level_name}")
        
        # 确认删除
        confirm = input(f"\n确认删除这 {count} 条记录吗？(y/n): ")
        if confirm.lower() not in ['y', 'yes', '是']:
            print("操作已取消")
            return
        
        # 执行删除
        delete_sql = f"DELETE FROM task_settings WHERE {where_clause}"
        cursor.execute(delete_sql, params)
        deleted_count = cursor.rowcount
        
        # 提交事务
        conn.commit()
        print(f"\n删除完成！实际删除了 {deleted_count} 条记录")
        
        # 验证删除结果
        cursor.execute(query_sql, params)
        result = cursor.fetchone()
        remaining_count = result[0]
        print(f"验证：剩余符合条件的记录数: {remaining_count}")
        
    except Exception as e:
        print(f"删除数据时发生错误: {e}")
        conn.rollback()
        
    finally:
        conn.close()

def delete_task_id_greater_than(task_id):
    """删除 task_id > 指定值的所有记录"""
    print(f"删除 task_settings 表中 task_id > {task_id} 的数据")
    print("=" * 50)
    
    # 数据库路径
    db_path = os.path.join(os.path.dirname(__file__), 'data', 'radar_operations.db')
    
    if not os.path.exists(db_path):
        print(f"数据库文件不存在: {db_path}")
        return
    
    # 连接数据库
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 先查询要删除的记录数和范围
        cursor.execute("SELECT COUNT(*), MIN(task_id), MAX(task_id) FROM task_settings WHERE task_id > ?", (task_id,))
        result = cursor.fetchone()
        count, min_id, max_id = result
        
        print(f"准备删除的记录信息:")
        print(f"  条件: task_id > {task_id}")
        print(f"  记录数量: {count}")
        if count > 0:
            print(f"  task_id 范围: {min_id} - {max_id}")
        
        if count == 0:
            print("没有符合条件的记录需要删除")
            return
        
        # 显示一些示例记录
        cursor.execute("""
            SELECT task_id, event_owner, difficulty_name, ai_level_name 
            FROM task_settings 
            WHERE task_id > ? 
            ORDER BY task_id 
            LIMIT 10
        """, (task_id,))
        samples = cursor.fetchall()
        
        print(f"\n示例记录 (前10条):")
        for task_id_val, event_owner, difficulty_name, ai_level_name in samples:
            print(f"  task_id={task_id_val}, owner={event_owner}, difficulty={difficulty_name}, ai_level={ai_level_name}")
        
        # 确认删除
        confirm = input(f"\n确认删除这 {count} 条记录吗？(y/n): ")
        if confirm.lower() not in ['y', 'yes', '是']:
            print("操作已取消")
            return
        
        # 执行删除
        cursor.execute("DELETE FROM task_settings WHERE task_id > ?", (task_id,))
        deleted_count = cursor.rowcount
        
        # 提交事务
        conn.commit()
        print(f"\n删除完成！实际删除了 {deleted_count} 条记录")
        
        # 验证删除结果
        cursor.execute("SELECT COUNT(*) FROM task_settings WHERE task_id > ?", (task_id,))
        remaining_count = cursor.fetchone()[0]
        print(f"验证：剩余 task_id > {task_id} 的记录数: {remaining_count}")
        
        # 显示当前最大的task_id
        cursor.execute("SELECT MAX(task_id) FROM task_settings")
        max_task_id = cursor.fetchone()[0]
        print(f"当前表中最大的 task_id: {max_task_id}")
        
    except Exception as e:
        print(f"删除数据时发生错误: {e}")
        conn.rollback()
        
    finally:
        conn.close()

if __name__ == "__main__":
    # 删除 task_id > 287 的数据
    delete_task_id_greater_than(287)
