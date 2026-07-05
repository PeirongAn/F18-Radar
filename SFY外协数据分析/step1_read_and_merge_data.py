from __future__ import annotations

import sqlite3
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import argparse


# ----------------------------
# 全局常量（提高可读性与复用性）
# ----------------------------
TASK_NAME_MAP: Dict[str, str] = {
    '传感器': 'sensor',
    '威胁排序': 'threat',
    '武器发射': 'weapon',
    '平台控制': 'platform',
}

AI_LEVEL_MAP: Dict[str, str] = {
    '低等级': 'L0',
    '中等级': 'L1',
    '高等级': 'L2',
}

DIFFICULTY_MAP: Dict[str, str] = {
    '低难度': 'low',
    '高难度': 'high',
}

AUDIO_MAP: Dict[str, str] = {
    '高工效': '1',
    '低工效': '0',
}

COLUMNS_TO_REMOVE = {
    'id', 'task_id', 'created_at'
}

# 问卷文件排序权重
TASK_SORT_ORDER: Dict[str, int] = {
    '传感器': 0,
    '威胁排序': 1,
    '武器发射': 2,
    '平台控制': 3,
}

LEVEL_SORT_ORDER: Dict[str, int] = {
    '低等级': 0,
    '中等级': 1,
    '高等级': 2,
}

DIFFICULTY_SORT_ORDER: Dict[str, int] = {
    '低难度': 0,
    '高难度': 1,
}

AUDIO_SORT_ORDER: Dict[str, int] = {
    '高工效': 0,
    '低工效': 1,
}

# 在代码中直接指定被试名：
SUBJECTS_IN_CODE: List[str] = ['jianglu','baidexiang','gaoqingshuang','anpeirong','yuanpeijun','lihongzu']

# 输出控制：默认仅打印错误与最终总结；将 VERBOSE 设为 True 可查看详细过程
VERBOSE: bool = False

def vprint(message: str) -> None:
    if VERBOSE:
        print(message)


def get_workspace_root() -> Path:
    """Return the path to the workspace root directory."""
    return Path(__file__).resolve().parent


def get_web_data_dir() -> Path:
    """Return the path to the WEB_data directory."""
    return get_workspace_root() / "WEB_data"


def get_db_path_for_subject(subject_dir: Path) -> Optional[Path]:
    """Get the radar_operations.db file path for a subject."""
    db_path = subject_dir / "radar_operations.db"
    if db_path.exists():
        return db_path
    return None


def get_clean_columns_and_data(source_conn: sqlite3.Connection, table_name: str) -> Tuple[List[str], List[Tuple]]:
    """Get only the needed columns and data directly from source database, with reordered columns and filtered data."""
    # 获取所有列名
    cursor = source_conn.execute(f"SELECT * FROM {table_name}")
    all_columns = [description[0] for description in cursor.description]
    
    # 过滤出要保留的列
    clean_columns = [col for col in all_columns if col not in COLUMNS_TO_REMOVE]
    
    # 重新排列列的顺序：将ai_level放到difficulty_level后面
    reordered_columns = []
    ai_level_col = None
    
    for col in clean_columns:
        if col == 'ai_level':
            # 暂时跳过ai_level，稍后插入
            ai_level_col = col
        elif col == 'difficulty_level':
            # 先添加difficulty_level
            reordered_columns.append(col)
            # 然后立即添加ai_level
            if ai_level_col:
                reordered_columns.append(ai_level_col)
                ai_level_col = None
        else:
            # 添加其他列
            reordered_columns.append(col)
    
    # 如果ai_level还没有被添加（比如difficulty_level不存在），则添加到末尾
    if ai_level_col:
        reordered_columns.append(ai_level_col)
    
    # 构建SELECT语句，按新的列顺序选择
    select_columns = ', '.join([f'"{col}"' for col in reordered_columns])
    select_sql = f"SELECT {select_columns} FROM {table_name}"
    
    # 执行查询，直接获取清理后的数据
    cursor = source_conn.execute(select_sql)
    all_data = cursor.fetchall()
    
    # 过滤数据：不保存ai_level为null且audio_enabled为0的数据
    filtered_data = []
    ai_level_idx = reordered_columns.index('ai_level')
    audio_enabled_idx = reordered_columns.index('audio_enabled')
    
    filtered_count = 0
    for row in all_data:
        ai_level = row[ai_level_idx]
        audio_enabled = row[audio_enabled_idx]
        
        # 如果ai_level为null且audio_enabled为0，则跳过这条数据
        if ai_level is None and audio_enabled == 0:
            filtered_count += 1
            continue
        
        filtered_data.append(row)
    
    if filtered_count > 0:
        vprint(f"  过滤掉了 {filtered_count} 条ai_level为null且audio_enabled为0的数据")
    
    return reordered_columns, filtered_data


def normalize_repetition(columns: List[str], data: List[Tuple]) -> List[Tuple]:
    """Normalize repetition numbers to start from 1 and be consecutive for each experiment setting.
    
    Check if repetition numbers are discontinuous, if so, renumber them to be consecutive.
    Example: [1,3,4,5,6,7,8,9,10,11] -> [1,2,3,4,5,6,7,8,9,10]
    """
    # 找到关键列的索引
    try:
        ai_level_idx = columns.index('ai_level')
        difficulty_idx = columns.index('difficulty_level')
        audio_enabled_idx = columns.index('audio_enabled')
        repetition_idx = columns.index('repetition_count')
    except ValueError as e:
        vprint(f"  警告: 无法找到必要的列: {e}")
        return data
    
    # 创建实验设置的唯一标识
    experiment_groups = {}
    
    for row in data:
        # 创建实验设置的键（排除repetition）
        key = (row[ai_level_idx], row[difficulty_idx], row[audio_enabled_idx])
        
        if key not in experiment_groups:
            experiment_groups[key] = []
        
        experiment_groups[key].append(row)
    
    # 重新编号repetition
    normalized_data = []
    for key, experiments in experiment_groups.items():
        # 按原始repetition排序，确保数据顺序一致
        experiments.sort(key=lambda x: x[repetition_idx] if x[repetition_idx] is not None else 0)
        
        # 检查repetition是否连续
        original_repetitions = [exp[repetition_idx] for exp in experiments]
        expected_repetitions = list(range(1, len(experiments) + 1))
        
        # 判断是否需要重新编号
        needs_renumbering = False
        if len(original_repetitions) != len(expected_repetitions):
            needs_renumbering = True
        else:
            for i, (orig, expected) in enumerate(zip(original_repetitions, expected_repetitions)):
                if orig != expected:
                    needs_renumbering = True
                    break
        
        if needs_renumbering:
            vprint(f"    实验设置 {key}: repetition编号不连续 {original_repetitions}，重新编号为 {expected_repetitions}")
            # 重新编号，从1开始
            for i, row in enumerate(experiments, 1):
                new_row = list(row)
                new_row[repetition_idx] = i
                normalized_data.append(tuple(new_row))
        else:
            vprint(f"    实验设置 {key}: repetition编号连续 {original_repetitions}，无需重新编号")
            # 保持原有编号
            normalized_data.extend(experiments)
    
    vprint(f"  重新编号了 {len(normalized_data)} 条数据的repetition字段")
    return normalized_data


def copy_table_data(source_conn: sqlite3.Connection, target_conn: sqlite3.Connection, 
                   table_name: str, subject_name: str):
    """Copy data from source table to target table, with data cleaning and repetition normalization."""
    try:
        # 检查源表是否存在
        cursor = source_conn.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
        if not cursor.fetchone():
            vprint(f"  警告: 表 {table_name} 在 {subject_name} 的数据库中不存在")
            return
        
        # 直接从源数据库提取需要的列和数据
        vprint(f"  从 {table_name} 表提取需要的列和数据...")
        clean_columns, clean_data = get_clean_columns_and_data(source_conn, table_name)
        
        if not clean_data:
            vprint(f"  表 {table_name} 没有数据")
            return
        
        # 重新编号repetition，从1开始连续编号
        vprint(f"  重新编号repetition字段...")
        final_data = normalize_repetition(clean_columns, clean_data)
        
        # 检查目标表是否存在，如果不存在则创建
        cursor = target_conn.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
        if not cursor.fetchone():
            # 创建表结构
            vprint(f"  创建表 {table_name}...")
            create_table_statement = f"CREATE TABLE {table_name} ("
            column_definitions = []
            for col in clean_columns:
                column_definitions.append(f'"{col}" TEXT')
            create_table_statement += ", ".join(column_definitions) + ")"
            target_conn.execute(create_table_statement)
            target_conn.commit()
        
        # 插入数据
        placeholders = ', '.join(['?' for _ in clean_columns])
        column_names = ', '.join([f'"{col}"' for col in clean_columns])
        insert_sql = f"INSERT INTO {table_name} ({column_names}) VALUES ({placeholders})"
        
        for row in final_data:
            target_conn.execute(insert_sql, row)
        
        target_conn.commit()
        vprint(f"  成功复制 {len(final_data)} 行清理后的数据到表 {table_name}")
        
    except Exception as e:
        print(f"  错误: 复制表 {table_name} 数据时出错: {e}")


def process_web_data(subject_dir: Path, all_data_conn: sqlite3.Connection) -> bool:
    """Process data for a single subject."""
    subject_name = subject_dir.name
    vprint(f"处理被试: {subject_name}")
    
    # 查找数据库文件
    db_path = get_db_path_for_subject(subject_dir)
    if not db_path:
        print(f"错误: 未找到 {subject_name} 的 radar_operations.db 文件")
        return False
    
    try:
        # 连接源数据库
        source_conn = sqlite3.connect(str(db_path))
        
        # 处理 sensor_task_statistics_plus 表
        vprint(f"  处理 sensor_task_statistics_plus 表...")
        copy_table_data(source_conn, all_data_conn, "sensor_task_statistics_plus", subject_name)
        
        # 处理 threat_task_statistics_plus 表
        vprint(f"  处理 threat_task_statistics_plus 表...")
        copy_table_data(source_conn, all_data_conn, "threat_task_statistics_plus", subject_name)
        
        source_conn.close()
        return True
        
    except Exception as e:
        print(f"错误: 处理 {subject_name} 数据时出错: {e}")
        return False


def create_all_data_database(output_path: Path) -> sqlite3.Connection:
    """Create the all_data database and return the connection."""
    vprint(f"创建合并数据库: {output_path}")
    
    # 如果输出文件已存在，先删除
    if output_path.exists():
        output_path.unlink()
        vprint("  删除了已存在的输出文件")
    
    # 创建新的数据库连接
    all_data_conn = sqlite3.connect(str(output_path))
    
    return all_data_conn


def get_questionnaire_dir() -> Path:
    """Return the path to the questionnaire directory."""
    return get_workspace_root() / "questionnaire"


def parse_questionnaire_filename(filename: str) -> Dict[str, str]:
    """Parse questionnaire filename to extract experiment settings.
    
    Expected format: "任务类型_任务难度_自主等级_交互工效_问卷结果_时间"
    """
    # 移除.json扩展名
    name = filename.replace('.json', '')
    
    # 按_分割
    parts = name.split('_')
    
    if len(parts) < 5:
        return {}
    
    # 提取信息
    task_type = parts[0]  # 任务类型
    difficulty = parts[1]  # 任务难度
    ai_level = parts[2]   # 自主等级
    audio_enabled = parts[3]  # 交互工效
    
    return {
        'task_type': task_type,
        'difficulty': difficulty,
        'ai_level': ai_level,
        'audio_enabled': audio_enabled
    }


def map_questionnaire_values(parsed_info: Dict[str, str]) -> Dict[str, str]:
    """Map questionnaire values to database format."""
    return {
        'task_name': TASK_NAME_MAP.get(parsed_info.get('task_type', ''), ''),
        'ai_level': AI_LEVEL_MAP.get(parsed_info.get('ai_level', ''), ''),
        'difficulty_level': DIFFICULTY_MAP.get(parsed_info.get('difficulty', ''), ''),
        'audio_enabled': AUDIO_MAP.get(parsed_info.get('audio_enabled', ''), '')
    }


def read_questionnaire_file(file_path: Path) -> List[int]:
    """Read questionnaire file and extract scores."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 提取7个问题的分数
        scores = []
        answers = data.get('答案', {})
        
        for i in range(1, 8):
            question_key = f'问题{i}'
            if question_key in answers:
                score = answers[question_key].get('分数', 0)
                scores.append(score)
            else:
                scores.append(0)
        
        return scores
    except Exception as e:
        vprint(f"  警告: 读取问卷文件 {file_path.name} 时出错: {e}")
        return [0] * 7  # 返回7个0


def process_questionnaire_data(subject_name: str, all_data_conn: sqlite3.Connection) -> bool:
    """Process questionnaire data for a subject."""
    vprint(f"处理问卷数据: {subject_name}")
    
    questionnaire_dir = get_questionnaire_dir() / subject_name
    if not questionnaire_dir.exists():
        print(f"错误: 未找到 {subject_name} 的问卷目录")
        return False
    
    # 查找所有问卷文件
    questionnaire_files = list(questionnaire_dir.glob('*问卷结果*.json'))
    if not questionnaire_files:
        print(f"错误: 未找到 {subject_name} 的问卷文件")
        return False
    
    vprint(f"  找到 {len(questionnaire_files)} 个问卷文件")
    
    # 按照正确的顺序排序文件：低-中-高等级
    def sort_questionnaire_files(file_path):
        """按照任务类型、难度、等级、工效的顺序排序"""
        filename = file_path.name
        task_order = min((TASK_SORT_ORDER[k] for k in TASK_SORT_ORDER if k in filename), default=999)
        difficulty_order = DIFFICULTY_SORT_ORDER['低难度'] if '低难度' in filename else DIFFICULTY_SORT_ORDER['高难度']
        level_order = min((LEVEL_SORT_ORDER[k] for k in LEVEL_SORT_ORDER if k in filename), default=999)
        audio_order = AUDIO_SORT_ORDER['高工效'] if '高工效' in filename else AUDIO_SORT_ORDER['低工效']
        return (task_order, difficulty_order, level_order, audio_order)
    
    # 排序文件
    questionnaire_files.sort(key=sort_questionnaire_files)
    
    vprint(f"  按顺序处理文件:")
    for i, file_path in enumerate(questionnaire_files, 1):
        vprint(f"    {i:2d}. {file_path.name}")
    
    # 检查questionnaire_statistics表是否存在，如果不存在则创建
    cursor = all_data_conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='questionnaire_statistics'")
    if not cursor.fetchone():
        vprint(f"  创建questionnaire_statistics表...")
        create_table_sql = """
        CREATE TABLE questionnaire_statistics (
            user_id TEXT,
            task_name TEXT,
            difficulty_level TEXT,
            ai_level TEXT,
            audio_enabled TEXT,
            q1_score INTEGER,
            q2_score INTEGER,
            q3_score INTEGER,
            q4_score INTEGER,
            q5_score INTEGER,
            q6_score INTEGER,
            q7_score INTEGER
        )
        """
        all_data_conn.execute(create_table_sql)
        all_data_conn.commit()
    
    # 处理每个问卷文件
    processed_count = 0
    for file_path in questionnaire_files:
        # 解析文件名
        parsed_info = parse_questionnaire_filename(file_path.name)
        if not parsed_info:
            vprint(f"  警告: 无法解析文件名 {file_path.name}")
            continue
        
        # 映射值
        mapped_values = map_questionnaire_values(parsed_info)
        if not all(mapped_values.values()):
            vprint(f"  警告: 无法映射文件名 {file_path.name} 的值")
            continue
        
        # 读取问卷分数
        scores = read_questionnaire_file(file_path)
        
        # 插入数据
        insert_sql = """
        INSERT INTO questionnaire_statistics (
            user_id, task_name, difficulty_level, ai_level, audio_enabled,
            q1_score, q2_score, q3_score, q4_score, q5_score, q6_score, q7_score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        values = (
            subject_name,
            mapped_values['task_name'],
            mapped_values['difficulty_level'],
            mapped_values['ai_level'],
            mapped_values['audio_enabled']
        ) + tuple(scores)
        
        all_data_conn.execute(insert_sql, values)
        processed_count += 1
    
    all_data_conn.commit()
    vprint(f"  成功处理 {processed_count} 个问卷文件")
    return True


def get_ue_data_dir() -> Path:
    """Return the path to the UE_data directory."""
    return get_workspace_root() / "UE_data"


def parse_ue_folder_name(folder_name: str) -> Dict[str, str]:
    """Parse UE folder name to extract experiment settings.
    
    Expected format: "编号-实验类型-任务类型-任务难度-自主等级-交互工效"
    Examples:
    - "01-交互-平台控制-高难度" (交互类型，无自主等级)
    - "05-信任-平台控制-高难度-低等级-高工效" (信任类型，有自主等级)
    """
    parts = folder_name.split('-')
    
    if len(parts) < 4:
        return {}
    
    # 基本信息
    folder_id = parts[0]  # 编号
    experiment_type = parts[1]  # 实验类型（交互/信任）
    task_type = parts[2]  # 任务类型（武器发射/平台控制）
    difficulty = parts[3]  # 任务难度
    
    result = {
        'folder_id': folder_id,
        'experiment_type': experiment_type,
        'task_type': task_type,
        'difficulty': difficulty
    }
    
    # 如果是信任类型，还有自主等级和交互工效
    if experiment_type == '信任' and len(parts) >= 6:
        result['ai_level'] = parts[4]  # 自主等级
        result['audio_enabled'] = parts[5]  # 交互工效
    else:
        result['ai_level'] = None
        result['audio_enabled'] = None
    
    return result


def map_ue_values(parsed_info: Dict[str, str]) -> Dict[str, str]:
    """Map UE values to database format."""
    # 实验类型和自主等级的组合映射
    if parsed_info.get('experiment_type') == '交互':
        ai_level = 'NULL'
    elif parsed_info.get('experiment_type') == '信任' and parsed_info.get('ai_level'):
        ai_level = AI_LEVEL_MAP.get(parsed_info['ai_level'], 'NULL')
    else:
        ai_level = 'NULL'
    
    # 设置audio_enabled：交互类型为'1'，信任类型根据文件夹名称设置
    if parsed_info.get('experiment_type') == '交互':
        audio_enabled = '1'  # 交互类型任务都设置为高工效
    else:
        # 信任类型任务根据文件夹名称设置
        audio_enabled = AUDIO_MAP.get(parsed_info.get('audio_enabled', ''), '0') if parsed_info.get('audio_enabled') else '0'
    
    return {
        'difficulty_level': DIFFICULTY_MAP.get(parsed_info.get('difficulty', ''), ''),
        'ai_level': ai_level,
        'audio_enabled': audio_enabled
    }


def process_ue_data(subject_name: str, all_data_conn: sqlite3.Connection) -> bool:
    """Process UE data for a subject."""
    vprint(f"处理UE数据: {subject_name}")
    
    ue_data_dir = get_ue_data_dir() / subject_name
    if not ue_data_dir.exists():
        print(f"错误: 未找到 {subject_name} 的UE数据目录")
        return False
    
    # 查找所有实验文件夹
    experiment_folders = [p for p in ue_data_dir.iterdir() if p.is_dir()]
    if not experiment_folders:
        print(f"错误: 未找到 {subject_name} 的实验文件夹")
        return False
    
    vprint(f"  找到 {len(experiment_folders)} 个实验文件夹")
    
    # 按文件夹ID排序
    experiment_folders.sort(key=lambda x: int(x.name.split('-')[0]))
    
    # 检查并创建weapon_statistics和platform_statistics表
    weapon_table_exists = all_data_conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='weapon_statistics'").fetchone()
    platform_table_exists = all_data_conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='platform_statistics'").fetchone()
    
    if not weapon_table_exists:
        vprint(f"  创建weapon_statistics表...")
        create_weapon_table_sql = """
        CREATE TABLE weapon_statistics (
            user_id TEXT,
            difficulty_level TEXT,
            ai_level TEXT,
            audio_enabled TEXT,
            repetition_count INTEGER,
            ai_remind_time REAL,
            current_times REAL,
            fire_result TEXT,
            ai_control_time REAL,
            person_control_time REAL
        )
        """
        all_data_conn.execute(create_weapon_table_sql)
        all_data_conn.commit()
    
    if not platform_table_exists:
        vprint(f"  创建platform_statistics表...")
        create_platform_table_sql = """
        CREATE TABLE platform_statistics (
            user_id TEXT,
            difficulty_level TEXT,
            ai_level TEXT,
            audio_enabled TEXT,
            repetition_count INTEGER,
            is_correct TEXT,
            current_mode TEXT,
            current_times REAL,
            distance REAL,
            ai_control_time REAL,
            person_control_time REAL
        )
        """
        all_data_conn.execute(create_platform_table_sql)
        all_data_conn.commit()
    
    # 处理每个实验文件夹
    weapon_count = 0
    platform_count = 0
    
    for folder_path in experiment_folders:
        folder_name = folder_path.name
        vprint(f"  处理文件夹: {folder_name}")
        
        # 解析文件夹名称
        parsed_info = parse_ue_folder_name(folder_name)
        if not parsed_info:
            vprint(f"    警告: 无法解析文件夹名称 {folder_name}")
            continue
        
        # 映射值
        mapped_values = map_ue_values(parsed_info)
        if not mapped_values['difficulty_level']:
            vprint(f"    警告: 无法映射文件夹 {folder_name} 的值")
            continue
        
        # 确定目标表
        if parsed_info['task_type'] == '武器发射':
            target_table = 'weapon_statistics'
            weapon_count += 1
        elif parsed_info['task_type'] == '平台控制':
            target_table = 'platform_statistics'
            platform_count += 1
        else:
            vprint(f"    警告: 未知任务类型 {parsed_info['task_type']}")
            continue
        
        # 查找JSON文件（1-10.json）
        json_files = []
        for i in range(1, 11):
            json_file = folder_path / f"{i:02d}.json"
            if json_file.exists():
                json_files.append(json_file)
        
        if not json_files:
            vprint(f"    警告: 文件夹 {folder_name} 中没有找到JSON文件")
            continue
        
        vprint(f"    找到 {len(json_files)} 个JSON文件")
        
        # 为每个JSON文件创建一条记录
        for json_file in json_files:
            # 从文件名提取repetition_count
            repetition = int(json_file.stem)
            
            # 根据任务类型选择不同的插入逻辑
            if target_table == 'platform_statistics':
                # 平台控制任务：读取JSON内容并提取统计数据
                json_data = read_platform_json_file(json_file)
                
                insert_sql = f"""
                INSERT INTO {target_table} (
                    user_id, difficulty_level, ai_level, audio_enabled, repetition_count,
                    is_correct, current_mode, current_times, distance, ai_control_time, person_control_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                
                values = (
                    subject_name,
                    mapped_values['difficulty_level'],
                    mapped_values['ai_level'],
                    mapped_values['audio_enabled'],
                    repetition,
                    json_data['is_correct'],
                    json_data['current_mode'],
                    json_data['current_time'],
                    json_data['distance'],
                    json_data['ai_control_time'],
                    json_data['person_control_time']
                )
            else:
                # 武器发射任务：读取JSON内容并提取统计数据
                json_data = read_weapon_json_file(json_file)
                
                insert_sql = f"""
                INSERT INTO {target_table} (
                    user_id, difficulty_level, ai_level, audio_enabled, repetition_count,
                    ai_remind_time, current_times, fire_result, ai_control_time, person_control_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                
                values = (
                    subject_name,
                    mapped_values['difficulty_level'],
                    mapped_values['ai_level'],
                    mapped_values['audio_enabled'],
                    repetition,
                    json_data['ai_remind_time'],
                    json_data['current_time'],
                    json_data['fire_result'],
                    json_data['ai_control_time'],
                    json_data['person_control_time']
                )
            
            all_data_conn.execute(insert_sql, values)
        
        all_data_conn.commit()
    
    vprint(f"  成功处理 {weapon_count} 个武器发射实验文件夹")
    vprint(f"  成功处理 {platform_count} 个平台控制实验文件夹")
    return True


def read_platform_json_file(file_path: Path) -> Dict[str, Any]:
    """Read platform control JSON file and extract relevant data."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 提取时间数据
        ai_control_time = data.get('AIcontrolTime', 0.0)
        person_control_time = data.get('PersonControlTime', 0.0)
        
        # 检查CurrentRedcord是否为空
        current_record = data.get('CurrentRedcord', [])
        is_correct = 'false' if not current_record else 'true'
        
        # 提取CurrentTime和CurrentMode数据
        current_time = None
        current_mode = None
        distance = None
        if current_record and len(current_record) > 0:
            # 取第一个记录的数据
            first_record = current_record[0]
            current_time = first_record.get('CurrentTime', None)
            current_mode = first_record.get('CurrentMode', None)
            distance = first_record.get('Distance', None)
        
        return {
            'is_correct': is_correct,
            'current_mode': current_mode,
            'current_time': current_time,
            'distance': distance,
            'ai_control_time': ai_control_time,
            'person_control_time': person_control_time
        }
    except Exception as e:
        vprint(f"    警告: 读取平台控制JSON文件 {file_path.name} 时出错: {e}")
        # 返回默认值
        return {
            'is_correct': 'false',
            'current_mode': None,
            'current_time': None,
            'distance': None,
            'ai_control_time': 0.0,
            'person_control_time': 0.0
        }


def read_weapon_json_file(file_path: Path) -> Dict[str, Any]:
    """Read weapon launch JSON file and extract relevant data."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 提取基本时间数据
        ai_remind_time = data.get('AITIME', {}).get('AiRemindTime', 0.0)
        ai_control_time = data.get('AIcontrolTime', 0.0)
        person_control_time = data.get('PersonControlTime', 0.0)
        
        # 检查Fire是否为空
        fire_data = data.get('Fire', [])
        if not fire_data:
            # Fire为空，设置默认值
            current_time = None
            fire_result = 'false'
        else:
            # Fire不为空，提取第一个记录的数据
            first_fire = fire_data[0]
            current_time = first_fire.get('CurrentTime', None)
            fire_result = 'true' if first_fire.get('FireResult', False) else 'false'
        
        return {
            'ai_remind_time': ai_remind_time,
            'current_time': current_time,
            'fire_result': fire_result,
            'ai_control_time': ai_control_time,
            'person_control_time': person_control_time
        }
    except Exception as e:
        vprint(f"    警告: 读取武器发射JSON文件 {file_path.name} 时出错: {e}")
        # 返回默认值
        return {
            'ai_remind_time': 0.0,
            'current_time': None,
            'fire_result': 'false',
            'ai_control_time': 0.0,
            'person_control_time': 0.0
        }


def main():
    parser = argparse.ArgumentParser(description="读取多个被试的数据库文件并合并到all_data数据库中，自动清理无用数据并重新编号repetition")
    parser.add_argument("--output", "-o", type=str, default="all_data.db", help="输出数据库文件名，默认为all_data.db")
    # 被试名仅从代码常量 SUBJECTS_IN_CODE 中读取
    args = parser.parse_args()
    
    # 设置路径
    web_data_dir = get_web_data_dir()
    output_path = get_workspace_root() / args.output
    
    vprint(f"WEB_data目录: {web_data_dir}")
    vprint(f"输出文件: {output_path}")
    vprint("注意: 程序将自动删除以下无用列: id, task_id, created_at")
    vprint("注意: 将保留所有数据，只重新编号repetition为连续序列")
    
    try:
        # 创建合并数据库
        all_data_conn = create_all_data_database(output_path)
        
        # 获取被试名列表：从代码常量 SUBJECTS_IN_CODE 读取
        selected_subject_names = SUBJECTS_IN_CODE
        if not selected_subject_names:
            print("错误: 未指定被试名。请在代码顶部的 SUBJECTS_IN_CODE 中填写，例如 ['jianglu']。")
            all_data_conn.close()
            return 1

        vprint(f"\n将处理以下被试: {selected_subject_names}")
        vprint(f"被试总数: {len(selected_subject_names)}")
        
        
        # 依次处理每个被试的每类数据
        questionnaire_success_count = 0
        ue_success_count = 0
        web_success_count = 0
        
        for subject_name in selected_subject_names:
            vprint(f"\n=== 处理被试: {subject_name} ===")
            
            # 处理问卷数据
            vprint(f"  处理问卷数据...")
            if process_questionnaire_data(subject_name, all_data_conn):
                questionnaire_success_count += 1
                vprint(f"  ✓ 问卷数据处理成功")
            else:
                vprint(f"  ✗ 跳过问卷数据（无数据或处理失败）")
            
            # 处理UE数据
            vprint(f"  处理UE数据...")
            if process_ue_data(subject_name, all_data_conn):
                ue_success_count += 1
                vprint(f"  ✓ UE数据处理成功")
            else:
                vprint(f"  ✗ 跳过UE数据（无数据或处理失败）")
            
            # 处理WEB数据
            vprint(f"  处理WEB数据...")
            subject_dir = web_data_dir / subject_name
            if process_web_data(subject_dir, all_data_conn):
                web_success_count += 1
                vprint(f"  ✓ WEB数据处理成功")
            else:
                vprint(f"  ✗ 跳过WEB数据（无数据或处理失败）")
            
            vprint("")  # 空行分隔

        # 关闭数据库连接
        all_data_conn.close()
        
        print("处理完成！")
        print(f"- 被试数量: {len(selected_subject_names)}")
        print(f"- 问卷处理成功: {questionnaire_success_count}/{len(selected_subject_names)}")
        print(f"- UE数据处理成功: {ue_success_count}/{len(selected_subject_names)}")
        print(f"- WEB数据处理成功: {web_success_count}/{len(selected_subject_names)}")
        print(f"合并后的数据已保存到: {output_path}")
        
    except Exception as e:
        print(f"程序执行出错: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
