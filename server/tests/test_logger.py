#!/usr/bin/env python3
"""
测试日志系统
"""

import sys
import os

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def test_logger_basic():
    """测试基本日志功能"""
    print("🧪 测试基本日志功能...")
    
    from managers.logger_manager import debug, info, warning, error, critical
    
    # 测试各种日志级别
    debug("这是一个调试消息", "test")
    info("这是一个信息消息", "test")
    warning("这是一个警告消息", "test")
    error("这是一个错误消息", "test")
    critical("这是一个严重错误消息", "test")
    
    print("✅ 基本日志功能测试完成")

def test_logger_levels():
    """测试日志级别控制"""
    print("\n🧪 测试日志级别控制...")
    
    from managers.logger_manager import get_logger_manager, debug, info, warning, error
    
    logger_manager = get_logger_manager()
    
    # 测试不同级别
    levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR']
    
    for level in levels:
        print(f"\n--- 设置日志级别为 {level} ---")
        logger_manager.set_level(level)
        
        debug("调试消息 (应该只在DEBUG级别显示)", "test")
        info("信息消息 (应该在INFO及以上级别显示)", "test")
        warning("警告消息 (应该在WARNING及以上级别显示)", "test")
        error("错误消息 (应该在所有级别显示)", "test")
    
    print("\n✅ 日志级别控制测试完成")

def test_module_specific_logger():
    """测试模块特定的日志器"""
    print("\n🧪 测试模块特定的日志器...")
    
    from managers.logger_manager import get_logger
    
    # 创建不同模块的日志器
    db_logger = get_logger("database")
    ws_logger = get_logger("websocket")
    config_logger = get_logger("config")
    
    db_logger.info("数据库连接成功")
    ws_logger.info("WebSocket服务器启动")
    config_logger.warning("配置文件未找到，使用默认配置")
    
    print("✅ 模块特定日志器测试完成")

def test_exception_logging():
    """测试异常日志记录"""
    print("\n🧪 测试异常日志记录...")
    
    from managers.logger_manager import error
    
    try:
        # 故意引发异常
        result = 1 / 0
    except Exception as e:
        error("除零错误演示", "test", exc_info=True)
    
    print("✅ 异常日志记录测试完成")

def test_environment_variables():
    """测试环境变量控制"""
    print("\n🧪 测试环境变量控制...")
    
    # 设置环境变量
    os.environ['LOG_LEVEL'] = 'WARNING'
    
    # 创建新的日志管理器实例（模拟重启）
    from managers.logger_manager import LoggerManager
    
    test_manager = LoggerManager()
    
    print("--- 使用环境变量 LOG_LEVEL=WARNING ---")
    test_manager.debug("这条调试消息不应该显示")
    test_manager.info("这条信息消息不应该显示")
    test_manager.warning("这条警告消息应该显示")
    test_manager.error("这条错误消息应该显示")
    
    # 清理环境变量
    if 'LOG_LEVEL' in os.environ:
        del os.environ['LOG_LEVEL']
    
    print("✅ 环境变量控制测试完成")

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 雷达系统日志模块测试")
    print("=" * 60)
    
    try:
        test_logger_basic()
        test_logger_levels()
        test_module_specific_logger()
        test_exception_logging()
        test_environment_variables()
        
        print("\n" + "=" * 60)
        print("🎉 所有日志测试通过！")
        print("💡 使用方法:")
        print("   - 设置环境变量 LOG_LEVEL 控制日志级别")
        print("   - 支持级别: DEBUG, INFO, WARNING, ERROR, CRITICAL")
        print("   - 设置环境变量 LOG_TO_FILE=true 启用文件日志")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc() 