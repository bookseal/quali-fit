import os
import re
from html import escape
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import db
import export
import validation
import scoring
from datetime import date, datetime
from pathlib import Path


REPO_URL = "https://github.com/bookseal/quali-fit"


def _build_info() -> str:
    """One-line build stamp (markdown) for the sidebar footer.

    Lets anyone confirm at a glance which build is live (i.e. that a deploy
    actually shipped). Values are injected as env vars at image build time
    (see Dockerfile / deploy.sh); locally they fall back to the VERSION file.
    The version links to its git tag and the commit links to its GitHub page.
    """
    version = (os.environ.get("APP_VERSION") or "").strip()
    if not version:
        try:
            version = (Path(__file__).parent / "VERSION").read_text().strip()
        except OSError:
            version = "dev"
    sha = (os.environ.get("GIT_SHA") or "").strip()
    built = (os.environ.get("BUILD_TIME") or "").strip()

    # Version -> tag page (skip the link for local/dev where no tag exists).
    if version and version != "dev":
        parts = [f"[v{version}]({REPO_URL}/tree/v{version})"]
    else:
        parts = [f"v{version}"]

    # Commit -> GitHub commit page, but only when it's a real git SHA
    # (manual/local tags like "manual-…" or "local" stay plain text).
    if re.fullmatch(r"[0-9a-f]{7,40}", sha):
        parts.append(f"[`{sha[:12]}`]({REPO_URL}/commit/{sha})")
    else:
        parts.append(f"`{sha[:12] or 'local'}`")

    if built:
        parts.append(built)
    return " · ".join(parts)


_TITLE_ORDER = [
        "원장", "대표", "사장", "부사장", "부원장", "전무", "상무", "본부장",
        "실장", "부장", "팀장", "차장", "과장", "대리", "주임", "사원", "위원",
        "수석", "이사",
]


def _title_rank(title: str) -> int:
        for idx, token in enumerate(_TITLE_ORDER):
                if token in str(title):
                        return idx
        return len(_TITLE_ORDER)


def _render_employee_org_chart(df: pd.DataFrame) -> None:
        """Render a department-based org chart from the current employee table."""
        if df.empty or not {"name", "dept", "title"}.issubset(df.columns):
                st.info("조직도를 만들 직원 데이터가 아직 없습니다.")
                return

        chart_df = df[["employee_id", "name", "dept", "title"]].copy()
        chart_df["dept"] = chart_df["dept"].fillna("부서 미지정")
        chart_df["title"] = chart_df["title"].fillna("직책 미지정")
        chart_df = chart_df.sort_values(
                by=["dept", "title", "name"],
                key=lambda col: col.map(_title_rank) if col.name == "title" else col.astype(str),
                kind="stable",
        )

        dept_count = chart_df["dept"].nunique(dropna=False)
        employee_count = len(chart_df)
        dept_blocks = []

        for dept, group in chart_df.groupby("dept", sort=False):
                employees = []
                for _, row in group.iterrows():
                        employees.append(
                                f"""
                                <div class=\"org-employee\">
                                    <div class=\"org-employee-name\">{escape(str(row['name']))}</div>
                                    <div class=\"org-employee-meta\">
                                        <span>{escape(str(row['title']))}</span>
                                        <span>{escape(str(row['employee_id']))}</span>
                                    </div>
                                </div>
                                """
                        )

                dept_blocks.append(
                        f"""
                        <section class=\"org-dept\">
                            <div class=\"org-dept-header\">
                                <div class=\"org-dept-name\">{escape(str(dept))}</div>
                                <div class=\"org-dept-count\">{len(group)}명</div>
                            </div>
                            <div class=\"org-employee-list\">{''.join(employees)}</div>
                        </section>
                        """
                )

        html = f"""
        <style>
            .org-wrap {{
                font-family: 'Noto Sans KR', 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif;
                color: #1f2937;
                padding: 8px 4px 0;
            }}
            .org-summary {{
                background: linear-gradient(135deg, #f8fafc 0%, #eef6ff 100%);
                border: 1px solid #dbe7f3;
                border-radius: 22px;
                padding: 20px 22px;
                box-shadow: 0 10px 30px rgba(15, 23, 42, 0.06);
            }}
            .org-kicker {{
                display: inline-block;
                font-size: 12px;
                font-weight: 700;
                letter-spacing: 0.04em;
                color: #2563eb;
                background: rgba(37, 99, 235, 0.1);
                border-radius: 999px;
                padding: 5px 10px;
                margin-bottom: 10px;
            }}
            .org-title {{
                font-size: 28px;
                font-weight: 800;
                margin: 0;
                line-height: 1.2;
            }}
            .org-desc {{
                margin-top: 8px;
                color: #475569;
                font-size: 14px;
            }}
            .org-stats {{
                display: flex;
                gap: 10px;
                flex-wrap: wrap;
                margin-top: 14px;
            }}
            .org-stat {{
                background: rgba(255, 255, 255, 0.8);
                border: 1px solid #dbe7f3;
                color: #0f172a;
                border-radius: 999px;
                padding: 6px 12px;
                font-size: 13px;
                font-weight: 700;
            }}
            .org-rail {{
                position: relative;
                margin: 18px 0 8px;
                padding-left: 18px;
            }}
            .org-rail::before {{
                content: '';
                position: absolute;
                left: 6px;
                top: 0;
                bottom: 0;
                width: 2px;
                background: linear-gradient(to bottom, #93c5fd, #cbd5e1);
            }}
            .org-root {{
                position: relative;
                background: #0f172a;
                color: white;
                border-radius: 18px;
                padding: 14px 18px;
                margin-left: 18px;
                width: fit-content;
                box-shadow: 0 8px 24px rgba(15, 23, 42, 0.12);
            }}
            .org-root::before {{
                content: '';
                position: absolute;
                left: -18px;
                top: 50%;
                width: 18px;
                height: 2px;
                background: #93c5fd;
            }}
            .org-root-title {{
                font-size: 15px;
                font-weight: 800;
            }}
            .org-root-sub {{
                margin-top: 3px;
                font-size: 12px;
                color: rgba(255, 255, 255, 0.72);
            }}
            .org-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
                gap: 16px;
                margin-top: 18px;
            }}
            .org-dept {{
                position: relative;
                background: white;
                border: 1px solid #e5e7eb;
                border-radius: 20px;
                padding: 16px;
                box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
            }}
            .org-dept::before {{
                content: '';
                position: absolute;
                left: 18px;
                top: -18px;
                width: 2px;
                height: 18px;
                background: #93c5fd;
            }}
            .org-dept-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 12px;
                margin-bottom: 12px;
            }}
            .org-dept-name {{
                font-size: 18px;
                font-weight: 800;
                color: #0f172a;
            }}
            .org-dept-count {{
                font-size: 12px;
                font-weight: 700;
                color: #1d4ed8;
                background: #eff6ff;
                border-radius: 999px;
                padding: 4px 10px;
                white-space: nowrap;
            }}
            .org-employee-list {{
                display: flex;
                flex-direction: column;
                gap: 10px;
            }}
            .org-employee {{
                position: relative;
                background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
                border: 1px solid #e5e7eb;
                border-radius: 16px;
                padding: 12px 14px 12px 16px;
            }}
            .org-employee::before {{
                content: '';
                position: absolute;
                left: -16px;
                top: 50%;
                width: 16px;
                height: 2px;
                background: #cbd5e1;
            }}
            .org-employee-name {{
                font-size: 16px;
                font-weight: 800;
                color: #111827;
            }}
            .org-employee-meta {{
                display: flex;
                gap: 8px;
                flex-wrap: wrap;
                margin-top: 8px;
            }}
            .org-employee-meta span {{
                display: inline-flex;
                align-items: center;
                border-radius: 999px;
                padding: 4px 8px;
                font-size: 12px;
                font-weight: 700;
                color: #334155;
                background: #e2e8f0;
            }}
            .org-empty {{
                padding: 16px 0 8px;
                color: #475569;
                font-size: 14px;
            }}
        </style>
        <div class="org-wrap">
            <div class="org-summary">
                <div class="org-kicker">자동 갱신</div>
                <div class="org-title">직원 기본정보 조직도</div>
                <div class="org-desc">이 화면은 직원 기본정보 표를 기준으로 부서와 직책을 다시 읽어 그립니다. 저장하거나 DB를 직접 바꾸면 다음 렌더에서 반영됩니다.</div>
                <div class="org-stats">
                    <span class="org-stat">부서 {dept_count}개</span>
                    <span class="org-stat">직원 {employee_count}명</span>
                    <span class="org-stat">정렬 기준: 부서 → 직책 → 이름</span>
                </div>
            </div>
            <div class="org-rail">
                <div class="org-root">
                    <div class="org-root-title">회사 조직</div>
                    <div class="org-root-sub">직원 기본정보를 기반으로 생성</div>
                </div>
            </div>
            <div class="org-grid">{''.join(dept_blocks)}</div>
        </div>
        """
        components.html(html, height=min(1600, 320 + employee_count * 72), scrolling=True)

st.set_page_config(page_title="quali-fit", layout="wide")
db.init_db()

# ============================================================
# UI label translations (identifiers stay English, display 한글)
# ============================================================
MODE_LABELS = {
    "manage":    "데이터 관리",
    "recommend": "직원 추천",
}

TABLE_LABELS = {
    "employee":            "직원 기본정보",
    "education":           "학력",
    "employee_cert":       "자격증 보유",
    "cert_master":         "자격증 마스터",
    "work_code_master":    "업무분류 마스터",
    "work_code_cert_map":  "업무분류-자격증 매핑",
}

CATEGORIES = {
    "employee_group": ["employee", "education", "employee_cert"],
    "work_group":     ["work_code_master", "work_code_cert_map"],
    "cert_group":     ["cert_master"],
}
CATEGORY_LABELS = {
    "employee_group": "직원",
    "work_group":     "업무분류",
    "cert_group":     "한국 자격증 목록",
}

COLUMN_LABELS = {
    # employee
    "employee_id":         "직원번호",
    "name":                "이름",
    "dept":                "부서",
    "title":               "직책",
    # cert_master
    "cert_code":           "자격증코드",
    "cert_name":           "자격증명",
    "l1_category":         "대분류",
    "l2_category":         "중분류",
    "costing_use":         "원가산정활용",
    "description":         "자격증내용",
    "performable_work":    "수행가능업무",
    "influence":           "영향력",
    "license_type":        "자격유형",
    "evidence_type":       "증빙유형",
    "license_grade":       "자격등급",
    "keywords":            "키워드",
    "ministry":            "관련부처",
    "issuer":              "발급기관",
    # work_code_master
    "work_code":           "업무분류코드",
    "l1":                  "대분류",
    "l2":                  "중분류",
    "l3":                  "소분류",
    "task_type":           "업무구분",
    "classification_basis":"분류기준",
    "applied_keywords":    "적용키워드",
    "classification_note": "분류근거",
    "guidelines":          "관련지침",
    "related_laws":        "관련법령",
    "owner":               "책임자",
    # education
    "education_id":        "학력번호",
    "keco_major":          "고용직업분류 대분류",
    "keco_minor":          "고용직업분류 중분류",
    "level":               "학력수준",
    "degree":              "학위",
    "school":              "학교명",
    "faculty":             "학부",
    "major":               "전공",
    "note":                "비고",
    # employee_cert
    "acquired_at":         "취득일",
    "registered_at":       "등록일",
    "expires_at":          "유효기간",
    # scoring outputs
    "score":               "점수",
    "match_count":         "매칭수",
    "expired_count":       "만료수",
    "valid":               "유효",
    "contribution":        "기여도",
}


def _label(col: str) -> str:
    return COLUMN_LABELS.get(col, col)


# ============================================================
# 자격증 보유 — 만료 표시 (주의 패널 + 셀 배경색 + CSV)
# ============================================================
CERT_WARN_DAYS = 30  # 만료 임박 기준 (일)

_CERT_STATUS_LABELS = {"expired": "만료", "expiring": "만료 예정"}
_CERT_STATUS_COLORS = {"expired": "#ffcccc", "expiring": "#fff3b0"}


def _parse_cert_date(value: str) -> date | None:
    """employee_cert 날짜 문자열('YY.MM.DD' 등)을 date로 파싱. 실패 시 None."""
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    for fmt in ("%y.%m.%d", "%Y-%m-%d", "%Y.%m.%d", "%y-%m-%d", "%Y/%m/%d", "%y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _cert_expiry_status(expires_at: str, today: date,
                        warn_days: int = CERT_WARN_DAYS) -> str:
    """expires_at을 today 기준으로 'expired' / 'expiring' / '' 로 분류.

    - 'expired'  : 유효기간이 오늘 이전(오늘 포함) → 만료
    - 'expiring' : warn_days(기본 30일) 이내 만료 예정
    - ''         : 여유 있음 / 날짜 미상
    """
    d = _parse_cert_date(expires_at)
    if d is None:
        return ""
    if d <= today:
        return "expired"
    if (d - today).days <= warn_days:
        return "expiring"
    return ""


def render_cert_expiry_section(df: pd.DataFrame, today: date) -> None:
    """자격증 보유 화면 상단: 만료 주의 패널 + 색상 표시 표 + 상태 포함 CSV.

    편집은 아래쪽 data_editor에서 그대로 하고, 이 영역은 만료 모니터링용
    읽기 전용 뷰입니다(셀 배경색은 st.data_editor가 지원하지 않으므로 분리).
    """
    if df.empty or "expires_at" not in df.columns:
        return
    status = df["expires_at"].apply(lambda v: _cert_expiry_status(v, today))

    # ---- 1. 주의 패널 ----
    expiring = df[status == "expiring"]
    expired = df[status == "expired"]
    if expiring.empty and expired.empty:
        st.success("만료되었거나 만료 예정인 자격증이 없습니다.")
    else:
        lines = ["**⚠️ 주의**"]
        for _, r in expiring.iterrows():
            lines.append(f"- {r['name']}, {r['cert_name']} 자격증 만료 예정")
        for _, r in expired.iterrows():
            lines.append(f"- {r['name']}, {r['cert_name']} 만료")
        st.warning("\n".join(lines))

    # ---- 2. 색상 표시 표 (읽기 전용) ----
    view = df.copy()
    view["status"] = status.map(_CERT_STATUS_LABELS).fillna("")

    def _style_row(row):
        color = _CERT_STATUS_COLORS.get(status.loc[row.name], "")
        return [f"background-color: {color}" if color else ""] * len(row)

    styled = view.style.apply(_style_row, axis=1)
    st.caption(f"🔴 만료 · 🟡 {CERT_WARN_DAYS}일 이내 만료 예정")
    column_config = {c: _label(c) for c in df.columns}
    column_config["status"] = st.column_config.TextColumn("상태")
    st.dataframe(styled, hide_index=True, width="stretch",
                 column_config=column_config)

    # ---- 3. CSV 다운로드 (상태 컬럼 포함 → 만료 정보 보존) ----
    csv_headers = {c: _label(c) for c in view.columns}
    csv_headers["status"] = "상태"
    csv_df = view.rename(columns=csv_headers)
    st.download_button(
        "CSV 다운로드 (만료 상태 포함)",
        data=csv_df.to_csv(index=False).encode("utf-8-sig"),
        file_name="employee_cert_status.csv",
        mime="text/csv",
    )
    st.divider()
    st.caption("아래 표에서 편집 후 **저장**하세요.")


def _render_education_summary(df: pd.DataFrame) -> None:
    """Render education counts by level/degree and KECO major/minor."""
    required = {"employee_id", "level", "degree", "keco_major", "keco_minor"}
    if df.empty or not required.issubset(df.columns):
        st.info("학력 집계를 만들 데이터가 아직 없습니다.")
        return

    has_keco_values = df[["keco_major", "keco_minor"]].notna().any().any()
    work = df.copy()
    work["level"] = work["level"].fillna("학력 미지정")
    work["degree"] = work["degree"].fillna("학위 미지정")
    work["keco_major"] = work["keco_major"].fillna("고용직업분류 미지정")
    work["keco_minor"] = work["keco_minor"].fillna("중분류 미지정")

    total_people = work["employee_id"].nunique()
    level_degree_summary = (
        work.groupby(["level", "degree"], dropna=False)["employee_id"]
        .nunique()
        .reset_index(name="인원")
        .sort_values(["인원", "level", "degree"], ascending=[False, True, True], ignore_index=True)
    )

    keco_summary = (
        work.groupby(["keco_major", "keco_minor", "level", "degree"], dropna=False)["employee_id"]
        .nunique()
        .reset_index(name="인원")
        .sort_values(["keco_major", "keco_minor", "level", "degree"], ignore_index=True)
    )

    st.caption(f"전체 인원 {total_people}명 기준으로 학력수준 / 학위 및 고용직업분류를 집계했습니다.")
    summary_cols = st.columns(3)
    summary_cols[0].metric("전체 인원", f"{total_people}명")
    summary_cols[1].metric("학력 조합 수", f"{len(level_degree_summary)}개")
    summary_cols[2].metric("KECO 조합 수", f"{len(keco_summary)}개")

    st.markdown("#### 학력수준 / 학위별 인원")
    st.dataframe(level_degree_summary, hide_index=True, width="stretch")

    st.markdown("#### 고용직업분류 대분류 / 중분류별 학력 인원")
    if not has_keco_values:
        st.info("고용직업분류 대분류와 중분류 값이 아직 없어, 아래 표는 '미지정' 기준으로 집계됩니다.")
    st.dataframe(keco_summary, hide_index=True, width="stretch")


# ============================================================
# Top-level mode (sidebar — primary nav)
# ============================================================
MODES = list(MODE_LABELS.keys())

url_mode = st.query_params.get("mode", "manage")
default_mode = url_mode if url_mode in MODES else "manage"

with st.sidebar:
    st.markdown("### quali-fit")
    mode = st.radio(
        "메뉴",
        MODES,
        index=MODES.index(default_mode),
        format_func=lambda m: MODE_LABELS[m],
        label_visibility="collapsed",
    )
    st.divider()
    st.caption(_build_info())
if mode and mode != st.query_params.get("mode"):
    st.query_params["mode"] = mode

# ============================================================
# 데이터 관리
# ============================================================
if mode == "manage":
    # ---- Category (tier 2 — section-level) ----
    url_cat = st.query_params.get("cat", "employee_group")
    if url_cat not in CATEGORIES:
        url_cat = "employee_group"

    st.subheader("카테고리")
    cat = st.segmented_control(
        "Category",
        list(CATEGORIES.keys()),
        default=url_cat,
        format_func=lambda c: CATEGORY_LABELS[c],
        label_visibility="collapsed",
    )
    if cat and cat != st.query_params.get("cat"):
        st.query_params["cat"] = cat

    # ---- Service (tier 3 — sub-selection) ----
    services = CATEGORIES[cat] if cat else CATEGORIES[url_cat]
    url_svc = st.query_params.get("svc", services[0])
    if url_svc not in services:
        url_svc = services[0]

    st.caption("서비스")
    choice = st.pills(
        "Service",
        services,
        default=url_svc,
        format_func=lambda t: TABLE_LABELS.get(t, t),
        label_visibility="collapsed",
    )
    if choice and choice != st.query_params.get("svc"):
        st.query_params["svc"] = choice

    if choice == "work_code_cert_map":
        st.subheader(TABLE_LABELS[choice])
        # ---- XLSX export: A3-landscape workbook, one sheet per 중분류 ----
        st.caption(
            "자격증(행, 보유자 많은 순) × 업무분류(열) 매핑 — **A3 가로 인쇄용 XLSX** 내보내기. "
            "**중분류별 시트**로 분할되고, 각 업무열 헤더는 4행(코드/중분류/소분류/산정·검증)입니다. "
            "셀 값은 영향력(1~5), 빈 칸은 매핑 없음. 이 화면은 편집용이 아닙니다."
        )

        certs, work_codes, influence = db.fetch_mapping_grid()
        xlsx_bytes = export.build_mapping_workbook(certs, work_codes, influence)

        st.download_button(
            "XLSX 다운로드",
            data=xlsx_bytes,
            file_name="work_code_cert_map.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )

        # On-screen preview: flat single-table view (the file itself is split by 중분류).
        preview = db.fetch_mapping_export()
        st.caption(
            f"미리보기 — 자격증 {len(preview)}행 × 업무분류 {len(preview.columns) - 3}열 "
            "(실제 파일은 중분류별 시트로 분할됩니다)"
        )
        st.dataframe(preview, hide_index=True, width="stretch")

    elif choice:
        st.subheader(TABLE_LABELS.get(choice, choice))
        # ---- Generic CRUD (all other tables) ----
        df = db.fetch_all(choice)

        # 자격증 보유: 만료 주의 패널 + 색상 표시 + 상태 포함 CSV (편집은 아래 표).
        if choice == "employee_cert":
            render_cert_expiry_section(df, date.today())

        if choice == "education":
            st.divider()
            st.subheader("학력 집계")
            st.caption("학력수준, 학위, 고용직업분류 대분류/중분류 기준으로 인원 수를 요약합니다.")
            _render_education_summary(df)

        editor_key = f"{choice}_editor"
        meta = db.table_meta(choice)
        fk_opts = db.fk_options(choice)

        column_config = {
            col: st.column_config.SelectboxColumn(_label(col), options=opts, required=True)
            for col, opts in fk_opts.items()
        }
        real_cols = set(meta["all_cols"])
        for c in df.columns:
            if c not in real_cols:
                column_config[c] = st.column_config.TextColumn(_label(c), disabled=True)
        for c in meta["auto_id_cols"]:
            column_config[c] = st.column_config.TextColumn(
                _label(c), disabled=True, help="저장 시 자동 생성"
            )
        for c in df.columns:
            if c not in column_config and c in real_cols:
                column_config[c] = st.column_config.Column(_label(c))

        st.data_editor(
            df,
            num_rows="dynamic",
            width="stretch",
            hide_index=True,
            key=editor_key,
            column_config=column_config,
        )

        if st.button("저장"):
            diff = st.session_state[editor_key]
            errors, warnings = validation.validate_diff(meta, df, diff)
            for msg in warnings:
                st.warning(msg)
            if errors:
                for msg in errors:
                    st.error(msg)
            else:
                try:
                    db.save_diff(choice, df, diff)
                    st.toast("저장됨.", icon="✅")
                    del st.session_state[editor_key]
                    st.rerun()
                except Exception as e:
                    st.error(f"저장 오류: {e}", icon="❌")

        if choice == "employee":
            st.divider()
            st.subheader("조직도")
            st.caption("직원 기본정보의 이름, 부서, 직책을 기준으로 자동 생성됩니다.")
            _render_employee_org_chart(df)

# ============================================================
# 직원 추천
# ============================================================
elif mode == "recommend":
    wc_df = db.fetch_all("work_code_master")[["work_code", "l1", "l2", "l3"]]
    wc_label = {
        r["work_code"]: f"{r['work_code']} — {r['l1']} / {r['l2']} / {r['l3']}"
        for _, r in wc_df.iterrows()
    }
    codes = wc_df["work_code"].tolist()

    url_wc = st.query_params.get("wc", codes[0])
    if url_wc not in wc_label:
        url_wc = codes[0]

    work_code = st.selectbox(
        "업무분류",
        codes,
        index=codes.index(url_wc),
        format_func=lambda c: wc_label[c],
    )
    if work_code and work_code != st.query_params.get("wc"):
        st.query_params["wc"] = work_code

    # ---- 요구 자격증 ----
    profile = db.fetch_cert_profile(work_code)
    if profile.empty:
        st.info(f"{work_code}에 매핑된 자격증이 없습니다.")
    else:
        st.subheader("요구 자격증")
        st.dataframe(
            profile,
            width="stretch",
            hide_index=True,
            column_config={
                "cert_code":   st.column_config.Column(_label("cert_code")),
                "cert_name":   st.column_config.Column(_label("cert_name")),
                "l1_category": st.column_config.Column(_label("l1_category")),
                "l2_category": st.column_config.Column(_label("l2_category")),
                "influence":   st.column_config.ProgressColumn(
                    _label("influence"), min_value=0, max_value=5, format="%d",
                ),
            },
        )

    # ---- 직원 랭킹 ----
    joined = db.fetch_scoring_data(work_code)
    if joined.empty:
        st.info(f"{work_code}에 적합한 직원이 없습니다.")
    else:
        ranking, rationale = scoring.rank(joined, date.today())
        st.subheader("직원 랭킹")
        st.dataframe(
            ranking,
            width="stretch",
            hide_index=True,
            column_config={
                "employee_id":   st.column_config.Column(_label("employee_id")),
                "name":          st.column_config.Column(_label("name")),
                "dept":          st.column_config.Column(_label("dept")),
                "title":         st.column_config.Column(_label("title")),
                "score":         st.column_config.ProgressColumn(
                    _label("score"), min_value=0, max_value=7, format="%.1f",
                ),
                "match_count":   st.column_config.NumberColumn(_label("match_count")),
                "expired_count": st.column_config.NumberColumn(_label("expired_count")),
            },
        )

        # ---- 상위 3명 근거 ----
        st.subheader("상위 3명 근거")
        for rank_idx, (_, row) in enumerate(ranking.head(3).iterrows(), start=1):
            emp_id = row["employee_id"]
            person = rationale[rationale["employee_id"] == emp_id]
            st.markdown(
                f"**{rank_idx}위. {row['name']} "
                f"({row['dept']} / {row['title']}) — 점수 {row['score']:.1f}**"
            )
            best = person["contribution"].max() if not person.empty else 0

            def style_row(r, best=best):
                if not r["valid"]:
                    return ["background-color: #ffe5e5"] * len(r)
                if r["contribution"] == best:
                    return ["font-weight: 700"] * len(r)
                return [""] * len(r)

            display_cols = ["cert_code", "cert_name", "influence",
                            "expires_at", "valid", "contribution"]
            styled = person[display_cols].style.apply(style_row, axis=1)
            st.dataframe(
                styled,
                hide_index=True,
                width="stretch",
                column_config={c: _label(c) for c in display_cols},
            )

        # ---- 설명 ----
        with st.expander("점수 산정 방식"):
            st.markdown(
                "**기여도 (자격증 1개당)**\n"
                "- `영향력 (1-5) × 유효성 (1 or 0)`\n"
                "- 만료된 자격증 → 기여도 0\n"
                "\n"
                "**총점**\n"
                "- 최고 기여도 + 다양성 보너스 (캡 2.0)\n"
                "- 다양성 보너스 = `min(추가 유효 자격증 수 × 0.5, 2.0)`\n"
                "\n"
                "**예시**: 유효 자격증 3개 영향력 [5, 3, 2] →\n"
                "- 최고 = 5\n"
                "- 보너스 = `min(2 × 0.5, 2)` = 1\n"
                "- **총점 = 6.0**\n"
                "\n"
                "**의도**\n"
                "- 핵심 자격증을 가진 사람이 우선 (최고 기여도)\n"
                "- 다재다능함도 가치 인정 (다양성 보너스)\n"
                "- 자격증 수집만으로 1위 못 감 (캡)\n"
                "- 만료 자격증은 카운트 안 됨 (데이터 신뢰)\n"
            )
