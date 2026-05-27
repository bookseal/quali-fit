"""SQLite layer (pure — no Streamlit). Schema and seed live here."""

import os
import sqlite3
import pandas as pd
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent))
DB_PATH = DATA_DIR / "app.db"
CSV_DIR = Path(__file__).parent / "Data"

SEED_PLAN = [
    # (CSV file, table, {csv_col: db_col}) — order respects FK (parents first)
    ("01_직원.csv", "employee", {
        "직원번호": "employee_id", "이름": "name", "소속": "dept", "직책": "title",
    }),
    ("02_자격증_마스터.csv", "cert_master", {
        "코드": "cert_code", "자격증명": "cert_name",
        "대분류": "l1_category", "중분류": "l2_category",
        "원가산정검증활용": "costing_use", "자격증내용": "description",
        "수행가능업무": "performable_work", "영향력": "influence",
        "자격유형": "license_type", "증빙유형": "evidence_type",
        "자격등급구분": "license_grade", "키워드": "keywords",
        "관련부처": "ministry", "시행/발급기관": "issuer",
    }),
    ("03_업무코드_마스터.csv", "work_code_master", {
        "업무분류코드": "work_code", "대분류": "l1", "중분류": "l2", "소분류": "l3",
        "업무구분": "task_type", "분류기준": "classification_basis",
        "관리부서": "dept", "책임자": "owner",
        "적용된키워드": "applied_keywords", "분류근거및설명": "classification_note",
        "관련지침": "guidelines", "관련법령": "related_laws",
    }),
    ("04_직원_학력.csv", "education", {
        "직원번호": "employee_id", "학력정보번호": "education_id",
        "학력": "level", "학위": "degree", "학교명": "school",
        "학부(과)": "faculty", "전공": "major", "비고": "note",
    }),
    ("05_직원_자격증.csv", "employee_cert", {
        "직원번호": "employee_id", "자격증코드": "cert_code",
        "취득일": "acquired_at", "등록일": "registered_at", "유효기간": "expires_at",
    }),
    ("06_업무코드_자격증_매핑.csv", "work_code_cert_map", {
        # CSV's "Primary Key" (MAP-NNN) is ignored — our composite PK is (work_code, cert_code)
        "업무분류코드": "work_code", "자격증코드": "cert_code",
        "업무관련영향력": "influence",
    }),
]

def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.row_factory = sqlite3.Row
    return conn

SCHEMA = """
CREATE TABLE IF NOT EXISTS employee (
    employee_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    dept TEXT NOT NULL,
    title TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cert_master (
    cert_code TEXT PRIMARY KEY,
    cert_name TEXT NOT NULL,
    l1_category TEXT,
    l2_category TEXT,
    costing_use TEXT,
    description TEXT,
    performable_work TEXT,
    influence INTEGER CHECK (influence BETWEEN 1 AND 5),
    license_type TEXT,
    evidence_type TEXT,
    license_grade TEXT,
    keywords TEXT,
    ministry TEXT,
    issuer TEXT
);

CREATE TABLE IF NOT EXISTS work_code_master (
    work_code            TEXT PRIMARY KEY,
    l1                   TEXT NOT NULL,
    l2                   TEXT NOT NULL,
    l3                   TEXT,
    task_type            TEXT NOT NULL CHECK (task_type IN ('산정','검증')),
    classification_basis TEXT,
    dept                 TEXT,
    owner                TEXT,
    applied_keywords     TEXT,
    classification_note  TEXT,
    guidelines           TEXT,
    related_laws         TEXT
);

CREATE TABLE IF NOT EXISTS education (
    education_id TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL,
    level TEXT,
    degree TEXT,
    school TEXT,
    faculty TEXT,
    major TEXT,
    note TEXT,
    FOREIGN KEY (employee_id) REFERENCES employee(employee_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS employee_cert (
    employee_id TEXT NOT NULL,
    cert_code TEXT NOT NULL,
    acquired_at TEXT,
    registered_at TEXT,
    expires_at TEXT,
    PRIMARY KEY (employee_id, cert_code),
    FOREIGN KEY (employee_id) REFERENCES employee(employee_id) ON DELETE CASCADE,
    FOREIGN KEY (cert_code) REFERENCES cert_master(cert_code) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS work_code_cert_map (
    work_code TEXT NOT NULL,
    cert_code TEXT NOT NULL,
    influence INTEGER NOT NULL CHECK (influence BETWEEN 1 AND 5),
    PRIMARY KEY (work_code, cert_code),
    FOREIGN KEY (work_code) REFERENCES work_code_master(work_code) ON DELETE CASCADE,
    FOREIGN KEY (cert_code) REFERENCES cert_master(cert_code) ON DELETE RESTRICT
);
"""

KNOWN_TABLES = [t for _, t, _ in SEED_PLAN]

# When showing a table that has an FK to one of these parents,
# also display these parent columns alongside (read-only).
DERIVED_LABELS = {
    "employee":         ["name"],
    "cert_master":      ["cert_name"],
    "work_code_master": ["l1", "l2", "l3"],
}

# Tables whose PK should be auto-generated on INSERT if left blank.
# The PK column is hidden from `required_cols` so validation won't flag it.
AUTO_ID_RULES = {
    "education": {"col": "education_id", "prefix": "EDU-"},
}


def _next_id(conn: sqlite3.Connection, table: str, pk_col: str, prefix: str) -> str:
    """Return the next available '{prefix}NNN' value for `pk_col` in `table`."""
    rows = conn.execute(
        f"SELECT {pk_col} FROM {table} WHERE {pk_col} LIKE ?",
        (f"{prefix}%",),
    ).fetchall()
    nums = []
    for r in rows:
        tail = r[pk_col][len(prefix):]
        if tail.isdigit():
            nums.append(int(tail))
    return f"{prefix}{(max(nums, default=0) + 1):03d}"

def init_db() -> None:
    """Create all tables if they don't exist. Safe to re-run."""
    with connect() as conn:
        conn.executescript(SCHEMA)

def fk_options(table: str) -> dict[str, list]:
    """For each FK column on this table, return the valid parent-PK values.
    Returns {child_col: [parent_pk_value, ...]}; empty dict if no FKs.

    Used by the UI to render FK columns as dropdowns instead of free text."""
    if table not in KNOWN_TABLES:
        raise ValueError(f"Unknown table: {table}")
    with connect() as conn:
        fks = conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()
        options: dict[str, list] = {}
        for fk in fks:
            child_col = fk["from"]
            parent_table = fk["table"]
            parent_col = fk["to"]
            rows = conn.execute(
                f"SELECT {parent_col} FROM {parent_table} ORDER BY {parent_col}"
            ).fetchall()
            options[child_col] = [r[parent_col] for r in rows]
    return options


def table_meta(table: str) -> dict:
    """Return schema metadata used by validation.

    Includes:
    - pk_cols:       primary-key columns (in order), single or composite
    - required_cols: columns that must have a value when present in the diff
                     (NOT NULL columns + PK columns — SQLite reports PK as
                     notnull=0 for TEXT PKs, so we union them explicitly)
    """
    if table not in KNOWN_TABLES:
        raise ValueError(f"Unknown table: {table}")
    with connect() as conn:
        info = conn.execute(f"PRAGMA table_info({table})").fetchall()
    auto_id_cols: set[str] = set()
    if table in AUTO_ID_RULES:
        auto_id_cols.add(AUTO_ID_RULES[table]["col"])
    return {
        "pk_cols":       [r["name"] for r in info if r["pk"] > 0],
        "required_cols": [
            r["name"] for r in info
            if (r["notnull"] or r["pk"] > 0) and r["name"] not in auto_id_cols
        ],
        "all_cols":      [r["name"] for r in info],
        "auto_id_cols":  sorted(auto_id_cols),
    }

def save_diff(table: str, original_df: pd.DataFrame, diff: dict) -> None:
    """Apply data_editor diff (deleted / edited / added) to any
    known table in a single transaction. PK columns are discovered
    at runtime via PRAGMA table_info, so single and composite PKs are handled uniformly."""
    if table not in KNOWN_TABLES:
        raise ValueError(f"Unknown table: {table}")
    
    with connect() as conn:
        info = conn.execute(f"PRAGMA table_info({table})").fetchall()
        pk_cols = [r["name"] for r in info if r["pk"] > 0]
        all_cols = {r["name"] for r in info}
        if not pk_cols:
            raise RuntimeError(f"Table {table} has no primary key")
        where_clause = " AND ".join(f"{c} = ?" for c in pk_cols)

        # ---- DELETE ----
        for idx in diff.get("deleted_rows", []):
            pk_values = tuple(original_df.iloc[idx][c] for c in pk_cols)
            conn.execute(f"DELETE FROM {table} WHERE {where_clause}", pk_values)

        # ---- UPDATE ----
        for idx, changes in diff.get("edited_rows", {}).items():
            real_changes = {k: v for k, v in changes.items() if k in all_cols}
            if not real_changes:
                continue
            pk_values = tuple(original_df.iloc[idx][c] for c in pk_cols)
            cols = list(real_changes.keys())
            values = list(real_changes.values())
            set_clause = ", ".join(f"{c} = ?" for c in cols)
            conn.execute(
                f"UPDATE {table} SET {set_clause} WHERE {where_clause}",
                (*values, *pk_values),
            )

        # ---- INSERT ----
        rule = AUTO_ID_RULES.get(table)
        for row in diff.get("added_rows", []):
            real_row = {k: v for k, v in row.items() if k in all_cols}
            if rule and not real_row.get(rule["col"]):
                real_row[rule["col"]] = _next_id(conn, table, rule["col"], rule["prefix"])
            cols = list(real_row.keys())
            if not cols:
                continue
            col_list = ", ".join(cols)
            placeholders = ", ".join(["?"] * len(cols))
            conn.execute(
                f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})",
                tuple(real_row[c] for c in cols),
            )

def fetch_all(table: str) -> pd.DataFrame:
    """Return table as a DataFrame, with each FK column followed by its
    parent-derived label columns (LEFT JOIN). Derived columns are
    read-only and exist purely for display."""
    if table not in KNOWN_TABLES:
        raise ValueError(f"Unknown table: {table}")
    with connect() as conn:
        info = conn.execute(f"PRAGMA table_info({table})").fetchall()
        fks = conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()
        fk_by_col = {fk["from"]: fk for fk in fks}

        select_parts: list[str] = []
        for col_info in info:
            col = col_info["name"]
            select_parts.append(f"{table}.{col}")
            fk = fk_by_col.get(col)
            if fk:
                for label in DERIVED_LABELS.get(fk["table"], []):
                    select_parts.append(f"{fk['table']}.{label}")

        join_parts = [
            f"LEFT JOIN {fk['table']} ON {table}.{fk['from']} = {fk['table']}.{fk['to']}"
            for fk in fks
        ]

        sql = f"SELECT {', '.join(select_parts)} FROM {table} {' '.join(join_parts)}"
        return pd.read_sql_query(sql, conn)

def fetch_cert_profile(work_code: str) -> pd.DataFrame:
    """Certs required by a work_code, sorted by influence DESC.
    Used by the Recommend view to show the work code's shape before
    ranking employees."""
    sql = """
        SELECT
            wccm.cert_code,
            cm.cert_name,
            wccm.influence,
            cm.l1_category,
            cm.l2_category
        FROM work_code_cert_map wccm
        JOIN cert_master cm ON cm.cert_code = wccm.cert_code
        WHERE wccm.work_code = ?
        ORDER BY wccm.influence DESC, wccm.cert_code
    """
    with connect() as conn:
        return pd.read_sql_query(sql, conn, params=[work_code])


def fetch_scoring_data(work_code: str) -> pd.DataFrame:
    """Return long-form (employee × matching cert) rows for the given work_code.
    Employees with no matching cert do not appear."""
    sql = """
        SELECT
            e.employee_id, e.name, e.dept, e.title,
            ec.cert_code, cm.cert_name,
            wccm.influence,
            ec.expires_at
        FROM work_code_cert_map wccm
        JOIN cert_master    cm ON cm.cert_code  = wccm.cert_code
        JOIN employee_cert  ec ON ec.cert_code  = wccm.cert_code
        JOIN employee       e  ON e.employee_id = ec.employee_id
        WHERE wccm.work_code = ?
    """
    with connect() as conn:
        return pd.read_sql_query(sql, conn, params=[work_code])

def seed_from_csv() -> None:
    """Reload tables from CSV files in Data/. Idempotent (wipe + reload)."""
    with connect() as conn:
        # Wipe in reverse FK order (children first).
        for _csv, table, _cols in reversed(SEED_PLAN):
            conn.execute(f"DELETE FROM {table}")

        # Insert in forward FK order (parents first).
        for csv_file, table, col_map in SEED_PLAN:
            df = pd.read_csv(CSV_DIR / csv_file, encoding="utf-8-sig", dtype=str).fillna("")
            df = df.rename(columns=col_map)
            db_cols = list(col_map.values())
            df = df[db_cols]
            col_list = ", ".join(db_cols)
            placeholders = ", ".join(["?"] * len(db_cols))
            conn.executemany(
                f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})",
                df.itertuples(index=False, name=None),
            )
