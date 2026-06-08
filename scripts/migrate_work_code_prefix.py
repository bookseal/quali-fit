#!/usr/bin/env python3
"""v0.0.11 migration — prefix work_code PKs with ``WORK-`` (issue #28).

Renames ``work_code`` in ``work_code_master`` and the ``work_code`` FK in
``work_code_cert_map`` so e.g. ``CA-111`` becomes ``WORK-CA-111`` — matching the
``cert_code`` convention (``CERT-…``).

Safe to run against an existing database (e.g. the live PVC ``app.db``):
  * **Idempotent** — rows already prefixed are skipped; re-running is a no-op.
  * **Backs up** the DB before touching it.
  * Renames parent + child in one transaction with ``foreign_keys=OFF`` (the FK
    has no ``ON UPDATE CASCADE``), then re-checks integrity.

Usage:
    DATA_DIR=/data python scripts/migrate_work_code_prefix.py
    # or point straight at a file:
    DB_PATH=/path/to/app.db python scripts/migrate_work_code_prefix.py
"""
import os
import shutil
import sqlite3
import sys

PREFIX = "WORK-"
DB_PATH = os.environ.get("DB_PATH") or os.path.join(
    os.environ.get("DATA_DIR", "."), "app.db"
)


def main() -> None:
    if not os.path.exists(DB_PATH):
        sys.exit(f"DB not found: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.isolation_level = None  # autocommit: we drive PRAGMA + BEGIN ourselves
    try:
        todo = conn.execute(
            "SELECT count(*) FROM work_code_master WHERE work_code NOT LIKE ?",
            (PREFIX + "%",),
        ).fetchone()[0]
        if todo == 0:
            print("already migrated — nothing to do")
            return

        # Back up only once there is real work to do, so a good backup is never
        # overwritten by an already-migrated copy.
        backup = DB_PATH + ".bak-work-prefix"
        shutil.copy2(DB_PATH, backup)
        print(f"backup written: {backup}")

        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("BEGIN")
        conn.execute(
            "UPDATE work_code_cert_map SET work_code = ? || work_code "
            "WHERE work_code NOT LIKE ?",
            (PREFIX, PREFIX + "%"),
        )
        conn.execute(
            "UPDATE work_code_master SET work_code = ? || work_code "
            "WHERE work_code NOT LIKE ?",
            (PREFIX, PREFIX + "%"),
        )
        conn.execute("COMMIT")
        conn.execute("PRAGMA foreign_keys=ON")

        bad = conn.execute("PRAGMA foreign_key_check").fetchall()
        if bad:
            sys.exit(f"FK integrity check FAILED: {bad}  (restore from {backup})")

        total = conn.execute("SELECT count(*) FROM work_code_master").fetchone()[0]
        mapped = conn.execute(
            "SELECT count(*) FROM work_code_cert_map"
        ).fetchone()[0]
        print(f"migrated {todo} work_codes; master={total}, mappings={mapped}; FK OK")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
