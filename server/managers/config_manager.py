import json
import os
from typing import Dict, Any
from .logger_manager import get_logger
from runtime_paths import CONFIG_DIR

class ConfigManager:
    """配置管理器，负责加载和管理系统配置"""
    
    def __init__(self):
        self.config: Dict[str, Any] = {}
        self.logger = get_logger("config")
        self.load_config()
    
    def load_config(self) -> None:
        """加载配置文件"""
        config_path = str(CONFIG_DIR / 'agent_level.json')
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            self.logger.info("Configuration loaded successfully.")
        except (FileNotFoundError, json.JSONDecodeError) as e:
            self.logger.warning(f"Error loading configuration: {e}. Using default settings.")
            self._use_default_config()
    
    def _use_default_config(self) -> None:
        """使用默认配置"""
        self.config = {
            "game_settings": {
                "current_difficulty": "low",
                "audio_enabled": True,
                "difficulty_levels": {
                    "low": {"threat_count": 4, "target_count": 5},
                    "high": {"threat_count": 8, "target_count": 10}
                }
            }
        }
    
    def get_config(self) -> Dict[str, Any]:
        """获取完整配置（每次从文件重新读取最新内容）"""
        self.load_config()
        return self.config
    
    def get_game_settings(self) -> Dict[str, Any]:
        """获取游戏设置"""
        return self.config.get('game_settings', {})
    
    def get_difficulty_levels(self) -> Dict[str, Any]:
        """获取难度级别配置"""
        return self.get_game_settings().get('difficulty_levels', {})
    
    def get_ai_levels(self) -> list:
        """获取AI级别配置"""
        return self.config.get('levels', [])

    def get_trust_calibration_config(self) -> Dict[str, Any]:
        """获取信任调控配置"""
        return self.config.get('trust_calibration', {})

    def get_trust_control_config(self) -> Dict[str, Any]:
        """获取统一信任调控配置。"""
        return self.config.get('trust_control', {})
    
    def is_audio_enabled(self) -> bool:
        """检查音频是否启用"""
        return self.get_game_settings().get('audio_enabled', True)

# 全局配置管理器实例
config_manager = ConfigManager()
