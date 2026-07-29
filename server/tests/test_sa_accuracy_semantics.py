import asyncio
import importlib
import json
import os
import sys


SERVER_DIR = os.path.dirname(os.path.dirname(__file__))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from managers.threat_manager import ThreatManager
from models.threat_models import EnhancedThreat, RadarConfig, ThreatPosition


def _radar_config():
    return RadarConfig(
        center_x=450,
        center_y=450,
        radius1=120,
        radius2=240,
        radius3=360,
        canvas_width=900,
        canvas_height=900,
    )


def _threat(threat_id: str, threat_type: str, score: float):
    return EnhancedThreat(
        id=threat_id,
        type=threat_type,
        label=threat_id,
        position=ThreatPosition(x=300, y=300),
        priority="high" if threat_type.startswith("Primary") else "medium",
        score=score,
        distance_from_center=100,
        is_missile=False,
    )


def test_sa_emergency_always_carries_the_post_upgrade_threat_list():
    message = ThreatManager().generate_enhanced_sa_emergency(
        [
            _threat("threat-1", "SecondaryAir", 0.4),
            _threat("threat-2", "SecondaryNaval", 0.6),
        ],
        _radar_config(),
    )

    assert message["event"] == "upgrade"
    assert {item["id"] for item in message["updated_threats"]} == {"threat-1", "threat-2"}


def test_sa_accuracy_snapshot_uses_post_upgrade_scores(monkeypatch):
    manager = ThreatManager()
    updated_threats = [
        {"id": "threat-1", "type": "SecondaryAir", "score": 0.25},
        {"id": "threat-2", "type": "PrimaryNaval", "score": 0.95},
    ]
    monkeypatch.setattr(
        manager,
        "generate_enhanced_sa_emergency",
        lambda threats, radar_config: {
            "type": "SAEmergency",
            "event": "upgrade",
            "updated_threats": updated_threats,
        },
    )

    async def no_delay(_seconds):
        return None

    threat_manager_module = importlib.import_module("managers.threat_manager")
    monkeypatch.setattr(threat_manager_module.asyncio, "sleep", no_delay)

    class FakeWebSocket:
        def __init__(self):
            self.messages = []

        async def send(self, message):
            self.messages.append(json.loads(message))

    websocket = FakeWebSocket()
    session_state = {
        "current_task_id": 42,
        "is_practice": True,
    }
    asyncio.run(manager.auto_send_enhanced_sa_emergency(
        websocket,
        [],
        _radar_config(),
        "pilot",
        "AI",
        session_state,
    ))

    snapshot = session_state["trust_task_snapshots"]["42"]
    assert websocket.messages[0]["updated_threats"] == updated_threats
    assert snapshot["source"] == "updated_threats"
    assert snapshot["candidate_ids"] == ["threat-1", "threat-2"]
    assert snapshot["ground_truth"] == "threat-2"
