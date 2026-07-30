import os
import sys


sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from network.netlog import log_ws_message, log_ws_send, should_log_ws_message


class CapturingLogger:
    def __init__(self):
        self.info_calls = []
        self.error_calls = []

    def info(self, *args):
        self.info_calls.append(args)

    def error(self, *args):
        self.error_calls.append(args)


def test_ue_ping_is_excluded_from_websocket_logs():
    logger = CapturingLogger()
    payload = {"type": "ue_ping"}

    assert should_log_ws_message(payload) is False
    log_ws_message(logger, "client-1", "/ws", '{"type":"ue_ping"}', payload)

    assert logger.info_calls == []


def test_non_ping_websocket_message_is_still_logged():
    logger = CapturingLogger()
    payload = {"type": "task_start", "user_id": "P001"}

    assert should_log_ws_message(payload) is True
    log_ws_message(logger, "client-1", "/ws", '{"type":"task_start"}', payload)

    assert len(logger.info_calls) == 1
    assert logger.info_calls[0][0] == "NET WS %s"


def test_platform_ack_send_log_contains_lifecycle_ids():
    logger = CapturingLogger()
    payload = {
        "type": "platform_task_ack",
        "status": "ok",
        "task_group_id": 61,
        "overall_task_id": 61,
        "task_id": 62,
        "task_type": "PLATFORM_CONTROL",
        "task_category": "platform_control",
        "sub_task_seq": 2,
        "completed_subtasks": 1,
        "expected_subtasks": 3,
        "task_status": "active",
    }

    log_ws_send(logger, "client-1", "/ws", payload, success=True)

    assert len(logger.info_calls) == 1
    rendered = logger.info_calls[0][1]
    assert "event=send" in rendered
    assert "type=platform_task_ack" in rendered
    assert "task_group_id=61" in rendered
    assert "task_id=62" in rendered
    assert "sub_task_seq=2" in rendered


def test_failed_platform_ack_send_is_logged_as_error():
    logger = CapturingLogger()

    log_ws_send(
        logger,
        "client-1",
        "/ws",
        {"type": "platform_task_ack", "status": "ok", "task_id": 62},
        success=False,
        error="connection closed",
    )

    assert len(logger.error_calls) == 1
    rendered = logger.error_calls[0][1]
    assert "event=send_failed" in rendered
    assert "type=platform_task_ack" in rendered
    assert "reason=connection closed" in rendered
