"""
外部配置更新处理器
接收 config_update 类型的消息，实时写入 init_config.json 和 agent_level.json。

消息格式示例:
{
  "type": "config_update",
  "userId": "pilot_01",
  "includeAI": true,
  "taskType": "radar",
  "isPractice": false,
  "useJoystick": true,
  "current_difficulty": "high",
  "audio_enabled": false
}
"""

import json
import os
from typing import Dict, Any

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from managers import get_logger

logger = get_logger("external_config")

PUBLIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'public'))
INIT_CONFIG_PATH = os.path.join(PUBLIC_DIR, 'init_config.json')
AGENT_LEVEL_PATH = os.path.join(PUBLIC_DIR, 'agent_level.json')

INIT_CONFIG_KEYS = {'userId', 'includeAI', 'taskType', 'isPractice', 'useJoystick'}
AGENT_LEVEL_KEYS = {'current_difficulty', 'audio_enabled'}


def _read_json(path: str) -> Dict[str, Any]:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _write_json(path: str, data: Dict[str, Any]) -> None:
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def apply_config_update(message: Dict[str, Any]) -> Dict[str, Any]:
    """根据消息内容更新配置文件，返回实际被修改的字段摘要"""
    changes: Dict[str, Any] = {}

    # --- init_config.json ---
    init_fields = {k: message[k] for k in INIT_CONFIG_KEYS if k in message}
    if init_fields:
        init_config = _read_json(INIT_CONFIG_PATH)
        init_config.update(init_fields)
        _write_json(INIT_CONFIG_PATH, init_config)
        changes['init_config'] = init_fields
        logger.info(f"init_config.json updated: {init_fields}")

    # --- agent_level.json (game_settings 子字段) ---
    agent_fields = {k: message[k] for k in AGENT_LEVEL_KEYS if k in message}
    if agent_fields:
        agent_config = _read_json(AGENT_LEVEL_PATH)
        game_settings = agent_config.setdefault('game_settings', {})
        game_settings.update(agent_fields)
        _write_json(AGENT_LEVEL_PATH, agent_config)
        changes['agent_level'] = agent_fields
        logger.info(f"agent_level.json updated: {agent_fields}")

    return changes
