import os
import sys
import sqlite3
from contextlib import contextmanager

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from managers import task_manager


class FakeDb:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE task_settings (task_id INTEGER)")
        self.conn.execute("CREATE TABLE user_operations (task_id INTEGER)")
        self.conn.execute("CREATE TABLE task_runs (task_id INTEGER)")
        self.conn.execute("INSERT INTO task_settings (task_id) VALUES (10)")
        self.conn.execute("INSERT INTO user_operations (task_id) VALUES (11)")
        self.conn.execute("INSERT INTO task_runs (task_id) VALUES (42)")
        self.conn.commit()

    @contextmanager
    def get_connection(self):
        yield self.conn


def test_generate_task_id_includes_task_runs(monkeypatch):
    fake_db = FakeDb()
    monkeypatch.setattr(task_manager, "db_manager", fake_db)

    assert task_manager.generate_task_id() == 43
