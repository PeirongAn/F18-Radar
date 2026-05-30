"""Step 1 compatibility entry for the current F18-Radar database.

The original SFY step1 merged WEB/UE/questionnaire files from an external
delivery bundle. In this repository the raw source is a single runtime SQLite
database, so this step delegates to export_all_data.py and writes the same
SFY-style all_data.db schema.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from export_all_data import export_database


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_SOURCE_DB = REPO_ROOT / "server" / "data" / "radar_operations.db"
DEFAULT_OUTPUT_DB = SCRIPT_DIR / "output" / "all_data.db"
DEFAULT_REPORT = SCRIPT_DIR / "output" / "quality_report.json"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build SFY-compatible all_data.db from server/data/radar_operations.db"
    )
    parser.add_argument("--source", default=str(DEFAULT_SOURCE_DB), help="source radar_operations.db")
    parser.add_argument("--output", "-o", default=str(DEFAULT_OUTPUT_DB), help="target all_data.db")
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="quality report JSON")
    parser.add_argument("--overwrite", action="store_true", help="overwrite target database")
    args = parser.parse_args()

    result = export_database(
        source=Path(args.source),
        output=Path(args.output),
        report=Path(args.report),
        overwrite=args.overwrite,
    )

    print(f"all_data.db: {args.output}")
    print(f"quality report: {args.report}")
    print(
        "questionnaires: "
        f"matched={result['questionnaires']['matched']} "
        f"unmatched={result['questionnaires']['unmatched']}"
    )
    for table, count in sorted(result["tables"].items()):
        print(f"{table}: {count}")


if __name__ == "__main__":
    main()
