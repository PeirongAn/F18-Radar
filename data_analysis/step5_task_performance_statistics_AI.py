import sqlite3
import pandas as pd
import os
from pathlib import Path

# 数据库文件路径
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"
ALL_DATA_DB = OUTPUT_DIR / "all_data.db"
DB_FILE = OUTPUT_DIR / 'task_performance_data.db'

def init_database():
    """初始化数据库，创建各任务AI绩效数据表"""
    try:
        OUTPUT_DIR.mkdir(exist_ok=True)
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # 传感器任务AI绩效表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS sensor_task_performance_AI (
            用户名 TEXT,
            动态容限 TEXT,
            智能助手自主等级 TEXT,
            交互工效 TEXT,
            记录数 INTEGER,
            智能助手完成目标锁定平均时长 REAL,
            操作员完成目标锁定平均时长 REAL,
            智能助手目标锁定准确率 REAL,
            操作员目标锁定准确率 REAL,
            PRIMARY KEY (用户名, 动态容限, 智能助手自主等级, 交互工效)
        )
        ''')
        
        # 威胁排序任务AI绩效表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS threat_task_performance_AI (
            用户名 TEXT,
            动态容限 TEXT,
            智能助手自主等级 TEXT,
            交互工效 TEXT,
            记录数 INTEGER,
            智能助手临机事件响应时长 REAL,
            操作员临机事件响应时长 REAL,
            智能助手更新最具威胁项准确率 REAL,
            操作员更新最具威胁项准确率 REAL,
            PRIMARY KEY (用户名, 动态容限, 智能助手自主等级, 交互工效)
        )
        ''')
        
        # 平台控制任务AI绩效表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS platform_task_performance_AI (
            用户名 TEXT,
            动态容限 TEXT,
            智能助手自主等级 TEXT,
            交互工效 TEXT,
            记录数 INTEGER,
            操作员路径点完成比例 REAL,
            智能助手路径点完成比例 REAL,
            操作员路径点完成平均时间 REAL,
            智能助手路径点完成平均时间 REAL,
            操作员路径点完成平均精度 REAL,
            智能助手路径点完成平均精度 REAL,
            PRIMARY KEY (用户名, 动态容限, 智能助手自主等级, 交互工效)
        )
        ''')
        
        # 武器发射任务AI绩效表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS weapon_task_performance_AI (
            用户名 TEXT,
            动态容限 TEXT,
            智能助手自主等级 TEXT,
            交互工效 TEXT,
            记录数 INTEGER,
            操作员目标击中成功率 REAL,
            发射武器平均耗时_秒 REAL,
            PRIMARY KEY (用户名, 动态容限, 智能助手自主等级, 交互工效)
        )
        ''')
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        pass

def save_to_database(user_stats, table_name, description):
    """将用户统计数据保存到数据库"""
    try:
        OUTPUT_DIR.mkdir(exist_ok=True)
        conn = sqlite3.connect(DB_FILE)
        
        # 重置索引，将user_id作为普通列
        data_to_save = user_stats.reset_index()
        
        # 保存到数据库，如果表已存在则替换
        data_to_save.to_sql(table_name, conn, if_exists='replace', index=False)
        
        conn.close()
        
    except Exception as e:
        pass

def calculate_sensor_task_ai_statistics():
    """计算传感器任务AI统计：按实验组合统计AI和手动操作的绩效"""
    
    try:
        # 连接数据库
        conn = sqlite3.connect(ALL_DATA_DB)
        
        # 读取数据（排除ai_level为null的数据）
        query = """
        SELECT 
            user_id,
            difficulty_level,
            ai_level,
            audio_enabled,
            repetition_count,
            selection_method,
            ai_select_time,
            person_select_time,
            ai_is_correct,
            person_is_correct
        FROM sensor_task_statistics_plus
        WHERE ai_level IS NOT NULL AND ai_level != 'NULL'
        """
        
        df = pd.read_sql_query(query, conn)
        
        # 处理数值字段
        df['ai_select_time_numeric'] = pd.to_numeric(df['ai_select_time'], errors='coerce') / 1000  # 转换为秒
        df['person_select_time_numeric'] = pd.to_numeric(df['person_select_time'], errors='coerce') / 1000  # 转换为秒
        df['ai_is_correct_numeric'] = df['ai_is_correct'].map({'true': 1, 'false': 0})
        df['person_is_correct_numeric'] = df['person_is_correct'].map({'true': 1, 'false': 0})
        
        # 按实验组合分组统计
        results = []
        
        for (user_id, difficulty_level, ai_level, audio_enabled), group in df.groupby(['user_id', 'difficulty_level', 'ai_level', 'audio_enabled']):
            # 总repetition次数（应该是10）
            total_repetitions = len(group)
            
            # 筛选AI数据
            ai_data = group[group['selection_method'] == 'AI']
            # 筛选手动数据
            manual_data = group[group['selection_method'] == 'manual']
            
            # 智能助手完成目标锁定平均时长
            ai_target_lock_time = ai_data['ai_select_time_numeric'].mean() if len(ai_data) > 0 else None
            # 智能助手目标锁定准确率
            ai_success_data = group[(group['selection_method'] == 'AI') & (group['ai_is_correct_numeric'] == 1)]
            ai_target_lock_accuracy = len(ai_success_data) / total_repetitions if total_repetitions > 0 else None
            
            # 操作员完成目标锁定平均时长
            manual_target_lock_time = manual_data['person_select_time_numeric'].mean() if len(manual_data) > 0 else None
            # 操作员目标锁定准确率
            manual_success_data = group[(group['selection_method'] == 'manual') & (group['person_is_correct_numeric'] == 1)]
            manual_target_lock_accuracy = len(manual_success_data) / total_repetitions if total_repetitions > 0 else None
            
            results.append({
                '用户名': user_id,
                '动态容限': difficulty_level,
                '智能助手自主等级': ai_level,
                '交互工效': audio_enabled,
                '记录数': total_repetitions,
                '智能助手完成目标锁定平均时长': ai_target_lock_time,
                '操作员完成目标锁定平均时长': manual_target_lock_time,
                '智能助手目标锁定准确率': ai_target_lock_accuracy,
                '操作员目标锁定准确率': manual_target_lock_accuracy
            })
        
        # 转换为DataFrame并设置索引
        results_df = pd.DataFrame(results)
        user_stats = results_df.set_index(['用户名', '动态容限', '智能助手自主等级', '交互工效'])
        
        # 保存到数据库
        save_to_database(user_stats, 'sensor_task_performance_AI', '传感器信任任务绩效数据')
        
        conn.close()
        
    except Exception as e:
        return None

def calculate_platform_task_ai_statistics():
    """计算平台控制任务AI统计：按实验组合统计AI和手动操作的绩效"""
    
    try:
        # 连接数据库
        conn = sqlite3.connect(ALL_DATA_DB)
        
        # 读取数据（排除ai_level为null的数据）
        query = """
        SELECT 
            user_id,
            difficulty_level,
            ai_level,
            audio_enabled,
            repetition_count,
            current_mode,
            is_correct,
            current_times,
            distance
        FROM platform_statistics
        WHERE ai_level IS NOT NULL AND ai_level != 'NULL'
        """
        
        df = pd.read_sql_query(query, conn)
        
        # 处理数值字段
        df['is_correct_numeric'] = df['is_correct'].map({'true': 1, 'false': 0})
        df['current_times_numeric'] = pd.to_numeric(df['current_times'], errors='coerce')
        df['distance_numeric'] = pd.to_numeric(df['distance'], errors='coerce')
        # 按实验组合分组统计
        results = []
        
        for (user_id, difficulty_level, ai_level, audio_enabled), group in df.groupby(['user_id', 'difficulty_level', 'ai_level', 'audio_enabled']):
            # 总repetition次数（应该是10）
            total_repetitions = len(group)  
            
            # 筛选操作员数据（current_mode=User且is_correct=true）
            manual_success_data = group[(group['current_mode'] == 'User') & (group['is_correct_numeric'] == 1)]
            # 操作员路径点完成比例
            manual_completion_rate = len(manual_success_data) / total_repetitions if total_repetitions > 0 else None
            # 操作员成功任务的平均时间和精度
            manual_completion_time = manual_success_data['current_times_numeric'].mean() if len(manual_success_data) > 0 else None
            manual_completion_accuracy = (1 - manual_success_data['distance_numeric'] / 10000).mean() if len(manual_success_data) > 0 else None
            
            # 筛选AI数据（current_mode=AI且is_correct=true）
            ai_success_data = group[(group['current_mode'] == 'AI') & (group['is_correct_numeric'] == 1)]
            # 智能助手路径点完成比例
            ai_completion_rate = len(ai_success_data) / total_repetitions if total_repetitions > 0 else None
            # 智能助手成功任务的平均时间和精度
            ai_completion_time = ai_success_data['current_times_numeric'].mean() if len(ai_success_data) > 0 else None
            ai_completion_accuracy = (1 - ai_success_data['distance_numeric'] / 10000).mean() if len(ai_success_data) > 0 else None
            
            results.append({
                '用户名': user_id,
                '动态容限': difficulty_level,
                '智能助手自主等级': ai_level,
                '交互工效': audio_enabled,
                '记录数': total_repetitions,
                '操作员路径点完成比例': manual_completion_rate,
                '智能助手路径点完成比例': ai_completion_rate,
                '操作员路径点完成平均时间': manual_completion_time,
                '智能助手路径点完成平均时间': ai_completion_time,
                '操作员路径点完成平均精度': manual_completion_accuracy,
                '智能助手路径点完成平均精度': ai_completion_accuracy
            })
        
        # 转换为DataFrame并设置索引
        results_df = pd.DataFrame(results)
        user_stats = results_df.set_index(['用户名', '动态容限', '智能助手自主等级', '交互工效'])
        
        # 保存到数据库
        save_to_database(user_stats, 'platform_task_performance_AI', '平台控制信任任务绩效数据')
        
        conn.close()
        
    except Exception as e:
        return None

def calculate_threat_task_ai_statistics():
    """计算威胁排序任务AI统计：按实验组合统计AI和手动操作的绩效"""
    
    try:
        # 连接数据库
        conn = sqlite3.connect(ALL_DATA_DB)
        
        # 读取数据（排除ai_level为null的数据）
        query = """
        SELECT 
            user_id,
            difficulty_level,
            ai_level,
            audio_enabled,
            repetition_count,
            selection_method,
            ai_select_time,
            person_select_time,
            ai_is_correct,
            person_is_correct
        FROM threat_task_statistics_plus
        WHERE ai_level IS NOT NULL AND ai_level != 'NULL'
        """
        
        df = pd.read_sql_query(query, conn)
        
        # 处理数值字段
        df['ai_select_time_numeric'] = pd.to_numeric(df['ai_select_time'], errors='coerce') / 1000  # 转换为秒
        df['person_select_time_numeric'] = pd.to_numeric(df['person_select_time'], errors='coerce') / 1000  # 转换为秒
        df['ai_is_correct_numeric'] = df['ai_is_correct'].map({'true': 1, 'false': 0})
        df['person_is_correct_numeric'] = df['person_is_correct'].map({'true': 1, 'false': 0})
        
        # 按实验组合分组统计
        results = []
        
        for (user_id, difficulty_level, ai_level, audio_enabled), group in df.groupby(['user_id', 'difficulty_level', 'ai_level', 'audio_enabled']):
            # 总repetition次数（应该是10）
            total_repetitions = len(group)
            
            # 筛选AI数据
            ai_data = group[group['selection_method'] == 'AI']
            # 筛选手动数据
            manual_data = group[group['selection_method'] == 'manual']
            
            # 绩效指标1：智能助手临机事件响应时长
            ai_response_time = ai_data['ai_select_time_numeric'].mean() if len(ai_data) > 0 else None
            
            # 绩效指标2：操作员临机事件响应时长
            manual_response_time = manual_data['person_select_time_numeric'].mean() if len(manual_data) > 0 else None
            
            # 绩效指标3：智能助手更新最具威胁项准确率
            ai_success_data = group[(group['selection_method'] == 'AI') & (group['ai_is_correct_numeric'] == 1)]
            ai_accuracy = len(ai_success_data) / total_repetitions if total_repetitions > 0 else None
            
            # 绩效指标4：操作员更新最具威胁项准确率
            manual_success_data = group[(group['selection_method'] == 'manual') & (group['person_is_correct_numeric'] == 1)]
            manual_accuracy = len(manual_success_data) / total_repetitions if total_repetitions > 0 else None
            
            results.append({
                '用户名': user_id,
                '动态容限': difficulty_level,
                '智能助手自主等级': ai_level,
                '交互工效': audio_enabled,
                '记录数': total_repetitions,
                '智能助手临机事件响应时长': ai_response_time,
                '操作员临机事件响应时长': manual_response_time,
                '智能助手更新最具威胁项准确率': ai_accuracy,
                '操作员更新最具威胁项准确率': manual_accuracy
            })
        
        # 转换为DataFrame并设置索引
        results_df = pd.DataFrame(results)
        user_stats = results_df.set_index(['用户名', '动态容限', '智能助手自主等级', '交互工效'])
        
        # 保存到数据库
        save_to_database(user_stats, 'threat_task_performance_AI', '威胁排序信任任务绩效数据')
        
        conn.close()
        
    except Exception as e:
        return None

def calculate_weapon_task_ai_statistics():
    """计算武器发射任务AI统计：按实验组合统计操作员绩效"""
    
    try:
        # 连接数据库
        conn = sqlite3.connect(ALL_DATA_DB)
        
        # 读取数据（排除ai_level为null的数据）
        query = """
        SELECT 
            user_id,
            difficulty_level,
            ai_level,
            audio_enabled,
            repetition_count,
            fire_result,
            current_times
        FROM weapon_statistics
        WHERE ai_level IS NOT NULL AND ai_level != 'NULL'
        """
        
        df = pd.read_sql_query(query, conn)
        
        # 处理数值字段
        df['fire_result_numeric'] = df['fire_result'].map({'true': 1, 'false': 0})
        df['current_times_numeric'] = pd.to_numeric(df['current_times'], errors='coerce')
        
        # 按实验组合分组统计
        results = []
        
        for (user_id, difficulty_level, ai_level, audio_enabled), group in df.groupby(['user_id', 'difficulty_level', 'ai_level', 'audio_enabled']):
            # 总repetition次数（应该是10）
            total_repetitions = len(group)
            
            # 操作员目标击中成功率：10个repetition中fire_result=true的比例
            hit_success_rate = group['fire_result_numeric'].mean() if total_repetitions > 0 else None
            
            # 发射武器平均耗时_秒：10个repetition平均的current_times
            average_fire_time = group['current_times_numeric'].mean() if total_repetitions > 0 else None
            
            results.append({
                '用户名': user_id,
                '动态容限': difficulty_level,
                '智能助手自主等级': ai_level,
                '交互工效': audio_enabled,
                '记录数': total_repetitions,
                '操作员目标击中成功率': hit_success_rate,
                '发射武器平均耗时_秒': average_fire_time
            })
        
        # 转换为DataFrame并设置索引
        results_df = pd.DataFrame(results)
        user_stats = results_df.set_index(['用户名', '动态容限', '智能助手自主等级', '交互工效'])
        
        # 保存到数据库
        save_to_database(user_stats, 'weapon_task_performance_AI', '武器发射信任任务绩效数据')
        
        conn.close()
        
    except Exception as e:
        return None

if __name__ == "__main__":
    # 初始化数据库
    init_database()
    
    # 传感器任务AI统计
    calculate_sensor_task_ai_statistics()
    
    # 平台控制任务AI统计
    calculate_platform_task_ai_statistics()
    
    # 威胁排序任务AI统计
    calculate_threat_task_ai_statistics()
    
    # 武器发射任务AI统计
    calculate_weapon_task_ai_statistics()
