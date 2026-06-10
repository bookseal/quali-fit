#!/usr/bin/env python3
"""Generate a sample mapping XLSX for visual / print review (issue #34).

Builds the same workbook the app's "XLSX 다운로드" produces, from any SQLite DB,
so you can open it in Excel and check the A3 print layout before shipping.

Usage (from the repo root):
    .venv/bin/python scripts/make_sample_xlsx.py
    DB=app_prod.db OUT=~/Desktop/sample.xlsx .venv/bin/python scripts/make_sample_xlsx.py

Env vars:
    DB   path to the SQLite file (default: ./app.db)
    OUT  output .xlsx path        (default: ./work_code_cert_map_SAMPLE.xlsx)

Note: the output holds confidential mapping data — it is git-ignored (*.xlsx).
"""
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

db_path = os.path.expanduser(os.environ.get("DB", os.path.join(ROOT, "app.db")))
out_path = os.path.expanduser(
    os.environ.get("OUT", os.path.join(ROOT, "work_code_cert_map_SAMPLE.xlsx"))
)

if not os.path.exists(db_path):
    sys.exit(f"DB not found: {db_path}")

# db.py resolves its file as DATA_DIR/app.db, so stage the chosen DB under that
# name in a temp dir and point DATA_DIR at it before importing db.
tmp = tempfile.mkdtemp()
shutil.copy2(db_path, os.path.join(tmp, "app.db"))
os.environ["DATA_DIR"] = tmp

import db        # noqa: E402  (must follow DATA_DIR setup)
import export    # noqa: E402

certs, work_codes, influence = db.fetch_mapping_grid()
xlsx = export.build_mapping_workbook(certs, work_codes, influence)
with open(out_path, "wb") as f:
    f.write(xlsx)

shutil.rmtree(tmp, ignore_errors=True)

n_pages = -(-len(work_codes) // export.WORK_CODES_PER_SHEET)
print(
    f"wrote {out_path} ({len(xlsx)} bytes)\n"
    f"  certs={len(certs)}  work_codes={len(work_codes)}  mappings={len(influence)}\n"
    f"  sheets={n_pages} ({export.WORK_CODES_PER_SHEET} work codes/sheet)"
)
