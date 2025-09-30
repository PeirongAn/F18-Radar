#!/usr/bin/env python3
"""
测试场景生成逻辑
"""

import json
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

if __name__ == "__main__":
    print("场景生成测试")
    print("=" * 50)
    
    # 加载配置
    config = load_config()
    manual_scenarios, ai_scenarios = generate_scenarios(config)
    
    print(f"Manual 场景总数: {len(manual_scenarios)}")
    print("Manual 场景详情:")
    for i, scenario in enumerate(manual_scenarios):
        print(f"  {i+1}. difficulty={scenario['difficulty_name']}, audio={scenario['audio_enabled']}")
    
    print(f"\nAI 场景总数: {len(ai_scenarios)}")
    print("AI 场景详情:")
    for i, scenario in enumerate(ai_scenarios):
        print(f"  {i+1}. level={scenario['ai_level_name']}, difficulty={scenario['difficulty_name']}, audio={scenario['audio_enabled']}")
    
    print(f"\n每个场景重复 10 次 (repetition_count: 1-10)")
    print(f"Manual 数据将需要 task_id: 43-{42 + len(manual_scenarios) * 10} (共 {len(manual_scenarios) * 10} 条记录)")
    print(f"AI 数据将需要 task_id: 208-{207 + len(ai_scenarios) * 10} (共 {len(ai_scenarios) * 10} 条记录)")
    
    # 检查manual数据是否能放入43-82范围
    if len(manual_scenarios) * 10 <= (82 - 43 + 1):
        print(f"\n✓ Manual数据可以完全放入43-82范围 (需要{len(manual_scenarios) * 10}个位置，可用{82-43+1}个位置)")
    else:
        print(f"\n✗ Manual数据超出43-82范围 (需要{len(manual_scenarios) * 10}个位置，只有{82-43+1}个可用位置)")



