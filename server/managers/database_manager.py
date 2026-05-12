import sqlite3
import json
import queue
import threading
import atexit
import os
from contextlib import contextmanager
from typing import Dict, Any, Optional, Set, Tuple
from .logger_manager import get_logger

class DatabaseManager:
    """数据库管理器，负责数据库连接、初始化和异步写入"""
    
    def __init__(self, db_path: str = ''):
        if db_path == '':
            # 根据当前文件位置确定数据库路径
            current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(current_dir, 'data', 'radar_operations.db')
        self.db_path = db_path
        self.writer_queue = queue.Queue()
        self.db_thread: Optional[threading.Thread] = None
        self.logger = get_logger("database")
        self._task_settings_lock = threading.Lock()
        self._pending_task_setting_keys: Set[Tuple[Any, ...]] = set()
        self._operation_lock = threading.Lock()
        self._pending_operation_keys: Set[Tuple[Any, ...]] = set()
        self._start_db_worker()
        atexit.register(self._cleanup_db_thread)

    @staticmethod
    def normalize_difficulty_value(value: Any) -> Any:
        """统一数据库中的难度表示为 high / medium / low。"""
        if value is None:
            return value
        s = str(value).strip()
        sl = s.lower()
        if sl in ('high', 'medium', 'low'):
            return sl
        try:
            n = int(float(s))
            if n <= 1:
                return 'high'
            if n == 2:
                return 'medium'
            return 'low'
        except ValueError:
            pass
        if '高' in s:
            return 'high'
        if '中' in s:
            return 'medium'
        if '低' in s:
            return 'low'
        return value
    
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

    def build_task_setting_key(self, scenario: Dict[str, Any], user_id: str, event_owner: str, task_type: str = '') -> Tuple[Any, ...]:
        """生成任务设置去重键。"""
        difficulty_name = self.normalize_difficulty_value(scenario['difficulty_name'])
        return (
            user_id,
            task_type,
            event_owner,
            scenario['repetition_info']['current'],
            int(bool(scenario['is_ai_active'])),
            scenario.get('ai_level_name') or '',
            difficulty_name,
            int(bool(scenario['audio_enabled'])),
        )

    def find_existing_task_setting_id(self, scenario: Dict[str, Any], user_id: str, event_owner: str, task_type: str = '') -> Optional[int]:
        """查找同一任务设置组合和重复序号是否已经有 task_id。"""
        task_setting_key = self.build_task_setting_key(scenario, user_id, event_owner, task_type)
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT task_id FROM task_settings
                    WHERE user_id = ?
                      AND IFNULL(task_type, '') = ?
                      AND IFNULL(event_owner, '') = ?
                      AND repetition_count = ?
                      AND is_ai_active = ?
                      AND IFNULL(ai_level_name, '') = ?
                      AND difficulty_name = ?
                      AND audio_enabled = ?
                    ORDER BY task_id
                    LIMIT 1
                    """,
                    task_setting_key
                )
                row = cursor.fetchone()
                return int(row[0]) if row else None
        except Exception as e:
            self.logger.warning(f"查找已有 task_settings 记录失败: {e}")
            return None

    def clear_task_operations(self, task_id: int) -> None:
        """清除某个 task_id 下的旧操作记录，用于重做未完成任务。"""
        if not task_id:
            return
        with self._operation_lock:
            self._pending_operation_keys = {
                key for key in self._pending_operation_keys
                if not key or key[0] != task_id
            }
        self.execute_async("DELETE FROM user_operations WHERE task_id = ?", (task_id,))
        self.logger.info(f"已排队清除未完成任务的旧操作记录: task_id {task_id}")
    
    def record_task_settings(self, task_id: int, scenario: Dict[str, Any], 
                           user_id: str, event_owner: str, is_practice: bool,
                           task_type: str = '') -> None:
        """记录任务设置"""
        if is_practice:
            self.logger.debug(f"练习模式，跳过 task_settings 记录: task_id {task_id}")
            return

        task_setting_key = self.build_task_setting_key(scenario, user_id, event_owner, task_type)

        with self._task_settings_lock:
            if task_setting_key in self._pending_task_setting_keys:
                self.logger.info(
                    "跳过重复任务设置记录: "
                    f"user_id={user_id}, task_type={task_type}, repetition={scenario['repetition_info']['current']}"
                )
                return

            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        SELECT task_id FROM task_settings
                        WHERE user_id = ?
                          AND IFNULL(task_type, '') = ?
                          AND IFNULL(event_owner, '') = ?
                          AND repetition_count = ?
                          AND is_ai_active = ?
                          AND IFNULL(ai_level_name, '') = ?
                          AND difficulty_name = ?
                          AND audio_enabled = ?
                        LIMIT 1
                        """,
                        task_setting_key
                    )
                    if cursor.fetchone():
                        self.logger.info(
                            "跳过已存在的任务设置记录: "
                            f"user_id={user_id}, task_type={task_type}, repetition={scenario['repetition_info']['current']}"
                        )
                        return
            except Exception as e:
                self.logger.warning(f"检查 task_settings 重复记录失败，将继续写入: {e}")

            self._pending_task_setting_keys.add(task_setting_key)

        sql = """
            INSERT INTO task_settings (
                task_id, task_type, user_id, event_owner, repetition_count, is_ai_active, 
                ai_level_config, difficulty_config, audio_enabled, ai_level_name, difficulty_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        difficulty_name = self.normalize_difficulty_value(scenario['difficulty_name'])
        params = (
            task_id,
            task_type,
            user_id,
            event_owner,
            scenario['repetition_info']['current'],
            scenario['is_ai_active'],
            json.dumps(scenario.get('ai_level_config')),
            json.dumps(scenario['difficulty_config']),
            scenario['audio_enabled'],
            scenario.get('ai_level_name'),
            difficulty_name
        )
        self.execute_async(sql, params)
        self.logger.info(f"记录任务设置: task_id {task_id}")
    
    def record_operation(self, operation: Dict[str, Any], is_practice: bool) -> None:
        """记录用户操作"""
        if is_practice:
            self.logger.debug(f"练习模式，跳过操作记录: {operation.get('operationType')}")
            return

        # 从parameters中提取is_correct值
        parameters = operation.get('parameters', {})
        parameters_json = json.dumps(parameters)
        task_id = operation.get('task_id')
        operation_type = operation.get('operationType')

        single_record_operations = {'settings_update', 'antenna_adjusted', 'sa_emergency', 'sa_emergency_enhanced'}
        actor_scoped_operations = {'target_selected', 'threat_clicked'}
        operation_key = None
        if operation_type in single_record_operations:
            operation_key = (task_id, operation_type)
        elif operation_type in actor_scoped_operations:
            operation_key = (task_id, operation_type, operation.get('event_owner') or '')
        if operation_key and task_id:
            with self._operation_lock:
                if operation_key in self._pending_operation_keys:
                    self.logger.info(f"跳过重复操作记录: task_id={task_id}, operation={operation_type}")
                    return
                try:
                    with self.get_connection() as conn:
                        cursor = conn.cursor()
                        if operation_type in single_record_operations:
                            cursor.execute(
                                "SELECT id FROM user_operations WHERE task_id = ? AND operation_type = ? LIMIT 1",
                                operation_key,
                            )
                        else:
                            cursor.execute(
                                """
                                SELECT id FROM user_operations
                                WHERE task_id = ? AND operation_type = ? AND IFNULL(event_owner, '') = ?
                                LIMIT 1
                                """,
                                operation_key,
                            )
                        if cursor.fetchone():
                            self.logger.info(f"跳过已存在操作记录: task_id={task_id}, operation={operation_type}")
                            return
                except Exception as e:
                    self.logger.warning(f"检查 user_operations 重复记录失败，将继续写入: {e}")
                self._pending_operation_keys.add(operation_key)
        
        # 处理is_correct字段，支持true, false, not_set三个值
        is_correct_value = parameters.get('is_correct', 'not_set')
        if isinstance(is_correct_value, bool):
            is_correct_str = 'true' if is_correct_value else 'false'
        elif is_correct_value in ['true', 'false', 'not_set']:
            is_correct_str = str(is_correct_value)
        else:
            is_correct_str = 'not_set'

        sql = """
            INSERT INTO user_operations (
                task_id, operation_type, timestamp, receive_timestamp, is_active, 
                parameters, user_id, event_owner, is_correct
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            task_id,
            operation_type,
            operation.get('timestamp'),
            operation.get('receive_timestamp'),
            1 if operation.get('isActive', False) else 0,
            parameters_json,
            operation.get('user_id'),
            operation.get('event_owner'),
            is_correct_str
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

                # 检查并创建 platform_external_tasks 表
                self._create_platform_external_tasks_table(cursor, conn)

                # 检查并创建 questionnaire_responses 表
                self._create_questionnaire_responses_table(cursor, conn)

                # 统一历史难度字段表示
                self._normalize_existing_difficulty_values(cursor, conn)
                
            self.logger.info("数据库初始化成功")
        except Exception as e:
            self.logger.error(f"数据库初始化失败: {e}", exc_info=True)

    def _normalize_existing_difficulty_values(self, cursor, conn) -> None:
        """把历史数据库中的数字/中文难度统一成 high / medium / low。"""
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='task_settings'")
        if cursor.fetchone():
            cursor.execute("""
                UPDATE task_settings
                SET difficulty_name = CASE
                    WHEN difficulty_name IN ('1', '1.0') OR difficulty_name LIKE '%高%' THEN 'high'
                    WHEN difficulty_name IN ('2', '2.0') OR difficulty_name LIKE '%中%' THEN 'medium'
                    WHEN difficulty_name IN ('3', '3.0') OR difficulty_name LIKE '%低%' THEN 'low'
                    ELSE difficulty_name
                END
            """)

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='questionnaire_responses'")
        if cursor.fetchone():
            cursor.execute("""
                UPDATE questionnaire_responses
                SET difficulty = CASE
                    WHEN difficulty IN ('1', '1.0') OR difficulty LIKE '%高%' THEN 'high'
                    WHEN difficulty IN ('2', '2.0') OR difficulty LIKE '%中%' THEN 'medium'
                    WHEN difficulty IN ('3', '3.0') OR difficulty LIKE '%低%' THEN 'low'
                    ELSE difficulty
                END
            """)

        conn.commit()
    
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
                    is_correct TEXT DEFAULT 'not_set',
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
        
        if 'is_correct' not in columns:
            self.logger.info("正在添加 is_correct 列...")
            cursor.execute("ALTER TABLE user_operations ADD COLUMN is_correct TEXT DEFAULT 'not_set'")
            conn.commit()
            self.logger.info("is_correct 列添加成功")
    
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
                    task_type TEXT,
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

        if 'task_type' not in columns:
            self.logger.info("正在添加 task_type 列...")
            cursor.execute("ALTER TABLE task_settings ADD COLUMN task_type TEXT")
            conn.commit()

        self._backfill_task_settings_task_type(cursor, conn)

    def _backfill_task_settings_task_type(self, cursor, conn) -> None:
        """根据已有操作记录回填历史 task_settings 的任务类型。"""
        cursor.execute("""
            UPDATE task_settings
            SET task_type = 'RADAR_TARGETING'
            WHERE (task_type IS NULL OR task_type = '')
              AND task_id IN (
                  SELECT DISTINCT task_id FROM user_operations
                  WHERE operation_type IN ('task_start', 'settings_update', 'antenna_adjusted', 'target_selected')
              )
        """)
        cursor.execute("""
            UPDATE task_settings
            SET task_type = 'SA_THREAT_RESPONSE'
            WHERE (task_type IS NULL OR task_type = '')
              AND task_id IN (
                  SELECT DISTINCT task_id FROM user_operations
                  WHERE operation_type IN ('SwitchSA', 'ResetSA', 'threat_clicked')
              )
        """)
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
                    is_completed BOOLEAN DEFAULT FALSE,
                    is_ai_completed BOOLEAN DEFAULT FALSE,
                    is_manual_completed BOOLEAN DEFAULT FALSE,
                    ai_current_scenario_json TEXT,
                    ai_repetition_counter INTEGER DEFAULT 0,
                    manual_current_scenario_json TEXT,
                    manual_repetition_counter INTEGER DEFAULT 0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, task_type)
                );
            """)
            conn.commit()
            self.logger.info("user_progress 表创建成功。")
        else:
            self._update_user_progress_table(cursor, conn)
            
    def _update_user_progress_table(self, cursor, conn) -> None:
        """更新用户进度表结构"""
        self.logger.debug("user_progress 表已存在，检查列...")
        cursor.execute("PRAGMA table_info(user_progress)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'is_completed' not in columns:
            self.logger.info("正在添加 is_completed 列...")
            cursor.execute("ALTER TABLE user_progress ADD COLUMN is_completed BOOLEAN DEFAULT FALSE")
            conn.commit()
            self.logger.info("is_completed 列添加成功")
        
        # 添加AI和手动模式的完成状态字段
        if 'is_ai_completed' not in columns:
            self.logger.info("正在添加 is_ai_completed 列...")
            cursor.execute("ALTER TABLE user_progress ADD COLUMN is_ai_completed BOOLEAN DEFAULT FALSE")
            conn.commit()
            self.logger.info("is_ai_completed 列添加成功")
        
        if 'is_manual_completed' not in columns:
            self.logger.info("正在添加 is_manual_completed 列...")
            cursor.execute("ALTER TABLE user_progress ADD COLUMN is_manual_completed BOOLEAN DEFAULT FALSE")
            conn.commit()
            self.logger.info("is_manual_completed 列添加成功")
        
        # 添加AI模式进度字段
        if 'ai_current_scenario_json' not in columns:
            self.logger.info("正在添加 ai_current_scenario_json 列...")
            cursor.execute("ALTER TABLE user_progress ADD COLUMN ai_current_scenario_json TEXT")
            conn.commit()
            self.logger.info("ai_current_scenario_json 列添加成功")
        
        if 'ai_repetition_counter' not in columns:
            self.logger.info("正在添加 ai_repetition_counter 列...")
            cursor.execute("ALTER TABLE user_progress ADD COLUMN ai_repetition_counter INTEGER DEFAULT 0")
            conn.commit()
            self.logger.info("ai_repetition_counter 列添加成功")
        
        # 添加手动模式进度字段
        if 'manual_current_scenario_json' not in columns:
            self.logger.info("正在添加 manual_current_scenario_json 列...")
            cursor.execute("ALTER TABLE user_progress ADD COLUMN manual_current_scenario_json TEXT")
            conn.commit()
            self.logger.info("manual_current_scenario_json 列添加成功")
        
        if 'manual_repetition_counter' not in columns:
            self.logger.info("正在添加 manual_repetition_counter 列...")
            cursor.execute("ALTER TABLE user_progress ADD COLUMN manual_repetition_counter INTEGER DEFAULT 0")
            conn.commit()
            self.logger.info("manual_repetition_counter 列添加成功")

    def _create_platform_external_tasks_table(self, cursor, conn) -> None:
        """创建外部平台任务表"""
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='platform_external_tasks'
        """)
        if not cursor.fetchone():
            self.logger.info("platform_external_tasks 表不存在，正在创建...")
            cursor.execute("""
                CREATE TABLE platform_external_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    task_category TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    sub_task_seq INTEGER,
                    user_id TEXT,
                    task_name TEXT,
                    gender TEXT,
                    ai_control_time REAL,
                    person_control_time REAL,
                    ai_remind_time REAL,
                    switch_count INTEGER,
                    fire_count INTEGER,
                    fire_success_count INTEGER,
                    raw_message TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            self.logger.info("platform_external_tasks 表创建成功")

    def record_external_task(self, task_id: int, task_category: str,
                             event_type: str, raw_message: str,
                             timestamp: int, user_id: str = None,
                             task_name: str = None, gender: str = None,
                             sub_task_seq: int = None) -> None:
        """记录外部平台任务生命周期事件"""
        sql = """
            INSERT INTO platform_external_tasks (
                task_id, task_category, event_type, sub_task_seq,
                user_id, task_name, gender, raw_message, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (task_id, task_category, event_type, sub_task_seq,
                  user_id, task_name, gender, raw_message, timestamp)
        self.execute_async(sql, params)
        self.logger.info("记录外部任务事件: task_id=%s category=%s event=%s seq=%s",
                         task_id, task_category, event_type, sub_task_seq)

    def _create_questionnaire_responses_table(self, cursor, conn) -> None:
        """创建问卷响应表"""
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='questionnaire_responses'
        """)
        if not cursor.fetchone():
            self.logger.info("questionnaire_responses 表不存在，正在创建...")
            cursor.execute("""
                CREATE TABLE questionnaire_responses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    task_type TEXT NOT NULL,
                    repetition_current INTEGER,
                    repetition_total INTEGER,
                    difficulty TEXT,
                    autonomy_level TEXT,
                    is_ai_active BOOLEAN,
                    is_practice BOOLEAN,
                    answers_json TEXT NOT NULL,
                    source TEXT DEFAULT 'unknown',
                    client_timestamp INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            self.logger.info("questionnaire_responses 表创建成功")
        else:
            cursor.execute("PRAGMA table_info(questionnaire_responses)")
            columns = {row[1] for row in cursor.fetchall()}
            if 'autonomy_level' not in columns:
                cursor.execute("ALTER TABLE questionnaire_responses ADD COLUMN autonomy_level TEXT")
                conn.commit()
                self.logger.info("questionnaire_responses 表已添加 autonomy_level 列")

    def record_questionnaire(self, data: Dict[str, Any]) -> None:
        """记录问卷提交数据"""
        task_info = data.get('taskInfo') or {}
        sql = """
            INSERT INTO questionnaire_responses (
                user_id, task_type, repetition_current, repetition_total,
                difficulty, autonomy_level, is_ai_active, is_practice,
                answers_json, source, client_timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        autonomy_level = task_info.get('autonomyLevel') or task_info.get('autonomy_level')
        legacy_is_ai_active = task_info.get('is_ai_active')
        if legacy_is_ai_active is None:
            legacy_is_ai_active = bool(autonomy_level)
        params = (
            data.get('userId', ''),
            data.get('taskType', ''),
            data.get('repetitionCurrent', 0),
            data.get('repetitionTotal', 0),
            self.normalize_difficulty_value(task_info.get('difficulty')),
            autonomy_level,
            1 if legacy_is_ai_active else 0,
            1 if task_info.get('isPractice') else 0,
            json.dumps(data.get('answers', {})),
            data.get('source', 'unknown'),
            data.get('timestamp'),
        )
        self.execute_async(sql, params)
        self.logger.info("记录问卷: user=%s task=%s rep=%s",
                         data.get('userId'), data.get('taskType'),
                         data.get('repetitionCurrent'))

    def record_external_task_result(self, task_id: int, task_category: str,
                                    raw_message: str, timestamp: int,
                                    user_id: str = None,
                                    ai_control_time: float = None,
                                    person_control_time: float = None,
                                    ai_remind_time: float = None,
                                    switch_count: int = None,
                                    fire_count: int = None,
                                    fire_success_count: int = None) -> None:
        """记录外部平台任务结果"""
        sql = """
            INSERT INTO platform_external_tasks (
                task_id, task_category, event_type, user_id,
                ai_control_time, person_control_time, ai_remind_time,
                switch_count, fire_count, fire_success_count,
                raw_message, timestamp
            ) VALUES (?, ?, 'task_result', ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (task_id, task_category, user_id,
                  ai_control_time, person_control_time, ai_remind_time,
                  switch_count, fire_count, fire_success_count,
                  raw_message, timestamp)
        self.execute_async(sql, params)
        self.logger.info("记录外部任务结果: task_id=%s category=%s", task_id, task_category)


# 全局数据库管理器实例
db_manager = DatabaseManager()
