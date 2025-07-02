import sqlite3
import json
import os
from typing import Dict, List, Any, Optional
from datetime import datetime

class DataStatistics:
    """数据统计分析器"""
    
    def __init__(self, db_path: str = "./data/radar_operations.db"):
        self.db_path = db_path
        self.conn = None
        
    def connect(self):
        """连接数据库"""
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"数据库文件不存在: {self.db_path}")
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        
    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            
    def create_statistics_tables(self):
        """创建统计结果表"""
        if not self.conn:
            raise RuntimeError("数据库连接未建立")
        cursor = self.conn.cursor()
        
        # 创建传感器任务统计表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sensor_task_statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                task_id INTEGER,
                is_ai_active BOOLEAN,
                ai_level TEXT,
                difficulty_level TEXT,
                audio_enabled BOOLEAN,
                repetition_count INTEGER,
                radar_settings_time INTEGER,
                antenna_settings_time INTEGER,
                target_selection_time INTEGER,
                total_task_time INTEGER,
                is_correct TEXT,
                selection_method TEXT,
                task_settings_detail TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 创建威胁排序任务统计表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS threat_task_statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                task_id INTEGER,
                is_ai_active BOOLEAN,
                ai_level TEXT,
                difficulty_level TEXT,
                audio_enabled BOOLEAN,
                repetition_count INTEGER,
                threat_selection_time INTEGER,
                total_task_time INTEGER,
                is_correct TEXT,
                selection_method TEXT,
                task_settings_detail TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        self.conn.commit()
        
    def calculate_repetition_count(self, task_settings_data: List[Dict]) -> Dict[int, int]:
        """计算重复序号"""
        repetition_counts = {}
        current_settings = None
        current_count = 0
        
        for record in task_settings_data:
            task_id = record['task_id']
            # 提取设置信息（排除id和task_id）
            settings_key = (
                record['user_id'],
                record['is_ai_active'],
                record['ai_level_name'],
                record['difficulty_name'],
                record['audio_enabled']
            )
            
            if current_settings == settings_key:
                current_count += 1
            else:
                current_count = 1
                current_settings = settings_key
                
            repetition_counts[task_id] = current_count
            
        return repetition_counts
        
    def generate_sensor_task_statistics(self):
        """生成传感器任务统计数据"""
        if not self.conn:
            raise RuntimeError("数据库连接未建立")
        cursor = self.conn.cursor()
        
        # 获取所有传感器任务相关的操作
        cursor.execute("""
            SELECT uo.*, ts.ai_level_name, ts.difficulty_name, ts.audio_enabled, ts.is_ai_active
            FROM user_operations uo
            LEFT JOIN task_settings ts ON uo.task_id = ts.task_id
            WHERE uo.operation_type IN ('task_start', 'settings_update', 'antenna_adjusted', 'target_selected')
            ORDER BY uo.task_id, uo.timestamp
        """)
        
        operations = cursor.fetchall()
        
        # 按task_id分组
        task_groups = {}
        for op in operations:
            task_id = op['task_id']
            if task_id not in task_groups:
                task_groups[task_id] = []
            task_groups[task_id].append(dict(op))
            
        # 获取任务设置数据用于计算重复序号
        cursor.execute("""
            SELECT * FROM task_settings 
            WHERE task_id IN (
                SELECT DISTINCT task_id FROM user_operations 
                WHERE operation_type IN ('task_start', 'settings_update', 'antenna_adjusted', 'target_selected')
            )
            ORDER BY task_id
        """)
        task_settings = [dict(row) for row in cursor.fetchall()]
        repetition_counts = self.calculate_repetition_count(task_settings)
        
        # 生成统计数据
        statistics = []
        for task_id, ops in task_groups.items():
            if not ops:
                continue
                
            # 查找关键操作
            task_start = None
            settings_update = None
            antenna_adjusted = None
            target_selected = None
            
            for op in ops:
                if op['operation_type'] == 'task_start':
                    task_start = op
                elif op['operation_type'] == 'settings_update':
                    settings_update = op
                elif op['operation_type'] == 'antenna_adjusted':
                    antenna_adjusted = op
                elif op['operation_type'] == 'target_selected':
                    target_selected = op
                    
            if not task_start or not target_selected:
                continue
                
            # 计算时间差
            radar_settings_time = None
            if settings_update:
                radar_settings_time = settings_update['timestamp'] - settings_update['receive_timestamp'] 
                
            antenna_settings_time = None
            if antenna_adjusted:
                antenna_settings_time = antenna_adjusted['timestamp'] - antenna_adjusted['receive_timestamp']
                
            target_selection_time =  target_selected['timestamp'] - target_selected['receive_timestamp']
            total_task_time = target_selected['timestamp'] - task_start['timestamp']
            
            # 获取任务设置详情
            task_settings_detail = json.dumps({
                'ai_level_config': target_selected.get('ai_level_name'),
                'difficulty_config': target_selected.get('difficulty_name'),
                'audio_enabled': target_selected.get('audio_enabled')
            })
            
            stat = {
                'user_id': target_selected['user_id'],
                'task_id': task_id,
                'is_ai_active': target_selected.get('is_active'),
                'ai_level': target_selected.get('ai_level_name'),
                'difficulty_level': target_selected.get('difficulty_name'),
                'audio_enabled': target_selected.get('audio_enabled'),
                'repetition_count': repetition_counts.get(task_id, 1),
                'radar_settings_time': radar_settings_time,
                'antenna_settings_time': antenna_settings_time,
                'target_selection_time': target_selection_time,
                'total_task_time': total_task_time,
                'is_correct': target_selected.get('is_correct', 'not_set'),
                'selection_method': target_selected.get('event_owner'),
                'task_settings_detail': task_settings_detail
            }
            
            statistics.append(stat)
            
        return statistics
        
    def generate_threat_task_statistics(self):
        """生成威胁排序任务统计数据"""
        if not self.conn:
            raise RuntimeError("数据库连接未建立")
        cursor = self.conn.cursor()
        
        # 获取所有威胁任务相关的操作
        cursor.execute("""
            SELECT uo.*, ts.ai_level_name, ts.difficulty_name, ts.audio_enabled, ts.is_ai_active
            FROM user_operations uo
            LEFT JOIN task_settings ts ON uo.task_id = ts.task_id
            WHERE uo.operation_type IN ('SwitchSA', 'ResetSA', 'threat_clicked')
            ORDER BY uo.task_id, uo.timestamp
        """)
        
        operations = cursor.fetchall()
        
        # 按task_id分组
        task_groups = {}
        for op in operations:
            task_id = op['task_id']
            if task_id not in task_groups:
                task_groups[task_id] = []
            task_groups[task_id].append(dict(op))
            
        # 获取任务设置数据用于计算重复序号
        cursor.execute("""
            SELECT * FROM task_settings 
            WHERE task_id IN (
                SELECT DISTINCT task_id FROM user_operations 
                WHERE operation_type IN ('SwitchSA', 'ResetSA', 'threat_clicked')
            )
            ORDER BY task_id
        """)
        task_settings = [dict(row) for row in cursor.fetchall()]
        repetition_counts = self.calculate_repetition_count(task_settings)
        
        # 生成统计数据
        statistics = []
        for task_id, ops in task_groups.items():
            if not ops:
                continue
                
            # 查找关键操作
            task_start = None
            threat_clicked = None
            
            for op in ops:
                if op['operation_type'] in ('SwitchSA', 'ResetSA'):
                    if not task_start or op['timestamp'] < task_start['timestamp']:
                        task_start = op
                elif op['operation_type'] == 'threat_clicked':
                    threat_clicked = op
                    
            if not task_start or not threat_clicked:
                continue
                
            # 计算时间差
            threat_selection_time =  threat_clicked['timestamp'] - threat_clicked['receive_timestamp']
            total_task_time = threat_clicked['timestamp'] - task_start['timestamp'] 
            
            # 获取任务设置详情
            task_settings_detail = json.dumps({
                'ai_level_config': threat_clicked.get('ai_level_name'),
                'difficulty_config': threat_clicked.get('difficulty_name'),
                'audio_enabled': threat_clicked.get('audio_enabled')
            })
            
            stat = {
                'user_id': threat_clicked['user_id'],
                'task_id': task_id,
                'is_ai_active': threat_clicked.get('is_active'),
                'ai_level': threat_clicked.get('ai_level_name'),
                'difficulty_level': threat_clicked.get('difficulty_name'),
                'audio_enabled': threat_clicked.get('audio_enabled'),
                'repetition_count': repetition_counts.get(task_id, 1),
                'threat_selection_time': threat_selection_time,
                'total_task_time': total_task_time,
                'is_correct': threat_clicked.get('is_correct', 'not_set'),
                'selection_method': threat_clicked.get('event_owner'),
                'task_settings_detail': task_settings_detail
            }
            
            statistics.append(stat)
            
        return statistics
        
    def save_statistics(self, sensor_stats: List[Dict], threat_stats: List[Dict]):
        """保存统计数据到数据库"""
        if not self.conn:
            raise RuntimeError("数据库连接未建立")
        cursor = self.conn.cursor()
        
        # 插入传感器任务统计数据
        for stat in sensor_stats:
            cursor.execute("""
                INSERT INTO sensor_task_statistics (
                    user_id, task_id, is_ai_active, ai_level, difficulty_level, 
                    audio_enabled, repetition_count, radar_settings_time, antenna_settings_time,
                    target_selection_time, total_task_time, is_correct, selection_method, task_settings_detail
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                stat['user_id'], stat['task_id'], stat['is_ai_active'], stat['ai_level'],
                stat['difficulty_level'], stat['audio_enabled'], stat['repetition_count'],
                stat['radar_settings_time'], stat['antenna_settings_time'], stat['target_selection_time'],
                stat['total_task_time'], stat['is_correct'], stat['selection_method'], stat['task_settings_detail']
            ))
            
        # 插入威胁任务统计数据
        for stat in threat_stats:
            cursor.execute("""
                INSERT INTO threat_task_statistics (
                    user_id, task_id, is_ai_active, ai_level, difficulty_level,
                    audio_enabled, repetition_count, threat_selection_time, total_task_time,
                    is_correct, selection_method, task_settings_detail
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                stat['user_id'], stat['task_id'], stat['is_ai_active'], stat['ai_level'],
                stat['difficulty_level'], stat['audio_enabled'], stat['repetition_count'],
                stat['threat_selection_time'], stat['total_task_time'], stat['is_correct'],
                stat['selection_method'], stat['task_settings_detail']
            ))
            
        self.conn.commit()
        print(f"已保存 {len(sensor_stats)} 条传感器任务统计数据和 {len(threat_stats)} 条威胁任务统计数据")
        
    def generate_statistics(self):
        """生成所有统计数据"""
        try:
            self.connect()
            self.create_statistics_tables()
            
            # 清空现有统计数据
            print("正在清空现有统计数据...")
            if not self.conn:
                raise RuntimeError("数据库连接未建立")
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM sensor_task_statistics")
            cursor.execute("DELETE FROM threat_task_statistics")
            self.conn.commit()
            print("现有统计数据已清空")
            
            print("正在生成传感器任务统计数据...")
            sensor_stats = self.generate_sensor_task_statistics()
            print(f"生成了 {len(sensor_stats)} 条传感器任务统计数据")
            
            print("正在生成威胁排序任务统计数据...")
            threat_stats = self.generate_threat_task_statistics()
            print(f"生成了 {len(threat_stats)} 条威胁任务统计数据")
            
            print("正在保存统计数据到数据库...")
            self.save_statistics(sensor_stats, threat_stats)
            
            print("数据统计完成！")
            
        except Exception as e:
            print(f"生成统计数据时出错: {e}")
            raise
        finally:
            self.close()

def main():
    """主函数"""
    statistics = DataStatistics()
    statistics.generate_statistics()

if __name__ == "__main__":
    main() 