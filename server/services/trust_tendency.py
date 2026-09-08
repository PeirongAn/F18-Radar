"""Configuration-backed tendency source; no behavior inference or UI rendering."""
import copy
import json
import logging
import os
import tempfile
from pathlib import Path

from runtime_paths import CONFIG_DIR

STATES = ("under_trust", "normal", "over_trust")
BASE_POLICY = {"show_evidence": False, "show_reliability": False, "highlight": "none"}
DEFAULT_CONFIG = {
    "tendency": "normal",
    "policies": {
        "under_trust": {**BASE_POLICY, "show_evidence": True, "highlight": "observation"},
        "normal": dict(BASE_POLICY),
        "over_trust": {**BASE_POLICY, "show_reliability": True, "highlight": "reliability"},
    },
}


def validate_config(value):
    if not isinstance(value, dict) or value.get("tendency") not in STATES:
        raise ValueError("信任倾向无效")
    policies = value.get("policies")
    if not isinstance(policies, dict) or set(policies) != set(STATES):
        raise ValueError("必须提供三种信任倾向的策略")
    for policy in policies.values():
        if not isinstance(policy, dict) or set(policy) != set(BASE_POLICY):
            raise ValueError("显示策略字段无效")
        if any(type(policy.get(key)) is not bool for key in ("show_evidence", "show_reliability")):
            raise ValueError("内容选项必须为布尔值")
        if policy.get("highlight") not in ("none", "observation", "reliability"):
            raise ValueError("高亮区域无效")
    return {"tendency": value["tendency"], "policies": copy.deepcopy(policies)}


class TrustTendencySource:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else CONFIG_DIR / "trust_control_v1.json"

    def read_config(self):
        return validate_config(json.loads(self.path.read_text(encoding="utf-8-sig")))

    def get_tendency(self, config=None):
        # An already-read config keeps state and policy from one file snapshot.
        return (config if config is not None else self.read_config())["tendency"]

    def save_config(self, value):
        config = validate_config(value)
        # Same-directory replacement leaves the previous file intact on write failure.
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             prefix=".trust-config-", suffix=".tmp", delete=False) as stream:
                temporary = stream.name
                json.dump(config, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
        return config


class TrustPolicyResolver:
    """Group snapshots remain stable until an explicit settings save."""
    def __init__(self, source):
        self.source = source
        self.snapshots = {}

    def apply_config(self, config):
        config = validate_config(config)
        self.snapshots.clear()
        tendency = self.source.get_tendency(config)
        return {"tendency": tendency, "source": "config", "valid": True,
                "policy": copy.deepcopy(config["policies"][tendency])}

    def resolve(self, user_id, group_id):
        key = (str(user_id or ""), str(group_id)) if group_id is not None else None
        if key is not None and key in self.snapshots:
            return copy.deepcopy(self.snapshots[key])
        try:
            config = self.source.read_config()
            tendency = self.source.get_tendency(config)
            result = {"tendency": tendency, "source": "config", "valid": True,
                      "policy": config["policies"][tendency]}
        except (OSError, ValueError, TypeError) as exc:
            logging.getLogger(__name__).warning("Trust config fallback: %s", exc)
            result = {"tendency": "normal", "source": "fallback", "valid": False,
                      "reason": "信任配置读取失败，使用基础显示", "policy": dict(BASE_POLICY)}
        if key is not None:
            self.snapshots[key] = copy.deepcopy(result)
        return result


trust_tendency_source = TrustTendencySource()


def get_tendency():
    """Stable public entry point for a future database-backed source."""
    return trust_tendency_source.get_tendency()
