import json
from typing import Dict, Any, Optional, List
from .database_manager import db_manager

class TaskScenarioManager:
    """管理与数据库绑定的、持久化的用户任务场景"""
    
    def __init__(self, config: Dict[str, Any], user_id: str, task_type: str, is_practice: bool = False):
        self.config = config
        self.user_id = user_id
        self.task_type = task_type
        self.is_practice = is_practice
        
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

        if not self._load_from_db():
            self._initialize_new_progress()
            self._save_to_db()

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
                    print(f"✅ [Task Manager] Found existing progress for user '{self.user_id}' and task '{self.task_type}'.")
                    self.current_scenario = json.loads(row[0]) if row[0] else None
                    self.repetition_counter = row[1] or 0
                    self.ai_queue = json.loads(row[2]) if row[2] else []
                    self.manual_queue = json.loads(row[3]) if row[3] else []
                    return True
        except Exception as e:
            print(f"❌ Error loading progress from DB: {e}")
        return False

    def _save_to_db(self) -> None:
        """将当前状态的写入操作放入队列，但练习模式除外"""
        if self.is_practice:
            print("💾 [Task Manager] Practice mode: Skipping DB save.")
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
        print(f"💾 [Task Manager] Progress save queued for user '{self.user_id}', task '{self.task_type}'.")

    def _initialize_new_progress(self) -> None:
        """为新用户或新任务生成全新的队列和状态"""
        print(f"✨ [Task Manager] Initializing new progress for user '{self.user_id}', task '{self.task_type}'.")
        all_levels = self.config.get('levels', [])
        game_settings = self.config.get('game_settings', {})
        all_difficulties = game_settings.get('difficulty_levels', {})
        audio_options = [True, False]

        # AI模式
        ai_scenarios = []
        for diff_name, diff_conf in all_difficulties.items():
            for level_conf in all_levels:
                for audio in audio_options:
                    ai_scenarios.append({
                        "is_ai_active": True, 
                        "audio_enabled": audio,
                        "ai_level_name": level_conf['level'], 
                        "ai_level_config": level_conf,
                        "difficulty_name": diff_name, 
                        "difficulty_config": diff_conf
                    })
        
        # 为每个AI场景添加类型编号
        total_ai_scenarios = len(ai_scenarios)
        for i, scenario in enumerate(ai_scenarios):
            scenario['scenario_info'] = {'index': i + 1, 'total': total_ai_scenarios}
        self.ai_queue = ai_scenarios

        # 手动模式
        manual_scenarios = []
        for diff_name, diff_conf in all_difficulties.items():
            for audio in audio_options:
                manual_scenarios.append({
                    "is_ai_active": False, 
                    "audio_enabled": audio,
                    "ai_level_name": None, 
                    "ai_level_config": None,
                    "difficulty_name": diff_name, 
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
            print(f"🔄 [Task Manager - {self.task_type}] Switched to {'AI' if is_ai_active_request else 'Manual'} queue.")

        self.active_queue = new_queue

        if self.current_scenario and self.repetition_counter < self.max_repetitions:
            self.repetition_counter += 1
        else:
            if self.active_queue:
                self.current_scenario = self.active_queue.pop(0)
                self.repetition_counter = 1
                print(f"🆕 [Task Manager - {self.task_type}] New scenario started: diff='{self.current_scenario['difficulty_name']}', ai='{self.current_scenario.get('ai_level_name') or 'N/A'}'")
            else:
                print(f"🎉 [Task Manager - {self.task_type}] Active queue empty.")
                self.current_scenario = None
                self.repetition_counter = 0

        # 如果当前场景为空（因为队列已空），检查是否所有任务都完成了
        if not self.current_scenario:
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
            self._save_to_db()
        return self.current_scenario

# 任务ID计数器
task_counter = 0

def generate_task_id() -> int:
    """生成新的任务ID"""
    global task_counter
    task_id = task_counter
    task_counter += 1
    return task_id 