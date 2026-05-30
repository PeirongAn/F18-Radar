"""Compare the exported all_data.db schema with the SFY reference schema."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_REFERENCE = REPO_ROOT / "SFY外协数据分析" / "all_data.db"
DEFAULT_TARGET = SCRIPT_DIR / "output" / "all_data.db"
TABLES = [
    "questionnaire_statistics",
    "sensor_task_statistics_plus",
    "threat_task_statistics_plus",
    "platform_statistics",
    "weapon_statistics",
]


def table_columns(db_path: Path, table_name: str) -> list[str]:
    with sqlite3.connect(db_path) as conn:
        return [row[1] for row in conn.execute(f"PRAGMA table_info({table_name})")]


def main() -> int:
    parser = argparse.ArgumentParser(description="Check all_data.db fields against SFY reference")
    parser.add_argument("--reference", default=str(DEFAULT_REFERENCE), help="reference all_data.db")
    parser.add_argument("--target", default=str(DEFAULT_TARGET), help="exported all_data.db")
    args = parser.parse_args()

    reference = Path(args.reference)
    target = Path(args.target)
    has_problem = False

    for db_path in (reference, target):
        if not db_path.exists():
            print(f"missing database: {db_path}")
            return 2

    for table in TABLES:
        reference_cols = table_columns(reference, table)
        target_cols = table_columns(target, table)
        missing = [col for col in reference_cols if col not in target_cols]
        extra = [col for col in target_cols if col not in reference_cols]
        order_changed = reference_cols != target_cols

        if missing or extra or order_changed:
            has_problem = True
            print(f"[DIFF] {table}")
            if missing:
                print(f"  missing: {missing}")
            if extra:
                print(f"  extra: {extra}")
            if order_changed and not missing and not extra:
                print("  same fields, different order")
        else:
            print(f"[OK] {table}: {len(target_cols)} fields")

    return 1 if has_problem else 0


if __name__ == "__main__":
    raise SystemExit(main())
