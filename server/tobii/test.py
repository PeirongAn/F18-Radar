import time
import tobii_research as tr
from datetime import datetime

def get_current_timestamp():
    """获取当前电脑的多种时间戳格式"""
    # 方法1: 微秒级时间戳 (和system_request_time_stamp相同格式)
    microsecond_timestamp = int(time.time() * 1000000)
    
    # 方法2: 秒级时间戳
    second_timestamp = int(time.time())
    
    # 方法3: 可读的日期时间格式
    readable_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    
    return {
        'microsecond': microsecond_timestamp,
        'second': second_timestamp,
        'readable': readable_time
    }

def time_synchronization_data_callback(time_synchronization_data):
    """时间同步数据的回调函数"""
    # 获取当前电脑时间戳
    pc_time = get_current_timestamp()
    
    print("\n" + "="*50)
    print("收到时间同步数据:")
    print(f"电脑时间 (可读): {pc_time['readable']}")
    print(f"电脑时间戳 (微秒): {pc_time['microsecond']}")
    print(f"电脑时间戳 (秒): {pc_time['second']}")
    print("-" * 30)
    print(f"眼动仪数据:")
    print(f"  system_request_time_stamp: {time_synchronization_data['system_request_time_stamp']}")
    print(f"  device_time_stamp: {time_synchronization_data['device_time_stamp']}")
    print(f"  system_response_time_stamp: {time_synchronization_data['system_response_time_stamp']}")
    
    # 计算时间差（验证同步关系）
    time_diff = time_synchronization_data['device_time_stamp'] - time_synchronization_data['system_request_time_stamp']
    print(f"  设备时间 - 系统请求时间 = {time_diff} 微秒 ({time_diff/1000000:.2f} 秒)")
    print("="*50)

def time_synchronization_data(eyetracker):
    """订阅时间同步数据"""
    print("\n开始采集时间同步数据...")
    print(f"眼动仪序列号: {eyetracker.serial_number}")
    
    # 订阅前的电脑时间
    start_time = get_current_timestamp()
    print(f"\n订阅前电脑时间: {start_time['readable']}")
    print(f"订阅前时间戳: {start_time['microsecond']} 微秒")
    
    # 订阅时间同步数据
    eyetracker.subscribe_to(
        tr.EYETRACKER_TIME_SYNCHRONIZATION_DATA,
        time_synchronization_data_callback, 
        as_dictionary=True
    )
    
    print("\n已订阅，等待数据采集 (2秒)...")
    
    # 等待收集一些时间同步数据（2秒）
    time.sleep(2)
    
    # 取消订阅
    eyetracker.unsubscribe_from(
        tr.EYETRACKER_TIME_SYNCHRONIZATION_DATA,
        time_synchronization_data_callback
    )
    
    # 订阅后的电脑时间
    end_time = get_current_timestamp()
    print(f"\n取消订阅后电脑时间: {end_time['readable']}")
    print(f"采集持续时间: {end_time['second'] - start_time['second']} 秒")
    print("已取消订阅时间同步数据。")

def find_and_use_eyetracker():
    """查找并使用眼动仪"""
    print("="*60)
    print("眼动仪时间同步数据采集程序")
    print("="*60)
    
    # 程序启动时的电脑时间
    program_start = get_current_timestamp()
    print(f"程序启动时间: {program_start['readable']}")
    print(f"启动时间戳: {program_start['microsecond']} 微秒")
    print("-" * 40)
    
    # 查找所有可用的眼动仪
    eyetrackers = tr.find_all_eyetrackers()
    
    if not eyetrackers:
        print("❌ 未找到眼动仪，请检查连接。")
        return
    
    # 使用第一个找到的眼动仪
    my_eyetracker = eyetrackers[0]
    print(f"✅ 找到眼动仪: {my_eyetracker.model}")
    print(f"   序列号: {my_eyetracker.serial_number}")
    print(f"   地址: {my_eyetracker.address}")
    print("-" * 40)
    
    # 获取时间同步数据
    time_synchronization_data(my_eyetracker)
    
    print("\n" + "="*60)
    print("程序运行结束")
    print("="*60)

# 主程序入口
if __name__ == "__main__":
    find_and_use_eyetracker()