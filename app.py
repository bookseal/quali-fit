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


# 직급 서열 (위 = 상위, 아래 = 하위). substring 매칭이라 더 구체적인
# 토큰(예: 주임연구원)을 더 일반적인 토큰(주임/연구원)보다 먼저 둬야 한다.
_TITLE_ORDER = [
        "원장", "대표", "사장", "부사장", "부원장", "전무", "상무", "이사",
        "본부장", "실장", "부장",
        "수석", "책임연구원", "선임연구원", "전임연구원", "주임연구원", "연구원",
        "팀장", "차장", "과장", "대리", "주임", "위원", "사원",
]


def _title_rank(title: str) -> int:
        # 부분 문자열 매칭이라 '부원장'이 '원장'에, '주임연구원'이 '주임'에
        # 잘못 걸린다. 후보 중 가장 구체적인(긴) 토큰을 골라 서열을 매긴다.
        text = str(title)
        best_idx, best_len = len(_TITLE_ORDER), -1
        for idx, token in enumerate(_TITLE_ORDER):
                if token in text and len(token) > best_len:
                        best_idx, best_len = idx, len(token)
        return best_idx


# 3대 본부(원가/건설/학술) 위주 재편. '회사 소개서' 실제 조직도 확정 시
# 이 매핑만 수정하면 화면 전체가 따라간다. (#36)
_HQ_ORDER = ["원장실", "원가본부", "건설본부", "학술본부", "경영지원", "기타"]
_DEPT_TO_HQ = {
        "원장":        "원장실",
        "원가분석":    "원가본부",
        "건설사업":    "건설본부",
        "품질관리":    "건설본부",
        "학술사업":    "학술본부",
        "학술연구":    "학술본부",
        "갈등조정중재": "학술본부",
        "경영기획":    "경영지원",
        "전략기획":    "경영지원",
}


def _hq_for(dept: str) -> str:
        return _DEPT_TO_HQ.get(str(dept).strip(), "기타")


def _hq_rank(hq: str) -> int:
        try:
                return _HQ_ORDER.index(hq)
        except ValueError:
                return len(_HQ_ORDER)


def _render_employee_org_chart(df: pd.DataFrame) -> None:
        """Render a 본부 → 부서 → 인원 org chart from the current employee table.

        - 직급순 하향식: 상위 직급이 위, 하위 직급이 아래 (_TITLE_ORDER).
        - 3대 본부(원가/건설/학술) 위주 그룹핑 (_DEPT_TO_HQ).
        - 세트 연계: 직원 → 보유 자격증 → 연관 업무기준 (db.fetch_employee_set_summary).
        - 본부 단위 아코디언(<details>) + 반응형/모바일 미디어쿼리.
        """
        if df.empty or not {"name", "dept", "title"}.issubset(df.columns):
                st.info("조직도를 만들 직원 데이터가 아직 없습니다.")
                return

        chart_df = df[["employee_id", "name", "dept", "title"]].copy()
        chart_df["dept"] = chart_df["dept"].replace({"-": None}).fillna("부서 미지정")
        chart_df["title"] = chart_df["title"].replace({"-": None}).fillna("직책 미지정")
        chart_df["hq"] = chart_df["dept"].map(_hq_for)
        chart_df["rank"] = chart_df["title"].map(_title_rank)

        # 세트 연계 요약 (직원 → 자격증 → 업무기준). 조회 실패해도 조직도는 그린다.
        try:
                set_df = db.fetch_employee_set_summary().set_index("employee_id")
                set_map = set_df.to_dict("index")
        except Exception:
                set_map = {}

        # 본부 → (가장 높은 직급 우선) 정렬, 본부 내 부서 → 직급 → 이름.
        chart_df = chart_df.sort_values(
                by=["hq", "dept", "rank", "name"],
                key=lambda col: col.map(_hq_rank) if col.name == "hq" else (
                        col if col.name == "rank" else col.astype(str)
                ),
                kind="stable",
        )

        dept_count = chart_df["dept"].nunique(dropna=False)
        hq_count = chart_df["hq"].nunique(dropna=False)
        employee_count = len(chart_df)
        certified = sum(1 for v in set_map.values() if (v.get("cert_count") or 0) > 0)

        def _employee_card(row) -> str:
                info = set_map.get(row["employee_id"], {})
                cert_n = int(info.get("cert_count") or 0)
                work_n = int(info.get("work_count") or 0)
                names = info.get("cert_names")
                names = names if isinstance(names, str) else ""
                set_chips = []
                if cert_n:
                        set_chips.append(f'<span class="org-chip chip-cert">자격증 {cert_n}</span>')
                if work_n:
                        set_chips.append(f'<span class="org-chip chip-work">업무기준 {work_n}</span>')
                if not set_chips:
                        set_chips.append('<span class="org-chip chip-none">연계 자격증 없음</span>')
                certline = (
                        f'<div class="org-employee-certs" title="{escape(names)}">{escape(names)}</div>'
                        if names else ""
                )
                return f"""
                                <div class=\"org-employee\">
                                    <div class=\"org-employee-name\">{escape(str(row['name']))}</div>
                                    <div class=\"org-employee-meta\">
                                        <span>{escape(str(row['title']))}</span>
                                        <span>{escape(str(row['employee_id']))}</span>
                                    </div>
                                    <div class=\"org-employee-set\">{''.join(set_chips)}</div>
                                    {certline}
                                </div>
                                """

        hq_blocks = []
        for hq, hq_group in chart_df.groupby("hq", sort=False):
                dept_blocks = []
                for dept, group in hq_group.groupby("dept", sort=False):
                        employees = [_employee_card(row) for _, row in group.iterrows()]
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
                hq_blocks.append(
                        f"""
                <details class=\"org-hq\" open>
                    <summary class=\"org-hq-summary\">
                        <span class=\"org-hq-name\">{escape(str(hq))}</span>
                        <span class=\"org-hq-count\">{len(hq_group)}명 · 부서 {hq_group['dept'].nunique()}개</span>
                        <span class=\"org-hq-caret\">▾</span>
                    </summary>
                    <div class=\"org-grid\">{''.join(dept_blocks)}</div>
                </details>
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
            /* ---- 본부 아코디언 ---- */
            .org-hq-list {{
                display: flex;
                flex-direction: column;
                gap: 16px;
                margin-top: 18px;
            }}
            .org-hq {{
                border: 1px solid #dbe7f3;
                border-radius: 20px;
                background: linear-gradient(135deg, #ffffff 0%, #f6faff 100%);
                box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
                overflow: hidden;
            }}
            .org-hq-summary {{
                list-style: none;
                cursor: pointer;
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 16px 20px;
                font-weight: 800;
                color: #0f172a;
                background: linear-gradient(135deg, #eef6ff 0%, #e0ecfb 100%);
                transition: background 0.25s ease;
                user-select: none;
            }}
            .org-hq-summary::-webkit-details-marker {{ display: none; }}
            .org-hq-summary:hover {{ background: #e0ecfb; }}
            .org-hq-name {{ font-size: 20px; }}
            .org-hq-count {{
                font-size: 12px;
                font-weight: 700;
                color: #1d4ed8;
                background: rgba(255, 255, 255, 0.85);
                border: 1px solid #cfe0f5;
                border-radius: 999px;
                padding: 4px 10px;
                white-space: nowrap;
            }}
            .org-hq-caret {{
                margin-left: auto;
                font-size: 16px;
                color: #2563eb;
                transition: transform 0.3s ease;
            }}
            .org-hq[open] .org-hq-caret {{ transform: rotate(180deg); }}
            .org-hq[open] .org-grid {{ animation: orgFade 0.35s ease; }}
            @keyframes orgFade {{
                from {{ opacity: 0; transform: translateY(-6px); }}
                to   {{ opacity: 1; transform: translateY(0); }}
            }}
            .org-hq .org-grid {{ padding: 16px 20px 20px; margin-top: 0; }}
            .org-dept {{ transition: transform 0.2s ease, box-shadow 0.2s ease; }}
            .org-dept:hover {{
                transform: translateY(-3px);
                box-shadow: 0 14px 30px rgba(15, 23, 42, 0.10);
            }}
            .org-employee {{ transition: transform 0.18s ease, border-color 0.18s ease; }}
            .org-employee:hover {{ transform: translateX(3px); border-color: #93c5fd; }}
            /* ---- 세트 연계 칩 (자격증 → 업무기준) ---- */
            .org-employee-set {{
                display: flex;
                gap: 6px;
                flex-wrap: wrap;
                margin-top: 8px;
            }}
            .org-chip {{
                font-size: 11px;
                font-weight: 800;
                border-radius: 999px;
                padding: 3px 9px;
            }}
            .chip-cert {{ color: #065f46; background: #d1fae5; }}
            .chip-work {{ color: #92400e; background: #fef3c7; }}
            .chip-none {{ color: #64748b; background: #eef2f7; }}
            .org-employee-certs {{
                margin-top: 6px;
                font-size: 11px;
                color: #64748b;
                line-height: 1.4;
                overflow: hidden;
                text-overflow: ellipsis;
                display: -webkit-box;
                -webkit-line-clamp: 2;
                -webkit-box-orient: vertical;
            }}
            /* ---- 반응형 / 모바일 ---- */
            @media (max-width: 640px) {{
                .org-title {{ font-size: 22px; }}
                .org-summary {{ padding: 16px; border-radius: 16px; }}
                .org-grid {{ grid-template-columns: 1fr; gap: 12px; }}
                .org-hq .org-grid {{ padding: 12px; }}
                .org-hq-summary {{ padding: 14px 16px; gap: 8px; flex-wrap: wrap; }}
                .org-hq-name {{ font-size: 17px; }}
                .org-root {{ width: auto; }}
            }}
            @media (prefers-reduced-motion: reduce) {{
                .org-hq[open] .org-grid,
                .org-dept, .org-employee, .org-hq-caret, .org-hq-summary {{
                    animation: none;
                    transition: none;
                }}
            }}
        </style>
        <div class="org-wrap">
            <div class="org-summary">
                <div class="org-kicker">자동 갱신</div>
                <div class="org-title">전문가 조직도</div>
                <div class="org-desc">3대 본부(원가·건설·학술) 기준으로 묶고, 직급순(상위→하위)으로 내려옵니다. 각 인원은 보유 자격증 → 연관 업무기준으로 연계됩니다. 본부 제목을 눌러 펼치고 접을 수 있습니다.</div>
                <div class="org-stats">
                    <span class="org-stat">본부 {hq_count}개</span>
                    <span class="org-stat">부서 {dept_count}개</span>
                    <span class="org-stat">직원 {employee_count}명</span>
                    <span class="org-stat">자격 연계 {certified}명</span>
                    <span class="org-stat">정렬: 본부 → 직급(↓) → 이름</span>
                </div>
            </div>
            <div class="org-rail">
                <div class="org-root">
                    <div class="org-root-title">연구소 (원장 직속)</div>
                    <div class="org-root-sub">전문가 인력 → 자격증 → 실적 → 업무기준 세트 연계</div>
                </div>
            </div>
            <div class="org-hq-list">{''.join(hq_blocks)}</div>
        </div>
        """
        components.html(html, height=min(2400, 360 + employee_count * 96), scrolling=True)

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


# 큰 전공 범주 — 위에서부터 우선순위로 키워드 매칭. KECO 코드 대신
# degree/faculty/major 텍스트를 직관적 학부 단위로 묶는다. (#37)
# 매핑 표는 '회사 소개서' 기준으로 추후 조정 가능.
_MAJOR_CATEGORIES = [
    ("법/행정",   ["법학", "법무", "소송", "행정", "법행정", "공공인재", "정경", "법정"]),
    ("신학",      ["신학", "기독교"]),
    ("농학(농대)", ["농학", "원예", "식물", "육종"]),
    ("경영(상대)", ["경영", "경제", "세무", "회계", "컨설팅", "매니지먼트", "무역", "마케팅", "금융", "경상"]),
    ("공학(공대)", ["공학", "공과", "전자", "기계", "건축", "화학", "조선", "토목", "산업",
                  "금속", "시스템", "정보통신", "컴퓨터", "설계", "건설", "제어", "전기"]),
]
_MAJOR_FALLBACK = "기타"
# 화면 노출 순서: 큰 학부 → 고졸 → 기타
_MAJOR_DISPLAY_ORDER = [
    "공학(공대)", "경영(상대)", "농학(농대)", "법/행정", "신학", "고졸", _MAJOR_FALLBACK,
]
_MAJOR_COLORS = {
    "공학(공대)": "#2563eb", "경영(상대)": "#0d9488", "농학(농대)": "#65a30d",
    "법/행정": "#9333ea", "신학": "#db2777", "고졸": "#64748b", _MAJOR_FALLBACK: "#94a3b8",
}


def _major_category(degree, faculty, major, level) -> str:
    text = " ".join(
        str(x) for x in (degree, faculty, major)
        if x is not None and str(x) not in ("", "nan")
    )
    if "고졸" in str(level) or "고졸" in text:
        return "고졸"
    for label, kws in _MAJOR_CATEGORIES:
        if any(k in text for k in kws):
            return label
    return _MAJOR_FALLBACK


def _render_education_summary(df: pd.DataFrame) -> None:
    """Render headcount by big, intuitive major categories (#37).

    KECO 코드 대신 degree/faculty/major를 큰 학부 범주로 묶어 인원을 집계하고,
    반응형 미디어쿼리 + 인터랙션(막대 애니메이션/hover) CSS로 표시한다.
    """
    required = {"employee_id", "level", "degree"}
    if df.empty or not required.issubset(df.columns):
        st.info("학력 집계를 만들 데이터가 아직 없습니다.")
        return

    work = df.copy()
    for col in ("level", "degree", "faculty", "major"):
        if col not in work.columns:
            work[col] = ""
    work["level"] = work["level"].fillna("").replace({"-": ""})
    work["category"] = work.apply(
        lambda r: _major_category(r["degree"], r["faculty"], r["major"], r["level"]),
        axis=1,
    )

    total_people = work["employee_id"].nunique()
    # 범주별 인원(중복 학력은 distinct 직원으로 카운트 — 복수전공/대학원은 여러 범주에 등장 가능)
    cat_people = work.groupby("category")["employee_id"].nunique()
    # 범주 × 학위 분포 (학사/석사/박사/전문학사/고졸)
    level_norm = work["level"].replace({"": "기타"})
    cat_level = work.groupby(["category", level_norm.rename("lv")])["employee_id"].nunique()

    max_count = int(cat_people.max()) if len(cat_people) else 0
    cards = []
    for cat in _MAJOR_DISPLAY_ORDER:
        n = int(cat_people.get(cat, 0))
        if n == 0:
            continue
        color = _MAJOR_COLORS.get(cat, "#94a3b8")
        pct = (n / max_count * 100) if max_count else 0
        share = (n / total_people * 100) if total_people else 0
        lv_chips = []
        for lv, cnt in cat_level.get(cat, pd.Series(dtype=int)).sort_values(ascending=False).items():
            lv_chips.append(f'<span class="edu-lv">{escape(str(lv))} {int(cnt)}</span>')
        cards.append(f"""
            <div class="edu-row" style="--bar:{pct:.1f}%; --c:{color};">
                <div class="edu-head">
                    <span class="edu-name">{escape(cat)}</span>
                    <span class="edu-count">{n}명 <em>· {share:.0f}%</em></span>
                </div>
                <div class="edu-track"><div class="edu-bar"></div></div>
                <div class="edu-lvs">{''.join(lv_chips)}</div>
            </div>
        """)

    used_cats = int((cat_people > 0).sum())
    html = f"""
    <style>
        .edu-wrap {{
            font-family: 'Noto Sans KR', 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif;
            color: #1f2937; padding: 6px 2px 2px;
        }}
        .edu-grid {{ display: flex; flex-direction: column; gap: 14px; }}
        .edu-row {{
            background: #fff; border: 1px solid #e5e7eb; border-radius: 16px;
            padding: 14px 16px; box-shadow: 0 6px 18px rgba(15,23,42,0.05);
            transition: transform .2s ease, box-shadow .2s ease, border-color .2s ease;
        }}
        .edu-row:hover {{
            transform: translateY(-3px); border-color: var(--c);
            box-shadow: 0 14px 30px rgba(15,23,42,0.10);
        }}
        .edu-head {{ display: flex; justify-content: space-between; align-items: baseline; gap: 10px; }}
        .edu-name {{ font-size: 17px; font-weight: 800; color: #0f172a; }}
        .edu-count {{ font-size: 15px; font-weight: 800; color: var(--c); white-space: nowrap; }}
        .edu-count em {{ font-style: normal; font-weight: 700; color: #64748b; font-size: 12px; }}
        .edu-track {{
            margin: 10px 0 10px; height: 12px; border-radius: 999px;
            background: #eef2f7; overflow: hidden;
        }}
        .edu-bar {{
            height: 100%; width: var(--bar); border-radius: 999px;
            background: linear-gradient(90deg, var(--c), color-mix(in srgb, var(--c) 55%, white));
            transform-origin: left center; animation: eduGrow 0.9s cubic-bezier(.2,.8,.2,1) both;
        }}
        @keyframes eduGrow {{ from {{ transform: scaleX(0); }} to {{ transform: scaleX(1); }} }}
        .edu-lvs {{ display: flex; flex-wrap: wrap; gap: 6px; }}
        .edu-lv {{
            font-size: 11px; font-weight: 700; color: #334155;
            background: #f1f5f9; border: 1px solid #e2e8f0;
            border-radius: 999px; padding: 3px 9px;
            transition: background .15s ease, color .15s ease;
        }}
        .edu-row:hover .edu-lv {{ background: color-mix(in srgb, var(--c) 12%, white); color: var(--c); }}
        @media (max-width: 640px) {{
            .edu-name {{ font-size: 15px; }}
            .edu-count {{ font-size: 13px; }}
            .edu-row {{ padding: 12px; border-radius: 12px; }}
            .edu-track {{ height: 10px; }}
        }}
        @media (prefers-reduced-motion: reduce) {{
            .edu-bar {{ animation: none; }}
            .edu-row {{ transition: none; }}
        }}
    </style>
    <div class="edu-wrap"><div class="edu-grid">{''.join(cards)}</div></div>
    """

    st.caption("KECO 코드 대신 큰 전공 범주(학부 단위)로 묶어 인원을 집계했습니다. 막대를 마우스로 올리면 강조됩니다.")
    summary_cols = st.columns(3)
    summary_cols[0].metric("전체 인원", f"{total_people}명")
    summary_cols[1].metric("전공 범주", f"{used_cats}개")
    top_cat = cat_people.idxmax() if len(cat_people) else "-"
    summary_cols[2].metric("최다 범주", f"{top_cat}")

    components.html(html, height=min(1200, 140 + used_cats * 120), scrolling=True)

    with st.expander("세부 전공 → 범주 매핑 보기"):
        detail = (
            work.groupby(["category", "degree", "faculty", "major"], dropna=False)["employee_id"]
            .nunique().reset_index(name="인원")
            .sort_values(["category", "인원"], ascending=[True, False], ignore_index=True)
        )
        st.dataframe(detail, hide_index=True, width="stretch")


# ============================================================
# SW 대가 산정 가이드 업데이트 배너 (KIBA 피드 구독)
# KIBA repo 가 sw.or.kr(cbIdx=276)을 매일 모니터링해 Pages 로 공개하는 피드를 읽어
# 새 대가산정 가이드/인건비/템플릿이 올라오면 관리 화면 상단에 알린다.
# ============================================================
_SW_GUIDE_FEED = "https://feed-mina.github.io/kiba_2026/data/sw_guide_latest.json"


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_sw_guide_feed():
    import json
    import urllib.request
    with urllib.request.urlopen(_SW_GUIDE_FEED, timeout=5) as r:
        return json.load(r)


def render_sw_guide_banner() -> None:
    try:
        data = _fetch_sw_guide_feed()
    except Exception:
        return  # 피드 접속 실패 시 조용히 생략
    latest = (data or {}).get("latest")
    if not latest:
        return
    is_new = bool(data.get("new_since_last_check"))
    icon = "🔔" if is_new else "📄"
    head = "SW 대가 산정 가이드 새 글" if is_new else "최신 SW 대가 산정 가이드"
    msg = f"{icon} **{head}** — [{latest['title']}]({latest['url']}) · {latest['date']}"
    (st.warning if is_new else st.info)(msg)


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
    render_sw_guide_banner()

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
