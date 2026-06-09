import os
import re
import streamlit as st
import db
import validation
import scoring
from datetime import date
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

st.set_page_config(page_title="quali-fit", layout="wide")

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
        # ---- CSV export view: rows = certs (by holder count), cols = work_codes ----
        st.caption(
            "자격증(행, 보유자 많은 순) × 업무분류(열) 매핑 — **CSV 내보내기용** 보기입니다. "
            "셀 값은 영향력(1~5), 빈 칸은 매핑 없음. 이 화면은 편집용이 아닙니다."
        )

        export_df = db.fetch_mapping_export()
        n_work = len(export_df.columns) - 3  # minus cert_code/cert_name/holder_count

        st.download_button(
            "CSV 다운로드",
            data=export_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="work_code_cert_map_export.csv",
            mime="text/csv",
            type="primary",
        )
        st.caption(f"자격증 {len(export_df)}행 × 업무분류 {n_work}열")
        st.dataframe(export_df, hide_index=True, width="stretch")

    elif choice:
        st.subheader(TABLE_LABELS.get(choice, choice))
        # ---- Generic CRUD (all other tables) ----
        df = db.fetch_all(choice)
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
