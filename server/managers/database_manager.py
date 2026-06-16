import sqlite3
import json
import queue
import threading
import atexit
import os
from contextlib import contextmanager
from typing import Dict, Any, List, Optional, Set, Tuple
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
        self._shutdown_lock = threading.Lock()
        self._shutdown_requested = False
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
                
        try:
            conn.commit()
        except sqlite3.Error:
            pass
        for sql in ("PRAGMA wal_checkpoint(TRUNCATE)", "PRAGMA journal_mode=DELETE"):
            try:
                conn.execute(sql).fetchall()
            except sqlite3.Error:
                pass
        conn.close()
        self.logger.info("DB worker thread stopped and connection closed.")
    
    def _cleanup_db_thread(self) -> None:
        """清理数据库线程"""
        self.shutdown()

    def shutdown(self, timeout: float = 5) -> None:
        """Stop the background SQLite writer before process-level WAL cleanup."""
        with self._shutdown_lock:
            if self._shutdown_requested:
                return
            self._shutdown_requested = True

        self.logger.info("Requesting DB worker thread to shut down...")
        self.writer_queue.put((None, None))
        if self.db_thread:
            self.db_thread.join(timeout=timeout)
            if self.db_thread.is_alive():
                self.logger.warning("DB worker thread did not stop within %.1f seconds.", timeout)
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

    @staticmethod
    def _extract_trust_events(parameters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从操作参数中提取 trust_events，兼容顶层和 extra 嵌套结构。"""
        direct_events = parameters.get('trust_events')
        if isinstance(direct_events, list):
            return [event for event in direct_events if isinstance(event, dict)]

        extra = parameters.get('extra')
        if isinstance(extra, dict):
            nested_events = extra.get('trust_events')
            if isinstance(nested_events, list):
                return [event for event in nested_events if isinstance(event, dict)]

        return []

    @staticmethod
    def _empty_trust_history_stats() -> Dict[str, Any]:
        return {
            'event_count': 0,
            'human_event_count': 0,
            'ai_event_count': 0,
            'human_decision_count': 0,
            'human_accept_count': 0,
            'human_reject_count': 0,
            'max_consecutive_reject_count': 0,
            'direct_accept_without_evidence_count': 0,
            'evidence_viewed_count': 0,
            'manual_review_count': 0,
            'result_confirmed_count': 0,
            'average_confirmation_latency_ms': None,
            'last_event_at': None,
            # —— 真值口径（AI 推荐正确性已知时统计）——
            'truth_known_count': 0,
            'ai_correct_count': 0,
            'ai_incorrect_count': 0,
            'unwarranted_reject_count': 0,   # 拒了对的（欠信任信号）
            'justified_reject_count': 0,     # 应该拒（正确校准）
            'unwarranted_accept_count': 0,   # 无证据接了错的（过信任信号）
            'ai_accuracy': None,
            'truth_coverage': None,
            '_latency_total': 0,
            '_latency_count': 0,
            '_current_reject_streak': 0,
        }

    @staticmethod
    def _public_trust_history_stats(stats: Dict[str, Any]) -> Dict[str, Any]:
        public_stats = dict(stats)
        latency_count = public_stats.pop('_latency_count', 0)
        latency_total = public_stats.pop('_latency_total', 0)
        public_stats.pop('_current_reject_streak', None)
        public_stats['average_confirmation_latency_ms'] = (
            latency_total / latency_count if latency_count else None
        )
        truth_known = public_stats.get('truth_known_count', 0)
        decision_count = public_stats.get('human_decision_count', 0)
        public_stats['ai_accuracy'] = (
            public_stats.get('ai_correct_count', 0) / truth_known if truth_known else None
        )
        public_stats['truth_coverage'] = (
            truth_known / decision_count if decision_count else None
        )
        return public_stats

    def get_trust_calibration_history(
        self,
        user_id: Optional[str] = None,
        limit: int = 500,
        minimum_sample_size: int = 30,
    ) -> Dict[str, Any]:
        """聚合历史 trust_events，用于信任调控设置页展示行为数据采集状态。"""
        safe_limit = max(1, min(int(limit or 500), 5000))
        rows: List[Tuple[Any, ...]] = []
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                sql = """
                    SELECT id, task_id, operation_type, timestamp, parameters, user_id, event_owner, created_at
                    FROM user_operations
                    WHERE parameters LIKE '%trust_events%'
                """
                params: List[Any] = []
                if user_id:
                    sql += " AND user_id = ?"
                    params.append(user_id)
                sql += " ORDER BY timestamp DESC LIMIT ?"
                params.append(safe_limit)
                cursor.execute(sql, tuple(params))
                rows = cursor.fetchall()
        except Exception as e:
            self.logger.warning(f"读取信任调控历史失败: {e}")

        events: List[Dict[str, Any]] = []
        for row in rows:
            operation_id, task_id, operation_type, op_timestamp, parameters_json, row_user_id, event_owner, created_at = row
            try:
                parameters = json.loads(parameters_json or '{}')
            except json.JSONDecodeError:
                continue

            for event in self._extract_trust_events(parameters):
                enriched_event = dict(event)
                enriched_event['_operation'] = {
                    'id': operation_id,
                    'task_id': task_id,
                    'operation_type': operation_type,
                    'timestamp': op_timestamp,
                    'user_id': row_user_id,
                    'event_owner': event_owner,
                    'created_at': created_at,
                }
                events.append(enriched_event)

        events.sort(key=lambda event: event.get('timestamp') or 0)

        summary = self._empty_trust_history_stats()
        task_breakdown: Dict[str, Dict[str, Any]] = {
            'sensor': self._empty_trust_history_stats(),
            'threat': self._empty_trust_history_stats(),
        }
        evidence_seen: Set[Tuple[str, str]] = set()

        for event in events:
            task = event.get('task') if event.get('task') in ('sensor', 'threat') else 'unknown'
            task_stats = task_breakdown.setdefault(task, self._empty_trust_history_stats())
            stats_targets = [summary, task_stats]
            actor = event.get('actor')
            event_type = event.get('eventType')
            recommendation_id = event.get('recommendationId')
            event_timestamp = event.get('timestamp')

            for stats in stats_targets:
                stats['event_count'] += 1
                if event_timestamp and (stats['last_event_at'] is None or event_timestamp > stats['last_event_at']):
                    stats['last_event_at'] = event_timestamp
                if actor == 'human':
                    stats['human_event_count'] += 1
                elif actor == 'ai':
                    stats['ai_event_count'] += 1

            if actor == 'human' and event_type == 'evidence_viewed':
                for stats in stats_targets:
                    stats['evidence_viewed_count'] += 1
                if recommendation_id:
                    evidence_seen.add((str(task), str(recommendation_id)))

            if actor == 'human' and event_type == 'manual_review_done':
                for stats in stats_targets:
                    stats['manual_review_count'] += 1

            if actor == 'human' and event_type == 'human_result_confirmed':
                for stats in stats_targets:
                    stats['result_confirmed_count'] += 1

            if actor == 'human' and event_type in ('human_accept', 'human_reject'):
                latency_ms = event.get('latencyMs')
                for stats in stats_targets:
                    stats['human_decision_count'] += 1
                    if event_type == 'human_accept':
                        stats['human_accept_count'] += 1
                        stats['_current_reject_streak'] = 0
                    else:
                        stats['human_reject_count'] += 1
                        stats['_current_reject_streak'] += 1
                        stats['max_consecutive_reject_count'] = max(
                            stats['max_consecutive_reject_count'],
                            stats['_current_reject_streak']
                        )
                    if isinstance(latency_ms, (int, float)) and latency_ms >= 0:
                        stats['_latency_total'] += latency_ms
                        stats['_latency_count'] += 1

                metadata = event.get('metadata') if isinstance(event.get('metadata'), dict) else {}
                metadata_evidence_viewed = metadata.get('evidenceViewed')
                evidence_viewed = (
                    metadata_evidence_viewed is True or
                    (
                        metadata_evidence_viewed is not False and
                        recommendation_id is not None and
                        (str(task), str(recommendation_id)) in evidence_seen
                    )
                )
                if event_type == 'human_accept' and not evidence_viewed:
                    for stats in stats_targets:
                        stats['direct_accept_without_evidence_count'] += 1

                # 真值口径：AI 推荐正确性已知时区分「该拒/不该拒」「该接/不该接」
                ai_correct = event.get('aiRecommendationCorrect')
                if isinstance(ai_correct, bool):
                    for stats in stats_targets:
                        stats['truth_known_count'] += 1
                        if ai_correct:
                            stats['ai_correct_count'] += 1
                        else:
                            stats['ai_incorrect_count'] += 1
                        if event_type == 'human_reject':
                            if ai_correct:
                                stats['unwarranted_reject_count'] += 1
                            else:
                                stats['justified_reject_count'] += 1
                        elif event_type == 'human_accept' and not ai_correct and not evidence_viewed:
                            stats['unwarranted_accept_count'] += 1

        public_summary = self._public_trust_history_stats(summary)
        public_breakdown = {
            task: self._public_trust_history_stats(stats)
            for task, stats in task_breakdown.items()
        }

        recent_events = list(reversed(events))[:20]
        return {
            'minimum_sample_size': minimum_sample_size,
            'sample_sufficient': public_summary['human_decision_count'] >= minimum_sample_size,
            'operation_count': len(rows),
            'event_count': len(events),
            'filters': {
                'user_id': user_id,
                'limit': safe_limit,
            },
            'summary': public_summary,
            'task_breakdown': public_breakdown,
            'recent_events': recent_events,
        }
    
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
                self._create_task_runs_table(cursor, conn)
                self._create_task_events_table(cursor, conn)
                self._create_task_subtask_results_table(cursor, conn)

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

    def _create_task_runs_table(self, cursor, conn) -> None:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='task_runs'")
        if not cursor.fetchone():
            cursor.execute("""
                CREATE TABLE task_runs (
                    task_id INTEGER PRIMARY KEY,
                    task_type TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    expected_subtasks INTEGER,
                    completed_subtasks INTEGER DEFAULT 0,
                    current_subtask_seq INTEGER DEFAULT 0,
                    started_at_ms INTEGER NOT NULL,
                    completed_at_ms INTEGER,
                    config_json TEXT,
                    last_raw_message_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX idx_task_runs_active ON task_runs(user_id, task_type, status, started_at_ms)")
            conn.commit()
        else:
            self._update_task_runs_table(cursor, conn)

    def _update_task_runs_table(self, cursor, conn) -> None:
        cursor.execute("PRAGMA table_info(task_runs)")
        columns = {row[1] for row in cursor.fetchall()}
        additions = {
            "task_type": "TEXT",
            "user_id": "TEXT",
            "status": "TEXT DEFAULT 'active'",
            "expected_subtasks": "INTEGER",
            "completed_subtasks": "INTEGER DEFAULT 0",
            "current_subtask_seq": "INTEGER DEFAULT 0",
            "started_at_ms": "INTEGER",
            "completed_at_ms": "INTEGER",
            "config_json": "TEXT",
            "last_raw_message_json": "TEXT",
            "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        }
        changed = False
        for name, column_type in additions.items():
            if name not in columns:
                cursor.execute(f"ALTER TABLE task_runs ADD COLUMN {name} {column_type}")
                changed = True
        if changed:
            conn.commit()

    def _create_task_events_table(self, cursor, conn) -> None:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='task_events'")
        if not cursor.fetchone():
            cursor.execute("""
                CREATE TABLE task_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    task_type TEXT NOT NULL,
                    user_id TEXT,
                    event_type TEXT NOT NULL,
                    sub_task_seq INTEGER,
                    timestamp_ms INTEGER NOT NULL,
                    payload_json TEXT,
                    raw_message_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX idx_task_events_task ON task_events(task_id, event_type, sub_task_seq)")
            conn.commit()
        else:
            self._update_task_events_table(cursor, conn)

    def _update_task_events_table(self, cursor, conn) -> None:
        cursor.execute("PRAGMA table_info(task_events)")
        columns = {row[1] for row in cursor.fetchall()}
        additions = {
            "task_type": "TEXT",
            "user_id": "TEXT",
            "sub_task_seq": "INTEGER",
            "payload_json": "TEXT",
            "raw_message_json": "TEXT",
        }
        changed = False
        for name, column_type in additions.items():
            if name not in columns:
                cursor.execute(f"ALTER TABLE task_events ADD COLUMN {name} {column_type}")
                changed = True
        if changed:
            conn.commit()

    def _create_task_subtask_results_table(self, cursor, conn) -> None:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='task_subtask_results'")
        if not cursor.fetchone():
            cursor.execute("""
                CREATE TABLE task_subtask_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    task_type TEXT NOT NULL,
                    user_id TEXT,
                    sub_task_seq INTEGER NOT NULL,
                    result_json TEXT NOT NULL,
                    current_task_score REAL,
                    ai_control_time REAL,
                    person_control_time REAL,
                    ai_remind_time REAL,
                    switch_count INTEGER,
                    fire_count INTEGER,
                    fire_success_count INTEGER,
                    timestamp_ms INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE UNIQUE INDEX idx_task_subtask_results_unique ON task_subtask_results(task_id, sub_task_seq)")
            conn.commit()
        else:
            self._update_task_subtask_results_table(cursor, conn)

    def _update_task_subtask_results_table(self, cursor, conn) -> None:
        cursor.execute("PRAGMA table_info(task_subtask_results)")
        columns = {row[1] for row in cursor.fetchall()}
        additions = {
            "task_type": "TEXT",
            "user_id": "TEXT",
            "current_task_score": "REAL",
            "ai_control_time": "REAL",
            "person_control_time": "REAL",
            "ai_remind_time": "REAL",
            "switch_count": "INTEGER",
            "fire_count": "INTEGER",
            "fire_success_count": "INTEGER",
        }
        changed = False
        for name, column_type in additions.items():
            if name not in columns:
                cursor.execute(f"ALTER TABLE task_subtask_results ADD COLUMN {name} {column_type}")
                changed = True
        if changed:
            conn.commit()

    def find_active_task_run(self, user_id: str, task_type: str) -> Optional[Dict[str, Any]]:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT task_id, task_type, user_id, status, expected_subtasks,
                           completed_subtasks, current_subtask_seq, started_at_ms,
                           completed_at_ms, config_json, last_raw_message_json
                    FROM task_runs
                    WHERE user_id = ? AND task_type = ? AND status != 'completed'
                    ORDER BY started_at_ms DESC, task_id DESC
                    LIMIT 1
                    """,
                    (user_id, task_type),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                keys = [
                    "task_id", "task_type", "user_id", "status", "expected_subtasks",
                    "completed_subtasks", "current_subtask_seq", "started_at_ms",
                    "completed_at_ms", "config_json", "last_raw_message_json",
                ]
                return dict(zip(keys, row))
        except Exception as e:
            self.logger.warning("查找 active task_run 失败: %s", e)
            return None

    def find_recent_completed_task_run(
        self,
        user_id: str,
        task_type: str,
        since_ms: int = None,
    ) -> Optional[Dict[str, Any]]:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                params = [user_id, task_type]
                since_clause = ""
                if since_ms is not None:
                    since_clause = "AND completed_at_ms >= ?"
                    params.append(since_ms)
                cursor.execute(
                    f"""
                    SELECT task_id, task_type, user_id, status, expected_subtasks,
                           completed_subtasks, current_subtask_seq, started_at_ms,
                           completed_at_ms, config_json, last_raw_message_json
                    FROM task_runs
                    WHERE user_id = ? AND task_type = ? AND status = 'completed'
                      AND completed_at_ms IS NOT NULL
                      {since_clause}
                    ORDER BY completed_at_ms DESC, task_id DESC
                    LIMIT 1
                    """,
                    tuple(params),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                keys = [
                    "task_id", "task_type", "user_id", "status", "expected_subtasks",
                    "completed_subtasks", "current_subtask_seq", "started_at_ms",
                    "completed_at_ms", "config_json", "last_raw_message_json",
                ]
                return dict(zip(keys, row))
        except Exception as e:
            self.logger.warning("查找 recent completed task_run 失败: %s", e)
            return None

    def create_task_run(self, task_id: int, task_type: str, user_id: str,
                        expected_subtasks: int, started_at_ms: int,
                        config_json: str, raw_message_json: str) -> None:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO task_runs (
                    task_id, task_type, user_id, status, expected_subtasks,
                    completed_subtasks, current_subtask_seq, started_at_ms,
                    config_json, last_raw_message_json, updated_at
                ) VALUES (?, ?, ?, 'active', ?, 0, 0, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (task_id, task_type, user_id, expected_subtasks, started_at_ms, config_json, raw_message_json),
            )
            conn.commit()
        self.logger.info("记录 task_run: task_id=%s task_type=%s user=%s total=%s",
                         task_id, task_type, user_id, expected_subtasks)

    def update_task_run_progress(self, task_id: int, current_subtask_seq: int = None,
                                 completed_subtasks: int = None, status: str = None,
                                 completed_at_ms: int = None,
                                 raw_message_json: str = None) -> None:
        fields = ["updated_at = CURRENT_TIMESTAMP"]
        params = []
        if current_subtask_seq is not None:
            fields.append("current_subtask_seq = ?")
            params.append(current_subtask_seq)
        if completed_subtasks is not None:
            fields.append("completed_subtasks = ?")
            params.append(completed_subtasks)
        if status is not None:
            fields.append("status = ?")
            params.append(status)
        if completed_at_ms is not None:
            fields.append("completed_at_ms = ?")
            params.append(completed_at_ms)
        if raw_message_json is not None:
            fields.append("last_raw_message_json = ?")
            params.append(raw_message_json)
        params.append(task_id)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE task_runs SET {', '.join(fields)} WHERE task_id = ?", tuple(params))
            conn.commit()

    def record_task_event(self, task_id: int, task_type: str, user_id: str,
                          event_type: str, timestamp_ms: int,
                          sub_task_seq: int = None,
                          payload_json: str = None,
                          raw_message_json: str = None) -> None:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO task_events (
                    task_id, task_type, user_id, event_type, sub_task_seq,
                    timestamp_ms, payload_json, raw_message_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (task_id, task_type, user_id, event_type, sub_task_seq,
                 timestamp_ms, payload_json, raw_message_json),
            )
            conn.commit()

    def record_subtask_result(self, task_id: int, task_type: str, user_id: str,
                              sub_task_seq: int, result_json: str,
                              timestamp_ms: int,
                              current_task_score: float = None,
                              ai_control_time: float = None,
                              person_control_time: float = None,
                              ai_remind_time: float = None,
                              switch_count: int = None,
                              fire_count: int = None,
                              fire_success_count: int = None) -> None:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO task_subtask_results (
                    task_id, task_type, user_id, sub_task_seq, result_json,
                    current_task_score, ai_control_time, person_control_time,
                    ai_remind_time, switch_count, fire_count, fire_success_count,
                    timestamp_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (task_id, task_type, user_id, sub_task_seq, result_json,
                 current_task_score, ai_control_time, person_control_time,
                 ai_remind_time, switch_count, fire_count, fire_success_count,
                 timestamp_ms),
            )
            conn.commit()

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
                    default_control_mode TEXT,
                    autonomy_level TEXT,
                    task_mode TEXT,
                    difficulty TEXT,
                    difficulty_display TEXT,
                    task_number TEXT,
                    repetition_total_override INTEGER,
                    is_ai_active BOOLEAN,
                    is_practice BOOLEAN,
                    ai_precision TEXT,
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

        else:
            self._update_platform_external_tasks_table(cursor, conn)

    def _update_platform_external_tasks_table(self, cursor, conn) -> None:
        """Ensure external platform task rows keep normalized RADAR/SA fields."""
        cursor.execute("PRAGMA table_info(platform_external_tasks)")
        columns = {row[1] for row in cursor.fetchall()}
        additions = {
            "default_control_mode": "TEXT",
            "autonomy_level": "TEXT",
            "task_mode": "TEXT",
            "difficulty": "TEXT",
            "difficulty_display": "TEXT",
            "task_number": "TEXT",
            "repetition_total_override": "INTEGER",
            "is_ai_active": "BOOLEAN",
            "is_practice": "BOOLEAN",
            "ai_precision": "TEXT",
        }
        changed = False
        for name, column_type in additions.items():
            if name not in columns:
                cursor.execute(f"ALTER TABLE platform_external_tasks ADD COLUMN {name} {column_type}")
                changed = True
        if changed:
            conn.commit()

    def record_external_task(self, task_id: int, task_category: str,
                             event_type: str, raw_message: str,
                             timestamp: int, user_id: str = None,
                             task_name: str = None, gender: str = None,
                             sub_task_seq: int = None,
                             default_control_mode: str = None,
                             autonomy_level: str = None,
                             task_mode: str = None,
                             difficulty: str = None,
                             difficulty_display: str = None,
                             task_number: str = None,
                             repetition_total_override: int = None,
                             is_ai_active: bool = None,
                             is_practice: bool = None,
                             ai_precision: str = None) -> None:
        """记录外部平台任务生命周期事件"""
        sql = """
            INSERT INTO platform_external_tasks (
                task_id, task_category, event_type, sub_task_seq,
                user_id, task_name, gender,
                default_control_mode, autonomy_level, task_mode, difficulty,
                difficulty_display, task_number, repetition_total_override,
                is_ai_active, is_practice, ai_precision,
                raw_message, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (task_id, task_category, event_type, sub_task_seq,
                  user_id, task_name, gender,
                  default_control_mode, autonomy_level, task_mode,
                  self.normalize_difficulty_value(difficulty), difficulty_display,
                  task_number, repetition_total_override,
                  None if is_ai_active is None else int(bool(is_ai_active)),
                  None if is_practice is None else int(bool(is_practice)),
                  ai_precision, raw_message, timestamp)
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
                                    fire_success_count: int = None,
                                    default_control_mode: str = None,
                                    autonomy_level: str = None,
                                    task_mode: str = None,
                                    difficulty: str = None,
                                    difficulty_display: str = None,
                                    task_number: str = None,
                                    repetition_total_override: int = None,
                                    is_ai_active: bool = None,
                                    is_practice: bool = None,
                                    ai_precision: str = None) -> None:
        """记录外部平台任务结果"""
        sql = """
            INSERT INTO platform_external_tasks (
                task_id, task_category, event_type, user_id,
                ai_control_time, person_control_time, ai_remind_time,
                switch_count, fire_count, fire_success_count,
                default_control_mode, autonomy_level, task_mode, difficulty,
                difficulty_display, task_number, repetition_total_override,
                is_ai_active, is_practice, ai_precision,
                raw_message, timestamp
            ) VALUES (?, ?, 'task_result', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (task_id, task_category, user_id,
                  ai_control_time, person_control_time, ai_remind_time,
                  switch_count, fire_count, fire_success_count,
                  default_control_mode, autonomy_level, task_mode,
                  self.normalize_difficulty_value(difficulty), difficulty_display,
                  task_number, repetition_total_override,
                  None if is_ai_active is None else int(bool(is_ai_active)),
                  None if is_practice is None else int(bool(is_practice)),
                  ai_precision,
                  raw_message, timestamp)
        self.execute_async(sql, params)
        self.logger.info("记录外部任务结果: task_id=%s category=%s", task_id, task_category)


# 全局数据库管理器实例
db_manager = DatabaseManager()
