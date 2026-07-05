import sqlite3
import pandas as pd
import os

# 数据库文件路径
DB_FILE = 'task_performance_data.db'

def init_database():
    """初始化数据库，创建各任务绩效数据表"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # 威胁排序任务绩效表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS threat_task_performance_nonAI (
            用户名 TEXT,
            动态容限 TEXT,
            记录数 INTEGER,
            更新最具威胁项准确率 REAL,
            临机事件响应时长_秒 REAL,
            PRIMARY KEY (用户名, 动态容限)
        )
        ''')
        
        # 传感器任务绩效表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS sensor_task_performance_nonAI (
            用户名 TEXT,
            动态容限 TEXT,
            记录数 INTEGER,
            雷达初始设置耗时_毫秒 REAL,
            雷达参数调节耗时_秒 REAL,
            目标锁定耗时_秒 REAL,
            目标锁定准确率 REAL,
            PRIMARY KEY (用户名, 动态容限)
        )
        ''')
        
        # 平台控制任务绩效表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS platform_task_performance_nonAI (
            用户名 TEXT,
            动态容限 TEXT,
            记录数 INTEGER,
            目标路径点完成比例 REAL,
            目标路径点完成耗时_秒 REAL,
            目标路径点完成精度 REAL,
            PRIMARY KEY (用户名, 动态容限)
        )
        ''')
        
        # 武器发射任务绩效表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS weapon_task_performance_nonAI (
            用户名 TEXT,
            动态容限 TEXT,
            记录数 INTEGER,
            目标击中成功率 REAL,
            发射武器平均耗时_秒 REAL,
            PRIMARY KEY (用户名, 动态容限)
        )
        ''')
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        pass

def save_to_database(user_stats, table_name, description):
    """将用户统计数据保存到数据库"""
    try:
        conn = sqlite3.connect(DB_FILE)
        
        # 保存到数据库，如果表已存在则替换
        user_stats.to_sql(table_name, conn, if_exists='replace', index=False)
        
        conn.close()
        
    except Exception as e:
        pass

def calculate_threat_task_statistics():
    """计算威胁排序任务统计：按被试分别统计person_is_correct和person_select_time的平均值（仅统计ai_level为NULL的记录）"""
    
    try:
        # 连接数据库
        conn = sqlite3.connect('all_data.db')
        
        # 读取数据（仅统计ai_level为NULL的记录）
        query = """
        SELECT 
            user_id,
            difficulty_level,
            person_is_correct,
            person_select_time
        FROM threat_task_statistics_plus
        WHERE (ai_level IS NULL OR ai_level = 'NULL')
        """
        
        df = pd.read_sql_query(query, conn)
        
        # 处理数值字段
        df['person_is_correct_numeric'] = df['person_is_correct'].map({'true': 1, 'false': 0})
        df['person_select_time_numeric'] = pd.to_numeric(df['person_select_time'], errors='coerce') / 1000  # 转换为秒
        
        # 按被试和难度分组统计
        user_stats = df.groupby(['user_id', 'difficulty_level']).agg({
            'person_is_correct_numeric': ['count', 'mean'],
            'person_select_time_numeric': 'mean'
        }).round(4)
        
        # 展平列名
        user_stats.columns = ['记录数', '更新最具威胁项准确率', '临机事件响应时长_秒']
        
        # 重置索引
        user_stats = user_stats.reset_index()
        user_stats = user_stats.rename(columns={'user_id': '用户名', 'difficulty_level': '动态容限'})
        
        # 保存到数据库
        save_to_database(user_stats, 'threat_task_performance_nonAI', '威胁排序交互任务绩效数据')
        
        conn.close()
        
    except Exception as e:
        return None

def calculate_sensor_task_statistics():
    """计算传感器任务统计：按被试分别统计radar_settings_time、antenna_settings_time、person_select_time和person_is_correct的平均值（仅统计ai_level为NULL的记录）"""
    
    try:
        # 连接数据库
        conn = sqlite3.connect('all_data.db')
        
        # 读取数据（仅统计ai_level为NULL的记录）
        query = """
        SELECT 
            user_id,
            difficulty_level,
            radar_settings_time,
            antenna_settings_time,
            person_select_time,
            person_is_correct
        FROM sensor_task_statistics_plus
        WHERE (ai_level IS NULL OR ai_level = 'NULL')
        """
        
        df = pd.read_sql_query(query, conn)
        
        # 处理数值字段
        df['person_is_correct_numeric'] = df['person_is_correct'].map({'true': 1, 'false': 0})
        df['radar_settings_time_numeric'] = pd.to_numeric(df['radar_settings_time'], errors='coerce')  # 保持毫秒
        df['antenna_settings_time_numeric'] = pd.to_numeric(df['antenna_settings_time'], errors='coerce') / 1000  # 转换为秒
        df['person_select_time_numeric'] = pd.to_numeric(df['person_select_time'], errors='coerce') / 1000  # 转换为秒
        
        # 按被试和难度分组统计
        user_stats = df.groupby(['user_id', 'difficulty_level']).agg({
            'person_is_correct_numeric': ['count', 'mean'],
            'radar_settings_time_numeric': 'mean',
            'antenna_settings_time_numeric': 'mean',
            'person_select_time_numeric': 'mean'
        }).round(4)
        
        # 展平列名
        user_stats.columns = ['记录数', '目标锁定准确率', '雷达初始设置耗时_毫秒', '雷达参数调节耗时_秒', '目标锁定耗时_秒']
        
        # 重新排列列的顺序
        user_stats = user_stats[['记录数', '雷达初始设置耗时_毫秒', '雷达参数调节耗时_秒', '目标锁定耗时_秒', '目标锁定准确率']]
        
        # 重置索引并重命名列
        user_stats = user_stats.reset_index()
        user_stats = user_stats.rename(columns={'user_id': '用户名', 'difficulty_level': '动态容限'})
        
        # 保存到数据库
        save_to_database(user_stats, 'sensor_task_performance_nonAI', '传感器交互任务绩效数据')
        
        conn.close()
        
    except Exception as e:
        return None

def calculate_platform_task_statistics():
    """计算平台控制任务统计：按被试分别统计is_correct、current_times和distance的平均值（仅统计ai_level为NULL的记录）"""
    
    try:
        # 连接数据库
        conn = sqlite3.connect('all_data.db')
        
        # 读取有效数据（ai_level为NULL的记录）
        valid_query = """
        SELECT 
            user_id,
            difficulty_level,
            is_correct,
            current_times,
            distance
        FROM platform_statistics
        WHERE (ai_level IS NULL OR ai_level = 'NULL')
        """
        
        df = pd.read_sql_query(valid_query, conn)
        
        # 处理数值字段
        df['is_correct_numeric'] = df['is_correct'].map({'true': 1, 'false': 0})
        df['current_times_numeric'] = pd.to_numeric(df['current_times'], errors='coerce')
        df['distance_numeric'] = pd.to_numeric(df['distance'], errors='coerce')
        
        # 按被试和难度分组统计
        user_stats = df.groupby(['user_id', 'difficulty_level']).agg({
            'is_correct_numeric': ['count', 'mean'],
            'current_times_numeric': lambda x: x[df.loc[x.index, 'is_correct'] == 'true'].mean(),
            'distance_numeric': lambda x: (1 - x[df.loc[x.index, 'is_correct'] == 'true'] / 10000).mean()
        }).round(4)
        
        # 展平列名
        user_stats.columns = ['记录数', '目标路径点完成比例', '目标路径点完成耗时_秒', '目标路径点完成精度']
        
        # 重置索引并重命名列
        user_stats = user_stats.reset_index()
        user_stats = user_stats.rename(columns={'user_id': '用户名', 'difficulty_level': '动态容限'})
        
        # 保存到数据库
        save_to_database(user_stats, 'platform_task_performance_nonAI', '平台控制交互任务绩效数据')
        
        conn.close()
        
    except Exception as e:
        return None

def calculate_weapon_task_statistics():
    """计算武器发射任务统计：按被试分别统计fire_result和current_times的平均值（仅统计ai_level为NULL的记录）"""
    
    try:
        # 连接数据库
        conn = sqlite3.connect('all_data.db')
        
        # 读取有效数据（ai_level为NULL的记录）
        valid_query = """
        SELECT 
            user_id,
            difficulty_level,
            fire_result,
            current_times
        FROM weapon_statistics
        WHERE (ai_level IS NULL OR ai_level = 'NULL')
        """
        
        df = pd.read_sql_query(valid_query, conn)
        
        # 处理数值字段
        df['fire_result_numeric'] = df['fire_result'].map({'true': 1, 'false': 0})
        df['current_times_numeric'] = pd.to_numeric(df['current_times'], errors='coerce')
        
        # 按被试和难度分组统计
        user_stats = df.groupby(['user_id', 'difficulty_level']).agg({
            'fire_result_numeric': ['count', 'mean'],
            'current_times_numeric': 'mean'
        }).round(4)
        
        # 展平列名
        user_stats.columns = ['记录数', '目标击中成功率', '发射武器平均耗时_秒']
        
        # 重置索引并重命名列
        user_stats = user_stats.reset_index()
        user_stats = user_stats.rename(columns={'user_id': '用户名', 'difficulty_level': '动态容限'})
        
        # 保存到数据库
        save_to_database(user_stats, 'weapon_task_performance_nonAI', '武器发射交互任务绩效数据')
        
        conn.close()
        
    except Exception as e:
        return None

if __name__ == "__main__":
    # 初始化数据库
    init_database()
    
    # 威胁排序任务统计
    calculate_threat_task_statistics()
    
    # 传感器任务统计
    calculate_sensor_task_statistics()
    
    # 平台控制任务统计
    calculate_platform_task_statistics()
    
    # 武器发射任务统计
    calculate_weapon_task_statistics()
