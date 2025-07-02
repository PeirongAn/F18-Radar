"""
日志管理器
提供统一的日志功能和级别控制
"""

import logging
import os
import sys
from datetime import datetime
from typing import Optional

# 尝试导入colorama，如果失败则使用无颜色版本
try:
    import colorama
    from colorama import Fore, Style
    colorama.init()
    COLORAMA_AVAILABLE = True
except ImportError:
    # 如果colorama不可用，定义空的颜色常量
    class Fore:
        CYAN = ''
        GREEN = ''
        YELLOW = ''
        RED = ''
        MAGENTA = ''
    
    class Style:
        RESET_ALL = ''
    
    COLORAMA_AVAILABLE = False

class ColoredFormatter(logging.Formatter):
    """彩色日志格式化器"""
    
    COLORS = {
        'DEBUG': Fore.CYAN,
        'INFO': Fore.GREEN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
        'CRITICAL': Fore.MAGENTA
    }
    
    ICONS = {
        'DEBUG': '🔍',
        'INFO': '✅',
        'WARNING': '⚠️',
        'ERROR': '❌',
        'CRITICAL': '🚨'
    }
    
    def format(self, record):
        # 获取颜色和图标
        color = self.COLORS.get(record.levelname, '') if COLORAMA_AVAILABLE else ''
        icon = self.ICONS.get(record.levelname, '📝')
        
        # 格式化时间
        timestamp = datetime.fromtimestamp(record.created).strftime('%H:%M:%S')
        
        # 格式化模块名
        module_name = record.name.split('.')[-1] if '.' in record.name else record.name
        
        # 构建日志消息
        reset = Style.RESET_ALL if COLORAMA_AVAILABLE else ''
        formatted_msg = f"{color}{icon} [{timestamp}] {module_name}: {record.getMessage()}{reset}"
        
        # 如果有异常信息，添加到消息中
        if record.exc_info:
            formatted_msg += f"\n{self.formatException(record.exc_info)}"
            
        return formatted_msg

class LoggerManager:
    """日志管理器"""
    
    def __init__(self, name: str = "radar_system", level: str = "INFO"):
        self.name = name
        self.logger = logging.getLogger(name)
        self.setup_logger(level)
    
    def setup_logger(self, level: str = "INFO"):
        """设置日志器"""
        # 清除现有的处理器
        self.logger.handlers.clear()
        
        # 设置日志级别
        log_level = getattr(logging, level.upper(), logging.INFO)
        self.logger.setLevel(log_level)
        
        # 创建控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        
        # 设置彩色格式化器
        console_formatter = ColoredFormatter()
        console_handler.setFormatter(console_formatter)
        
        # 添加处理器
        self.logger.addHandler(console_handler)
        
        # 创建文件处理器（可选）
        if self._should_create_file_handler():
            file_handler = self._create_file_handler(log_level)
            if file_handler:
                self.logger.addHandler(file_handler)
        
        # 防止日志重复
        self.logger.propagate = False
    
    def _should_create_file_handler(self) -> bool:
        """判断是否应该创建文件处理器"""
        # 从环境变量或配置中读取
        return os.getenv('LOG_TO_FILE', 'false').lower() == 'true'
    
    def _create_file_handler(self, log_level) -> Optional[logging.FileHandler]:
        """创建文件处理器"""
        try:
            # 确保日志目录存在
            log_dir = "logs"
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)
            
            # 创建日志文件名（按日期）
            today = datetime.now().strftime('%Y-%m-%d')
            log_file = os.path.join(log_dir, f"radar_system_{today}.log")
            
            # 创建文件处理器
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(log_level)
            
            # 文件格式化器（不使用颜色）
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            file_handler.setFormatter(file_formatter)
            
            return file_handler
        except Exception as e:
            # 使用标准输出，避免循环依赖
            sys.stdout.write(f"⚠️ 无法创建日志文件处理器: {e}\n")
            return None
    
    def set_level(self, level: str):
        """动态设置日志级别"""
        log_level = getattr(logging, level.upper(), logging.INFO)
        self.logger.setLevel(log_level)
        
        # 更新所有处理器的级别
        for handler in self.logger.handlers:
            handler.setLevel(log_level)
    
    def get_logger(self, module_name: str = None) -> logging.Logger:
        """获取特定模块的日志器"""
        if module_name:
            return logging.getLogger(f"{self.name}.{module_name}")
        return self.logger
    
    def debug(self, message: str, module: str = "system"):
        """调试日志"""
        logger = self.get_logger(module)
        logger.debug(message)
    
    def info(self, message: str, module: str = "system"):
        """信息日志"""
        logger = self.get_logger(module)
        logger.info(message)
    
    def warning(self, message: str, module: str = "system"):
        """警告日志"""
        logger = self.get_logger(module)
        logger.warning(message)
    
    def error(self, message: str, module: str = "system", exc_info: bool = False):
        """错误日志"""
        logger = self.get_logger(module)
        logger.error(message, exc_info=exc_info)
    
    def critical(self, message: str, module: str = "system", exc_info: bool = False):
        """严重错误日志"""
        logger = self.get_logger(module)
        logger.critical(message, exc_info=exc_info)

# 全局日志管理器实例
_logger_manager = None

def get_logger_manager() -> LoggerManager:
    """获取全局日志管理器实例"""
    global _logger_manager
    if _logger_manager is None:
        # 从环境变量获取日志级别，默认为INFO
        log_level = os.getenv('LOG_LEVEL', 'INFO')
        _logger_manager = LoggerManager(level=log_level)
    return _logger_manager

def get_logger(module_name: str) -> logging.Logger:
    """便捷函数：获取特定模块的日志器"""
    return get_logger_manager().get_logger(module_name)

# 便捷函数
def debug(message: str, module: str = "system"):
    """调试日志"""
    get_logger_manager().debug(message, module)

def info(message: str, module: str = "system"):
    """信息日志"""
    get_logger_manager().info(message, module)

def warning(message: str, module: str = "system"):
    """警告日志"""
    get_logger_manager().warning(message, module)

def error(message: str, module: str = "system", exc_info: bool = False):
    """错误日志"""
    get_logger_manager().error(message, module, exc_info)

def critical(message: str, module: str = "system", exc_info: bool = False):
    """严重错误日志"""
    get_logger_manager().critical(message, module, exc_info)

def set_log_level(level: str):
    """设置日志级别"""
    get_logger_manager().set_level(level) 