import asyncio
import websockets
import json
import numpy as np
import time
import sqlite3
import os
from datetime import datetime
import queue
import threading
from contextlib import contextmanager
import atexit
import random

# 全局配置
CONFIG = {}
# 废除全局任务场景管理器
# task_manager = None

# 加载配置文件
def load_config():
    global CONFIG
    script_dir = os.path.dirname(__file__)
    config_path = os.path.join(script_dir, '../public/agent_level.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            CONFIG = json.load(f)
        print("Configuration loaded successfully.")
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error loading configuration: {e}. Using default settings.")
        # 如果加载失败，使用默认配置
        CONFIG = {
            "game_settings": {
                "current_difficulty": "low",
                "audio_enabled": True,
                "difficulty_levels": {
                    "low": {"threat_count": 4, "target_count": 5},
                    "high": {"threat_count": 8, "target_count": 10}
                }
            }
        }

# 在程序启动时加载配置
load_config()

# ---- 新增：数据库写入队列 ----
db_writer_queue = queue.Queue()

def db_worker():
    """在后台线程中同步处理所有数据库写入操作。"""
    conn = sqlite3.connect('radar_operations.db', check_same_thread=False)
    # 设置WAL模式，可以提高并发性能，允许多个读和一个写同时进行
    conn.execute('PRAGMA journal_mode=WAL;')
    print("🗃️ DB worker thread started, connection in WAL mode.")
    
    while True:
        try:
            # 阻塞直到从队列中获取到任务
            # 设置一个超时，以便线程可以优雅地退出（如果需要）
            sql, params = db_writer_queue.get(timeout=1)
            
            # None作为一个哨兵值，用于终止线程
            if sql is None:
                print("🗃️ DB worker thread received shutdown signal.")
                break
                
            conn.execute(sql, params)
            conn.commit()
            
        except queue.Empty:
            # 队列为空时超时，继续循环
            continue
        except Exception as e:
            print(f"❌ [DB Worker Error] Failed to execute DB operation: {e}")
            # 在这里可以添加更复杂的错误处理逻辑，比如重试或记录到文件
            
    conn.close()
    print("🗃️ DB worker thread stopped and connection closed.")

# 在主线程中启动数据库工作线程
db_thread = threading.Thread(target=db_worker, daemon=True)
db_thread.start()

# ---- 新增：程序退出时，向队列发送停止信号 ----
def cleanup_db_thread():
    print("Requesting DB worker thread to shut down...")
    db_writer_queue.put((None, None))
    db_thread.join(timeout=5) # 等待线程结束
    print("DB worker thread has been shut down.")

atexit.register(cleanup_db_thread)

# ---- 重新设计的：持久化任务场景管理器 ----
class TaskScenarioManager:
    """管理与数据库绑定的、持久化的用户任务场景。"""
    def __init__(self, config, user_id, task_type, is_practice=False):
        self.config = config
        self.user_id = user_id
        self.task_type = task_type
        self.is_practice = is_practice # 由外部传入
        
        # 从配置中读取练习模式设置
        game_settings = self.config.get('game_settings', {})
        practice_reps = game_settings.get('practice_repetitions', 3)
        formal_reps = game_settings.get('max_repetitions', 1)
        self.max_repetitions = practice_reps if self.is_practice else formal_reps
        
        # 内部状态
        self.ai_queue = []
        self.manual_queue = []
        self.active_queue = None
        self.current_scenario = None
        self.repetition_counter = 0

        if not self._load_from_db():
            self._initialize_new_progress()
            self._save_to_db()

    def _load_from_db(self):
        """尝试从数据库加载用户进度。"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT current_scenario_json, repetition_counter, ai_queue_json, manual_queue_json FROM user_progress WHERE user_id = ? AND task_type = ?",
                    (self.user_id, self.task_type)
                )
                row = cursor.fetchone()
                if row:
                    print(f"✅ [Task Manager] Found existing progress for user '{self.user_id}' and task '{self.task_type}'.")
                    self.current_scenario = json.loads(row[0]) if row[0] else None
                    self.repetition_counter = row[1] or 0
                    self.ai_queue = json.loads(row[2]) if row[2] else []
                    self.manual_queue = json.loads(row[3]) if row[3] else []
                    return True
        except Exception as e:
            print(f"❌ Error loading progress from DB: {e}")
        return False

    def _save_to_db(self):
        """将当前状态的写入操作放入队列，但练习模式除外。"""
        if self.is_practice:
            print("💾 [Task Manager] Practice mode: Skipping DB save.")
            return
        
        sql = """
            INSERT OR REPLACE INTO user_progress 
            (user_id, task_type, current_scenario_json, repetition_counter, ai_queue_json, manual_queue_json, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """
        params = (
            self.user_id,
            self.task_type,
            json.dumps(self.current_scenario) if self.current_scenario else None,
            self.repetition_counter,
            json.dumps(self.ai_queue),
            json.dumps(self.manual_queue)
        )
        db_writer_queue.put((sql, params))
        print(f"💾 [Task Manager] Progress save queued for user '{self.user_id}', task '{self.task_type}'.")

    def _initialize_new_progress(self):
        """为新用户或新任务生成全新的队列和状态。"""
        print(f"✨ [Task Manager] Initializing new progress for user '{self.user_id}', task '{self.task_type}'.")
        all_levels = self.config.get('levels', [])
        game_settings = self.config.get('game_settings', {})
        all_difficulties = game_settings.get('difficulty_levels', {})
        audio_options = [True, False]

        # AI模式
        ai_scenarios = []
        for level_conf in all_levels:
            for diff_name, diff_conf in all_difficulties.items():
                for audio in audio_options:
                    ai_scenarios.append({
                        "is_ai_active": True, "audio_enabled": audio,
                        "ai_level_name": level_conf['level'], "ai_level_config": level_conf,
                        "difficulty_name": diff_name, "difficulty_config": diff_conf
                    })
        # 为每个AI场景添加类型编号
        total_ai_scenarios = len(ai_scenarios)
        for i, scenario in enumerate(ai_scenarios):
            scenario['scenario_info'] = {'index': i + 1, 'total': total_ai_scenarios}
        self.ai_queue = ai_scenarios

        # 手动模式
        manual_scenarios = []
        for diff_name, diff_conf in all_difficulties.items():
            for audio in audio_options:
                manual_scenarios.append({
                    "is_ai_active": False, "audio_enabled": audio,
                    "ai_level_name": None, "ai_level_config": None,
                    "difficulty_name": diff_name, "difficulty_config": diff_conf
                })
        # 为每个手动场景添加类型编号
        total_manual_scenarios = len(manual_scenarios)
        for i, scenario in enumerate(manual_scenarios):
            scenario['scenario_info'] = {'index': i + 1, 'total': total_manual_scenarios}
        self.manual_queue = manual_scenarios
        
        self.current_scenario = None
        self.repetition_counter = 0

    def are_all_scenarios_completed(self):
        """检查此任务类型的所有场景（AI和手动）是否都已完成。"""
        return not self.ai_queue and not self.manual_queue

    def get_next_task_parameters(self, is_ai_active_request):
        """获取下一个场景参数，并自动保存进度。"""
        new_queue = self.ai_queue if is_ai_active_request else self.manual_queue
        
        # 检查是否切换了模式 (AI vs Manual)
        queue_switched = False
        if self.active_queue is not None: # 避免首次调用时被误判为切换
            current_queue_name = 'ai_queue' if self.active_queue is self.ai_queue else 'manual_queue'
            new_queue_name = 'ai_queue' if new_queue is self.ai_queue else 'manual_queue'
            if current_queue_name != new_queue_name:
                queue_switched = True

        if queue_switched:
            self.active_queue = new_queue
            self.current_scenario = None
            self.repetition_counter = 0
            print(f"🔄 [Task Manager - {self.task_type}] Switched to {'AI' if is_ai_active_request else 'Manual'} queue.")

        self.active_queue = new_queue

        if self.current_scenario and self.repetition_counter < self.max_repetitions:
            self.repetition_counter += 1
        else:
            if self.active_queue:
                self.current_scenario = self.active_queue.pop(0)
                self.repetition_counter = 1
                print(f"🆕 [Task Manager - {self.task_type}] New scenario started: diff='{self.current_scenario['difficulty_name']}', ai='{self.current_scenario.get('ai_level_name') or 'N/A'}'")
            else:
                print(f"🎉 [Task Manager - {self.task_type}] Active queue empty.")
                self.current_scenario = None
                self.repetition_counter = 0

        # 如果当前场景为空（因为队列已空），检查是否所有任务都完成了
        if not self.current_scenario:
            self._save_to_db()
            if self.are_all_scenarios_completed():
                return "ALL_COMPLETED"
            return None
        
        repetition_info = {
            "current": self.repetition_counter,
            "total": self.max_repetitions,
            "is_practice": self.is_practice
        }
        # 将类型编号添加到repetition_info中
        if self.current_scenario.get("scenario_info"):
            scenario_info = self.current_scenario["scenario_info"]
            repetition_info["scenario_index"] = scenario_info.get("index")
            repetition_info["scenario_total"] = scenario_info.get("total")

        self.current_scenario['repetition_info'] = repetition_info
        if self.current_scenario:
            self._save_to_db()
        return self.current_scenario

# 用于存储目标信息的全局变量
unknown_targets = []
own_heading = 278  # 当前航向 (度)
radar_azimuth = 0  # 固定的雷达方位角值
radar_range = 80   # 雷达范围 (海里)
scan_angle = 60    # 扫描角度 (度)

# 任务ID计数器
task_counter = 0

# --- 威胁评估权重配置 ---
# 您可以调整这些权重来改变距离和朝向在威胁判断中的重要性
DISTANCE_WEIGHT = 0.6  # 距离权重
HEADING_WEIGHT = 0.4   # 朝向权重

# 当前会话状态
current_session = {
    'task_id': None,
    'stage': 'init',  # 'init', 'antenna_adjustment', 'target_identification'
    'target_elevation': None,
    'operations': []
}

# 修改：get_db_connection 现在只用于读取操作
@contextmanager
def get_db_connection():
    """
    提供一个用于 **只读** 操作的数据库连接。
    写入操作必须通过 db_writer_queue 进行。
    """
    conn = None
    try:
        # 对于只读操作，可以创建临时连接
        conn = sqlite3.connect('radar_operations.db', check_same_thread=False)
        conn.execute('PRAGMA journal_mode=WAL;') # 确保读取时也使用WAL模式
        yield conn
    finally:
        if conn:
            conn.close()

# 修改：所有写入函数现在都将任务放入队列
def record_task_settings_to_db(task_id, scenario, user_id, event_owner, session_state):
    """将任务设置的写入操作放入队列。"""
    if session_state.get('is_practice', False):
        print(f"큐에 추가 안함 (연습 모드): record_task_settings for task_id {task_id}")
        return
        
    sql = """
        INSERT INTO task_settings (
            task_id, user_id, event_owner, repetition_count, is_ai_active, 
            ai_level_config, difficulty_config, audio_enabled, ai_level_name, difficulty_name
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    params = (
        task_id,
        user_id,
        event_owner,
        scenario['repetition_info']['current'],
        scenario['is_ai_active'],
        json.dumps(scenario.get('ai_level_config')),
        json.dumps(scenario['difficulty_config']),
        scenario['audio_enabled'],
        scenario.get('ai_level_name'),
        scenario['difficulty_name']
    )
    db_writer_queue.put((sql, params))
    print(f"큐에 추가: record_task_settings for task_id {task_id}")


def record_operation_to_db(operation, session_state):
    """将单个操作的写入操作放入队列。"""
    if session_state.get('is_practice', False):
        print(f"record_operation {operation.get('operationType')}")
        return

    sql = """
        INSERT INTO user_operations (
            task_id, operation_type, timestamp, receive_timestamp, is_active, 
            parameters, user_id, event_owner
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    parameters_json = json.dumps(operation.get('parameters', {}))
    params = (
        operation.get('task_id'),
        operation.get('operationType'),
        operation.get('timestamp'),
        operation.get('receive_timestamp'),
        1 if operation.get('isActive', False) else 0,
        parameters_json,
        operation.get('user_id'),
        operation.get('event_owner')
    )
    db_writer_queue.put((sql, params))
    # print(f"큐에 추가: record_operation {operation.get('operationType')}")


def cleanup():
    # 这个函数现在不再需要，因为我们使用 atexit.register
    pass

# 全局数据库连接池实例 - **废除**
# db_pool = ConnectionPool()
# atexit.register(db_pool.close_all)

# 生成新的任务ID
def generate_task_id():
    global task_counter
    task_id = task_counter
    task_counter += 1
    return task_id

# 初始化未知目标数据，引入基于距离和朝向的威胁评估逻辑
def initialize_targets(difficulty_config):
    """根据传入的难度配置初始化目标，并基于威胁评估来决定敌友。"""
    global unknown_targets, scan_angle, radar_range, own_heading
    
    total_targets = difficulty_config.get('target_count', 5)
    num_enemies = 2  # 我们总是将威胁分数最高的2个目标设为敌机

    # 1. 生成所有目标，初始时都视为"未知"
    potential_targets = []
    for i in range(total_targets):
        angle = random.uniform(-scan_angle / 2, scan_angle / 2)
        distance = random.uniform(radar_range * 0.1, radar_range)
        speed = random.uniform(3, 12)  # 速度范围更广
        direction = random.uniform(0, 2 * np.pi) # 初始朝向是完全随机的
        
        potential_targets.append({
            "id": f"target-{i+1}", # 临时ID
            "position": {"x": angle, "y": distance},
            "speed": speed,
            "direction": direction, # 弧度制
            "last_update": time.time() # 新增：记录上次更新时间
        })

    # 2. 对每个"未知"目标进行威胁评估
    evaluated_targets = []
    for target in potential_targets:
        distance = target['position']['y']
        
        # 计算目标航向与朝向我方(原点)的夹角
        # 目标的绝对角度 (0度朝上)
        target_angle_rad = target['position']['x'] * (np.pi / 180)
        # 朝向我方的矢量角度 (从目标指向原点)
        inbound_heading_rad = target_angle_rad + np.pi # 角度反向
        
        # 计算两个航向之间的最小夹角 (0-180度)
        angle_diff_rad = abs((target['direction'] - inbound_heading_rad + np.pi) % (2 * np.pi) - np.pi)
        angle_diff_deg = np.rad2deg(angle_diff_rad)

        # a. 计算距离分数 (0-1)
        distance_score = 1 - (distance / radar_range)
        
        # b. 计算朝向分数 (0-1)
        heading_score = 1 - (angle_diff_deg / 180)
        
        # c. 计算加权总分
        threat_score = (distance_score * DISTANCE_WEIGHT) + (heading_score * HEADING_WEIGHT)
        
        target['threat_score'] = threat_score
        evaluated_targets.append(target)
        
        # --- 新增：为调试打印详细的计算过程 ---
        print(f"  [Threat Eval for {target['id']}]")
        print(f"    - Distance: {distance:.1f}nm -> Score: {distance_score:.2f} (raw)")
        print(f"    - Heading Diff: {angle_diff_deg:.1f}° -> Score: {heading_score:.2f} (raw)")
        print(f"    - Weighted Score: ({distance_score:.2f} * {DISTANCE_WEIGHT}) + ({heading_score:.2f} * {HEADING_WEIGHT}) = {threat_score:.2f}")
        # --- 结束新增 ---
        
    # 3. 根据威胁分数排序，分数最高的为敌机
    evaluated_targets.sort(key=lambda t: t['threat_score'], reverse=True)
    
    # 4. 分配最终的ID和类型
    final_targets = []
    for i, target in enumerate(evaluated_targets):
        if i < num_enemies:
            target['type'] = 'army'
            target['id'] = f"enemy-{i+1}"
        else:
            target['type'] = 'friend'
            target['id'] = f"friend-{i - num_enemies + 1}"
        
        final_targets.append(target)
        
    unknown_targets = final_targets
    
    print(f"已初始化 {len(unknown_targets)} 个未知目标 (Difficulty: {difficulty_config.get('name')})")
    for target in unknown_targets:
        print(f"  -> ID: {target['id']}, Type: {target['type']}, Threat Score: {target['threat_score']:.2f}, "
              f"Pos: ({target['position']['x']:.1f}°, {target['position']['y']:.1f}nm)")

# 获取要发送给前端的数据
def get_radar_data(include_targets=False):
    global unknown_targets, own_heading, radar_azimuth, radar_range, scan_angle
    
    try:
        current_time = time.time()

        # 更新所有目标的位置和朝向
        for target in unknown_targets:
            delta_t = current_time - target.get('last_update', current_time)
            
            # 简单的线性移动模型
            # 将速度从 (海里/秒) 转换为 (雷达距离单位/秒)
            # 假设1度角位移和1海里距离位移在视觉上近似
            speed_x = target['speed'] * np.cos(target['direction']) * 0.1 # 减小横向移动幅度
            speed_y = target['speed'] * np.sin(target['direction']) * 0.1 # 减小纵向移动幅度
            
            target['position']['x'] += speed_x * delta_t
            target['position']['y'] -= speed_y * delta_t # Y轴向下是距离减小
            
            # 随机轻微调整航向，模拟机动
            target['direction'] += random.uniform(-0.05, 0.05)
            
            # 确保航向在 [0, 2*pi] 范围内
            target['direction'] = target['direction'] % (2 * np.pi)

            # --- 新增: 计算并更新相对航向 ---
            # 1. 将我机航向从度转换为弧度
            own_heading_rad = np.deg2rad(own_heading)
            
            # 2. 计算航向差值
            diff_rad = target['direction'] - own_heading_rad
            
            # 3. 归一化到 [-pi, pi]
            if diff_rad > np.pi:
                diff_rad -= 2 * np.pi
            elif diff_rad < -np.pi:
                diff_rad += 2 * np.pi

            # 4. 将结果从弧度转为度，并添加到目标数据中
            target['relative_heading'] = np.rad2deg(diff_rad)
            # --- 结束新增 ---

            target['last_update'] = current_time


        print("【调试】开始生成雷达数据...")
        
        # 从配置中获取音频设置
        audio_enabled = CONFIG.get('game_settings', {}).get('audio_enabled', True)
        
        # 基础数据，不包含目标
        data = {
            "radar_azimuth": float(radar_azimuth),
            "own_heading": float(own_heading),
            "timestamp": time.time(),
            "range": float(radar_range),
            "scanAngle": float(scan_angle),
            "audioEnabled": audio_enabled
        }
        
        # 仅当明确指定要包含目标时，才添加目标数据
        if include_targets:
            print("【调试】请求包含目标数据 - 正在验证格式")
            
            # 手动输出所有目标数据
            print(f"【调试】原始目标数据 (共 {len(unknown_targets)} 个):")
            for i, target in enumerate(unknown_targets):
                print(f"【调试】目标 {i+1}: {target}")
            
            # 验证目标数据格式
            validated_targets = []
            for target in unknown_targets:
                # 确保每个目标都有必要的字段
                try:
                    if ("id" in target and 
                        "position" in target and 
                        isinstance(target["position"], dict) and
                        "x" in target["position"] and 
                        "y" in target["position"]):
                        validated_targets.append(target)
                    else:
                        print(f"【警告】跳过格式不正确的目标: {target}")
                except Exception as e:
                    print(f"【错误】处理目标时出错: {e}")
            
            data["externalTargets"] = validated_targets
            print(f"【调试】添加目标数据到响应, 有效目标数量: {len(validated_targets)}")
            
            if validated_targets:
                print(f"【调试】第一个有效目标示例: {validated_targets[0]}")
                print(f"【调试】validated_targets 类型: {type(validated_targets)}")
            
        print(f"【调试】响应数据包含的键: {list(data.keys())}")
        
        # 打印完整的JSON数据以进行验证
        json_data = json.dumps(data)
        print(f"【调试】生成的JSON数据长度: {len(json_data)}")
        if 'externalTargets' in data:
            print(f"【调试】JSON中externalTargets的内容: {json.dumps(data['externalTargets'])[:100]}...")
        
        return data
    except Exception as e:
        print(f"【错误】生成雷达数据时出错: {e}")
        # 返回一个最小的有效数据结构
        return {
            "radar_azimuth": float(radar_azimuth),
            "own_heading": float(own_heading),
            "timestamp": time.time(),
            "range": float(radar_range),
            "scanAngle": float(scan_angle)
        }

# 检查是否满足发送目标数据的条件
def should_include_targets(message=None):
    global scan_angle, radar_range
    
    print("\n【调试】===== 条件检查开始 =====")
    
    # 如果没有传入消息，使用全局变量
    if message is None:
        print("【调试】使用全局变量进行检查")
        scan_angle_value = scan_angle
        radar_range_value = radar_range
    else:
        print("【调试】使用消息中的参数进行检查")
        scan_angle_value = message.get('scanAngle')
        radar_range_value = message.get('range')
    
    print(f"【调试】当前参数: scan_angle={scan_angle_value} (类型: {type(scan_angle_value)}), radar_range={radar_range_value} (类型: {type(radar_range_value)})")
    
    # 使用更宽松的条件检查
    try:
        scan_angle_float = float(scan_angle_value)
        radar_range_float = float(radar_range_value)
        
        # 计算与设定值的差异百分比
        scan_angle_diff = abs(scan_angle_float - 30) / 30 * 100  # 30是设定值
        range_diff = abs(radar_range_float - 80) / 80 * 100     # 80是设定值
        
        # 允许20%的误差
        scan_angle_condition = scan_angle_diff <= 2
        range_condition = range_diff <= 2
        
        print(f"【调试】参数值: scan_angle={scan_angle_float}, range={radar_range_float}")
        print(f"【调试】差异百分比: scan_angle={scan_angle_diff:.2f}%, range={range_diff:.2f}%")
        print(f"【调试】条件判断: scan_angle条件={scan_angle_condition}, range条件={range_condition}")
        
        result = scan_angle_condition and range_condition
        print(f"【调试】最终结果: {result}")
        
        if result:
            print("【调试】✅ 满足条件，将发送目标数据")
            print("【调试】unknown_targets 长度:", len(unknown_targets))
        else:
            print("【调试】❌ 不满足条件，不发送目标数据")
        
    except (ValueError, TypeError) as e:
        print(f"【错误】条件检查出错: {e}")
        result = False
    
    print("【调试】===== 条件检查结束 =====\n")
    return result

# 生成随机天线高度指令
def generate_antenna_adjustment():
    # 从-3,-2,-1,1,2,3中随机选择一个调整值
    direction = random.choice([-3, -2, -1, 1, 2, 3])
    target_elevation = direction
    
    # 更新当前会话状态
    global current_session
    current_session['target_elevation'] = target_elevation
    current_session['stage'] = 'antenna_adjustment'
    
    return {
        "type": "adjust_antenna",
        "targetElevation": target_elevation,
        "message": f"请将天线高度{'上移' if direction > 0 else '下移'} {abs(target_elevation)}格"
    }

# 处理天线高度调整确认
def handle_antenna_adjustment(message):
    # 获取客户端设置的高度
    try:
        client_elevation = message.get('elevation')
        
        # 检查是否在预期范围内（允许±2°的误差）
        global current_session
        target_elevation = current_session.get('target_elevation')
        
        if target_elevation is None:
            return {
                "type": "settings_validation",
                "status": "error",
                "message": "未找到目标天线高度设置，请重新初始化系统"
            }, False
        
        if abs(client_elevation - target_elevation) <= 0.1:
            # 高度设置正确
            current_session['stage'] = 'target_identification'
            print('【调试】天线高度设置正确，开始发送目标数据')
            return {
                "type": "settings_validation",
                "status": "success",
                "message": "天线高度设置正确，开始发送目标数据"
            }, True
        else:
            # 高度设置不正确
            return {
                "type": "settings_validation",
                "status": "error",
                "message": f"天线高度设置不正确，目标为{target_elevation}°，当前为{client_elevation}°"
            }, False
    except Exception as e:
        print(f"天线调整出错: {e}")
        return {"type": "ERROR", "message": f"处理天线调整时出错: {e}"}

# 生成SA页面威胁数组
SA_ICON_TYPES = [
    'PrimaryAir',
    'SecondaryAir',
    'PrimaryAntiAircraftArtillery',
    'SecondaryAntiAircraftArtillery',
    'PrimaryNaval',
    'SecondaryNaval',
]
SA_LABELS = {
    'PrimaryAir': ['J-11', 'F-16', 'Su-27', 'F-15'],
    'SecondaryAir': ['MiG-29', 'F-5', 'F-7', 'Su-30'],
    'PrimaryAntiAircraftArtillery': ['SA-10', 'HQ-9', 'S-300'],
    'SecondaryAntiAircraftArtillery': ['SA-6', 'HQ-7', 'S-75'],
    'PrimaryNaval': ['052D', '054A', '055', 'Kirov'],
    'SecondaryNaval': ['056', '053H3', 'Frigate', 'Corvette'],
}
def generate_sa_threats(difficulty_config):
    """根据传入的难度配置生成SA威胁。"""
    # 从传入的配置中获取威胁数量
    n = difficulty_config.get('threat_count', 4)

    threats = []
    
    # 方案1：允许重复类型，主要使用Secondary类型，但可以重复生成
    secondary_types = [t for t in SA_ICON_TYPES if t.startswith('Secondary')]
    
    # 如果需要的威胁数量超过Secondary类型数量，允许重复选择
    if n <= len(secondary_types):
        # 如果需要的数量不超过可用类型，正常选择不重复
        chosen_types = random.sample(secondary_types, k=n)
    else:
        # 如果需要更多威胁，允许重复选择类型
        chosen_types = []
        for i in range(n):
            chosen_types.append(random.choice(secondary_types))
    
    
    # 生成威胁
    for i, threat_type in enumerate(chosen_types):
        label = random.choice(SA_LABELS[threat_type])
        threats.append({
            'id': f'{threat_type}-{random.randint(1000,9999)}-{i}', # 添加索引避免ID重复
            'type': threat_type,
            'label': label
        })
    
    print(f"[SA威胁生成] 生成了{len(threats)}个威胁 (Difficulty: {difficulty_config.get('name')})")
    return threats

def generate_sa_emergency(threats):
    # 随机选择事件类型
    event_type = random.choice(['upgrade', 'missile'])
    if event_type == 'upgrade':
        # 随机决定是否进行类型升级 (50%概率升级类型，50%概率保持原类型)
        should_upgrade_type = random.choice([True, False])
        
        if should_upgrade_type:
            # 找到所有secondary威胁并升级为primary
            secondary = [t for t in threats if t['type'].startswith('Secondary')]
            if secondary:
                to_upgrade = random.choice(secondary)
                # 升级为primary
                primary_type = to_upgrade['type'].replace('Secondary', 'Primary')
                to_upgrade['type'] = primary_type
                to_upgrade['label'] = random.choice(SA_LABELS[primary_type])
                print(f"[SA升级] 威胁类型升级: {to_upgrade['id']} -> {primary_type}")
        else:
            # 不升级类型，保持现有威胁，让客户端根据位置判断优先级
            print(f"[SA升级] 威胁未升级类型，客户端将根据位置判断优先级")
        
        return {
            'type': 'SAEmergency',
            'event': 'upgrade',
            'saThreats': threats
        }
    else:
        missile_type = random.choice(['MissileUp', 'MissileDown'])
        return {
            'type': 'SAEmergency',
            'event': 'missile',
            'missileType': missile_type,
            'saThreats': threats
        }

async def auto_send_sa_emergency(websocket, threats, user_id, event_owner, session_state):
    await asyncio.sleep(random.uniform(2, 3))
    emergency_msg = generate_sa_emergency(threats)
    await send_message(websocket, emergency_msg)
    print(f"[自动] 已发送SAEmergency事件: {emergency_msg['event']}")
    # 记录临机事件日志
    try:
        # 只有在非练习模式下才记录数据库
        if not session_state.get('is_practice', False):
            record_operation_to_db({
                'task_id': current_session.get('task_id'),
                'operationType': 'sa_emergency',
                'timestamp': int(time.time() * 1000),
                'isActive': False,
                'parameters': emergency_msg,
                'user_id': user_id,
                'event_owner': event_owner
            }, session_state)
        else:
            print("练习模式，跳过 sa_emergency 数据库记录。")
    except Exception as e:
        print(f"记录SAEmergency日志失败: {e}")

# 修改：handle_client_message
async def handle_client_message(message_str, session_state, websocket=None):
    global radar_range, scan_angle, unknown_targets, current_session
    
    try:
        print("\n===== 接收到客户端消息 =====")
        print(f"原始消息: {message_str}")
        
        message = json.loads(message_str)
        print(f"解析后的消息: {message}")
        
        message_type = message.get('type', '')
        client_event_owner = message.get('event_owner', '')

        if message_type == 'task_start':
            print("消息类型: task_start", message.get('user_id', ''))
            is_ai_active_request = message.get('include_ai', False)
            user_id = message.get('user_id', '')
            event_owner = 'AI' if is_ai_active_request else 'manual'
            is_practice = message.get('is_practice', False) # 从消息获取
            session_state['is_practice'] = is_practice # 存入会话

            if not user_id:
                return [{"type": "error", "message": "user_id is required for task_start"}]
            
            # 将 user_id 保存到全局会话，以便后续操作使用
            current_session['user_id'] = user_id
            
            task_type = 'RADAR_TARGETING'
            
            # 1. 创建或加载与用户绑定的持久化任务管理器
            # 这个管理器在初始化时会自动处理数据库加载/新建逻辑
            task_manager = TaskScenarioManager(CONFIG, user_id, task_type, is_practice=is_practice)
            session_state['task_manager'] = task_manager # 存入会话以便其他消息处理器使用
            
            # 2. 从管理器获取下一个任务场景
            current_scenario = task_manager.get_next_task_parameters(is_ai_active_request)
            
            if current_scenario == "ALL_COMPLETED":
                return [{"type": "all_tasks_completed", "task_type": task_type, "message": "祝贺！所有SA威胁应对任务已完成。"}]
            if not current_scenario:
                return [{"type": "all_tasks_completed", "task_type": task_type, "message": f"当前模式的{task_type}任务已完成。"}]

            current_session[f'{task_type}_scenario'] = current_scenario
            task_id = generate_task_id()
            current_session['task_id'] = task_id
            
            # 只有在非练习模式下才记录数据库
            if not session_state.get('is_practice', False):
                record_operation_to_db({
                    'task_id': task_id,
                    'operationType': 'task_start',
                    'timestamp': message.get('timestamp', int(time.time() * 1000)),
                    'isActive': True,
                    'parameters': {'include_ai': is_ai_active_request},
                    'user_id': user_id,
                    'event_owner': event_owner
                }, session_state)
            else:
                print("练习模式，跳过 task_start 数据库记录。")

            record_task_settings_to_db(task_id, current_scenario, user_id, event_owner, session_state)
            initialize_targets(current_scenario['difficulty_config'])

            init_response = {
                "type": "init_settings",
                "task_id": task_id,
                "timestamp": time.time() * 1000,
                "settings": {"range": 80, "scanAngle": 30},
                "is_ai_active": current_scenario['is_ai_active'],
                "ai_level": current_scenario.get('ai_level_name'),
                "ai_configs": CONFIG.get('levels', []),
                "audio_enabled": current_scenario['audio_enabled'],
                "repetition_info": current_scenario['repetition_info'],
                "task_type": task_type
            }
            return [init_response]
        
        elif message_type == 'settings_update':
            print("消息类型: settings_update")
            
            # --- 严格的三步验证逻辑 ---
            # 第二步：验证雷达参数是否与init_settings一致
            client_range = message.get('range')
            client_scan_angle = message.get('scanAngle')

            # 从init_settings获取预设值
            # 注意：在真实的多用户场景中，这些预设值应该从会话(session)中获取
            required_range = 80
            required_scan_angle = 30

            if client_range == required_range and client_scan_angle == required_scan_angle:
                # 参数正确，进入天线调整阶段
                print("雷达参数验证成功，发送天线调整指令。")
                # 只有在非练习模式下才记录数据库
                if not session_state.get('is_practice', False):
                    record_operation_to_db({
                        'task_id': current_session.get('task_id'),
                        'operationType': 'settings_update',
                        'timestamp': message.get('timestamp', int(time.time() * 1000)),
                        'receive_timestamp': message.get('receive_timestamp'),
                        'isActive': True,
                        'parameters': message, 
                        'user_id': message.get('user_id', ''),
                        'event_owner': client_event_owner
                    }, session_state)
                else:
                    print("练习模式，跳过 settings_update 数据库记录。")

                validation_response = {"type": "settings_validation", "status": "success", "message": "雷达参数设置正确，请继续进行天线高度调整"}
                antenna_command = generate_antenna_adjustment()
                return [validation_response, antenna_command]
            else:
                # 参数不正确
                print(f"雷达参数验证失败。需要: range={required_range}, scanAngle={required_scan_angle}。收到: range={client_range}, scanAngle={client_scan_angle}")
                validation_response = {"type": "settings_validation", "status": "error", "message": "雷达参数设置不正确，请调整参数"}
                return [validation_response]
        
        elif message_type == 'antenna_adjusted':
            print("消息类型: antenna_adjusted")
            
            validation_response, is_valid = handle_antenna_adjustment(message)
            if is_valid:
                # 只有在非练习模式下才记录数据库
                if not session_state.get('is_practice', False):
                    record_operation_to_db({
                        'task_id': current_session.get('task_id'),
                        'operationType': 'antenna_adjusted',
                        'timestamp': message.get('timestamp', int(time.time() * 1000)),
                            'receive_timestamp': message.get('receive_timestamp'),
                        'isActive': True,
                        'parameters': {'elevation': message.get('elevation')},
                            'user_id': message.get('user_id', ''),
                            'event_owner': client_event_owner
                        }, session_state)
                else:
                    print("练习模式，跳过 antenna_adjusted 数据库记录。")

                return validation_response, True 
            else:
                return [validation_response]

        elif message_type == 'target_selected':
            print("消息类型: target_selected")
            target_id = message.get('target_id')
            iff_mode = message.get('iff_mode', False)
            is_enemy = any(target['id'] == target_id and target['type'] == 'army' for target in unknown_targets)
            
            # 只有在非练习模式下才记录数据库
            if not session_state.get('is_practice', False):
                record_operation_to_db({
                    'task_id': current_session.get('task_id'),
                    'operationType': 'target_selected',
                    'timestamp': message.get('timestamp', int(time.time() * 1000)),
                    'receive_timestamp': message.get('receive_timestamp'),
                    'isActive': not iff_mode,
                    'parameters': {
                        'target_id': target_id,
                        'action': message.get('action', 'select'),
                        'iff_mode': iff_mode,
                        'is_enemy': is_enemy
                    },
                    'user_id': message.get('user_id', ''),
                    'event_owner': client_event_owner # Pass event_owner
                }, session_state)
            else:
                print("练习模式，跳过 target_selected 数据库记录。")

            return []

        elif message_type == 'threat_clicked':
            print("消息类型: threat_clicked")

            # 只有在非练习模式下才记录数据库
            if not session_state.get('is_practice', False):
                record_operation_to_db({
                    'task_id': current_session.get('task_id'),
                    'operationType': 'threat_clicked',
                    'timestamp': message.get('timestamp', int(time.time() * 1000)),
                    'isActive': True,
                    'receive_timestamp': message.get('receive_timestamp'),
                    'parameters': {
                        'threat_id': message.get('threat_id'),
                        'label': message.get('label'),
                        'priority': message.get('priority'),
                        'is_highest_priority': message.get('is_highest_priority'),
                        'is_correct': message.get('is_correct'),
                        'correct_answer': message.get('correct_answer'),
                        'extra': message.get('extra', {})
                    },
                    'user_id': message.get('user_id', ''),
                    'event_owner': client_event_owner # Pass event_owner
                }, session_state)
            else:
                print("练习模式，跳过 threat_clicked 数据库记录。")
            return []
        
        # For record_operation and record_bulk_operations, event_owner should be part of each 'operation' item
        elif message_type == 'record_operation':
            print("消息类型: record_operation")
            operation = message.get('operation', {})
            # Ensure event_owner from the outer message is also considered if not in operation itself
            if 'event_owner' not in operation:
                operation['event_owner'] = client_event_owner
            record_operation_to_db(operation, session_state)
            return []
        
        elif message_type == 'record_bulk_operations':
            print("消息类型: record_bulk_operations")
            operations = message.get('operations', [])
            for operation in operations:
                if 'event_owner' not in operation:
                    operation['event_owner'] = client_event_owner
                record_operation_to_db(operation, session_state)
            return []
        
        # For SA related, if there's an owner, it should be in the message.
        elif message_type == 'SwitchSA' or message_type == 'ResetSA':
            user_id = message.get('user_id')
            if not user_id:
                 return [{"type": "error", "message": "Cannot switch SA without a user_id in the message."}]

            task_type = 'SA_THREAT_RESPONSE'
            is_practice = message.get('is_practice', False) # 从消息获取
            session_state['is_practice'] = is_practice # 存入会话
            # 为SA任务也创建一个持久化管理器
            task_manager = TaskScenarioManager(CONFIG, user_id, task_type, is_practice=is_practice)
            session_state['sa_task_manager'] = task_manager

            event_owner = message.get('event_owner', 'manual')
            is_ai_active_request = (event_owner == 'AI')
            
            current_scenario = task_manager.get_next_task_parameters(is_ai_active_request)
            
            if current_scenario == "ALL_COMPLETED":
                return [{"type": "all_tasks_completed", "task_type": task_type, "message": "祝贺！所有SA威胁应对任务已完成。"}]
            if not current_scenario:
                return [{"type": "all_tasks_completed", "task_type": task_type, "message": "当前模式的SA任务已完成。"}]

            current_session[f'{task_type}_scenario'] = current_scenario
            print(f"current_scenario: {session_state}")
            # 只有在非练习模式下才记录数据库
            if not session_state.get('is_practice', False):
                record_operation_to_db({
                    'task_id': current_session.get('task_id'),
                    'operationType': message_type,
                    'timestamp': message.get('timestamp', int(time.time() * 1000)),
                    'isActive': True, 
                    'parameters': {}, 
                    'user_id': user_id, 
                    'event_owner': event_owner
                }, session_state)
            
            threats = generate_sa_threats(current_scenario['difficulty_config'])
            
            response = {
                'type': 'sa_task_updated',
                'saThreats': threats,
                'repetition_info': current_scenario['repetition_info'],
                'task_type': task_type
            }

            if websocket:
                asyncio.create_task(
                    auto_send_sa_emergency(
                        websocket, 
                        threats,
                        user_id,
                        event_owner,
                        session_state
                        )
                    )
            return [response]
        
        elif message_type == 'reset_targets':
            print("消息类型: reset_targets ( advancing scenario counter )")
            
            user_id = current_session.get('user_id', '')
            if not user_id:
                 return [{"type": "error", "message": "Cannot reset_targets without a user session."}]

            task_manager = session_state.get('task_manager')
            if not task_manager:
                return [{"type": "error", "message": "Task not started. Cannot reset targets."}]

            is_ai_active_request = current_session.get('RADAR_TARGETING_scenario', {}).get('is_ai_active', False)
            event_owner = 'AI' if is_ai_active_request else 'manual'

            current_scenario = task_manager.get_next_task_parameters(is_ai_active_request)
            if not current_scenario:
                return [{"type": "all_tasks_completed", "task_type": task_type, "message": "Congratulations! All Radar Targeting scenarios have been completed."}]

            current_session[f'RADAR_TARGETING_scenario'] = current_scenario
            task_id = generate_task_id()
            current_session['task_id'] = task_id
            
            record_task_settings_to_db(task_id, current_scenario, user_id, event_owner, session_state)

            # 5. 根据新场景重新初始化目标
            initialize_targets(current_scenario['difficulty_config'])
            
            # 6. 构造一个init_settings消息，以便前端可以更新其状态（包括计数器）
            response_message = {
                "type": "init_settings",
                "task_id": task_id,
                "timestamp": time.time() * 1000,
                "settings": {"range": 80, "scanAngle": 30},
                "is_ai_active": current_scenario['is_ai_active'],
                "ai_level": current_scenario['ai_level_name'],
                "ai_configs": CONFIG.get('levels', []),
                "audio_enabled": current_scenario['audio_enabled'],
                "repetition_info": current_scenario['repetition_info'],
                "task_type": task_type
            }
            return [response_message]
            
    except json.JSONDecodeError as e:
        print(f"解析JSON时出错: {e}")
    except Exception as e:
        print(f"处理客户端消息时出错: {e}")
    
    print("===== 客户端消息处理失败 =====\n")
    return False, False # Default return for unhandled or error cases

# 单独方法发送消息到客户端
async def send_message(websocket, message):
    try:
        json_str = json.dumps(message)
        await websocket.send(json_str)
        print(f"发送消息: {message['type']}")
        return True
    except Exception as e:
        print(f"发送消息失败: {e}")
        return False

# 修改：WebSocket处理函数
async def radar_server(websocket):
    print("【服务器】客户端已连接")
    session_state = {} # 为每个连接创建一个独立的会话状态
    try:
        # 初始连接时发送不包含目标数据的基础数据
        initial_data = get_radar_data(include_targets=False)
        initial_json = json.dumps(initial_data)
        await websocket.send(initial_json)
        print(f"【服务器】已发送基础数据（不含目标），长度: {len(initial_json)}")
        
        # # 初始化SA威胁并发送  <--- MODIFIED: Commented out
        # threats = generate_sa_threats(n=random.randint(3, 6))
        # sa_msg = {'type': 'SAThreats', 'saThreats': threats}
        # await send_message(websocket, sa_msg)
        # print("【服务器】已发送初始SA威胁数组")

        # # 2~3秒后自动推送一次SAEmergency <--- MODIFIED: Commented out
        # # If you re-enable this, ensure 'threats' is defined, e.g., after a 'SwitchSA'
        # # asyncio.create_task(auto_send_sa_emergency(websocket, threats))
        
        # 接收并处理客户端消息
        while True:
            try:
                # 等待消息，但设置超时以保持连接活跃
                message = await asyncio.wait_for(websocket.recv(), timeout=60)
                print(f"【服务器】接收到消息: {message[:50]}..." if len(message) > 50 else message)
                # 将会话状态传递给消息处理器
                result = await handle_client_message(message, session_state, websocket)
                # 检查返回结果类型
                if isinstance(result, list):
                    for msg in result:
                        await send_message(websocket, msg)
                elif isinstance(result, tuple) and len(result) == 2:
                    settings_updated, include_targets = result
                    if settings_updated:
                        # Ensure validation message is sent BEFORE data frame
                        if 'type' in settings_updated and settings_updated['type'] == 'settings_validation':
                            print(f"【服务器】发送验证结果: {settings_updated}") 
                            await websocket.send(json.dumps(settings_updated))

                        # Now prepare and send the main data frame
                        data = get_radar_data(include_targets=include_targets)
                        data["_timestamp"] = time.time()
                        data_json = json.dumps(data)

                        if include_targets:
                            print(f"【服务器】正在发送包含目标的数据，JSON长度: {len(data_json)}")
                            print(f"【服务器】数据键: {list(data.keys())}")
                            if 'externalTargets' in data:
                                print(f"【服务器】externalTargets长度: {len(data['externalTargets'])}")
                        else:
                            print(f"【服务器】正在发送不含目标的数据，JSON长度: {len(data_json)}")
                        
                        await websocket.send(data_json)
                        
                        if include_targets:
                            print("【服务器】✅ 已发送更新后的数据（包含目标）")
                        else:
                            print("【服务器】✅ 已发送更新后的数据（不含目标）")
            except asyncio.TimeoutError:
                pass
            except websockets.exceptions.ConnectionClosed:
                print("【服务器】客户端连接已关闭")
                break
    except websockets.exceptions.ConnectionClosed:
        print("【服务器】客户端已断开连接")
    except Exception as e:
        print(f"【服务器】【错误】WebSocket处理时出错: {e}")

# 修改：main
async def main():
    # 不再需要在这里初始化全局管理器
    # task_manager = TaskScenarioManager(CONFIG, max_repetitions=10)
    
    # 首次启动时，根据默认难度初始化目标
    default_difficulty_name = CONFIG.get('game_settings', {}).get('current_difficulty', 'low')
    default_difficulty_config = CONFIG.get('game_settings', {}).get('difficulty_levels', {}).get(default_difficulty_name, {})
    initialize_targets(default_difficulty_config)
    
    # 初始化数据库
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 检查 user_operations 表是否存在
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='user_operations'
            """)
            
            if not cursor.fetchone():
                print("user_operations 表不存在，正在创建...")
                # 创建 user_operations 表
                cursor.execute("""
                    CREATE TABLE user_operations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_id INTEGER,
                        operation_type TEXT NOT NULL,
                        timestamp INTEGER NOT NULL,
                        receive_timestamp INTEGER,
                        is_active INTEGER NOT NULL,
                        parameters TEXT,
                        user_id TEXT,
                        event_owner TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
                print("user_operations 表创建成功")
            else:
                print("user_operations 表已存在，检查列...")
                # 检查 receive_timestamp 列是否存在
                cursor.execute("PRAGMA table_info(user_operations)")
                columns = [column[1] for column in cursor.fetchall()]
                if 'receive_timestamp' not in columns:
                    print("正在添加 receive_timestamp 列...")
                    cursor.execute("""
                        ALTER TABLE user_operations 
                        ADD COLUMN receive_timestamp INTEGER
                    """)
                    conn.commit()
                    print("receive_timestamp 列添加成功")
                else:
                    print("receive_timestamp 列已存在")
                
                # 检查 event_owner 列是否存在
                if 'event_owner' not in columns:
                    print("正在添加 event_owner 列...")
                    cursor.execute("""
                        ALTER TABLE user_operations
                        ADD COLUMN event_owner TEXT
                    """)
                    conn.commit()
                    print("event_owner 列添加成功")
                else:
                    print("event_owner 列已存在")
                
            # ---- 新增：检查和创建 task_settings 表 ----
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='task_settings'")
            if not cursor.fetchone():
                print("task_settings 表不存在，正在创建...")
                cursor.execute("""
                    CREATE TABLE task_settings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_id INTEGER NOT NULL UNIQUE,
                        user_id TEXT,
                        event_owner TEXT,
                        execution_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        repetition_count INTEGER NOT NULL,
                        is_ai_active BOOLEAN NOT NULL,
                        ai_level_config TEXT,
                        difficulty_config TEXT NOT NULL,
                        audio_enabled BOOLEAN NOT NULL,
                        ai_level_name TEXT,
                        difficulty_name TEXT NOT NULL,
                        FOREIGN KEY (task_id) REFERENCES user_operations (task_id)
                    )
                """)
                conn.commit()
                print("task_settings 表创建成功")
            else:
                print("task_settings 表已存在，检查列...")
                cursor.execute("PRAGMA table_info(task_settings)")
                columns = [column[1] for column in cursor.fetchall()]
                if 'user_id' not in columns:
                    print("正在添加 user_id 列...")
                    cursor.execute("ALTER TABLE task_settings ADD COLUMN user_id TEXT")
                    conn.commit()
                if 'event_owner' not in columns:
                    print("正在添加 event_owner 列...")
                    cursor.execute("ALTER TABLE task_settings ADD COLUMN event_owner TEXT")
                    conn.commit()

            # --- 核心修改：在启动时检查并创建 user_progress 表 ---
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_progress'")
            if not cursor.fetchone():
                print("user_progress 表不存在，正在创建...")
                cursor.execute("""
                    CREATE TABLE user_progress (
                        user_id TEXT NOT NULL,
                        task_type TEXT NOT NULL,
                        current_scenario_json TEXT,
                        repetition_counter INTEGER,
                        ai_queue_json TEXT,
                        manual_queue_json TEXT,
                        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (user_id, task_type)
                    );
                """)
                conn.commit()
                print("user_progress 表创建成功。")
            else:
                print("user_progress 表已存在。")

        print("数据库初始化成功")
    except Exception as e:
        print(f"数据库初始化失败: {e}")
    
    # 启动服务器
    async with websockets.serve(radar_server, "0.0.0.0", 8765):
        print("雷达服务器已启动于 ws://localhost:8765")
        await asyncio.Future()  # 运行直到被取消

if __name__ == "__main__":
    asyncio.run(main()) 