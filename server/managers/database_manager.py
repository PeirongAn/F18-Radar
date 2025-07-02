import sqlite3
import json
import queue
import threading
import atexit
import os
from contextlib import contextmanager
from typing import Dict, Any, Optional
from .logger_manager import get_logger

class DatabaseManager:
    """数据库管理器，负责数据库连接、初始化和异步写入"""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            # 根据当前文件位置确定数据库路径
            current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(current_dir, 'data', 'radar_operations.db')
        self.db_path = db_path
        self.writer_queue = queue.Queue()
        self.db_thread: Optional[threading.Thread] = None
        self.logger = get_logger("database")
        self._start_db_worker()
        atexit.register(self._cleanup_db_thread)
    
    def _start_db_worker(self) -> None:
        """启动数据库工作线程"""
        self.db_thread = threading.Thread(target=self._db_worker, daemon=True)
        self.db_thread.start()
    
    def _db_worker(self) -> None:
        """在后台线程中同步处理所有数据库写入操作"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute('PRAGMA journal_mode=WAL;')
        self.logger.info("DB worker thread started, connection in WAL mode.")
        
        while True:
            try:
                sql, params = self.writer_queue.get(timeout=1)
                
                if sql is None:  # 停止信号
                    self.logger.info("DB worker thread received shutdown signal.")
                    break
                    
                conn.execute(sql, params)
                conn.commit()
                
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"Failed to execute DB operation: {e}", exc_info=True)
                
        conn.close()
        self.logger.info("DB worker thread stopped and connection closed.")
    
    def _cleanup_db_thread(self) -> None:
        """清理数据库线程"""
        self.logger.info("Requesting DB worker thread to shut down...")
        self.writer_queue.put((None, None))
        if self.db_thread:
            self.db_thread.join(timeout=5)
        self.logger.info("DB worker thread has been shut down.")
    
    @contextmanager
    def get_connection(self):
        """获取数据库连接（只读操作）"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.execute('PRAGMA journal_mode=WAL;')
            yield conn
        finally:
            if conn:
                conn.close()
    
    def execute_async(self, sql: str, params: tuple) -> None:
        """异步执行SQL语句"""
        self.writer_queue.put((sql, params))
    
    def record_task_settings(self, task_id: int, scenario: Dict[str, Any], 
                           user_id: str, event_owner: str, is_practice: bool) -> None:
        """记录任务设置"""
        if is_practice:
            self.logger.debug(f"练习模式，跳过 task_settings 记录: task_id {task_id}")
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
        self.execute_async(sql, params)
        self.logger.info(f"记录任务设置: task_id {task_id}")
    
    def record_operation(self, operation: Dict[str, Any], is_practice: bool) -> None:
        """记录用户操作"""
        if is_practice:
            self.logger.debug(f"练习模式，跳过操作记录: {operation.get('operationType')}")
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
        self.execute_async(sql, params)
    
    def initialize_database(self) -> None:
        """初始化数据库表结构"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # 检查并创建 user_operations 表
                self._create_user_operations_table(cursor, conn)
                
                # 检查并创建 task_settings 表
                self._create_task_settings_table(cursor, conn)
                
                # 检查并创建 user_progress 表
                self._create_user_progress_table(cursor, conn)
                
            self.logger.info("数据库初始化成功")
        except Exception as e:
            self.logger.error(f"数据库初始化失败: {e}", exc_info=True)
    
    def _create_user_operations_table(self, cursor, conn) -> None:
        """创建用户操作表"""
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='user_operations'
        """)
        
        if not cursor.fetchone():
            self.logger.info("user_operations 表不存在，正在创建...")
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
            self.logger.info("user_operations 表创建成功")
        else:
            self._update_user_operations_table(cursor, conn)
    
    def _update_user_operations_table(self, cursor, conn) -> None:
        """更新用户操作表结构"""
        self.logger.debug("user_operations 表已存在，检查列...")
        cursor.execute("PRAGMA table_info(user_operations)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'receive_timestamp' not in columns:
            self.logger.info("正在添加 receive_timestamp 列...")
            cursor.execute("ALTER TABLE user_operations ADD COLUMN receive_timestamp INTEGER")
            conn.commit()
            self.logger.info("receive_timestamp 列添加成功")
        
        if 'event_owner' not in columns:
            self.logger.info("正在添加 event_owner 列...")
            cursor.execute("ALTER TABLE user_operations ADD COLUMN event_owner TEXT")
            conn.commit()
            self.logger.info("event_owner 列添加成功")
    
    def _create_task_settings_table(self, cursor, conn) -> None:
        """创建任务设置表"""
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='task_settings'")
        if not cursor.fetchone():
            self.logger.info("task_settings 表不存在，正在创建...")
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
            self.logger.info("task_settings 表创建成功")
        else:
            self._update_task_settings_table(cursor, conn)
    
    def _update_task_settings_table(self, cursor, conn) -> None:
        """更新任务设置表结构"""
        self.logger.debug("task_settings 表已存在，检查列...")
        cursor.execute("PRAGMA table_info(task_settings)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'user_id' not in columns:
            self.logger.info("正在添加 user_id 列...")
            cursor.execute("ALTER TABLE task_settings ADD COLUMN user_id TEXT")
            conn.commit()
        
        if 'event_owner' not in columns:
            self.logger.info("正在添加 event_owner 列...")
            cursor.execute("ALTER TABLE task_settings ADD COLUMN event_owner TEXT")
            conn.commit()
    
    def _create_user_progress_table(self, cursor, conn) -> None:
        """创建用户进度表"""
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_progress'")
        if not cursor.fetchone():
            self.logger.info("user_progress 表不存在，正在创建...")
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
            self.logger.info("user_progress 表创建成功。")
        else:
            self.logger.debug("user_progress 表已存在。")

# 全局数据库管理器实例
db_manager = DatabaseManager() 