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

def init_db() -> None:
    """Create all tables if they don't exist. Safe to re-run."""
    with connect() as conn:
        conn.executescript(SCHEMA)

def save_employee_diff(original_df: pd.DataFrame, diff: dict) -> None:
    """Apply st.data_editor diff (edited / added / deleted ) in one transaction."""
    with connect() as conn:
        # Deletions: row idx -> look up employee_id in the original snapshot
        for idx in diff.get("deleted_rows", []):
            emp_id = original_df.iloc[idx]["employee_id"]
            conn.execute("DELETE FROM employee WHERE employee_id = ?", (emp_id,))

        # Edits: {idx: {col: new_value, ...}}
        for idx, changes in diff.get("edited_rows", {}).items():
            emp_id = original_df.iloc[idx]["employee_id"]
            cols = list(changes.keys())
            values = list(changes.values())
            set_clause = ", ".join(f"{c} = ?" for c in cols)
            conn.execute(
                f"UPDATE employee SET {set_clause} WHERE employee_id = ?",
                (*values, emp_id),
            )

        # Additions: list of {col: value, ...}
        for row in diff.get("added_rows", []):
            conn.execute(
                "INSERT INTO employee (employee_id, name, dept, title) VALUES (?, ?, ?, ?)",
                (row.get("employee_id", ""), row.get("name", ""),
                row.get("dept", ""), row.get("title", "")),
            )

def fetch_all(table: str) -> pd.DataFrame:
    """Return entire table as a DataFrame. Read-only helper for the UI layer."""
    if table not in KNOWN_TABLES:
        raise ValueError(f"Unknown table: {table}")
    with connect() as conn:
        return pd.read_sql_query(f"SELECT * FROM {table}", conn)

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
