import json
from typing import Dict, Any, Optional, List
from .database_manager import db_manager
from .logger_manager import get_logger
import time
import random

class TaskScenarioManager:
    """管理与数据库绑定的、持久化的用户任务场景"""
    
    # 练习模式的内存缓存，格式: {(user_id, task_type): progress_data}
    _practice_memory_cache: Dict[tuple, Dict[str, Any]] = {}
    
    def __init__(self, config: Dict[str, Any], user_id: str, task_type: str, is_practice: bool = False):
        self.config = config
        self.user_id = user_id
        self.task_type = task_type
        self.is_practice = is_practice
        self.logger = get_logger("task_manager")
        
        # 从配置中读取练习模式设置
        game_settings = self.config.get('game_settings', {})
        practice_reps = game_settings.get('practice_repetitions', 3)
        formal_reps = game_settings.get('max_repetitions', 1)
        self.max_repetitions = practice_reps if self.is_practice else formal_reps
        
        # 内部状态
        self.ai_queue: List[Dict[str, Any]] = []
        self.manual_queue: List[Dict[str, Any]] = []
        self.active_queue: Optional[List[Dict[str, Any]]] = None
        self.current_scenario: Optional[Dict[str, Any]] = None
        self.repetition_counter: int = 0

        if self.is_practice:
            # 练习模式：尝试从内存缓存加载，失败则初始化新进度
            if not self._load_from_memory():
                self.logger.debug("Practice mode: No cached progress found, initializing fresh progress")
                self._initialize_new_progress()
            else:
                self.logger.debug("Practice mode: Loaded progress from memory cache")
        else:
            # 正式模式：尝试从数据库加载，失败则初始化新进度
            if not self._load_from_db():
                self._initialize_new_progress()
                self._save_to_db()

    def _load_from_memory(self) -> bool:
        """尝试从内存缓存加载练习模式进度"""
        cache_key = (self.user_id, self.task_type)
        if cache_key in self._practice_memory_cache:
            progress_data = self._practice_memory_cache[cache_key]
            self.current_scenario = progress_data.get('current_scenario')
            self.repetition_counter = progress_data.get('repetition_counter', 0)
            self.ai_queue = progress_data.get('ai_queue', [])
            self.manual_queue = progress_data.get('manual_queue', [])
            return True
        return False

    def _save_to_memory(self) -> None:
        """将当前状态保存到内存缓存（仅练习模式）"""
        if not self.is_practice:
            return
        
        cache_key = (self.user_id, self.task_type)
        self._practice_memory_cache[cache_key] = {
            'current_scenario': self.current_scenario,
            'repetition_counter': self.repetition_counter,
            'ai_queue': self.ai_queue.copy(),  # 复制列表避免引用问题
            'manual_queue': self.manual_queue.copy()
        }
        self.logger.debug(f"Practice mode progress saved to memory for user '{self.user_id}', task '{self.task_type}'")

    def _load_from_db(self) -> bool:
        """尝试从数据库加载用户进度"""
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT current_scenario_json, repetition_counter, ai_queue_json, manual_queue_json FROM user_progress WHERE user_id = ? AND task_type = ?",
                    (self.user_id, self.task_type)
                )
                row = cursor.fetchone()
                if row:
                    self.logger.info(f"Found existing progress for user '{self.user_id}' and task '{self.task_type}'")
                    self.current_scenario = json.loads(row[0]) if row[0] else None
                    self.repetition_counter = row[1] or 0
                    self.ai_queue = json.loads(row[2]) if row[2] else []
                    self.manual_queue = json.loads(row[3]) if row[3] else []
                    return True
        except Exception as e:
            self.logger.error(f"Error loading progress from DB: {e}", exc_info=True)
        return False

    def _save_to_db(self) -> None:
        """将当前状态的写入操作放入队列，但练习模式除外"""
        if self.is_practice:
            self.logger.debug("Practice mode: Skipping DB save")
            return
        
        sql = """
            INSERT OR REPLACE INTO user_progress 
            (user_id, task_type, current_scenario_json, repetition_counter, ai_queue_json, manual_queue_json, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """
        params = (
            self.user_id,
            self.task_type,
            json.dumps(self.current_scenario) if self.current_scenario else None,
            self.repetition_counter,
            json.dumps(self.ai_queue),
            json.dumps(self.manual_queue)
        )
        db_manager.execute_async(sql, params)
        self.logger.debug(f"Progress save queued for user '{self.user_id}', task '{self.task_type}'")

    def _initialize_new_progress(self) -> None:
        """为新用户或新任务生成全新的队列和状态"""
        self.logger.info(f"Initializing new progress for user '{self.user_id}', task '{self.task_type}'")
        all_levels = self.config.get('levels', [])
        game_settings = self.config.get('game_settings', {})
        all_difficulties = game_settings.get('difficulty_levels', {})
        
        # 从配置文件中获取执行顺序
        execution_order = game_settings.get('execution_order', {})
        preferred_difficulty_order = execution_order.get('difficulty_order', ['high', 'low'])
        preferred_level_order = execution_order.get('level_order', ['L0', 'L1', 'L2'])
        audio_options = execution_order.get('audio_options', [True, False])
        
        # 创建按指定顺序排列的level列表
        ordered_levels = []
        for level_name in preferred_level_order:
            for level_conf in all_levels:
                if level_conf.get('level') == level_name:
                    ordered_levels.append(level_conf)
                    break
        
        difficulties = []
        for diff_name in preferred_difficulty_order:
            if diff_name in all_difficulties:
                diff_conf = all_difficulties[diff_name]
                diff_conf['difficulty_name'] = diff_name  # 确保配置中包含难度名称
                difficulties.append(diff_conf)

        # AI模式
        ai_scenarios = []
        for diff_conf in difficulties:
            for level_conf in ordered_levels:
                for audio in audio_options:
                    ai_scenarios.append({
                        "is_ai_active": True, 
                        "audio_enabled": audio,
                        "ai_level_name": level_conf['level'], 
                        "ai_level_config": level_conf,
                        "difficulty_name": diff_conf['difficulty_name'], 
                        "difficulty_config": diff_conf
                    })
        
        # 为每个AI场景添加类型编号
        total_ai_scenarios = len(ai_scenarios)
        for i, scenario in enumerate(ai_scenarios):
            scenario['scenario_info'] = {'index': i + 1, 'total': total_ai_scenarios}
        self.ai_queue = ai_scenarios

        # 手动模式
        manual_scenarios = []
        for diff_conf in difficulties: 
            for audio in audio_options:
                manual_scenarios.append({
                    "is_ai_active": False, 
                    "audio_enabled": audio,
                    "ai_level_name": None, 
                    "ai_level_config": None,
                    "difficulty_name": diff_conf['difficulty_name'], 
                    "difficulty_config": diff_conf
                })
    
        # 为每个手动场景添加类型编号
        total_manual_scenarios = len(manual_scenarios)
        for i, scenario in enumerate(manual_scenarios):
            scenario['scenario_info'] = {'index': i + 1, 'total': total_manual_scenarios}
        self.manual_queue = manual_scenarios
        
        self.current_scenario = None
        self.repetition_counter = 0

    def are_all_scenarios_completed(self) -> bool:
        """检查此任务类型的所有场景（AI和手动）是否都已完成"""
        return not self.ai_queue and not self.manual_queue

    @classmethod
    def clear_practice_cache(cls, user_id: str = None, task_type: str = None) -> None:
        """清理练习模式的内存缓存
        
        Args:
            user_id: 如果指定，只清理该用户的缓存
            task_type: 如果指定，只清理该任务类型的缓存
        """
        if user_id is None and task_type is None:
            # 清理所有缓存
            cls._practice_memory_cache.clear()
        else:
            # 清理指定的缓存
            keys_to_remove = []
            for cache_key in cls._practice_memory_cache.keys():
                cached_user_id, cached_task_type = cache_key
                should_remove = True
                if user_id is not None and cached_user_id != user_id:
                    should_remove = False
                if task_type is not None and cached_task_type != task_type:
                    should_remove = False
                if should_remove:
                    keys_to_remove.append(cache_key)
            
            for key in keys_to_remove:
                del cls._practice_memory_cache[key]

    def get_next_task_parameters(self, is_ai_active_request: bool) -> Optional[Dict[str, Any]]:
        """获取下一个场景参数，并自动保存进度"""
        new_queue = self.ai_queue if is_ai_active_request else self.manual_queue
        
        # 检查是否切换了模式 (AI vs Manual)
        queue_switched = False
        if self.active_queue is not None:  # 避免首次调用时被误判为切换
            current_queue_name = 'ai_queue' if self.active_queue is self.ai_queue else 'manual_queue'
            new_queue_name = 'ai_queue' if new_queue is self.ai_queue else 'manual_queue'
            if current_queue_name != new_queue_name:
                queue_switched = True

        if queue_switched:
            self.active_queue = new_queue
            self.current_scenario = None
            self.repetition_counter = 0
            self.logger.info(f"Switched to {'AI' if is_ai_active_request else 'Manual'} queue for task '{self.task_type}'")

        self.active_queue = new_queue

        if self.current_scenario and self.repetition_counter < self.max_repetitions:
            self.repetition_counter += 1
        else:
            if self.active_queue:
                self.current_scenario = self.active_queue.pop(0)
                self.repetition_counter = 1
                self.logger.info(f"New scenario started for task '{self.task_type}': diff='{self.current_scenario['difficulty_name']}', ai='{self.current_scenario.get('ai_level_name') or 'N/A'}'")
            else:
                self.logger.info(f"Active queue empty for task '{self.task_type}'")
                self.current_scenario = None
                self.repetition_counter = 0

        # 如果当前场景为空（因为队列已空），检查是否所有任务都完成了
        if not self.current_scenario:
            if self.is_practice:
                self._save_to_memory()
            else:
                self._save_to_db()
            if self.are_all_scenarios_completed():
                return "ALL_COMPLETED"
            return None
        
        repetition_info = {
            "current": self.repetition_counter,
            "total": self.max_repetitions,
            "is_practice": self.is_practice,
            "difficulty": self.current_scenario.get('difficulty_name'),
            "is_ai_active": self.current_scenario.get('is_ai_active'),
            "audio_enabled": self.current_scenario.get('audio_enabled')
        }
        
        # 将类型编号添加到repetition_info中
        if self.current_scenario.get("scenario_info"):
            scenario_info = self.current_scenario["scenario_info"]
            repetition_info["scenario_index"] = scenario_info.get("index")
            repetition_info["scenario_total"] = scenario_info.get("total")

        self.current_scenario['repetition_info'] = repetition_info
        if self.current_scenario:
            if self.is_practice:
                self._save_to_memory()
            else:
                self._save_to_db()
        return self.current_scenario

def generate_task_id_timestamp() -> int:
    """生成新的任务ID"""
    # 使用时间戳(毫秒) + 随机数确保唯一性
    # 时间戳精确到毫秒，再加上随机数，几乎不可能重复
    timestamp_ms = int(time.time() * 1000)
    random_suffix = random.randint(100, 999)
    task_id = int(f"{timestamp_ms}{random_suffix}")
    
    return task_id

def generate_task_id() -> int:
    """从数据库查询最大task_id并生成新的唯一ID（备选方案）"""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            # 查询task_settings表中的最大task_id
            cursor.execute("SELECT MAX(task_id) FROM task_settings")
            result = cursor.fetchone()
            max_id = result[0] if result and result[0] is not None else 0
            
            # 查询user_operations表中的最大task_id
            cursor.execute("SELECT MAX(task_id) FROM user_operations")  
            result = cursor.fetchone()
            max_id_ops = result[0] if result and result[0] is not None else 0
            
            # 取两个表中的最大值，然后+1
            return max(max_id, max_id_ops) + 1
    except Exception as e:
        # 如果数据库查询失败，回退到时间戳方案
        get_logger("task_manager").warning(f"Failed to query max task_id from DB: {e}")
        return generate_task_id_timestamp() 