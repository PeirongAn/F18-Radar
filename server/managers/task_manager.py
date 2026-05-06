import json
from typing import Dict, Any, Optional, List
from .database_manager import db_manager
from .config_manager import config_manager
from .logger_manager import get_logger
import time
import random

class TaskScenarioManager:
    """管理与数据库绑定的、持久化的用户任务场景"""
    
    # 练习模式的内存缓存，格式: {(user_id, task_type): progress_data}
    _practice_memory_cache: Dict[tuple, Dict[str, Any]] = {}
    
    def __init__(self, config: Dict[str, Any], user_id: str, task_type: str, is_practice: bool = False, is_ai_active_request: bool = False):
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
            if not self._load_from_db(is_ai_active_request):
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
        
        # 获取现有的 is_completed 状态（如果存在）
        current_is_completed = False  # 默认为未完成
        if cache_key in self._practice_memory_cache:
            current_is_completed = self._practice_memory_cache[cache_key].get('is_completed', False)
        
        self._practice_memory_cache[cache_key] = {
            'current_scenario': self.current_scenario,
            'repetition_counter': self.repetition_counter,
            'ai_queue': self.ai_queue.copy(),  # 复制列表避免引用问题
            'manual_queue': self.manual_queue.copy(),
            'is_completed': current_is_completed  # 保持现有的完成状态，不自动修改
        }
        self.logger.debug(f"Practice mode progress saved to memory for user '{self.user_id}', task '{self.task_type}'")

    def _load_from_db(self, is_ai_active_request: bool) -> bool:
        """尝试从数据库加载用户进度，根据AI模式选择对应的进度"""
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                # 查询扩展后的字段，包括AI和手动模式的分别进度
                cursor.execute(
                    """SELECT current_scenario_json, repetition_counter, ai_queue_json, manual_queue_json, is_completed,
                              ai_current_scenario_json, ai_repetition_counter, 
                              manual_current_scenario_json, manual_repetition_counter,
                              is_ai_completed, is_manual_completed 
                       FROM user_progress WHERE user_id = ? AND task_type = ?""",
                    (self.user_id, self.task_type)
                )
                row = cursor.fetchone()
                if row:
                    self.logger.info(f"Found existing progress for user '{self.user_id}' and task '{self.task_type}', AI mode: {is_ai_active_request}")
                    
                    # 加载队列（AI和手动队列都需要加载）
                    self.ai_queue = json.loads(row[2]) if row[2] else []
                    self.manual_queue = json.loads(row[3]) if row[3] else []
                    
                    # 根据请求的AI模式选择对应的进度
                    if is_ai_active_request:
                        # 加载AI模式的进度
                        ai_scenario_json = row[5] if len(row) > 5 else None
                        ai_repetition = row[6] if len(row) > 6 else None
                        
                        if ai_scenario_json:
                            self.current_scenario = json.loads(ai_scenario_json)
                            self.repetition_counter = ai_repetition or 0
                            self.logger.info(f"Loaded AI mode progress: scenario exists, repetition {self.repetition_counter}")
                        else:
                            # 如果没有AI模式的进度，但有旧的通用进度，且是AI场景，则使用旧进度
                            old_scenario = json.loads(row[0]) if row[0] else None
                            if old_scenario and old_scenario.get('is_ai_active', False):
                                self.current_scenario = old_scenario
                                self.repetition_counter = row[1] or 0
                                self.logger.info(f"Using legacy AI progress: repetition {self.repetition_counter}")
                            else:
                                # 没有AI进度，重新开始
                                self.current_scenario = None
                                self.repetition_counter = 0
                                self.logger.info("No AI mode progress found, starting fresh")
                    else:
                        # 加载手动模式的进度
                        manual_scenario_json = row[7] if len(row) > 7 else None
                        manual_repetition = row[8] if len(row) > 8 else None
                        
                        if manual_scenario_json:
                            self.current_scenario = json.loads(manual_scenario_json)
                            self.repetition_counter = manual_repetition or 0
                            self.logger.info(f"Loaded manual mode progress: scenario exists, repetition {self.repetition_counter}")
                        else:
                            # 如果没有手动模式的进度，但有旧的通用进度，且是手动场景，则使用旧进度
                            old_scenario = json.loads(row[0]) if row[0] else None
                            if old_scenario and not old_scenario.get('is_ai_active', True):
                                self.current_scenario = old_scenario
                                self.repetition_counter = row[1] or 0
                                self.logger.info(f"Using legacy manual progress: repetition {self.repetition_counter}")
                            else:
                                # 没有手动进度，重新开始
                                self.current_scenario = None
                                self.repetition_counter = 0
                                self.logger.info("No manual mode progress found, starting fresh")
                    
                    return True
        except Exception as e:
            self.logger.error(f"Error loading progress from DB: {e}", exc_info=True)
        return False

    def _save_to_db(self) -> None:
        """将当前状态的写入操作放入队列，分别保存AI和手动模式的进度"""
        if self.is_practice:
            self.logger.debug("Practice mode: Skipping DB save")
            return
        
        # 获取当前的 is_completed 状态（从数据库或使用默认值）
        current_is_completed = False  # 默认为未完成
        current_is_ai_completed = False  # 默认为未完成
        current_is_manual_completed = False  # 默认为未完成
        ai_scenario_json = None
        ai_repetition = 0
        manual_scenario_json = None
        manual_repetition = 0
        
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT is_completed, ai_current_scenario_json, ai_repetition_counter,
                              manual_current_scenario_json, manual_repetition_counter,
                              is_ai_completed, is_manual_completed
                       FROM user_progress WHERE user_id = ? AND task_type = ?""",
                    (self.user_id, self.task_type)
                )
                result = cursor.fetchone()
                if result:
                    current_is_completed = bool(result[0])
                    ai_scenario_json = result[1]
                    ai_repetition = result[2] or 0
                    manual_scenario_json = result[3]
                    manual_repetition = result[4] or 0
                    current_is_ai_completed = bool(result[5]) if len(result) > 5 else False
                    current_is_manual_completed = bool(result[6]) if len(result) > 6 else False
        except Exception as e:
            self.logger.debug(f"Could not fetch current progress status, using defaults: {e}")
        
        # 根据当前场景的AI模式决定更新哪个字段
        if self.current_scenario and self.current_scenario.get('is_ai_active', False):
            # 当前是AI模式，更新AI字段
            ai_scenario_json = json.dumps(self.current_scenario)
            ai_repetition = self.repetition_counter
            self.logger.debug(f"Updating AI mode progress: repetition {ai_repetition}")
        elif self.current_scenario:
            # 当前是手动模式，更新手动字段
            manual_scenario_json = json.dumps(self.current_scenario)
            manual_repetition = self.repetition_counter
            self.logger.debug(f"Updating manual mode progress: repetition {manual_repetition}")
        
        sql = """
            INSERT OR REPLACE INTO user_progress 
            (user_id, task_type, current_scenario_json, repetition_counter, ai_queue_json, manual_queue_json, is_completed, 
             ai_current_scenario_json, ai_repetition_counter, manual_current_scenario_json, manual_repetition_counter,
             is_ai_completed, is_manual_completed, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """
        params = (
            self.user_id,
            self.task_type,
            json.dumps(self.current_scenario) if self.current_scenario else None,  # 保留旧字段兼容性
            self.repetition_counter,  # 保留旧字段兼容性
            json.dumps(self.ai_queue),
            json.dumps(self.manual_queue),
            current_is_completed,  # 保持现有的完成状态，不自动修改
            ai_scenario_json,  # AI模式的当前场景
            ai_repetition,     # AI模式的重复计数
            manual_scenario_json,  # 手动模式的当前场景
            manual_repetition,     # 手动模式的重复计数
            current_is_ai_completed,  # AI模式的完成状态
            current_is_manual_completed  # 手动模式的完成状态
        )
        db_manager.execute_async(sql, params)
        self.logger.debug(f"Progress save queued for user '{self.user_id}', task '{self.task_type}'")
        
    def _check_previous_task_completion_status(self) -> bool:
        """检查上一个任务的完成状态
        
        Returns:
            bool: True表示上一个任务已完成，False表示上一个任务仍在进行中
        """
        if self.is_practice:
            # 练习模式：检查内存缓存
            cache_key = (self.user_id, self.task_type)
            if cache_key in self._practice_memory_cache:
                # 根据当前场景的AI模式选择对应的完成状态
                if self.current_scenario and self.current_scenario.get('is_ai_active', False):
                    is_completed = self._practice_memory_cache[cache_key].get('is_ai_completed', False)
                    print(f"Practice mode: Previous AI task completion status = {is_completed}")
                else:
                    is_completed = self._practice_memory_cache[cache_key].get('is_manual_completed', False)
                    print(f"Practice mode: Previous manual task completion status = {is_completed}")
                return is_completed
            return True  # 没有缓存表示没有上一个任务，视为已完成
        else:
            # 正式模式：检查数据库
            try:
                with db_manager.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT is_completed, is_ai_completed, is_manual_completed FROM user_progress WHERE user_id = ? AND task_type = ?",
                        (self.user_id, self.task_type)
                    )
                    result = cursor.fetchone()
                    if result:
                        # 根据当前场景的AI模式选择对应的完成状态
                        if self.current_scenario and self.current_scenario.get('is_ai_active', False):
                            is_completed = bool(result[1]) if len(result) > 1 else bool(result[0])  # 优先使用is_ai_completed，回退到is_completed
                            self.logger.debug(f"Formal mode: Previous AI task completion status = {is_completed}")
                        else:
                            is_completed = bool(result[2]) if len(result) > 2 else bool(result[0])  # 优先使用is_manual_completed，回退到is_completed
                            self.logger.debug(f"Formal mode: Previous manual task completion status = {is_completed}")
                        return is_completed
                    return True  # 没有记录表示没有上一个任务，视为已完成
            except Exception as e:
                self.logger.error(f"Error checking previous task completion status: {e}", exc_info=True)
                return True  # 出错时默认视为已完成

    def _update_completion_status(self, is_completed: bool) -> None:
        """更新任务完成状态
        
        Args:
            is_completed: True表示任务已完成，False表示任务未完成/进行中
        """
        if self.is_practice:
            # 练习模式：更新内存缓存
            cache_key = (self.user_id, self.task_type)
            if cache_key in self._practice_memory_cache:
                # 根据当前场景的AI模式更新对应的完成状态
                if self.current_scenario and self.current_scenario.get('is_ai_active', False):
                    self._practice_memory_cache[cache_key]['is_ai_completed'] = is_completed
                    self.logger.debug(f"Practice mode: Updated is_ai_completed={is_completed} for user '{self.user_id}', task '{self.task_type}'")
                else:
                    self._practice_memory_cache[cache_key]['is_manual_completed'] = is_completed
                    self.logger.debug(f"Practice mode: Updated is_manual_completed={is_completed} for user '{self.user_id}', task '{self.task_type}'")
                # 同时更新通用的is_completed字段以保持兼容性
                self._practice_memory_cache[cache_key]['is_completed'] = is_completed
        else:
            # 正式模式：更新数据库
            if self.current_scenario and self.current_scenario.get('is_ai_active', False):
                # 当前是AI模式，更新AI完成状态
                sql = """
                    UPDATE user_progress 
                    SET is_ai_completed = ?, is_completed = ?, last_updated = CURRENT_TIMESTAMP
                    WHERE user_id = ? AND task_type = ?
                """
                db_manager.execute_async(sql, (is_completed, is_completed, self.user_id, self.task_type))
                self.logger.debug(f"Formal mode: Queued is_ai_completed={is_completed} update for user '{self.user_id}', task '{self.task_type}'")
            else:
                # 当前是手动模式，更新手动完成状态
                sql = """
                    UPDATE user_progress 
                    SET is_manual_completed = ?, is_completed = ?, last_updated = CURRENT_TIMESTAMP
                    WHERE user_id = ? AND task_type = ?
                """
                db_manager.execute_async(sql, (is_completed, is_completed, self.user_id, self.task_type))
                self.logger.debug(f"Formal mode: Queued is_manual_completed={is_completed} update for user '{self.user_id}', task '{self.task_type}'")

    def _initialize_new_progress(self) -> None:
        """为新用户或新任务生成全新的队列和状态
        
        只生成 1 个 AI 场景和 1 个手动场景，具体参数由配置文件实时决定。
        """
        self.logger.info(f"Initializing new progress for user '{self.user_id}', task '{self.task_type}'")
        game_settings = self.config.get('game_settings', {})
        current_diff = game_settings.get('current_difficulty', 'low')
        all_difficulties = game_settings.get('difficulty_levels', {})
        diff_conf = all_difficulties.get(current_diff, {}).copy()
        diff_conf['difficulty_name'] = current_diff

        current_level_name = self.config.get('current_level', 'L0')
        current_level_conf = None
        for lv in self.config.get('levels', []):
            if lv.get('level') == current_level_name:
                current_level_conf = lv
                break

        audio = True  # 永远启用高功效

        # AI 模式：1 个场景
        ai_scenario = {
            "is_ai_active": True,
            "audio_enabled": audio,
            "ai_level_name": current_level_name,
            "ai_level_config": current_level_conf,
            "difficulty_name": current_diff,
            "difficulty_config": diff_conf,
            "scenario_info": {"index": 1, "total": 1},
            "will_difficulty_change": False
        }
        self.ai_queue = [ai_scenario]

        # 手动模式：1 个场景
        manual_scenario = {
            "is_ai_active": False,
            "audio_enabled": audio,
            "ai_level_name": None,
            "ai_level_config": None,
            "difficulty_name": current_diff,
            "difficulty_config": diff_conf,
            "scenario_info": {"index": 1, "total": 1},
            "will_difficulty_change": False
        }
        self.manual_queue = [manual_scenario]
        
        self.current_scenario = None
        self.repetition_counter = 0
        
        # 在初始化时显式设置is_completed为False（未完成状态）
        if self.is_practice:
            # 练习模式：设置内存缓存中的初始状态
            cache_key = (self.user_id, self.task_type)
            if cache_key not in self._practice_memory_cache:
                self._practice_memory_cache[cache_key] = {}
            self._practice_memory_cache[cache_key]['is_completed'] = False
            self._practice_memory_cache[cache_key]['is_ai_completed'] = False
            self._practice_memory_cache[cache_key]['is_manual_completed'] = False
            self.logger.debug(f"Practice mode: Initialized completion status to False for new progress")
        else:
            # 正式模式：通过_update_completion_status设置初始状态
            # 不直接在这里调用，因为可能还没有数据库记录，会在第一次_save_to_db时依赖默认值
            self.logger.debug(f"Formal mode: completion status will be set to default FALSE in database")

    def _refresh_config(self) -> None:
        """重新读取最新配置文件，更新运行时参数（max_repetitions 等）

        若当前场景上挂了 max_repetitions_override（来自外部平台 TaskNumber），
        以场景上的覆盖值为准，配置文件中的 max_repetitions / practice_repetitions 让位。
        """
        self.config = config_manager.get_config()
        game_settings = self.config.get('game_settings', {})
        practice_reps = game_settings.get('practice_repetitions', 3)
        formal_reps = game_settings.get('max_repetitions', 1)
        base = practice_reps if self.is_practice else formal_reps

        override = (self.current_scenario or {}).get('max_repetitions_override')
        if override is not None:
            try:
                self.max_repetitions = max(1, int(override))
            except (TypeError, ValueError):
                self.max_repetitions = base
        else:
            self.max_repetitions = base
        self.logger.debug("Config refreshed from file")

    def apply_repetition_override(self, n: int) -> None:
        """外部平台 TaskNumber 注入：把当前场景的总重复次数锁定为 n。

        语义：以"第一次设置"为准——若当前场景已有 override，则忽略本次。
        会同时更新 self.max_repetitions 并把 override 持久化到当前场景，
        以便下一次 task_start 创建新的 manager 时仍能加载到。
        """
        if self.current_scenario is None:
            return
        if self.current_scenario.get('max_repetitions_override') is not None:
            return
        try:
            n_int = max(1, int(n))
        except (TypeError, ValueError):
            return
        self.current_scenario['max_repetitions_override'] = n_int
        self.max_repetitions = n_int
        if self.is_practice:
            self._save_to_memory()
        else:
            self._save_to_db()
        self.logger.info(
            "Applied repetition override n=%s for user '%s' task '%s'",
            n_int, self.user_id, self.task_type,
        )

    def _refresh_scenario_config(self, scenario: Dict[str, Any]) -> None:
        """用最新配置刷新场景中所有可配置字段"""
        if not scenario:
            return

        game_settings = self.config.get('game_settings', {})
        all_levels = self.config.get('levels', [])
        all_difficulties = game_settings.get('difficulty_levels', {})

        # 永远启用高功效
        scenario['audio_enabled'] = True

        # 用 current_difficulty 覆盖场景的难度
        current_diff = game_settings.get('current_difficulty')
        if current_diff and current_diff in all_difficulties:
            scenario['difficulty_name'] = current_diff
            diff_conf = all_difficulties[current_diff].copy()
            diff_conf['difficulty_name'] = current_diff
            scenario['difficulty_config'] = diff_conf
        else:
            # 回退：用场景自身的 difficulty_name 刷新 config
            diff_name = scenario.get('difficulty_name')
            if diff_name and diff_name in all_difficulties:
                diff_conf = all_difficulties[diff_name].copy()
                diff_conf['difficulty_name'] = diff_name
                scenario['difficulty_config'] = diff_conf

        # 刷新 ai_level_config
        level_name = scenario.get('ai_level_name')
        if level_name:
            for level_conf in all_levels:
                if level_conf.get('level') == level_name:
                    scenario['ai_level_config'] = level_conf.copy()
                    break

    def are_all_scenarios_completed(self) -> bool:
        """检查此任务类型的所有场景（AI和手动）是否都已完成"""
        return not self.ai_queue and not self.manual_queue
        
    def mark_task_completed(self) -> None:
        """手动标记当前任务为已完成状态
        
        这个方法可以在以下情况下调用：
        - 用户主动退出任务
        - 系统检测到任务超时
        - 任务因其他原因需要被标记为完成
        """
        self._update_completion_status(True)  # True = 已完成
        self.logger.info(f"Task manually marked as completed for user '{self.user_id}', task '{self.task_type}'")

    @classmethod
    def clear_practice_cache(cls, user_id: str = '', task_type: str = '') -> None:
        """清理练习模式的内存缓存
        
        Args:
            user_id: 如果指定，只清理该用户的缓存
            task_type: 如果指定，只清理该任务类型的缓存
        """
        if user_id == '' and task_type == '':
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
        # 实时读取最新配置
        self._refresh_config()
        
        # 首先检查上一个任务的完成状态
        print('get_next_task_parameters# 0', is_ai_active_request)
        previous_task_completed = self._check_previous_task_completion_status()
        
        new_queue = self.ai_queue if is_ai_active_request else self.manual_queue
        
        # 检查是否切换了模式 (AI vs Manual)
        queue_switched = False
        print('get_next_task_parameters# 1queue_switched', self.active_queue)

        if self.active_queue is not None:  # 避免首次调用时被误判为切换
            current_queue_name = 'ai_queue' if self.active_queue is self.ai_queue else 'manual_queue'
            new_queue_name = 'ai_queue' if new_queue is self.ai_queue else 'manual_queue'
            if current_queue_name != new_queue_name:
                queue_switched = True
        print('get_next_task_parameters# 2queue_switched', queue_switched)
        if queue_switched:
            # 切换模式时，先标记上一个任务为完成状态
            self.active_queue = new_queue
            self.current_scenario = None
            self.repetition_counter = 0
            self.logger.info(f"Switched to {'AI' if is_ai_active_request else 'Manual'} queue for task '{self.task_type}'")

        self.active_queue = new_queue
        print('get_next_task_parameters# 3active_queue', self.active_queue)
        # 判断是否需要获取新场景
        need_new_scenario = False
        if not self.current_scenario:
            need_new_scenario = True
        elif self.repetition_counter < self.max_repetitions:
            # 检查上一个任务的完成状态，如果未完成则不能继续重复
            if previous_task_completed:
                self.repetition_counter += 1
                self._update_completion_status(False)
                self.logger.debug(f"Task repetition incremented to {self.repetition_counter}/{self.max_repetitions}")
            # else:
            #     self.logger.warning(f"Previous task not completed, cannot increment repetition counter")
            #     # 可以选择强制标记为完成，或者返回错误状态
            #     # self._update_completion_status(True)  # True = 已完成
                # need_new_scenario = False
        else:
            # 当前场景的重复次数已达上限，需要获取新场景
            need_new_scenario = previous_task_completed
            # 标记当前场景完成
            self.logger.info(f"Current scenario repetitions completed for task '{self.task_type}'")
            # self._update_completion_status(True)  # True = 已完成
        print('get_next_task_parameters# 4need_new_scenario', need_new_scenario)
        if need_new_scenario:
            if not self.active_queue:
                self.logger.info(f"Active queue empty for task '{self.task_type}', all scenarios completed")
                if self.is_practice:
                    self._save_to_memory()
                else:
                    self._save_to_db()
                if self.are_all_scenarios_completed():
                    return "ALL_COMPLETED"
                return None

            self.current_scenario = self.active_queue.pop(0)
            self.repetition_counter = 1
            self.logger.info(f"New scenario started for task '{self.task_type}': diff='{self.current_scenario['difficulty_name']}', ai='{self.current_scenario.get('ai_level_name') or 'N/A'}'")
            self._update_completion_status(False)
        print('get_next_task_parameters# 5current_scenario', self.current_scenario)
        
        # 在构建 repetition_info 之前，先用最新配置刷新场景
        self._refresh_scenario_config(self.current_scenario)
        print(f'[CONFIG REFRESH] audio_enabled={self.current_scenario.get("audio_enabled")}, '
              f'difficulty_name={self.current_scenario.get("difficulty_name")}, '
              f'difficulty_config={self.current_scenario.get("difficulty_config")}')
        
        repetition_info = {
            "current": self.repetition_counter,
            "total": self.max_repetitions,
            "is_practice": self.is_practice,
            "difficulty": self.current_scenario.get('difficulty_name'),
            "is_ai_active": self.current_scenario.get('is_ai_active'),
            "audio_enabled": self.current_scenario.get('audio_enabled'),
            "previous_task_completed": previous_task_completed,  # 添加状态信息供调试
            "will_difficulty_change": self.current_scenario.get('will_difficulty_change', False)  # 从场景中获取预计算的难度变化标记
        }
        
        # 将类型编号添加到repetition_info中
        if self.current_scenario.get("scenario_info"):
            scenario_info = self.current_scenario["scenario_info"]
            repetition_info["scenario_index"] = scenario_info.get("index")
            repetition_info["scenario_total"] = scenario_info.get("total")

        self.current_scenario['repetition_info'] = repetition_info
        
        # 确保场景的 is_ai_active 与请求参数一致
        if self.current_scenario:
            original_ai_active = self.current_scenario.get('is_ai_active')
            self.current_scenario['is_ai_active'] = is_ai_active_request
            if original_ai_active != is_ai_active_request:
                self.logger.info(f"Synchronized scenario AI mode: {original_ai_active} -> {is_ai_active_request}")
            # 同时更新 repetition_info 中的 is_ai_active
            repetition_info["is_ai_active"] = is_ai_active_request
        
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