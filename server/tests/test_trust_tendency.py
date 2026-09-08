import asyncio
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.trust_tendency import (
    BASE_POLICY, DEFAULT_CONFIG, TrustPolicyResolver, TrustTendencySource, validate_config,
)


@pytest.fixture
def source(tmp_path):
    instance = TrustTendencySource(tmp_path / "trust_control_v1.json")
    instance.save_config(DEFAULT_CONFIG)
    return instance


def test_save_reload_and_get_tendency(source):
    config = source.read_config()
    config["tendency"] = "over_trust"
    source.save_config(config)
    assert TrustTendencySource(source.path).get_tendency() == "over_trust"


@pytest.mark.parametrize("change", [
    lambda c: c.update(tendency="unknown"),
    lambda c: c["policies"].pop("normal"),
    lambda c: c["policies"]["normal"].update(show_evidence="false"),
    lambda c: c["policies"]["normal"].update(highlight="script"),
])
def test_invalid_save_preserves_file(source, change):
    before = source.path.read_bytes()
    config = source.read_config()
    change(config)
    with pytest.raises(ValueError):
        source.save_config(config)
    assert source.path.read_bytes() == before


def test_failed_replace_preserves_file(source, monkeypatch):
    import services.trust_tendency as module
    before = source.path.read_bytes()
    def deny(*args):
        raise PermissionError("denied")
    monkeypatch.setattr(module.os, "replace", deny)
    with pytest.raises(PermissionError):
        source.save_config(DEFAULT_CONFIG)
    assert source.path.read_bytes() == before
    assert not list(source.path.parent.glob(".trust-config-*.tmp"))


def test_group_snapshot_and_reconnection(source):
    resolver = TrustPolicyResolver(source)
    first = resolver.resolve("u1", 100)
    changed = source.read_config()
    changed["tendency"] = "over_trust"
    source.save_config(changed)
    assert resolver.resolve("u1", 100) == first
    # A new browser/session uses the same process-owned resolver.
    assert resolver.resolve("u1", 100)["tendency"] == "normal"
    assert resolver.resolve("u1", 101)["tendency"] == "over_trust"
    assert resolver.resolve("u2", 100)["tendency"] == "over_trust"
    first["policy"]["highlight"] = "observation"
    assert resolver.resolve("u1", 100)["policy"] == BASE_POLICY


def test_no_group_preview_does_not_freeze(source):
    resolver = TrustPolicyResolver(source)
    resolver.resolve("u", None)
    config = source.read_config()
    config["tendency"] = "under_trust"
    source.save_config(config)
    assert resolver.resolve("u", 1)["tendency"] == "under_trust"


@pytest.mark.parametrize("contents", [None, "{invalid", '{"tendency":"bad"}'])
def test_bad_config_uses_basic_display(tmp_path, contents):
    path = tmp_path / "config.json"
    if contents is not None:
        path.write_text(contents)
    result = TrustPolicyResolver(TrustTendencySource(path)).resolve("u", 1)
    assert not result["valid"]
    assert result["source"] == "fallback"
    assert result["policy"] == BASE_POLICY


def test_form_only_does_not_enable_content():
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["policies"]["normal"]["highlight"] = "reliability"
    assert validate_config(config)["policies"]["normal"] == {
        **BASE_POLICY, "highlight": "reliability",
    }


def test_websocket_config_and_task_payload(source, monkeypatch):
    from core.message_handler import MessageHandler
    from managers import db_manager
    handler = MessageHandler()
    handler.trust_policy_resolver = TrustPolicyResolver(source)
    monkeypatch.setattr(db_manager, "get_trust_history", lambda *args: [
        {"trust_outcome": "over_trust", "ai_correct": False},
    ])
    def request(message):
        return asyncio.run(handler.handle_client_message(json.dumps(message), {}))[0]
    response = request({"type": "trust_config_get", "request_id": "read"})
    assert response["ok"] and response["request_id"] == "read"
    scenario = {"difficulty_name": "high", "ai_level_name": "L1"}
    radar = handler._build_trust_control_state(1, "RADAR_TARGETING", scenario, "u")
    handler.current_session['task_start_responses'] = {
        'RADAR_TARGETING': {'responses': [{'trust_control': copy.deepcopy(radar)}]},
    }
    config = response["config"]
    config["tendency"] = "under_trust"
    saved = request({"type": "trust_config_save", "request_id": "save", "config": config})
    assert saved["ok"] and saved["config"] == config
    sa = handler._build_trust_control_state(1, "SA_THREAT_RESPONSE", scenario, "u")
    assert radar["display_config"]["tendency"] == "normal"  # history never overrides config
    assert sa["display_config"]["tendency"] == "under_trust"
    assert saved["display_config"] == sa["display_config"]
    cached = handler.current_session['task_start_responses']['RADAR_TARGETING']['responses'][0]
    assert cached['trust_control']['display_config'] == saved['display_config']
    next_group = handler._build_trust_control_state(2, "RADAR_TARGETING", scenario, "u")
    assert next_group["display_config"]["tendency"] == "under_trust"
    assert not request({"type": "trust_config_save", "config": {}})["ok"]
    assert handler._build_trust_control_state(1, "RADAR_TARGETING", scenario, "u")["display_config"] == saved['display_config']


def test_save_emits_live_update_only_on_success(source):
    from core.message_handler import MessageHandler
    handler = MessageHandler()
    handler.trust_policy_resolver = TrustPolicyResolver(source)
    config = source.read_config()
    config['tendency'] = 'over_trust'
    responses = asyncio.run(handler.handle_client_message(json.dumps({
        'type': 'trust_config_save', 'config': config, 'request_id': 'live',
    }), {}))
    assert len(responses) == 2
    assert responses[1]['type'] == 'trust_display_updated'
    assert responses[1]['display_config'] == responses[0]['display_config']
    assert responses[1]['display_config']['tendency'] == 'over_trust'
    invalid = asyncio.run(handler.handle_client_message(json.dumps({
        'type': 'trust_config_save', 'config': {},
    }), {}))
    assert len(invalid) == 1 and not invalid[0]['ok']
