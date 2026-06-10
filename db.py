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


def fetch_mapping_matrix(cert_l1_cats: list[str]) -> pd.DataFrame:
    """Wide matrix for a set of cert categories:
      rows = all work_codes (sorted by work_code),
      columns = cert_codes whose cert_master.l1_category IN cert_l1_cats
               AND at least one employee currently holds the cert
               (sorted by holder_count DESC, then cert_code).

    Info columns (left, read-only): work_code, l1, l2, l3, task_type.
    Value columns: one per cert_code, cells = influence (1-5) or NA.
    """
    if not cert_l1_cats:
        raise ValueError("cert_l1_cats must contain at least one category")
    placeholders = ", ".join(["?"] * len(cert_l1_cats))
    params = tuple(cert_l1_cats)

    with connect() as conn:
        work_codes = pd.read_sql_query("""
            SELECT work_code, l1, l2, l3, task_type
            FROM work_code_master
            ORDER BY work_code
        """, conn)

        # INNER JOIN drops certs that no employee holds.
        certs = pd.read_sql_query(f"""
            SELECT
                c.cert_code,
                c.cert_name,
                h.holder_count
            FROM cert_master c
            INNER JOIN (
                SELECT cert_code, COUNT(*) AS holder_count
                FROM employee_cert
                GROUP BY cert_code
            ) h ON h.cert_code = c.cert_code
            WHERE c.l1_category IN ({placeholders})
            ORDER BY h.holder_count DESC, c.cert_code
        """, conn, params=params)

        mappings = pd.read_sql_query(f"""
            SELECT m.work_code, m.cert_code, m.influence
            FROM work_code_cert_map m
            JOIN cert_master c ON c.cert_code = m.cert_code
            WHERE c.l1_category IN ({placeholders})
        """, conn, params=params)

    cert_list = certs["cert_code"].tolist()
    cert_name_by_code = dict(zip(certs["cert_code"], certs["cert_name"]))

    if mappings.empty:
        pivoted = pd.DataFrame({"work_code": pd.Series(dtype=str)})
    else:
        pivoted = (
            mappings.pivot(index="work_code", columns="cert_code", values="influence")
            .reset_index()
        )

    for cert in cert_list:
        if cert not in pivoted.columns:
            pivoted[cert] = pd.NA

    matrix = work_codes.merge(pivoted, on="work_code", how="left")
    info_cols = ["work_code", "l1", "l2", "l3", "task_type"]
    matrix = matrix[info_cols + cert_list]

    # Nullable Int64 for every influence column.
    for cert in cert_list:
        matrix[cert] = pd.to_numeric(matrix[cert], errors="coerce").astype("Int64")

    # Sidecar dict for the UI to label columns with cert_name + holder_count.
    matrix.attrs["cert_meta"] = (
        certs.set_index("cert_code")[["cert_name", "holder_count"]].to_dict("index")
    )
    return matrix


def fetch_mapping_export() -> pd.DataFrame:
    """Wide matrix for CSV export (issue #30).

      rows    = all certs, sorted by holder_count DESC then cert_code
      columns = all work_codes; header = "work_code · l2 · l3 · task_type"
      cells   = influence (1-5) as nullable Int64, NA where no mapping

    Left info columns: cert_code, cert_name, holder_count. Read-only /
    export-oriented — this matrix is not edited in the app.
    """
    with connect() as conn:
        # All certs with holder counts (LEFT JOIN keeps 0-holder certs).
        certs = pd.read_sql_query("""
            SELECT c.cert_code, c.cert_name,
                   COUNT(ec.employee_id) AS holder_count
            FROM cert_master c
            LEFT JOIN employee_cert ec ON ec.cert_code = c.cert_code
            GROUP BY c.cert_code, c.cert_name
            ORDER BY holder_count DESC, c.cert_code
        """, conn)

        work_codes = pd.read_sql_query("""
            SELECT work_code, l2, l3, task_type
            FROM work_code_master
            ORDER BY work_code
        """, conn)

        mappings = pd.read_sql_query(
            "SELECT work_code, cert_code, influence FROM work_code_cert_map", conn
        )

    # One joined header per work_code: code · 중분류 · 소분류 · 산정/검증.
    def _header(row) -> str:
        parts = [row["work_code"], row["l2"], row["l3"], row["task_type"]]
        return " · ".join(str(p) for p in parts if p)

    work_codes = work_codes.copy()
    work_codes["header"] = work_codes.apply(_header, axis=1)
    col_order = work_codes["work_code"].tolist()
    header_by_code = dict(zip(work_codes["work_code"], work_codes["header"]))

    # Pivot to cert (rows) × work_code (cols); influence in the cells.
    if mappings.empty:
        pivot = pd.DataFrame(index=pd.Index([], name="cert_code"))
    else:
        pivot = mappings.pivot(
            index="cert_code", columns="work_code", values="influence"
        )
    for wc in col_order:
        if wc not in pivot.columns:
            pivot[wc] = pd.NA
    pivot = pivot[col_order]

    # Left-join keeps the cert (holder-count) ordering from `certs`.
    out = certs.merge(pivot, left_on="cert_code", right_index=True, how="left")
    for wc in col_order:
        out[wc] = pd.to_numeric(out[wc], errors="coerce").astype("Int64")

    return out.rename(columns=header_by_code)


_MATRIX_INFO_COLS = {
    "work_code": ("work_code", "l1", "l2", "l3", "task_type"),
    "cert_code": ("cert_code", "cert_name", "holder_count"),
}


def save_mapping_matrix_diff(
    original: pd.DataFrame,
    edited: pd.DataFrame,
    *,
    row_axis: str,
) -> dict:
    """Diff two wide matrices cell-by-cell; apply INSERT/UPDATE/DELETE to
    work_code_cert_map in one transaction.

    `row_axis` is the column used as the row identity:
      - "work_code": rows = work_codes, columns = cert_codes
      - "cert_code": rows = certs, columns = work_codes
    All other recognised info columns are skipped; the rest are value cells.

    Returns {'inserted': N, 'updated': N, 'deleted': N}.
    """
    if row_axis not in _MATRIX_INFO_COLS:
        raise ValueError(f"row_axis must be one of {list(_MATRIX_INFO_COLS)}")
    info_cols = set(_MATRIX_INFO_COLS[row_axis])
    value_cols = [c for c in original.columns if c not in info_cols]

    orig = original.set_index(row_axis)
    edit = edited.set_index(row_axis)

    inserts: list[tuple] = []   # (work_code, cert_code, influence)
    updates: list[tuple] = []   # (influence, work_code, cert_code)
    deletes: list[tuple] = []   # (work_code, cert_code)

    def wc_cc(row_key, col_key):
        # SQL always uses (work_code, cert_code) tuples.
        return (row_key, col_key) if row_axis == "work_code" else (col_key, row_key)

    for row_key in orig.index:
        for col_key in value_cols:
            o = orig.at[row_key, col_key]
            e = edit.at[row_key, col_key] if row_key in edit.index else o
            o_na, e_na = pd.isna(o), pd.isna(e)
            if o_na and e_na:
                continue
            if not e_na:
                ev = int(e)
                if not (1 <= ev <= 5):
                    raise ValueError(
                        f"influence must be 1..5; got {ev} at "
                        f"({row_axis}={row_key}, {col_key})"
                    )
            wc, cc = wc_cc(row_key, col_key)
            if o_na:
                inserts.append((wc, cc, ev))
            elif e_na:
                deletes.append((wc, cc))
            elif int(o) != ev:
                updates.append((ev, wc, cc))

    with connect() as conn:
        for params in deletes:
            conn.execute(
                "DELETE FROM work_code_cert_map WHERE work_code = ? AND cert_code = ?",
                params,
            )
        for params in updates:
            conn.execute(
                "UPDATE work_code_cert_map SET influence = ? "
                "WHERE work_code = ? AND cert_code = ?",
                params,
            )
        for params in inserts:
            conn.execute(
                "INSERT INTO work_code_cert_map (work_code, cert_code, influence) "
                "VALUES (?, ?, ?)",
                params,
            )

    return {"inserted": len(inserts), "updated": len(updates), "deleted": len(deletes)}


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
