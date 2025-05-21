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

# 用于存储目标信息的全局变量
unknown_targets = []
own_heading = 278  # 当前航向 (度)
radar_azimuth = 0  # 固定的雷达方位角值
radar_range = 80   # 雷达范围 (海里)
scan_angle = 60    # 扫描角度 (度)

# 任务ID计数器
task_counter = 0

# 当前会话状态
current_session = {
    'task_id': None,
    'stage': 'init',  # 'init', 'antenna_adjustment', 'target_identification'
    'target_elevation': None,
    'operations': []
}

# 数据库连接池
class ConnectionPool:
    def __init__(self, max_connections=5):
        self.max_connections = max_connections
        self.pool = queue.Queue(maxsize=max_connections)
        self.lock = threading.Lock()
        
        # 初始化连接池
        for _ in range(max_connections):
            conn = sqlite3.connect('radar_operations.db', check_same_thread=False)
            self.pool.put(conn)
    
    def get_connection(self):
        with self.lock:
            return self.pool.get()
    
    def return_connection(self, conn):
        with self.lock:
            self.pool.put(conn)
    
    def close_all(self):
        with self.lock:
            while not self.pool.empty():
                conn = self.pool.get()
                conn.close()

# 创建全局连接池
db_pool = ConnectionPool()

@contextmanager
def get_db_connection():
    conn = db_pool.get_connection()
    try:
        yield conn
    finally:
        db_pool.return_connection(conn)

# 记录操作到数据库
def record_operation_to_db(operation):
    max_retries = 3
    retry_delay = 0.1  # 100ms
    
    for attempt in range(max_retries):
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # 开始事务
                cursor.execute('BEGIN TRANSACTION')
                
                # 插入操作记录
                cursor.execute('''
                INSERT INTO user_operations (
                    task_id, 
                    operation_type, 
                    timestamp, 
                    receive_timestamp,
                    is_active, 
                    parameters, 
                    user_id,
                    event_owner
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    operation.get('task_id', current_session.get('task_id', 0)),
                    operation.get('operationType', ''),
                    operation.get('timestamp', int(time.time() * 1000)),
                    operation.get('receive_timestamp'),  # 从客户端消息中获取接收时间戳
                    1 if operation.get('isActive', False) else 0,
                    json.dumps(operation.get('parameters', {})),
                    operation.get('user_id', ''),
                    operation.get('event_owner', '')
                ))
                
                # 提交事务
                conn.commit()
                print(f"已记录操作到数据库: {operation.get('operationType')}")
                return True
                
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < max_retries - 1:
                print(f"数据库锁定，等待重试 ({attempt + 1}/{max_retries})")
                time.sleep(retry_delay)
                continue
            else:
                print(f"记录操作到数据库时出错: {e}")
                return False
        except Exception as e:
            print(f"记录操作到数据库时出错: {e}")
            return False

# 在程序退出时关闭所有连接
def cleanup():
    db_pool.close_all()

# 注册清理函数
atexit.register(cleanup)

# 生成新的任务ID
def generate_task_id():
    global task_counter
    task_id = task_counter
    task_counter += 1
    return task_id

# 初始化未知目标数据，使用与mockUnknownTargets.ts相同的数据结构
def initialize_targets():
    global unknown_targets
    
    # 定义雷达显示区域的边界（可以根据实际显示区域调整）
    min_x, max_x = -100, 100
    min_y, max_y = -100, 100
    
    # 创建空的目标列表
    unknown_targets = []
    
    # 生成3个友机
    for i in range(3):
        # 随机生成位置
        x = random.uniform(min_x, max_x)
        y = random.uniform(min_y, max_y)
        
        # 随机生成速度（友机速度较慢）
        speed = random.uniform(3, 6)
        
        # 随机生成方向
        direction = random.uniform(0, 2 * np.pi)
        
        unknown_targets.append({
            "id": f"friend-{i+1}",
            "position": {"x": x, "y": y},
            "history": [],
            "speed": speed,
            "direction": direction,
            "type": "friend"
        })
    
    # 生成2个敌机
    for i in range(2):
        # 随机生成位置
        x = random.uniform(min_x, max_x)
        y = random.uniform(min_y, max_y)
        
        # 随机生成速度（敌机速度较快）
        speed = random.uniform(8, 12)
        
        # 随机生成方向
        direction = random.uniform(0, 2 * np.pi)
        
        unknown_targets.append({
            "id": f"enemy-{i+1}",
            "position": {"x": x, "y": y},
            "history": [],
            "speed": speed,
            "direction": direction,
            "type": "army"
        })
    
    print(f"已初始化 {len(unknown_targets)} 个未知目标")
    # 打印目标信息用于调试
    for target in unknown_targets:
        print(f"目标 {target['id']}: 位置({target['position']['x']:.1f}, {target['position']['y']:.1f}), "
              f"速度 {target['speed']:.1f}, 类型 {target['type']}")

# 获取要发送给前端的数据
def get_radar_data(include_targets=False):
    global unknown_targets, own_heading, radar_azimuth, radar_range, scan_angle
    
    try:
        print("【调试】开始生成雷达数据...")
        
        # 基础数据，不包含目标
        data = {
            "radar_azimuth": float(radar_azimuth),
            "own_heading": float(own_heading),
            "timestamp": time.time(),
            "range": float(radar_range),
            "scanAngle": float(scan_angle)
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
    # 随机选择上移或下移3格
    direction = random.choice([-3, 3])
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
def generate_sa_threats(n=4):
    threats = []
    # 只从secondary类型中选取
    secondary_types = [t for t in SA_ICON_TYPES if t.startswith('Secondary')]
    chosen_types = random.sample(secondary_types, k=min(n, len(secondary_types)))
    for t in chosen_types:
        label = random.choice(SA_LABELS[t])
        threats.append({
            'id': f'{t}-{random.randint(1000,9999)}',
            'type': t,
            'label': label
        })
    return threats

def generate_sa_emergency(threats):
    # 随机选择事件类型
    event_type = random.choice(['upgrade', 'missile'])
    if event_type == 'upgrade':
        # 找到所有secondary威胁
        secondary = [t for t in threats if t['type'].startswith('Secondary')]
        if secondary:
            to_upgrade = random.choice(secondary)
            # 升级为primary
            primary_type = to_upgrade['type'].replace('Secondary', 'Primary')
            to_upgrade['type'] = primary_type
            to_upgrade['label'] = random.choice(SA_LABELS[primary_type])
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

async def auto_send_sa_emergency(websocket, threats):
    await asyncio.sleep(random.uniform(2, 3))
    emergency_msg = generate_sa_emergency(threats)
    await send_message(websocket, emergency_msg)
    print(f"[自动] 已发送SAEmergency事件: {emergency_msg['event']}")
    # 记录临机事件日志
    try:
        record_operation_to_db({
            'task_id': current_session.get('task_id'),
            'operationType': 'sa_emergency',
            'timestamp': int(time.time() * 1000),
            'isActive': False,
            'parameters': emergency_msg,
            'user_id': '',
            'event_owner': ''
        })
    except Exception as e:
        print(f"记录SAEmergency日志失败: {e}")

# 处理从客户端接收的消息
async def handle_client_message(message_str, websocket=None):
    global radar_range, scan_angle, unknown_targets, current_session
    
    try:
        print("\n===== 接收到客户端消息 =====")
        print(f"原始消息: {message_str}")
        
        message = json.loads(message_str)
        print(f"解析后的消息: {message}")
        
        message_type = message.get('type', '')
        client_event_owner = message.get('event_owner', '') # Get event_owner from the message
        
        if message_type == 'task_start':
            print("消息类型: task_start", message.get('user_id', ''))
            task_id = generate_task_id()
            current_session['task_id'] = task_id
            current_session['stage'] = 'init'
            record_operation_to_db({
                'task_id': task_id,
                'operationType': 'task_start',
                'timestamp': message.get('timestamp', int(time.time() * 1000)),
                'isActive': True,
                'parameters': {},
                'user_id': message.get('user_id', ''),
                'event_owner': client_event_owner # Pass event_owner
            })
            response = {"type": "task_id_assigned", "task_id": task_id, "timestamp": time.time() * 1000}
            init_settings = {
                "type": "init_settings",
                "settings": {"range": 80, "scanAngle": 30},
                "timestamp": time.time() * 1000
            }
            return [response, init_settings]
        
        elif message_type == 'settings_update':
            print("消息类型: settings_update")
            record_operation_to_db({
                'task_id': current_session.get('task_id'),
                'operationType': 'settings_update',
                'timestamp': message.get('timestamp', int(time.time() * 1000)),
                'receive_timestamp': message.get('receive_timestamp'),
                'isActive': True,
                'parameters': message, # Entire message as parameters for now
                'user_id': message.get('user_id', ''),
                'event_owner': client_event_owner # Pass event_owner
            })
            if should_include_targets(message):
                validation_response = {"type": "settings_validation", "status": "success", "message": "雷达参数设置正确，请继续进行天线高度调整"}
                antenna_command = generate_antenna_adjustment()
                return [validation_response, antenna_command]
            else:
                validation_response = {"type": "settings_validation", "status": "error", "message": "雷达参数设置不正确，请调整参数"}
                return [validation_response]
        
        elif message_type == 'antenna_adjusted':
            print("消息类型: antenna_adjusted")
            record_operation_to_db({
                'task_id': current_session.get('task_id'),
                'operationType': 'antenna_adjusted',
                'timestamp': message.get('timestamp', int(time.time() * 1000)),
                'receive_timestamp': message.get('receive_timestamp'),
                'isActive': True,
                'parameters': {'elevation': message.get('elevation')},
                'user_id': message.get('user_id', ''),
                'event_owner': client_event_owner # Pass event_owner
            })
            validation_response, is_valid = handle_antenna_adjustment(message)
            if is_valid:
                # If settings are correct, initialize and return target data
                # This response might be redundant if settings_validation is already sent by handle_antenna_adjustment
                # For now, we follow the logic that a successful antenna adjustment leads to target identification phase
                # The actual data sending is handled by the main loop based on 'is_valid'
                # We might want to send a specific message here indicating success, or rely on the main loop.
                # For now, let's assume `is_valid` being True is enough to trigger data sending in the main loop.
                return validation_response, True # Signal to send data with targets
            else:
                return [validation_response] # Only send validation error

        elif message_type == 'target_selected':
            print("消息类型: target_selected")
            target_id = message.get('target_id')
            iff_mode = message.get('iff_mode', False)
            is_enemy = any(target['id'] == target_id and target['type'] == 'army' for target in unknown_targets)
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
            })
            return []

        elif message_type == 'threat_clicked':
            print("消息类型: threat_clicked")
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
                    'extra': message.get('extra', {})
                },
                'user_id': message.get('user_id', ''),
                'event_owner': client_event_owner # Pass event_owner
            })
            return []
        
        # For record_operation and record_bulk_operations, event_owner should be part of each 'operation' item
        elif message_type == 'record_operation':
            print("消息类型: record_operation")
            operation = message.get('operation', {})
            # Ensure event_owner from the outer message is also considered if not in operation itself
            if 'event_owner' not in operation:
                operation['event_owner'] = client_event_owner
            record_operation_to_db(operation)
            return []
        
        elif message_type == 'record_bulk_operations':
            print("消息类型: record_bulk_operations")
            operations = message.get('operations', [])
            for operation in operations:
                if 'event_owner' not in operation:
                    operation['event_owner'] = client_event_owner
                record_operation_to_db(operation)
            return []

        # ... (other message types like SwitchSA, ResetSA, reset_targets)
        # These might not have a direct client-side event_owner in the same way, 
        # or they are server-initiated in some contexts.
        # For SA related, if there's an owner, it should be in the message.
        elif message_type == 'SwitchSA':
            print('收到SwitchSA事件，生成SA威胁数组')
            record_operation_to_db({
                'task_id': current_session.get('task_id'),
                'operationType': message_type,
                'timestamp': message.get('timestamp', int(time.time() * 1000)),
                'isActive': True, 
                'parameters': {}, 
                'user_id': message.get('user_id', ''),
                'event_owner': client_event_owner
            })
            threats = generate_sa_threats(n=random.randint(3, 6))
            response = {'type': 'SAThreats', 'saThreats': threats}
            if websocket:
                asyncio.create_task(auto_send_sa_emergency(websocket, threats))
            return [response]
        
        elif message_type == 'ResetSA':
            print('收到ResetSA事件，重新生成SA威胁数组')
            record_operation_to_db({
                'task_id': current_session.get('task_id'),
                'operationType': message_type,
                'timestamp': message.get('timestamp', int(time.time() * 1000)),
                'isActive': True, 
                'parameters': {}, 
                'user_id': message.get('user_id', ''),
                'event_owner': client_event_owner
            })
            threats = generate_sa_threats(n=random.randint(3, 6))
            response = {'type': 'SAThreats', 'saThreats': threats}
            if websocket:
                asyncio.create_task(auto_send_sa_emergency(websocket, threats))
            return [response]

        elif message_type == 'reset_targets':
            print("消息类型: reset_targets")
            record_operation_to_db({
                'task_id': current_session.get('task_id'),
                'operationType': message_type,
                'timestamp': message.get('timestamp', int(time.time() * 1000)),
                'isActive': True, 
                'parameters': {}, 
                'user_id': message.get('user_id', ''),
                'event_owner': client_event_owner 
            })
            initialize_targets()
            return True, False # Signal to send data, but no targets initially

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

# WebSocket处理函数
async def radar_server(websocket):
    print("【服务器】客户端已连接")
    try:
        # 初始连接时发送不包含目标数据的基础数据
        initial_data = get_radar_data(include_targets=False)
        initial_json = json.dumps(initial_data)
        await websocket.send(initial_json)
        print(f"【服务器】已发送基础数据（不含目标），长度: {len(initial_json)}")
        
        # 初始化SA威胁并发送
        threats = generate_sa_threats(n=random.randint(3, 6))
        sa_msg = {'type': 'SAThreats', 'saThreats': threats}
        await send_message(websocket, sa_msg)
        print("【服务器】已发送初始SA威胁数组")

        # 2~3秒后自动推送一次SAEmergency
        asyncio.create_task(auto_send_sa_emergency(websocket, threats))

        # 接收并处理客户端消息
        while True:
            try:
                # 等待消息，但设置超时以保持连接活跃
                message = await asyncio.wait_for(websocket.recv(), timeout=60)
                print(f"【服务器】接收到消息: {message[:50]}..." if len(message) > 50 else message)
                # 处理消息
                result = await handle_client_message(message, websocket)
                # 检查返回结果类型
                if isinstance(result, list):
                    for msg in result:
                        await send_message(websocket, msg)
                elif isinstance(result, tuple) and len(result) == 2:
                    settings_updated, include_targets = result
                    if settings_updated:
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
                        if 'type' in settings_updated and settings_updated['type'] == 'settings_validation':
                            print(f"【服务器】发送验证结果: {settings_updated}") 
                            await websocket.send(json.dumps(settings_updated))
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

# 启动WebSocket服务器
async def main():
    # 初始化目标
    initialize_targets()
    
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
                
        print("数据库初始化成功")
    except Exception as e:
        print(f"数据库初始化失败: {e}")
    
    # 启动服务器
    async with websockets.serve(radar_server, "0.0.0.0", 8765):
        print("雷达服务器已启动于 ws://localhost:8765")
        await asyncio.Future()  # 运行直到被取消

if __name__ == "__main__":
    asyncio.run(main()) 