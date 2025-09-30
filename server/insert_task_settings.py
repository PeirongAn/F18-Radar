#!/usr/bin/env python3
"""
向 task_settings 表插入测试数据的脚本
按照 _initialize_new_progress 方法中的顺序生成数据
"""

import sqlite3
import json
from datetime import datetime, timedelta
import os
import sys

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def load_config():
    """加载配置文件"""
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'public', 'agent_level.json')
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def generate_scenarios(config):
    """
    根据配置生成场景，模拟 _initialize_new_progress 方法
    返回 (manual_scenarios, ai_scenarios)
    """
    all_levels = config.get('levels', [])
    game_settings = config.get('game_settings', {})
    all_difficulties = game_settings.get('difficulty_levels', {})
    
    # 从配置文件中获取执行顺序
    execution_order = game_settings.get('execution_order', {})
    preferred_difficulty_order = execution_order.get('difficulty_order', ['high', 'low'])
    preferred_level_order = execution_order.get('level_order', ['L0', 'L1', 'L2'])
    audio_options = execution_order.get('audio_options', [True, False])
    
    # 创建按指定顺序排列的level列表
    ordered_levels = []
    for level_name in preferred_level_order:
        for level_conf in all_levels:
            if level_conf.get('level') == level_name:
                ordered_levels.append(level_conf)
                break
    
    difficulties = []
    for diff_name in preferred_difficulty_order:
        if diff_name in all_difficulties:
            diff_conf = all_difficulties[diff_name]
            diff_conf['difficulty_name'] = diff_name  # 确保配置中包含难度名称
            difficulties.append(diff_conf)

    # AI模式场景
    ai_scenarios = []
    for diff_conf in difficulties:
        for level_conf in ordered_levels:
            for audio in audio_options:
                ai_scenarios.append({
                    "is_ai_active": True, 
                    "audio_enabled": audio,
                    "ai_level_name": level_conf['level'], 
                    "ai_level_config": level_conf,
                    "difficulty_name": diff_conf['difficulty_name'], 
                    "difficulty_config": diff_conf
                })
    
    # 手动模式场景
    manual_scenarios = []
    for diff_conf in difficulties: 
        for audio in audio_options:
            manual_scenarios.append({
                "is_ai_active": False, 
                "audio_enabled": audio,
                "ai_level_name": None, 
                "ai_level_config": None,
                "difficulty_name": diff_conf['difficulty_name'], 
                "difficulty_config": diff_conf
            })
    
    return manual_scenarios, ai_scenarios

def delete_previous_data():
    """删除之前插入的数据 (task_id >= 208)"""
    # 数据库路径
    db_path = os.path.join(os.path.dirname(__file__), 'data', 'radar_operations.db')
    
    if not os.path.exists(db_path):
        print(f"数据库文件不存在: {db_path}")
        return
    
    # 连接数据库
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 先查询要删除的记录数
        cursor.execute("SELECT COUNT(*) FROM task_settings WHERE task_id >= 208")
        count_before = cursor.fetchone()[0]
        print(f"准备删除 {count_before} 条 task_id >= 208 的记录")
        
        if count_before > 0:
            # 删除数据
            cursor.execute("DELETE FROM task_settings WHERE task_id >= 208")
            conn.commit()
            
            # 验证删除结果
            cursor.execute("SELECT COUNT(*) FROM task_settings WHERE task_id >= 208")
            count_after = cursor.fetchone()[0]
            print(f"删除完成，剩余 {count_after} 条记录")
        else:
            print("没有需要删除的记录")
            
    except Exception as e:
        print(f"删除数据时发生错误: {e}")
        conn.rollback()
        
    finally:
        conn.close()

def insert_manual_scenarios_43_82():
    """在task_id 43-82范围插入manual场景数据"""
    # 数据库路径
    db_path = os.path.join(os.path.dirname(__file__), 'data', 'radar_operations.db')
    
    if not os.path.exists(db_path):
        print(f"数据库文件不存在: {db_path}")
        return
    
    # 加载配置
    config = load_config()
    manual_scenarios, ai_scenarios = generate_scenarios(config)
    
    # 检查task_id范围是否足够
    total_manual_records = len(manual_scenarios) * 10
    if total_manual_records > (82 - 43 + 1):
        print(f"警告：manual数据记录数({total_manual_records})超过了可用的task_id范围(43-82)")
        return
    
    print(f"将在task_id 43-82范围插入 {len(manual_scenarios)} 个manual场景的数据")
    
    # 连接数据库
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 起始 task_id (43开始)
        task_id_counter = 43
        
        # 基础时间戳
        base_timestamp = datetime.now()
        
        # 插入manual场景数据
        print("\n开始插入Manual场景数据 (task_id: 43-82)...")
        for scenario_idx, scenario in enumerate(manual_scenarios):
            # repetition_count 从1到10循环
            for repetition in range(1, 11):
                if task_id_counter > 82:
                    print(f"达到task_id上限82，停止插入")
                    break
                    
                # 计算时间戳
                execution_timestamp = base_timestamp + timedelta(minutes=task_id_counter - 43)
                
                # 插入数据
                cursor.execute("""
                    INSERT OR REPLACE INTO task_settings (
                        task_id, user_id, event_owner, execution_timestamp, repetition_count,
                        is_ai_active, ai_level_config, difficulty_config, audio_enabled,
                        ai_level_name, difficulty_name
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    task_id_counter,
                    "jianglu",
                    "manual",
                    execution_timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    repetition,
                    scenario['is_ai_active'],
                    json.dumps(scenario['ai_level_config']) if scenario['ai_level_config'] else None,
                    json.dumps(scenario['difficulty_config']),
                    scenario['audio_enabled'],
                    scenario['ai_level_name'],
                    scenario['difficulty_name']
                ))
                
                print(f"插入Manual记录: task_id={task_id_counter}, difficulty={scenario['difficulty_name']}, audio={scenario['audio_enabled']}, repetition={repetition}")
                task_id_counter += 1
        
        # 提交事务
        conn.commit()
        print(f"\nManual数据插入完成！总共插入了 {task_id_counter - 43} 条记录")
        print(f"task_id 范围: 43 - {task_id_counter - 1}")
        
    except Exception as e:
        print(f"插入Manual数据时发生错误: {e}")
        conn.rollback()
        
    finally:
        conn.close()

def insert_ai_scenarios_from_208():
    """从task_id 208开始插入AI场景数据"""
    # 数据库路径
    db_path = os.path.join(os.path.dirname(__file__), 'data', 'radar_operations.db')
    
    if not os.path.exists(db_path):
        print(f"数据库文件不存在: {db_path}")
        return
    
    # 加载配置
    config = load_config()
    manual_scenarios, ai_scenarios = generate_scenarios(config)
    
    print(f"将从task_id 208开始插入 {len(ai_scenarios)} 个AI场景的数据")
    
    # 连接数据库
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 起始 task_id (208开始)
        task_id_counter = 208
        
        # 基础时间戳
        base_timestamp = datetime.now()
        
        # 插入AI场景数据
        print("\n开始插入AI场景数据 (task_id >= 208)...")
        for scenario_idx, scenario in enumerate(ai_scenarios):
            # repetition_count 从1到10循环
            for repetition in range(1, 11):
                # 计算时间戳
                execution_timestamp = base_timestamp + timedelta(minutes=task_id_counter - 208)
                
                # 插入数据
                cursor.execute("""
                    INSERT OR REPLACE INTO task_settings (
                        task_id, user_id, event_owner, execution_timestamp, repetition_count,
                        is_ai_active, ai_level_config, difficulty_config, audio_enabled,
                        ai_level_name, difficulty_name
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    task_id_counter,
                    "jianglu",
                    "AI",
                    execution_timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    repetition,
                    scenario['is_ai_active'],
                    json.dumps(scenario['ai_level_config']) if scenario['ai_level_config'] else None,
                    json.dumps(scenario['difficulty_config']),
                    scenario['audio_enabled'],
                    scenario['ai_level_name'],
                    scenario['difficulty_name']
                ))
                
                print(f"插入AI记录: task_id={task_id_counter}, level={scenario['ai_level_name']}, difficulty={scenario['difficulty_name']}, audio={scenario['audio_enabled']}, repetition={repetition}")
                task_id_counter += 1
        
        # 提交事务
        conn.commit()
        print(f"\nAI数据插入完成！总共插入了 {task_id_counter - 208} 条记录")
        print(f"task_id 范围: 208 - {task_id_counter - 1}")
        
        # 验证插入的数据
        cursor.execute("SELECT COUNT(*) FROM task_settings WHERE task_id >= 208")
        count = cursor.fetchone()[0]
        print(f"验证：数据库中 task_id >= 208 的记录总数: {count}")
        
    except Exception as e:
        print(f"插入AI数据时发生错误: {e}")
        conn.rollback()
        
    finally:
        conn.close()

def show_scenario_info():
    """显示将要生成的场景信息"""
    config = load_config()
    manual_scenarios, ai_scenarios = generate_scenarios(config)
    
    print("=== 场景生成信息 ===")
    print(f"Manual 场景总数: {len(manual_scenarios)}")
    print("Manual 场景详情:")
    for i, scenario in enumerate(manual_scenarios):
        print(f"  {i+1}. difficulty={scenario['difficulty_name']}, audio={scenario['audio_enabled']}")
    
    print(f"\nAI 场景总数: {len(ai_scenarios)}")
    print("AI 场景详情:")
    for i, scenario in enumerate(ai_scenarios):
        print(f"  {i+1}. level={scenario['ai_level_name']}, difficulty={scenario['difficulty_name']}, audio={scenario['audio_enabled']}")
    
    print(f"\n每个场景重复 10 次 (repetition_count: 1-10)")
    print(f"Manual 数据将插入到 task_id: 43-82 (共 {len(manual_scenarios) * 10} 条记录)")
    print(f"AI 数据将插入到 task_id: 208+ (共 {len(ai_scenarios) * 10} 条记录)")

if __name__ == "__main__":
    print("雷达系统 task_settings 数据插入脚本")
    print("=" * 60)
    
    # 显示场景信息
    show_scenario_info()
    
    # 第一步：删除现有的task_id >= 208的数据
    print("\n第一步：删除现有数据")
    delete_response = input("是否删除 task_id >= 208 的现有数据？(y/n): ")
    if delete_response.lower() in ['y', 'yes', '是']:
        delete_previous_data()
    
    # 第二步：插入manual数据到43-82
    print("\n第二步：插入Manual数据")
    manual_response = input("是否在 task_id 43-82 范围插入Manual数据？(y/n): ")
    if manual_response.lower() in ['y', 'yes', '是']:
        insert_manual_scenarios_43_82()
    
    # 第三步：插入AI数据从208开始
    print("\n第三步：插入AI数据")
    ai_response = input("是否从 task_id 208 开始插入AI数据？(y/n): ")
    if ai_response.lower() in ['y', 'yes', '是']:
        insert_ai_scenarios_from_208()
    
    print("\n操作完成！")
