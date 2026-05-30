import sqlite3
import pandas as pd
import os
import numpy as np
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"
ALL_DATA_DB = OUTPUT_DIR / "all_data.db"
VALID_DATA_DB = OUTPUT_DIR / "valid_data.db"

def write_enhanced_records_to_db(enhanced_records, task_name, trust_conn):
    """
    通用函数：将增强的记录写入trust_data表
    """
    if not enhanced_records:
        return 0
    
    enhanced_df = pd.DataFrame(enhanced_records)
    
    # 确保repetition_count按照数字顺序排序，并转换为整数类型
    enhanced_df['repetition_count_int'] = enhanced_df['repetition_count'].astype(int)
    enhanced_df = enhanced_df.sort_values(['user_id', 'difficulty', 'ai_level', 'audio_enabled', 'repetition_count_int'])
    enhanced_df['repetition_count'] = enhanced_df['repetition_count_int']
    enhanced_df = enhanced_df.drop('repetition_count_int', axis=1)
    
    # 删除原有的任务记录
    trust_conn.execute(f"DELETE FROM trust_data WHERE task_name = '{task_name}'")
    
    # 插入增强的记录
    enhanced_df.to_sql('trust_data', trust_conn, if_exists='append', index=False)
    
    return len(enhanced_records)

def calculate_common_features(ai_control_time, person_control_time):
    """
    通用函数：计算共同的特征值
    """
    # 计算AI时间比例：ai_control_time / (ai_control_time + person_control_time)
    if pd.notna(ai_control_time) and pd.notna(person_control_time):
        total_time = float(ai_control_time) + float(person_control_time)
        if total_time > 0:
            ai_time_ratio = float(ai_control_time) / total_time
        else:
            ai_time_ratio = 0.0
    else:
        ai_time_ratio = 0.0
    
    # 计算人类主导程度：person_control_time / ai_control_time
    if pd.notna(ai_control_time) and pd.notna(person_control_time) and float(ai_control_time) > 0:
        person_dominance = float(person_control_time) / float(ai_control_time)
    else:
        person_dominance = 0.0
    
    return ai_time_ratio, person_dominance

def extract_weapon_features(trust_conn, source_conn):
    """
    为武器发射任务提取特征数据
    """
    weapon_records = pd.read_sql_query("""
        SELECT user_id, difficulty, ai_level, audio_enabled, data_label
        FROM trust_data 
        WHERE task_name = 'weapon'
    """, trust_conn)
    
    enhanced_records = []
    
    for _, record in weapon_records.iterrows():
        user_id = record['user_id']
        difficulty = record['difficulty']
        ai_level = record['ai_level']
        audio_enabled = record['audio_enabled']
        data_label = record['data_label']
        
        query = """
        SELECT repetition_count, ai_control_time, person_control_time, 
               current_times, ai_remind_time
        FROM weapon_statistics
        WHERE user_id = ? 
        AND difficulty_level = ? 
        AND ai_level = ? 
        AND audio_enabled = ?
        ORDER BY repetition_count
        """
        
        weapon_data = pd.read_sql_query(query, source_conn, 
                                      params=[user_id, difficulty, ai_level, audio_enabled])
            
        for _, weapon_row in weapon_data.iterrows():
            rep_count = weapon_row['repetition_count']
            ai_control_time = weapon_row['ai_control_time']
            person_control_time = weapon_row['person_control_time']
            current_times = weapon_row['current_times']
            ai_remind_time = weapon_row['ai_remind_time']
            
            # 计算特征
            ai_time_ratio, person_dominance = calculate_common_features(ai_control_time, person_control_time)
            
            # 计算接受AI建议：current_times - ai_remind_time
            if pd.notna(current_times) and pd.notna(ai_remind_time):
                accept_ai_advice = float(current_times) - float(ai_remind_time)
            else:
                accept_ai_advice = 0.0
            
            enhanced_record = {
                'user_id': user_id,
                'task_name': 'weapon',
                'difficulty': difficulty,
                'ai_level': ai_level,
                'audio_enabled': audio_enabled,
                'data_label': data_label,
                'repetition_count': rep_count,
                'ai_control_time': float(ai_control_time) if pd.notna(ai_control_time) else 0.0,
                'person_control_time': float(person_control_time) if pd.notna(person_control_time) else 0.0,
                'total_time': float(ai_control_time) + float(person_control_time) if pd.notna(ai_control_time) and pd.notna(person_control_time) else 0.0,
                'ai_time_ratio': ai_time_ratio,
                'person_dominance': person_dominance,
                'accept_ai_advice': accept_ai_advice
            }
            
            enhanced_records.append(enhanced_record)
    
    return write_enhanced_records_to_db(enhanced_records, 'weapon', trust_conn)

def extract_platform_features(trust_conn, source_conn):
    """
    为平台控制任务提取特征数据
    """
    platform_records = pd.read_sql_query("""
        SELECT user_id, difficulty, ai_level, audio_enabled, data_label
        FROM trust_data 
        WHERE task_name = 'platform'
    """, trust_conn)
    
    enhanced_records = []
    
    for _, record in platform_records.iterrows():
        user_id = record['user_id']
        difficulty = record['difficulty']
        ai_level = record['ai_level']
        audio_enabled = record['audio_enabled']
        data_label = record['data_label']
        
        query = """
        SELECT repetition_count, ai_control_time, person_control_time, 
               current_mode
        FROM platform_statistics
        WHERE user_id = ? 
        AND difficulty_level = ? 
        AND ai_level = ? 
        AND audio_enabled = ?
        ORDER BY repetition_count
        """
        
        platform_data = pd.read_sql_query(query, source_conn, 
                                        params=[user_id, difficulty, ai_level, audio_enabled])
        
        for _, platform_row in platform_data.iterrows():
            rep_count = platform_row['repetition_count']
            ai_control_time = platform_row['ai_control_time']
            person_control_time = platform_row['person_control_time']
            current_mode = platform_row['current_mode']
            
            # 计算特征
            ai_time_ratio, person_dominance = calculate_common_features(ai_control_time, person_control_time)
            
            # 判断是否接受AI建议
            if pd.notna(current_mode):
                if current_mode == 'user':
                    accept_ai_advice = 0
                elif current_mode == 'AI':
                    accept_ai_advice = 1
                else:
                    accept_ai_advice = 0
            else:
                accept_ai_advice = 0
            
            enhanced_record = {
                'user_id': user_id,
                'task_name': 'platform',
                'difficulty': difficulty,
                'ai_level': ai_level,
                'audio_enabled': audio_enabled,
                'data_label': data_label,
                'repetition_count': rep_count,
                'ai_control_time': float(ai_control_time) if pd.notna(ai_control_time) else 0.0,
                'person_control_time': float(person_control_time) if pd.notna(person_control_time) else 0.0,
                'total_time': float(ai_control_time) + float(person_control_time) if pd.notna(ai_control_time) and pd.notna(person_control_time) else 0.0,
                'ai_time_ratio': ai_time_ratio,
                'person_dominance': person_dominance,
                'accept_ai_advice': accept_ai_advice
            }
            
            enhanced_records.append(enhanced_record)
    
    return write_enhanced_records_to_db(enhanced_records, 'platform', trust_conn)

def extract_threat_features(trust_conn, source_conn):
    """
    为威胁排序任务提取特征数据
    """
    threat_records = pd.read_sql_query("""
        SELECT user_id, difficulty, ai_level, audio_enabled, data_label
        FROM trust_data 
        WHERE task_name = 'threat'
    """, trust_conn)
    
    enhanced_records = []
    
    for _, record in threat_records.iterrows():
        user_id = record['user_id']
        difficulty = record['difficulty']
        ai_level = record['ai_level']
        audio_enabled = record['audio_enabled']
        data_label = record['data_label']
        
        query = """
        SELECT repetition_count, ai_select_time, person_select_time, 
               ai_target_id, person_target_id
        FROM threat_task_statistics_plus
        WHERE user_id = ? 
        AND difficulty_level = ? 
        AND ai_level = ? 
        AND audio_enabled = ?
        ORDER BY CAST(repetition_count AS INTEGER)
        """
        
        threat_data = pd.read_sql_query(query, source_conn, 
                                      params=[user_id, difficulty, ai_level, audio_enabled])
            
        for _, threat_row in threat_data.iterrows():
            rep_count = threat_row['repetition_count']
            ai_select_time = threat_row['ai_select_time']
            person_select_time = threat_row['person_select_time']
            ai_target = threat_row['ai_target_id']
            person_target = threat_row['person_target_id']
            
            # 计算控制时间（从毫秒转换为秒）
            ai_control_time = float(ai_select_time) / 1000.0 if pd.notna(ai_select_time) else 0.0
            if pd.notna(person_select_time) and pd.notna(ai_select_time):
                person_control_time = (float(person_select_time) - float(ai_select_time)) / 1000.0
            else:
                person_control_time = 0.0
            
            # 计算特征
            ai_time_ratio, person_dominance = calculate_common_features(
                ai_control_time, person_control_time
            )
            
            # 判断是否接受AI建议
            if pd.notna(ai_target) and pd.notna(person_target):
                accept_ai_advice = 1 if ai_target == person_target else 0
            else:
                accept_ai_advice = 0
            
            enhanced_record = {
                'user_id': user_id,
                'task_name': 'threat',
                'difficulty': difficulty,
                'ai_level': ai_level,
                'audio_enabled': audio_enabled,
                'data_label': data_label,
                'repetition_count': rep_count,
                'ai_control_time': ai_control_time,
                'person_control_time': person_control_time,
                'total_time': ai_control_time + person_control_time,
                'ai_time_ratio': ai_time_ratio,
                'person_dominance': person_dominance,
                'accept_ai_advice': accept_ai_advice
            }
            
            enhanced_records.append(enhanced_record)
    
    return write_enhanced_records_to_db(enhanced_records, 'threat', trust_conn)

def extract_sensor_features(trust_conn, source_conn):
    """
    为传感器任务提取特征数据
    """
    sensor_records = pd.read_sql_query("""
        SELECT user_id, difficulty, ai_level, audio_enabled, data_label
        FROM trust_data 
        WHERE task_name = 'sensor'
    """, trust_conn)
    
    enhanced_records = []
    
    for _, record in sensor_records.iterrows():
        user_id = record['user_id']
        difficulty = record['difficulty']
        ai_level = record['ai_level']
        audio_enabled = record['audio_enabled']
        data_label = record['data_label']
        
        query = """
        SELECT repetition_count, ai_select_time, person_select_time, 
               ai_target_id, person_target_id
        FROM sensor_task_statistics_plus
        WHERE user_id = ? 
        AND difficulty_level = ? 
        AND ai_level = ? 
        AND audio_enabled = ?
        ORDER BY CAST(repetition_count AS INTEGER)
        """
        
        sensor_data = pd.read_sql_query(query, source_conn, 
                                      params=[user_id, difficulty, ai_level, audio_enabled])
            
        for _, sensor_row in sensor_data.iterrows():
            rep_count = sensor_row['repetition_count']
            ai_select_time = sensor_row['ai_select_time']
            person_select_time = sensor_row['person_select_time']
            ai_target = sensor_row['ai_target_id']
            person_target = sensor_row['person_target_id']
            
            # 计算控制时间（从毫秒转换为秒）
            ai_control_time = float(ai_select_time) / 1000.0 if pd.notna(ai_select_time) else 0.0
            if pd.notna(person_select_time) and pd.notna(ai_select_time):
                person_control_time = (float(person_select_time) - float(ai_select_time)) / 1000.0
            else:
                person_control_time = 0.0
            
            # 计算特征
            ai_time_ratio, person_dominance = calculate_common_features(
                ai_control_time, person_control_time
            )
            
            # 判断是否接受AI建议
            if pd.notna(ai_target) and pd.notna(person_target):
                accept_ai_advice = 1 if ai_target == person_target else 0
            else:
                accept_ai_advice = 0
            
            enhanced_record = {
                'user_id': user_id,
                'task_name': 'sensor',
                'difficulty': difficulty,
                'ai_level': ai_level,
                'audio_enabled': audio_enabled,
                'data_label': data_label,
                'repetition_count': rep_count,
                'ai_control_time': ai_control_time,
                'person_control_time': person_control_time,
                'total_time': ai_control_time + person_control_time,
                'ai_time_ratio': ai_time_ratio,
                'person_dominance': person_dominance,
                'accept_ai_advice': accept_ai_advice
            }
            
            enhanced_records.append(enhanced_record)
    
    return write_enhanced_records_to_db(enhanced_records, 'sensor', trust_conn)


def build_trust_data():
    """
    构建trust_data数据库，包含标签数据和传感器特征
    """
    # 连接到源数据库
    OUTPUT_DIR.mkdir(exist_ok=True)
    source_conn = sqlite3.connect(ALL_DATA_DB)
    
    # 读取questionnaire_statistics表的数据
    query = """
    SELECT 
        user_id,
        task_name,
        difficulty_level as difficulty,
        ai_level,
        audio_enabled,
        q6_score as data_label
    FROM questionnaire_statistics
    """
    
    df = pd.read_sql_query(query, source_conn)
    
    # 创建trust_data数据库
    trust_conn = sqlite3.connect(VALID_DATA_DB)
    
    # 先删除旧表（如果存在）
    trust_conn.execute("DROP TABLE IF EXISTS trust_data")
    
    # 创建包含所有字段的表结构
    create_table_sql = """
    CREATE TABLE trust_data (
        user_id TEXT,
        task_name TEXT,
        difficulty TEXT,
        ai_level TEXT,
        audio_enabled TEXT,
        data_label INTEGER,
        repetition_count INTEGER,
        ai_control_time REAL,
        person_control_time REAL,
        total_time REAL,
        ai_time_ratio REAL,
        person_dominance REAL,
        accept_ai_advice INTEGER
    )
    """
    trust_conn.execute(create_table_sql)
    
    # 为所有记录添加默认的传感器特征字段值
    df['repetition_count'] = None
    df['ai_control_time'] = None
    df['person_control_time'] = None
    df['total_time'] = None
    df['ai_time_ratio'] = None
    df['person_dominance'] = None
    df['accept_ai_advice'] = None
    
    # 将基础数据写入表
    df.to_sql('trust_data', trust_conn, if_exists='append', index=False)
    
    # 创建索引以提高查询性能
    trust_conn.execute('CREATE INDEX IF NOT EXISTS idx_user_id ON trust_data(user_id)')
    trust_conn.execute('CREATE INDEX IF NOT EXISTS idx_task_name ON trust_data(task_name)')
    trust_conn.execute('CREATE INDEX IF NOT EXISTS idx_difficulty ON trust_data(difficulty)')
    trust_conn.execute('CREATE INDEX IF NOT EXISTS idx_ai_level ON trust_data(ai_level)')
    trust_conn.execute('CREATE INDEX IF NOT EXISTS idx_audio_enabled ON trust_data(audio_enabled)')
    trust_conn.execute('CREATE INDEX IF NOT EXISTS idx_data_label ON trust_data(data_label)')
    
    # 提取各任务特征
    sensor_count = extract_sensor_features(trust_conn, source_conn)
    threat_count = extract_threat_features(trust_conn, source_conn)
    platform_count = extract_platform_features(trust_conn, source_conn)
    weapon_count = extract_weapon_features(trust_conn, source_conn)
    
    print("valid_data trust_data build completed")
    print(f"sensor: {sensor_count}")
    print(f"threat: {threat_count}")
    print(f"platform: {platform_count}")
    print(f"weapon: {weapon_count}")
    
    # 关闭连接
    source_conn.close()
    trust_conn.close()
    
    return True

if __name__ == "__main__":
    print("\n" + "="*50)
    
    # 构建trust_data数据库
    build_trust_data()
    
    print("\n" + "="*50)
    
