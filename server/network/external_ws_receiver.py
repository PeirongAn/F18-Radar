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
  "taskNumber": 3,
  "current_difficulty": "high",
  "audio_enabled": false,
  "trust_calibration": {
    "enabled": true,
    "sensor": {},
    "threat": {},
    "display": {}
  }
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

INIT_CONFIG_KEYS = {'userId', 'includeAI', 'taskType', 'isPractice', 'useJoystick', 'taskNumber'}
AGENT_LEVEL_KEYS = {'current_difficulty', 'audio_enabled'}
TRUST_CALIBRATION_KEY = 'trust_calibration'


def _read_json(path: str) -> Dict[str, Any]:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _write_json(path: str, data: Dict[str, Any]) -> None:
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


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

    # --- agent_level.json (game_settings 子字段 + trust_calibration 顶层字段) ---
    agent_fields = {k: message[k] for k in AGENT_LEVEL_KEYS if k in message}
    trust_calibration = message.get(TRUST_CALIBRATION_KEY)
    if agent_fields or trust_calibration is not None:
        agent_config = _read_json(AGENT_LEVEL_PATH)
        agent_changes: Dict[str, Any] = {}

        if agent_fields:
            game_settings = agent_config.setdefault('game_settings', {})
            game_settings.update(agent_fields)
            agent_changes.update(agent_fields)

        if trust_calibration is not None:
            if not isinstance(trust_calibration, dict):
                raise ValueError('trust_calibration must be an object')
            existing_trust_config = agent_config.get(TRUST_CALIBRATION_KEY)
            if not isinstance(existing_trust_config, dict):
                existing_trust_config = {}
            merged_trust_config = _merge_dict(existing_trust_config, trust_calibration)
            agent_config[TRUST_CALIBRATION_KEY] = merged_trust_config
            agent_changes[TRUST_CALIBRATION_KEY] = merged_trust_config

        _write_json(AGENT_LEVEL_PATH, agent_config)
        changes['agent_level'] = agent_changes
        logger.info(f"agent_level.json updated: {agent_changes}")

        try:
            from managers import config_manager
            config_manager.load_config()
        except Exception as exc:
            logger.warning(f"agent_level.json updated, but in-memory config reload failed: {exc}")

    return changes
