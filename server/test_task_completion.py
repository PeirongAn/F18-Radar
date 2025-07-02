#!/usr/bin/env python3
"""
测试任务完成状态管理功能
"""

import json
import sys
import os

# 添加server目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from managers.database_manager import db_manager
from managers.task_manager import TaskScenarioManager

# 模拟配置
TEST_CONFIG = {
    "current_level": "L2",
    "levels": [
        {
            "level": "L0",
            "desc": "测试低级智能体",
            "threat_select_delay_ms": 1000,
            "tdc_select_delay_ms": 1000,
            "decision_probabilities": [0.3, 0.5]
        },
        {
            "level": "L1", 
            "desc": "测试中级智能体",
            "threat_select_delay_ms": 500,
            "tdc_select_delay_ms": 500,
            "decision_probabilities": [0.7, 0.9]
        }
    ],
    "game_settings": {
        "current_difficulty": "high",
        "audio_enabled": True,
        "max_repetitions": 2,
        "practice_repetitions": 1,
        "difficulty_levels": {
            "high": {
                "name": "高",
                "threat_count": 5,
                "target_count": 5
            },
            "low": {
                "name": "低", 
                "threat_count": 3,
                "target_count": 3
            }
        },
        "execution_order": {
            "difficulty_order": ["high", "low"],
            "level_order": ["L0", "L1"],
            "audio_options": [True, False]
        }
    }
}

def test_completion_status():
    """测试任务完成状态功能"""
    print("=== 测试任务完成状态管理功能 ===")
    
    # 初始化数据库
    db_manager.initialize_database()
    
    test_user_id = "test_user_completion"
    test_task_type = "tdc"
    
    # 清理测试数据
    print(f"\n1. 清理测试用户 {test_user_id} 的数据...")
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_progress WHERE user_id = ?", (test_user_id,))
        conn.commit()
    
    # 创建任务管理器（正式模式）
    print(f"2. 创建任务管理器 (正式模式)...")
    task_manager = TaskScenarioManager(TEST_CONFIG, test_user_id, test_task_type, is_practice=False)
    
    # 获取第一个任务
    print(f"3. 获取第一个任务...")
    scenario1 = task_manager.get_next_task_parameters(True)  # AI模式
    if scenario1:
        print(f"   - 获得场景: 难度={scenario1.get('difficulty_name')}, AI={scenario1.get('ai_level_name')}")
        print(f"   - 重复信息: {scenario1.get('repetition_info')}")
    
    # 检查数据库中的状态
    print(f"4. 检查数据库中的完成状态...")
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT is_completed FROM user_progress WHERE user_id = ? AND task_type = ?", 
                      (test_user_id, test_task_type))
        result = cursor.fetchone()
        if result:
            is_completed = result[0]
            print(f"   - 数据库中 is_completed = {is_completed} ({'任务已完成' if is_completed else '任务未完成/进行中'})")
        else:
            print("   - 数据库中未找到记录")
    
    # 测试重复调用（检查状态判断）
    print(f"4.5. 测试重复调用和状态检查...")
    scenario2 = task_manager.get_next_task_parameters(True)  # 同样的AI模式
    if scenario2:
        rep_info = scenario2.get('repetition_info', {})
        previous_completed = rep_info.get('previous_task_completed', 'unknown')
        print(f"   - 重复调用: 当前次数={rep_info.get('current')}, 总次数={rep_info.get('total')}")
        print(f"   - 上一个任务状态: {previous_completed}")
    
    # 模拟任务重复次数达到上限
    print(f"4.6. 模拟任务重复完成...")
    scenario3 = task_manager.get_next_task_parameters(True)  # 第3次调用，应该获取新场景
    if scenario3:
        rep_info = scenario3.get('repetition_info', {})
        previous_completed = rep_info.get('previous_task_completed', 'unknown')
        print(f"   - 新场景: 难度={scenario3.get('difficulty_name')}, 重复={rep_info.get('current')}/{rep_info.get('total')}")
        print(f"   - 上一个任务状态: {previous_completed}")
    
    # 再次检查状态
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT is_completed FROM user_progress WHERE user_id = ? AND task_type = ?", 
                      (test_user_id, test_task_type))
        result = cursor.fetchone()
        if result:
            is_completed = result[0]
            print(f"   - 状态检查: is_completed = {is_completed} ({'任务已完成' if is_completed else '任务未完成/进行中'})")
    
    # 测试状态检查逻辑
    print(f"4.7. 测试状态检查对重复计数的影响...")
    # 手动设置一个未完成状态来测试
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE user_progress SET is_completed = ? WHERE user_id = ? AND task_type = ?", 
                      (False, test_user_id, test_task_type))  # 设置为未完成/进行中
        conn.commit()
    
    # 创建新的任务管理器实例来测试状态检查
    test_task_manager = TaskScenarioManager(TEST_CONFIG, test_user_id, test_task_type, is_practice=False)
    scenario4 = test_task_manager.get_next_task_parameters(True)
    if scenario4:
        rep_info = scenario4.get('repetition_info', {})
        previous_completed = rep_info.get('previous_task_completed', 'unknown')
        print(f"   - 状态检查测试: 重复={rep_info.get('current')}, 上一个任务状态={previous_completed}")
    
    # 手动标记任务完成
    print(f"5. 手动标记任务完成...")
    task_manager.mark_task_completed()
    
    # 再次检查状态
    print(f"6. 再次检查完成状态...")
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT is_completed FROM user_progress WHERE user_id = ? AND task_type = ?", 
                      (test_user_id, test_task_type))
        result = cursor.fetchone()
        if result:
            is_completed = result[0]
            print(f"   - 数据库中 is_completed = {is_completed} ({'任务已完成' if is_completed else '任务未完成/进行中'})")
    
    # 测试练习模式
    print(f"\n7. 测试练习模式...")
    practice_task_manager = TaskScenarioManager(TEST_CONFIG, test_user_id, test_task_type, is_practice=True)
    scenario_practice = practice_task_manager.get_next_task_parameters(True)
    if scenario_practice:
        print(f"   - 练习模式场景获取成功")
    
    # 清理练习模式缓存
    print(f"8. 清理练习模式缓存...")
    TaskScenarioManager.clear_practice_cache(test_user_id, test_task_type)
    print(f"   - 缓存已清理")
    
    # 清理测试数据
    print(f"\n9. 清理测试数据...")
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_progress WHERE user_id = ?", (test_user_id,))
        conn.commit()
    
    print("\n=== 测试完成 ===")

def check_database_schema():
    """检查数据库表结构"""
    print("=== 检查数据库表结构 ===")
    
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # 检查 user_progress 表结构
            cursor.execute("PRAGMA table_info(user_progress)")
            columns = cursor.fetchall()
            
            print("user_progress 表结构:")
            for col in columns:
                print(f"  - {col[1]} ({col[2]}) {'NOT NULL' if col[3] else ''} {'DEFAULT ' + str(col[4]) if col[4] else ''}")
            
            # 检查是否有 is_completed 字段
            column_names = [col[1] for col in columns]
            if 'is_completed' in column_names:
                print("✅ is_completed 字段存在")
            else:
                print("❌ is_completed 字段不存在")
                
    except Exception as e:
        print(f"检查数据库结构时出错: {e}")

if __name__ == "__main__":
    # 检查数据库结构
    check_database_schema()
    
    # 运行测试
    test_completion_status() 