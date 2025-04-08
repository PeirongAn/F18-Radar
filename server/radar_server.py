import asyncio
import websockets
import json
import numpy as np
import time

# 用于存储目标信息的全局变量
unknown_targets = []
own_heading = 278  # 当前航向 (度)
radar_azimuth = 0  # 固定的雷达方位角值
radar_range = 80   # 雷达范围 (海里)
scan_angle = 60    # 扫描角度 (度)

# 初始化未知目标数据，使用与mockUnknownTargets.ts相同的数据结构
def initialize_targets():
    global unknown_targets
    
    # 偏移值，用于设置目标的初始位置
    offsets = [
        [-60, 40],   # 目标1偏移 - 左上方高处（友机）
        [60, 30],    # 目标2偏移 - 右上方高处（友机）
        [10, -30],   # 目标3偏移 - 低处中央偏右（敌机）
        [-40, 20],   # 目标4偏移 - 中左位置（友机）
        [70, -20]    # 目标5偏移 - 右侧低处（敌机）
    ]
    
    # 屏幕中心位置（将在前端计算实际显示位置）
    center_x = 0
    center_y = 0
    
    # 创建目标数据 - 按照图示2个敌机，3个友机
    unknown_targets = [
        {
            "id": "target-1",
            "position": {"x": center_x + offsets[0][0], "y": center_y + offsets[0][1]},
            "history": [],
            "speed": 5,
            "direction": np.pi * 3 / 4,  # 向左下方移动（远离）
            "type": "friend"  # 友机1 - 高处左侧，远离
        },
        {
            "id": "target-2",
            "position": {"x": center_x + offsets[1][0], "y": center_y + offsets[1][1]},
            "history": [],
            "speed": 4,
            "direction": np.pi,  # 向左水平移动（平行）
            "type": "friend"  # 友机2 - 高处右侧，平行移动
        },
        {
            "id": "target-3",
            "position": {"x": center_x + offsets[2][0], "y": center_y + offsets[2][1]},
            "history": [],
            "speed": 9,  # 速度更快
            "direction": -np.pi * 3 / 4,  # 向右上方移动（接近）
            "type": "army"  # 敌机1 - 低处中央，向上接近
        },
        {
            "id": "target-4",
            "position": {"x": center_x + offsets[3][0], "y": center_y + offsets[3][1]},
            "history": [],
            "speed": 3,
            "direction": np.pi / 2,  # 向下移动（平行）
            "type": "friend"  # 友机3 - 左侧中间位置，平行移动
        },
        {
            "id": "target-5",
            "position": {"x": center_x + offsets[4][0], "y": center_y + offsets[4][1]},
            "history": [],
            "speed": 10,
            "direction": np.pi * 3 / 4,  # 向左下移动（接近）
            "type": "army"  # 敌机2 - 右侧低处，向左接近
        }
    ]
    print(f"已初始化 {len(unknown_targets)} 个未知目标")

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
def should_include_targets():
    global scan_angle, radar_range
    
    print("\n【调试】===== 条件检查开始 =====")
    # 打印当前的值
    print(f"【调试】当前状态: scan_angle={scan_angle} (类型: {type(scan_angle)}), radar_range={radar_range} (类型: {type(radar_range)})")
    
    # 使用更宽松的条件检查
    try:
        scan_angle_float = float(scan_angle)
        radar_range_float = float(radar_range)
        
        # 放宽条件: 扫描角度在29.5到30.5之间，范围在79.5到80.5之间
        scan_angle_condition = 29.5 <= scan_angle_float <= 30.5
        range_condition = 79.5 <= radar_range_float <= 80.5
        
        # 如果要特别放宽条件以便测试，可以取消下面的注释
        # scan_angle_condition = True
        # range_condition = True
        
        print(f"【调试】条件值: scan_angle={scan_angle_float}, range={radar_range_float}")
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

# 处理从客户端接收的消息
async def handle_client_message(message_str):
    global radar_range, scan_angle, unknown_targets
    
    try:
        print("\n===== 接收到客户端消息 =====")
        print(f"原始消息: {message_str}")
        
        # 解析消息
        message = json.loads(message_str)
        print(f"解析后的消息: {message}")
        
        # 检查消息类型
        if message.get('type') == 'settings_update':
            print("消息类型: settings_update")
            
            # 记录设置更新前的条件状态
            prev_should_include = should_include_targets()
            print(f"更新前是否应包含目标: {prev_should_include}")
            
            # 更新设置
            if 'range' in message:
                old_range = radar_range
                try:
                    radar_range = float(message['range'])
                    print(f"已更新雷达范围: {old_range} -> {radar_range} 海里")
                except (ValueError, TypeError) as e:
                    print(f"解析range值出错: {e}, 原始值: {message['range']}")
                
            if 'scanAngle' in message:
                old_angle = scan_angle
                try:
                    scan_angle = float(message['scanAngle'])
                    print(f"已更新扫描角度: {old_angle} -> {scan_angle} 度")
                except (ValueError, TypeError) as e:
                    print(f"解析scanAngle值出错: {e}, 原始值: {message['scanAngle']}")
            
            # 检查更新后是否满足条件
            current_should_include = should_include_targets()
            print(f"更新后是否应包含目标: {current_should_include}")
            
            # 返回是否需要包含目标数据的标志
            print("===== 客户端消息处理完成 =====\n")
            return True, current_should_include
        
        # 处理重置目标的消息
        elif message.get('type') == 'reset_targets':
            print("消息类型: reset_targets")
            print("重置所有目标数据")
            
            # 重新初始化目标数据
            initialize_targets()
            
            # 返回标志，表明应该立即返回不包含目标的数据
            return True, False
            
    except json.JSONDecodeError as e:
        print(f"解析JSON时出错: {e}")
    except Exception as e:
        print(f"处理客户端消息时出错: {e}")
    
    print("===== 客户端消息处理失败 =====\n")
    return False, False

# WebSocket处理函数
async def radar_server(websocket):
    print("【服务器】客户端已连接")
    try:
        # 初始连接时发送不包含目标数据的基础数据
        initial_data = get_radar_data(include_targets=False)
        initial_json = json.dumps(initial_data)
        await websocket.send(initial_json)
        print(f"【服务器】已发送基础数据（不含目标），长度: {len(initial_json)}")
        
        # 接收并处理客户端消息
        while True:
            try:
                # 等待消息，但设置超时以保持连接活跃
                message = await asyncio.wait_for(websocket.recv(), timeout=60)
                print(f"【服务器】接收到消息: {message[:50]}..." if len(message) > 50 else message)
                
                # 处理消息
                settings_updated, include_targets = await handle_client_message(message)
                
                # 如果设置被更新，发送新的数据
                if settings_updated:
                    # 根据条件决定是否包含目标数据
                    data = get_radar_data(include_targets=include_targets)
                    
                    # 添加一个时间戳确保每次发送的数据不同
                    data["_timestamp"] = time.time()
                    
                    # 发送前检查数据格式
                    data_json = json.dumps(data)
                    
                    # 记录发送的内容
                    if include_targets:
                        print(f"【服务器】正在发送包含目标的数据，JSON长度: {len(data_json)}")
                        print(f"【服务器】数据键: {list(data.keys())}")
                        if 'externalTargets' in data:
                            print(f"【服务器】externalTargets长度: {len(data['externalTargets'])}")
                    else:
                        print(f"【服务器】正在发送不含目标的数据，JSON长度: {len(data_json)}")
                    
                    # 发送数据
                    await websocket.send(data_json)
                    
                    # 确认数据已发送
                    if include_targets:
                        print("【服务器】✅ 已发送更新后的数据（包含目标）")
                    else:
                        print("【服务器】✅ 已发送更新后的数据（不含目标）")
            except asyncio.TimeoutError:
                # 超时，只是用来保持连接活跃
                pass
            except websockets.exceptions.ConnectionClosed:
                # 连接已关闭
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
    
    # 启动服务器
    async with websockets.serve(radar_server, "0.0.0.0", 8765):
        print("雷达服务器已启动于 ws://localhost:8765")
        await asyncio.Future()  # 运行直到被取消

if __name__ == "__main__":
    asyncio.run(main()) 