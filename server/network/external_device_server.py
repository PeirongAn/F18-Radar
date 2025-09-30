#!/usr/bin/env python3
"""
外部设备WebSocket客户端
连接到8765端口的外部服务，监听ForceSwitch控制数据
将ForceSwitch数据转换为TDC坐标并广播给雷达客户端
"""

import asyncio
import json
import websockets
import time
from typing import Dict, Any, Optional
import logging

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ExternalDeviceClient:
    """外部设备WebSocket客户端"""
    
    def __init__(self, host: str = "localhost", port: int = 8765):
        self.host = host
        self.port = port
        self.radar_clients = set()      # 存储雷达客户端连接
        self.last_tdc_data = None       # 缓存最后的TDC数据
        self.websocket = None           # 外部设备连接
        self.message_count = 0          # 消息计数器
        self.is_connected = False       # 连接状态
        self.reconnect_interval = 5     # 重连间隔（秒）
        self.last_force_switch = None   # 缓存上一次的ForceSwitch数据
        self.change_threshold = 0.001   # ForceSwitch变化阈值
        
    def has_force_switch_changed(self, new_force_switch):
        """检测ForceSwitch是否发生了显著变化"""
        if self.last_force_switch is None:
            return True  # 第一次接收数据
        
        if len(new_force_switch) < 2 or len(self.last_force_switch) < 2:
            return True  # 数据格式异常，当作变化处理
        
        # 计算变化幅度
        x_change = abs(new_force_switch[0] - self.last_force_switch[0])
        y_change = abs(new_force_switch[1] - self.last_force_switch[1])
        
        # 如果任一坐标的变化超过阈值，则认为发生了变化
        return x_change > self.change_threshold or y_change > self.change_threshold
    
    def set_change_threshold(self, threshold: float):
        """设置ForceSwitch变化检测阈值"""
        self.change_threshold = max(0.0001, min(0.1, threshold))  # 限制在合理范围内
        print(f"🔧 ForceSwitch变化阈值已设置为: {self.change_threshold:.6f}")
        
    async def register_radar_client(self, websocket):
        """注册雷达客户端连接"""
        self.radar_clients.add(websocket)
        client_address = getattr(websocket, 'remote_address', 'unknown')
        print(f"\n📱 【雷达客户端注册】")
        print(f"   📍 客户端地址: {client_address}")
        print(f"   📊 当前连接数: {len(self.radar_clients)}")
        print(f"   🎯 已准备接收TDC坐标消息")
        logger.info(f"雷达客户端已注册，当前连接数: {len(self.radar_clients)}")
        
        # 如果有缓存的TDC数据，立即发送给新连接的客户端
        if self.last_tdc_data:
            try:
                message_str = json.dumps(self.last_tdc_data)
                if hasattr(websocket, 'send_str'):
                    # aiohttp WebSocketResponse
                    await websocket.send_str(message_str)
                elif hasattr(websocket, 'send'):
                    # websockets WebSocket
                    await websocket.send(message_str)
                else:
                    raise Exception(f"不支持的WebSocket客户端类型: {type(websocket)}")
                
                print(f"   📤 已发送缓存的TDC数据: {self.last_tdc_data}")
                logger.info("已向新雷达客户端发送缓存的TDC数据")
            except Exception as e:
                print(f"   ❌ 发送缓存数据失败: {e}")
                logger.error(f"向新雷达客户端发送TDC数据失败: {e}")
    
    def unregister_radar_client(self, websocket):
        """注销雷达客户端连接"""
        self.radar_clients.discard(websocket)
        logger.info(f"雷达客户端已断开，当前连接数: {len(self.radar_clients)}")
    
    async def connect_to_external_device(self):
        """连接到外部设备WebSocket服务"""
        uri = f"ws://{self.host}:{self.port}"
        
        while True:
            try:
                print(f"\n🔌 尝试连接到外部设备服务: {uri}")
                logger.info(f"尝试连接到外部设备服务: {uri}")
                
                async with websockets.connect(uri) as websocket:
                    self.websocket = websocket
                    self.is_connected = True
                    
                    print(f"✅ 【连接成功】已连接到外部设备服务!")
                    print(f"   📍 服务地址: {uri}")
                    print(f"   📊 雷达客户端连接数: {len(self.radar_clients)}")
                    print(f"   🎯 开始监听ForceSwitch数据...")
                    logger.info(f"已连接到外部设备服务: {uri}")
                    
                    # 监听消息
                    async for message in websocket:
                        await self.process_external_message(message)
                        
            except websockets.exceptions.ConnectionClosed:
                print(f"🔌 与外部设备服务的连接已断开")
                logger.info("与外部设备服务的连接已断开")
            except ConnectionRefusedError:
                print(f"❌ 无法连接到外部设备服务 {uri}")
                print(f"   可能原因: 外部设备服务未启动或端口不正确")
                logger.error(f"无法连接到外部设备服务 {uri}")
            except Exception as e:
                print(f"❌ 连接外部设备服务时出错: {e}")
                logger.error(f"连接外部设备服务时出错: {e}")
            finally:
                self.websocket = None
                self.is_connected = False
                
            print(f"⏳ {self.reconnect_interval}秒后尝试重新连接...")
            await asyncio.sleep(self.reconnect_interval)
    
    async def process_external_message(self, message_str: str):
        """处理外部设备消息"""
        try:
            # 增加消息计数
            self.message_count += 1
            
            # 解析JSON消息（静默解析，不打印原始数据）
            data = json.loads(message_str)
            
            # 提取ForceSwitch数据
            force_switch = data.get('ForceSwitch')
            if force_switch is None or len(force_switch) < 2:
                # 只在第一次或偶尔打印警告，避免刷屏
                if self.message_count % 100 == 1:  # 每100条消息打印一次警告
                    print(f"⚠️  消息#{self.message_count}: 缺少ForceSwitch数据")
                    logger.warning("消息中缺少ForceSwitch数据或数据不完整")
                return
            
            # 检查ForceSwitch是否发生变化
            if not self.has_force_switch_changed(force_switch):
                # 数据未变化，静默跳过
                return
            
            # 数据发生了变化，开始处理
            print(f"\n🔄 【ForceSwitch变化 #{self.message_count}】")
            print(f"   ⏰ 时间: {time.strftime('%H:%M:%S')}")
            
            # 提取坐标数据
            x = float(force_switch[0])
            y = float(force_switch[1])
            timestamp = data.get('timestamp', time.time())
            
            # 显示变化信息
            if self.last_force_switch is not None:
                old_x, old_y = self.last_force_switch[0], self.last_force_switch[1]
                print(f"   📍 坐标变化: [{old_x:.6f}, {old_y:.6f}] → [{x:.6f}, {y:.6f}]")
                x_change = abs(x - old_x)
                y_change = abs(y - old_y)
                print(f"   📏 变化幅度: Δx={x_change:.6f}, Δy={y_change:.6f}")
            else:
                print(f"   📍 初始坐标: [{x:.6f}, {y:.6f}]")
            
            # 更新缓存的ForceSwitch数据
            self.last_force_switch = [x, y]
            
            logger.info(f"ForceSwitch变化: x={x:.6f}, y={y:.6f}, timestamp={timestamp}")
            
            # 验证坐标范围
            original_x, original_y = x, y
            x = max(-1.0, min(1.0, x))  # 限制在-1到1范围内
            y = max(-1.0, min(1.0, y))
            
            if x != original_x or y != original_y:
                print(f"   ⚠️  坐标范围调整: ({original_x:.6f}, {original_y:.6f}) → ({x:.6f}, {y:.6f})")
            
            # 构造TDC坐标消息
            tdc_message = {
                "type": "tdc_coordinate",
                "x": x,
                "y": y,
                "timestamp": timestamp
            }
            
            print(f"   🎯 TDC消息: x={x:.6f}, y={y:.6f}")
            print(f"   📡 广播给 {len(self.radar_clients)} 个雷达客户端")
            
            # 缓存数据
            self.last_tdc_data = tdc_message
            
            # 广播给所有雷达客户端
            await self.broadcast_to_radar_clients(tdc_message)
            
        except json.JSONDecodeError as e:
            logger.error(f"解析外部设备JSON消息失败: {e}")
        except (ValueError, TypeError) as e:
            logger.error(f"处理外部设备坐标数据失败: {e}")
        except Exception as e:
            logger.error(f"处理外部设备消息时出现未知错误: {e}")
    
    async def broadcast_to_radar_clients(self, message: Dict[str, Any]):
        """广播消息给所有雷达客户端"""
        if not self.radar_clients:
            print(f"   ⚠️  没有雷达客户端连接，跳过广播")
            logger.debug("没有雷达客户端连接，跳过广播")
            return
        
        message_str = json.dumps(message)
        print(f"   📤 准备发送消息: {message_str}")
        disconnected_clients = set()
        
        success_count = 0
        for client in self.radar_clients:
            try:
                # 检查客户端类型并使用相应的发送方法
                if hasattr(client, 'send_str'):
                    # aiohttp WebSocketResponse
                    await client.send_str(message_str)
                elif hasattr(client, 'send'):
                    # websockets WebSocket
                    await client.send(message_str)
                else:
                    raise Exception(f"不支持的WebSocket客户端类型: {type(client)}")
                
                success_count += 1
                client_address = getattr(client, 'remote_address', 'unknown')
                print(f"   ✅ 成功发送给雷达客户端: {client_address}")
                logger.info(f"已向雷达客户端发送TDC坐标: {message}")
            except websockets.exceptions.ConnectionClosed:
                client_address = getattr(client, 'remote_address', 'unknown')
                print(f"   ❌ 雷达客户端连接已关闭: {client_address}")
                logger.info("雷达客户端连接已关闭")
                disconnected_clients.add(client)
            except Exception as e:
                print(f"   ❌ 发送失败: {e}")
                logger.error(f"向雷达客户端发送消息失败: {e}")
                disconnected_clients.add(client)
        
        print(f"   📊 广播结果: {success_count}/{len(self.radar_clients)} 个客户端成功接收")
        
        # 清理断开的连接
        for client in disconnected_clients:
            self.radar_clients.discard(client)
        
        if disconnected_clients:
            logger.info(f"已清理 {len(disconnected_clients)} 个断开的雷达客户端连接")
    
    async def start_client(self):
        """启动外部设备WebSocket客户端"""
        print(f"\n🚀 正在启动外部设备WebSocket客户端...")
        print(f"🎯 目标服务: ws://{self.host}:{self.port}")
        print(f"📋 客户端配置:")
        print(f"   - 雷达客户端连接数: {len(self.radar_clients)}")
        print(f"   - 自动重连间隔: {self.reconnect_interval}秒")
        print(f"   - ForceSwitch变化阈值: {self.change_threshold:.6f}")
        print(f"   - 变化检测: 启用 (只有坐标变化时才发送)")
        print(f"✅ 外部设备客户端已准备就绪，可以接受雷达客户端注册")
        print("-" * 50)
        
        logger.info(f"启动外部设备WebSocket客户端，目标: {self.host}:{self.port}")
        
        # 开始连接循环（这个会一直运行）
        await self.connect_to_external_device()
    
    async def stop_client(self):
        """停止客户端"""
        if self.websocket:
            logger.info("正在断开外部设备WebSocket连接...")
            await self.websocket.close()
            logger.info("外部设备WebSocket客户端已停止")

# 全局实例
external_device_client = ExternalDeviceClient()

# 便捷函数
async def start_external_device_client(host: str = "localhost", port: int = 8765):
    """启动外部设备客户端的便捷函数"""
    external_device_client.host = host
    external_device_client.port = port
    await external_device_client.start_client()

async def register_radar_client(websocket):
    """注册雷达客户端的便捷函数"""
    print(f"🔧 [DEBUG] register_radar_client被调用")
    print(f"🔧 [DEBUG] external_device_client对象: {external_device_client}")
    print(f"🔧 [DEBUG] 当前radar_clients数量: {len(external_device_client.radar_clients)}")
    await external_device_client.register_radar_client(websocket)

def unregister_radar_client(websocket):
    """注销雷达客户端的便捷函数"""
    external_device_client.unregister_radar_client(websocket)

if __name__ == "__main__":
    # 独立运行测试
    logger.info("独立启动外部设备WebSocket客户端")
    asyncio.run(start_external_device_client())
