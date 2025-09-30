#!/usr/bin/env python3
"""
SQLite数据库表结构获取工具
使用方法: python get_db_schema.py [database_path]
"""
import sqlite3
import sys
import os
from typing import List, Dict, Any

def get_table_names(conn: sqlite3.Connection) -> List[str]:
    """获取所有表名"""
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    return [row[0] for row in cursor.fetchall()]

def get_table_schema(conn: sqlite3.Connection, table_name: str) -> str:
    """获取表的创建语句"""
    cursor = conn.cursor()
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    result = cursor.fetchone()
    return result[0] if result else ""

def get_table_info(conn: sqlite3.Connection, table_name: str) -> List[Dict[str, Any]]:
    """获取表的列信息"""
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    
    return [
        {
            'cid': col[0],
            'name': col[1],
            'type': col[2],
            'notnull': bool(col[3]),
            'default_value': col[4],
            'pk': bool(col[5])
        }
        for col in columns
    ]

def get_indexes(conn: sqlite3.Connection, table_name: str) -> List[str]:
    """获取表的索引信息"""
    cursor = conn.cursor()
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL", (table_name,))
    return [row[0] for row in cursor.fetchall()]

def analyze_database(db_path: str) -> None:
    """分析数据库结构"""
    if not os.path.exists(db_path):
        print(f"错误：数据库文件 {db_path} 不存在")
        return
    
    try:
        with sqlite3.connect(db_path) as conn:
            print(f"数据库文件: {db_path}")
            print("=" * 80)
            
            # 获取所有表
            tables = get_table_names(conn)
            if not tables:
                print("数据库中没有找到用户定义的表")
                return
            
            print(f"共找到 {len(tables)} 个表:")
            for i, table in enumerate(tables, 1):
                print(f"{i}. {table}")
            print()
            
            # 详细分析每个表
            for table_name in tables:
                print(f"表名: {table_name}")
                print("-" * 60)
                
                # 表结构
                schema = get_table_schema(conn, table_name)
                print("创建语句:")
                print(schema)
                print()
                
                # 列信息
                columns = get_table_info(conn, table_name)
                print("列信息:")
                print(f"{'序号':<4} {'列名':<20} {'类型':<15} {'非空':<6} {'主键':<6} {'默认值':<15}")
                print("-" * 70)
                for col in columns:
                    print(f"{col['cid']:<4} {col['name']:<20} {col['type']:<15} "
                          f"{'是' if col['notnull'] else '否':<6} "
                          f"{'是' if col['pk'] else '否':<6} "
                          f"{str(col['default_value']) if col['default_value'] is not None else '':<15}")
                print()
                
                # 索引信息
                indexes = get_indexes(conn, table_name)
                if indexes:
                    print("索引:")
                    for idx in indexes:
                        print(f"  {idx}")
                    print()
                
                # 数据统计
                cursor = conn.cursor()
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = cursor.fetchone()[0]
                print(f"记录数: {count}")
                print("=" * 80)
                print()
    
    except sqlite3.Error as e:
        print(f"数据库错误: {e}")
    except Exception as e:
        print(f"其他错误: {e}")

def main():
    """主函数"""
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        # 默认使用项目中的数据库文件
        db_path = "radar_operations.db"
    
    analyze_database(db_path)

if __name__ == "__main__":
    main()
