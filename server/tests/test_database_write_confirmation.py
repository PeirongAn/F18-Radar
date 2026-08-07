import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from managers.database_manager import DatabaseManager


def test_record_operation_can_wait_for_committed_write(tmp_path):
    manager = DatabaseManager(str(tmp_path / "confirmed-write.db"))
    try:
        manager.initialize_database()
        manager.record_operation({
            "task_id": 7001,
            "operationType": "target_selected",
            "timestamp": 123456,
            "receive_timestamp": 123400,
            "isActive": True,
            "parameters": {
                "target_id": "enemy-1",
                "is_correct": True,
            },
            "user_id": "pure-ai-user",
            "event_owner": "AI",
        }, False, wait_for_commit=True)

        with manager.get_connection() as conn:
            row = conn.execute(
                "SELECT operation_type, event_owner FROM user_operations WHERE task_id = ?",
                (7001,),
            ).fetchone()
        assert row == ("target_selected", "AI")
    finally:
        manager.shutdown()
