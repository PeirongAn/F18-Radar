"""
管理器模块
包含各种功能管理器：配置、数据库、任务、目标、威胁
"""

from .config_manager import config_manager, ConfigManager
from .database_manager import db_manager, DatabaseManager
from .task_manager import TaskScenarioManager, generate_task_id
from .target_manager import target_manager, TargetManager
from .threat_manager import threat_manager, ThreatManager
from .logger_manager import (
    get_logger_manager, get_logger, set_log_level,
    debug, info, warning, error, critical
)

__all__ = [
    'config_manager', 'ConfigManager',
    'db_manager', 'DatabaseManager', 
    'TaskScenarioManager', 'generate_task_id',
    'target_manager', 'TargetManager',
    'threat_manager', 'ThreatManager',
    'get_logger_manager', 'get_logger', 'set_log_level',
    'debug', 'info', 'warning', 'error', 'critical'
] 