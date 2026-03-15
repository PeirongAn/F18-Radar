from flask import Flask
import tobii_research as tr
from flask import request, jsonify
import math
from collections import deque
import uuid
import threading
import time
import json

import pymysql
from pymysql import Error
import websockets
import asyncio
# 数据库配置
DB_CONFIG = {
    'host': 'localhost',      # MySQL服务器地址
    'port': 3306,             # MySQL端口（默认3306）
    'user': 'root',           # 用户名（改成你自己的）
    'password': '123456',  # 密码（改成你安装时设置的root密码）
    'database': 'task_logs',  # 数据库名
    'charset': 'utf8mb4'
}

eyetrackers = None # 全局变量
eyetracker = None

flag = False # 全局变量，判断是否在注释
gaze_window = deque(maxlen=600)
# 当前任务
current_task = None
task_active = False
# 线程锁，防止 gaze 回调和 Flask 请求同时改数据
window_lock = threading.Lock()
state_lock = threading.Lock()

# 日志文件
FIXATION_LOG_FILE = "fixation_events.txt"
TASK_LOG_FILE = "task_records.txt"

# 存储最新的注视点（用于可视化）
latest_gaze_point = None
latest_gaze_time = None
gaze_point_lock = threading.Lock()

# WebSocket连接管理
connected_clients = set()
antenna_clients = set()  # 天线调整WebSocket客户端
clients_lock = threading.Lock()
antenna_clients_lock = threading.Lock()

# 连续非注视计数器
consecutive_non_fixation = 0
consecutive_non_fixation_lock = threading.Lock()

class HTTPServer:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.app = Flask(__name__)
        self.setup_routes()
    
    def setup_routes(self):
        """设置HTTP路由"""
        @self.app.route("/")
        def index():
            return "Tobii Server Running"
        
        @self.app.route("/tobii/test", methods=["POST"])
        def tobii_test():
            data = request.get_json()

            if data is None:
                return jsonify({
                    "ok": False,
                    "msg": "请求体必须是 JSON"
                }), 400

            print("收到前端请求:", data)

            return jsonify({
                "ok": True,
                "msg": "请求接收成功",
                "data": data
            })
        
        @self.app.route("/tobii/hand", methods=["POST"])
        def tobii_hand():
            global flag, task_active, current_task
            init_database()
            data = request.get_json()
            if data is None:
                return jsonify({
                    "ok": False,
                    "msg": "请求体必须是 JSON"
                }), 400

            required_fields = [
                "bbox",
                "scream_data",
                "system_time",
                "box_visible",
                "user_id",
                "task_source",
                "task_name"
            ]
            for field in required_fields:
                if field not in data:
                    return jsonify({
                        "ok": False,
                        "msg": f"缺少字段: {field}"
                    }), 400

            bbox = data["bbox"]
            scream_data = data["scream_data"]
            system_time = data["system_time"]
            box_visible = data["box_visible"]
            user_id = data["user_id"]
            task_source = data["task_source"]
            task_name = data["task_name"]

            screen_width, screen_height = scream_data
            bbox = normalize_bboxes(bbox,screen_width,screen_height)

            print("收到前端请求:", data)

            # 1. 窗口出现：开始任务
            if box_visible is True:
                task_id = str(uuid.uuid4())

                with state_lock:
                    current_task = {
                        "task_id": task_id,
                        "bbox": bbox,
                        "start_system_time": system_time,
                        "user_id": user_id,
                        "task_source": task_source,
                        "task_name": task_name
                    }
                    task_active = True
                    flag = False

                return jsonify({
                    "ok": True,
                    "msg": "窗口出现，任务开始",
                    "task_id": task_id,
                    "flag": flag
                })

            # 2. 窗口消失：结束任务
            else:
                task_id = data.get("task_id")
                if not task_id:
                    return jsonify({
                        "ok": False,
                        "msg": "窗口消失时必须传 task_id"
                    }), 400

                with state_lock:
                    # 如果结束前还是注视中，补一条 fixation_end
                    if task_active and flag is True:
                        log_fixation_event(task_id, "fixation_end",system_time)

                    flag = False
                    task_active = False
                    task_info = current_task
                    begin_time = current_task.get("start_system_time")
                    end_time = system_time
                    current_task = None

                log_task_record(task_id, user_id, task_source, task_name,begin_time,end_time)

                return jsonify({
                    "ok": True,
                    "msg": "窗口消失，任务结束",
                    "task_id": task_id,
                    "flag": flag,
                    "task_info": task_info
                })
        
        @self.app.route("/tobii/gaze_point", methods=["GET"])
        def get_gaze_point():
            """
            获取最新的注视点坐标，用于前端可视化
            """
            global latest_gaze_point, latest_gaze_time
            
            with gaze_point_lock:
                if latest_gaze_point is None:
                    return jsonify({
                        "ok": False,
                        "msg": "尚无注视点数据"
                    }), 404
                
                # 检查数据是否太旧（超过1秒）
                current_time = time.time() * 1000
                if current_time - latest_gaze_time > 1000:
                    print("数据过期")
                    return jsonify({
                        "ok": False,
                        "msg": "注视点数据已过期"
                    }), 404
                
                return jsonify({
                    "ok": True,
                    "gaze_point": latest_gaze_point,
                    "timestamp": latest_gaze_time
                })
    
    def start(self):
        """启动HTTP服务器"""
        print(f"HTTP服务器启动在 {self.host}:{self.port}")
        self.app.run(host=self.host, port=self.port, debug=False)

# WebSocket连接管理
connected_clients = set()
clients_lock = threading.Lock()

def normalize_bboxes(bbox_list, screen_width, screen_height, clip_to_01=True):
    """
    将多个bbox根据屏幕分辨率归一化
    
    Args:
        bbox_list: list of [x1, y1, x2, y2]
        screen_width: 屏幕宽度
        screen_height: 屏幕高度
        clip_to_01: 是否将值限制在0-1之间
    
    Returns:
        list of normalized [x1, y1, x2, y2]
    """
    normalized = []
    
    for bbox in bbox_list:
        x1, y1, x2, y2 = bbox
        
        # 归一化
        norm_x1 = x1 / screen_width
        norm_y1 = y1 / screen_height
        norm_x2 = x2 / screen_width
        norm_y2 = y2 / screen_height
        
        # 限制范围
        if clip_to_01:
            norm_x1 = max(0, min(1, norm_x1))
            norm_y1 = max(0, min(1, norm_y1))
            norm_x2 = max(0, min(1, norm_x2))
            norm_y2 = max(0, min(1, norm_y2))
        
        normalized.append([norm_x1, norm_y1, norm_x2, norm_y2])
    
    return normalized


def get_db_connection():
    """获取数据库连接"""
    try:
        connection = pymysql.connect(
            host=DB_CONFIG['host'],
            port=DB_CONFIG['port'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            database=DB_CONFIG['database'],
            charset=DB_CONFIG['charset'],
            cursorclass=pymysql.cursors.DictCursor  # 返回字典类型的结果
        )
        return connection
    except Error as e:
        print(f"数据库连接失败: {e}")
        return None
def log_fixation_event(task_id, event_type,local_time_ms):
    """
    第一张表：注视开始/结束（写入MySQL）
    """
    
    
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        if not connection:
            print("无法连接数据库，记录写入失败")
            return False
            
        cursor = connection.cursor()
        
        # SQL插入语句
        sql = """
        INSERT INTO fixation_events (local_time_ms, task_id, event_type) 
        VALUES (%s, %s, %s)
        """
        
        # 执行插入
        cursor.execute(sql, (local_time_ms, task_id, event_type))
        
        # 提交事务
        connection.commit()
        
        print(f"写入 fixation 事件成功: task_id={task_id}, event_type={event_type}")
        return True
        
    except Error as e:
        print(f"写入 fixation 事件失败: {e}")
        if connection:
            connection.rollback()  # 发生错误时回滚
        return False
        
    finally:
        # 关闭游标和连接
        if cursor:
            cursor.close()
        if connection:
            connection.close()

def log_task_record(task_id, user_id, task_source, task_name, begin_time, end_time):
    """
    第二张表：任务结束记录（写入MySQL）
    """
    # local_time_ms = int(time.time() * 1000)
    
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        if not connection:
            print("无法连接数据库，记录写入失败")
            return False
            
        cursor = connection.cursor()
        
        # SQL插入语句
        sql = """
        INSERT INTO task_records (begin_time, end_time, task_id, user_id, task_source, task_name ) 
        VALUES (%s, %s, %s, %s, %s, %s)
        """
        
        # 执行插入
        cursor.execute(sql, (begin_time,end_time, task_id, user_id, task_source, task_name))
        
        # 提交事务
        connection.commit()
        
        print(f"写入 task 记录成功: task_id={task_id}, user_id={user_id}")
        return True
        
    except Error as e:
        print(f"写入 task 记录失败: {e}")
        if connection:
            connection.rollback()
        return False
        
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

def init_database():
    """初始化数据库（创建表）"""
    # 先连接MySQL（不指定数据库）
    connection = None
    cursor = None
    try:
        connection = pymysql.connect(
            host=DB_CONFIG['host'],
            port=DB_CONFIG['port'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            charset='utf8mb4'
        )
        cursor = connection.cursor()
        
        # 创建数据库
        cursor.execute("CREATE DATABASE IF NOT EXISTS task_logs DEFAULT CHARACTER SET utf8mb4")
        cursor.execute("USE task_logs")
        
        # 创建表
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS fixation_events (
            id INT AUTO_INCREMENT PRIMARY KEY,
            local_time_ms BIGINT NOT NULL,
            task_id VARCHAR(100) NOT NULL,
            event_type VARCHAR(20) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_task_id (task_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_records (
            id INT AUTO_INCREMENT PRIMARY KEY,
            begin_time BIGINT NOT NULL,
            end_time BIGINT NOT NULL,
            task_id VARCHAR(100) NOT NULL,
            user_id VARCHAR(50) NOT NULL,
            task_source VARCHAR(50) NOT NULL,
            task_name VARCHAR(200) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_task_id (task_id),
            INDEX idx_user_id (user_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        
        connection.commit()
        print("数据库初始化成功！")
        
    except Error as e:
        print(f"数据库初始化失败: {e}")
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

def query_recent_fixations(limit=10):
    """查询最近的注视事件"""
    connection = get_db_connection()
    if not connection:
        return []
    
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM fixation_events ORDER BY local_time_ms DESC LIMIT %s", (limit,))
    results = cursor.fetchall()
    cursor.close()
    connection.close()
    return results




def get_valid_gaze_point(gaze_data):
    """
    从 Tobii 返回的数据里提取有效注视点。
    优先取双眼平均；如果只有单眼有效，就取单眼。
    返回:
        (x, y)  # 0~1 归一化坐标
        或 (0,0)
    """
    left_valid = gaze_data.get("left_gaze_point_validity") == 1
    right_valid = gaze_data.get("right_gaze_point_validity") == 1

    left_point = gaze_data.get("left_gaze_point_on_display_area")
    right_point = gaze_data.get("right_gaze_point_on_display_area")

    if left_valid and right_valid:
        lx, ly = left_point
        rx, ry = right_point

        if not (math.isnan(lx) or math.isnan(ly) or math.isnan(rx) or math.isnan(ry)):
            return ((lx + rx) / 2, (ly + ry) / 2)

    if left_valid:
        lx, ly = left_point
        if not (math.isnan(lx) or math.isnan(ly)):
            return (lx, ly)

    if right_valid:
        rx, ry = right_point
        if not (math.isnan(rx) or math.isnan(ry)):
            return (rx, ry)

    return (0,0)


def gaze_data_callback(gaze_data):
    """
    每来一帧 Tobii 数据，就写入滑动窗口
    并在有活动任务时，实时检测 flag 的状态切换
    """
    global flag, task_active, current_task, latest_gaze_point, latest_gaze_time, consecutive_non_fixation
    # if flag is True :
    #     print("注释中")
    # print(gaze_data)
    system_time_stamp = gaze_data.get("system_time_stamp")
    system_time_stamp = int(time.time()*1000*1000)
    gaze_point = get_valid_gaze_point(gaze_data)
    frame_record = {
        "system_time_stamp": system_time_stamp,
        "gaze_point": gaze_point
    }
    
    with window_lock:
        gaze_window.append(frame_record)

      # 更新最新注视点（用于可视化）
    with gaze_point_lock:
        latest_gaze_point = list(gaze_point)  # 转换为列表，便于JSON序列化
        latest_gaze_time = time.time() * 1000  # 使用本地时间戳
    # 调试打印
    # print("最新帧:", frame_record)
    # print("当前窗口大小:", len(gaze_window))

    with state_lock:
        if not task_active or current_task is None:
            return
        task = current_task
        old_flag = flag

    # 只在任务开始之后处理
    if system_time_stamp is None:
        return

    # if system_time_stamp < task["start_system_time"]:
    #     print("返回了")
    #     return

    # 当前帧是否落在框内
    current_in_box = point_in_bboxes(gaze_point, task["bbox"])
    # print(current_in_box)
    
    # 处理连续非注视计数
    with consecutive_non_fixation_lock:
        if current_in_box:
            # 重置计数器
            consecutive_non_fixation = 0
        else:
            # 增加计数器
            consecutive_non_fixation += 1
            # 当连续200帧不在框内时，触发闪烁
            if consecutive_non_fixation >= 200:
                consecutive_non_fixation = 0  # 重置计数器
                # 发送闪烁指令给天线调整客户端
                send_flash_command()
    
    with state_lock:
        # 再次确认任务还存在
        if not task_active or current_task is None:
            return

        # False -> True
        if flag is False and current_in_box is True:
            flag = True
            log_fixation_event(task["task_id"], "fixation_start",system_time_stamp)

        # True -> False
        elif flag is True and current_in_box is False:
            flag = False
            log_fixation_event(task["task_id"], "fixation_end",system_time_stamp)


def point_in_bbox(point, bbox):
    """
    point: (x, y)，Tobii 归一化坐标 0~1
    bbox: [x1, y1, x2, y2]
    这里要求前端传来的 bbox 也是 0~1 坐标
    """
    if point is None:
        return False

    x, y = point
    x1, y1, x2, y2 = bbox

    return x1 <= x <= x2 and y1 <= y <= y2


def point_in_bboxes(point, bboxes):
    """
    判断 gaze 点是否在任意一个 bbox 内
    
    Args:
        point: (x, y)，Tobii 归一化坐标 0~1
        bboxes: 多个bbox的列表 [[x1,y1,x2,y2], [x1,y1,x2,y2], ...]
               要求每个 bbox 也是 0~1 坐标
    
    Returns:
        bool: 如果在任意一个bbox内返回True，否则返回False
        int: 所在的bbox索引（可选），如果不在任何bbox内返回-1
    """
    return_index = False
    if point is None or not bboxes:
        return False if not return_index else (False, -1)
    
    x, y = point
    
    for i, bbox in enumerate(bboxes):
        x1, y1, x2, y2 = bbox
        if x1 <= x <= x2 and y1 <= y <= y2:
            return True if not return_index else (True, i)
    
    return False if not return_index else (False, -1)


def send_flash_command():
    """
    发送闪烁指令给天线调整WebSocket客户端
    """
    import asyncio
    message = json.dumps({
        "type": "round_feedback",
        "should_flash": True,
        "duration_ms": 3000,
        "message": "用户连续200帧未注视目标",
        "echo": {},
        "serverTime": time.strftime("%Y-%m-%dT%H:%M:%S.%fZ", time.gmtime())
    })
    
    with antenna_clients_lock:
        for client in antenna_clients:
            try:
                # 使用asyncio.run在非异步线程中发送消息
                asyncio.run(client.send(message))
            except Exception as e:
                print(f"发送闪烁指令失败: {e}")

class WebSocketServer:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.server = None
    
    async def handle_client(self, websocket):
        # 从连接对象中获取路径信息
        path = getattr(websocket, 'path', '/')
        
        # 根据路径区分客户端类型
        if path == "/ws/antenna-adjustment":
            # 天线调整客户端
            with antenna_clients_lock:
                antenna_clients.add(websocket)
            
            try:
                async for message in websocket:
                    # 处理天线调整相关消息
                    try:
                        data = json.loads(message)
                        await self.process_antenna_message(websocket, data)
                    except json.JSONDecodeError:
                        await websocket.send(json.dumps({"ok": False, "msg": "无效的JSON格式"}))
            except websockets.ConnectionClosed:
                pass
            finally:
                # 移除天线调整客户端
                with antenna_clients_lock:
                    if websocket in antenna_clients:
                        antenna_clients.remove(websocket)
        else:
            # 普通客户端
            with clients_lock:
                connected_clients.add(websocket)
            
            try:
                async for message in websocket:
                    # 处理接收到的消息
                    try:
                        data = json.loads(message)
                        await self.process_message(websocket, data)
                    except json.JSONDecodeError:
                        await websocket.send(json.dumps({"ok": False, "msg": "无效的JSON格式"}))
            except websockets.ConnectionClosed:
                pass
            finally:
                # 移除客户端
                with clients_lock:
                    if websocket in connected_clients:
                        connected_clients.remove(websocket)
    
    async def process_message(self, websocket, data):
        """处理WebSocket消息，实现与HTTP服务相同的功能"""
        global flag, task_active, current_task
        
        try:
            # 初始化数据库
            init_database()
            
            # 获取消息类型
            message_type = data.get("type")
            
            if message_type == "test":
                # 测试消息
                await websocket.send(json.dumps({
                    "ok": True,
                    "msg": "请求接收成功",
                    "data": data
                }))
            
            elif message_type == "hand":
                # 处理任务相关消息
                required_fields = [
                    "bbox",
                    "scream_data",
                    "system_time",
                    "box_visible",
                    "user_id",
                    "task_source",
                    "task_name"
                ]
                
                for field in required_fields:
                    if field not in data:
                        await websocket.send(json.dumps({
                            "ok": False,
                            "msg": f"缺少字段: {field}"
                        }))
                        return
                
                bbox = data["bbox"]
                scream_data = data["scream_data"]
                system_time = data["system_time"]
                box_visible = data["box_visible"]
                user_id = data["user_id"]
                task_source = data["task_source"]
                task_name = data["task_name"]
                
                screen_width, screen_height = scream_data
                bbox = normalize_bboxes(bbox, screen_width, screen_height)
                
                # 1. 窗口出现：开始任务
                if box_visible is True:
                    task_id = str(uuid.uuid4())
                    
                    with state_lock:
                        current_task = {
                            "task_id": task_id,
                            "bbox": bbox,
                            "start_system_time": system_time,
                            "user_id": user_id,
                            "task_source": task_source,
                            "task_name": task_name
                        }
                        task_active = True
                        flag = False
                    
                    await websocket.send(json.dumps({
                        "ok": True,
                        "msg": "窗口出现，任务开始",
                        "task_id": task_id,
                        "flag": flag
                    }))
                
                # 2. 窗口消失：结束任务
                else:
                    task_id = data.get("task_id")
                    if not task_id:
                        await websocket.send(json.dumps({
                            "ok": False,
                            "msg": "窗口消失时必须传 task_id"
                        }))
                        return
                    
                    with state_lock:
                        # 如果结束前还是注视中，补一条 fixation_end
                        if task_active and flag is True:
                            log_fixation_event(task_id, "fixation_end", system_time)
                        
                        flag = False
                        task_active = False
                        task_info = current_task
                        begin_time = current_task.get("start_system_time")
                        end_time = system_time
                        current_task = None
                    
                    log_task_record(task_id, user_id, task_source, task_name, begin_time, end_time)
                    
                    await websocket.send(json.dumps({
                        "ok": True,
                        "msg": "窗口消失，任务结束",
                        "task_id": task_id,
                        "flag": flag,
                        "task_info": task_info
                    }))
            
            elif message_type == "gaze_point":
                # 获取最新注视点
                global latest_gaze_point, latest_gaze_time
                
                with gaze_point_lock:
                    if latest_gaze_point is None:
                        await websocket.send(json.dumps({
                            "ok": False,
                            "msg": "尚无注视点数据"
                        }))
                        return
                    
                    # 检查数据是否太旧（超过1秒）
                    current_time = time.time() * 1000
                    if current_time - latest_gaze_time > 1000:
                        await websocket.send(json.dumps({
                            "ok": False,
                            "msg": "注视点数据已过期"
                        }))
                        return
                    
                    await websocket.send(json.dumps({
                        "ok": True,
                        "gaze_point": latest_gaze_point,
                        "timestamp": latest_gaze_time
                    }))
            
            else:
                await websocket.send(json.dumps({
                    "ok": False,
                    "msg": "未知的消息类型"
                }))
        except Exception as e:
            print(f"处理WebSocket消息时出错: {e}")
            await websocket.send(json.dumps({
                "ok": False,
                "msg": f"服务器内部错误: {str(e)}"
            }))
    
    async def process_antenna_message(self, websocket, data):
        """处理天线调整WebSocket消息"""
        try:
            # 获取消息类型
            message_type = data.get("type")
            
            if message_type == "start_round":
                # 处理开始回合消息
                await websocket.send(json.dumps({
                    "type": "round_feedback",
                    "should_flash": False,
                    "duration_ms": 0,
                    "message": "回合开始",
                    "echo": data,
                    "serverTime": time.strftime("%Y-%m-%dT%H:%M:%S.%fZ", time.gmtime())
                }))
            
            elif message_type == "end_round":
                # 处理结束回合消息
                await websocket.send(json.dumps({
                    "type": "round_feedback",
                    "should_flash": False,
                    "duration_ms": 0,
                    "message": "回合结束",
                    "echo": data,
                    "serverTime": time.strftime("%Y-%m-%dT%H:%M:%S.%fZ", time.gmtime())
                }))
            
            elif message_type == "update_bbox":
                # 处理更新边界框消息
                await websocket.send(json.dumps({
                    "type": "round_feedback",
                    "should_flash": False,
                    "duration_ms": 0,
                    "message": "边界框更新",
                    "echo": data,
                    "serverTime": time.strftime("%Y-%m-%dT%H:%M:%S.%fZ", time.gmtime())
                }))
            
            else:
                await websocket.send(json.dumps({
                    "type": "round_feedback",
                    "should_flash": False,
                    "duration_ms": 0,
                    "message": "未知的消息类型",
                    "echo": data,
                    "serverTime": time.strftime("%Y-%m-%dT%H:%M:%S.%fZ", time.gmtime())
                }))
        except Exception as e:
            print(f"处理天线调整消息时出错: {e}")
            await websocket.send(json.dumps({
                "type": "round_feedback",
                "should_flash": False,
                "duration_ms": 0,
                "message": f"服务器内部错误: {str(e)}",
                "echo": data,
                "serverTime": time.strftime("%Y-%m-%dT%H:%M:%S.%fZ", time.gmtime())
            }))
            await websocket.send(json.dumps({
                "type": "round_feedback",
                "should_flash": False,
                "duration_ms": 0,
                "message": f"服务器内部错误: {str(e)}",
                "echo": data,
                "serverTime": time.strftime("%Y-%m-%dT%H:%M:%S.%fZ", time.gmtime())
            }))
    
    async def broadcast_gaze_data(self):
        """广播最新的注视点数据给所有客户端"""
        while True:
            await asyncio.sleep(0.033)  # 约30fps
            
            with gaze_point_lock:
                if latest_gaze_point is None:
                    continue
                
                # 检查数据是否太旧（超过1秒）
                current_time = time.time() * 1000
                if current_time - latest_gaze_time > 1000:
                    continue
                
                message = json.dumps({
                    "type": "gaze_update",
                    "gaze_point": latest_gaze_point,
                    "timestamp": latest_gaze_time
                })
            
            # 广播给所有客户端
            with clients_lock:
                for client in connected_clients:
                    try:
                        await client.send(message)
                    except:
                        # 忽略发送失败的客户端
                        pass
    
    async def _run_server(self):
        """运行WebSocket服务器的异步方法"""
        # 启动广播任务
        asyncio.create_task(self.broadcast_gaze_data())
        
        # 启动WebSocket服务器
        async with websockets.serve(
            self.handle_client, 
            self.host, 
            self.port
        ):
            # 等待服务器关闭
            await asyncio.Future()  # 永远等待
    
    def start(self):
        """启动WebSocket服务器"""
        print(f"WebSocket服务器启动在 {self.host}:{self.port}")
        # 初始化数据库
        init_database()
        
        # 使用asyncio.run运行服务器
        asyncio.run(self._run_server())

if __name__ == "__main__":

    # 启动眼动仪
    eyetrackers = tr.find_all_eyetrackers()
    if len(eyetrackers) == 0:
        raise RuntimeError("No eye tracker found")
    eyetracker = eyetrackers[0]
    print("Connected to:", eyetracker.device_name)

    # 订阅实时注视数据流
    eyetracker.subscribe_to(
        tr.EYETRACKER_GAZE_DATA, 
        gaze_data_callback, 
        as_dictionary=True)
    
    # 初始化数据库
    init_database()
    
    # 启动HTTP服务（在后台线程）
    # # http_server = HTTPServer("0.0.0.0", 8081)
    # def run_http_server():
    #     http_server.start()
    
    # http_thread = threading.Thread(target=run_http_server)
    # http_thread.daemon = True
    # http_thread.start()
    
    # 启动WebSocket服务
    print("启动WebSocket服务...")
    ws_server = WebSocketServer("0.0.0.0", 8081)
    ws_server.start()