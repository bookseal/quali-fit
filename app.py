import streamlit as st
import db
import validation
import scoring
from datetime import date

st.set_page_config(page_title="quali-fit", layout="wide")

# ---- Top-level mode toggle ----
MODES = ["Manage data", "Recommend staff"]
MODE_PARAM = {"Manage data": "manage", "Recommend staff": "recommend"}
PARAM_MODE = {v: k for k, v in MODE_PARAM.items()}

url_mode = st.query_params.get("mode", "manage")
default_mode = PARAM_MODE.get(url_mode, "Manage data")

mode = st.segmented_control(
    "Mode",
    MODES,
    default=default_mode,
    label_visibility="collapsed",
)
if mode and MODE_PARAM[mode] != st.query_params.get("mode"):
    st.query_params["mode"] = MODE_PARAM[mode]

# ======================================================================
# Manage data mode
# ======================================================================
if mode == "Manage data":
    url_choice = st.query_params.get("svc", db.KNOWN_TABLES[0])
    if url_choice not in db.KNOWN_TABLES:
        url_choice = db.KNOWN_TABLES[0]

    choice = st.segmented_control(
        "Service",
        db.KNOWN_TABLES,
        default=url_choice,
        label_visibility="collapsed",
    )
    if choice and choice != st.query_params.get("svc"):
        st.query_params["svc"] = choice

    if choice:
        st.subheader(choice)
        df = db.fetch_all(choice)
        editor_key = f"{choice}_editor"
        meta = db.table_meta(choice)
        fk_opts = db.fk_options(choice)
        column_config = {
            col: st.column_config.SelectboxColumn(col, options=opts, required=True)
            for col, opts in fk_opts.items()
        }
        real_cols = set(meta["all_cols"])
        for c in df.columns:
            if c not in real_cols:
                column_config[c] = st.column_config.TextColumn(c, disabled=True)
        for c in meta["auto_id_cols"]:
            column_config[c] = st.column_config.TextColumn(c, disabled=True, help="auto-generated on save")

        st.data_editor(
            df,
            num_rows="dynamic",
            width="stretch",
            hide_index=True,
            key=editor_key,
            column_config=column_config,
        )

        if st.button("Save"):
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
                    st.toast("Saved.", icon="✅")
                    del st.session_state[editor_key]
                    st.rerun()
                except Exception as e:
                    st.error(f"Error saving changes: {e}", icon="❌")

# ======================================================================
# Recommend staff mode
# ======================================================================
elif mode == "Recommend staff":
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
        "Work code",
        codes,
        index=codes.index(url_wc),
        format_func=lambda c: wc_label[c],
    )
    if work_code and work_code != st.query_params.get("wc"):
        st.query_params["wc"] = work_code

    joined = db.fetch_scoring_data(work_code)
    if joined.empty:
        st.info(f"No employees match {work_code} yet.")
    else:
        ranking, rationale = scoring.rank(joined, date.today())
        st.dataframe(
            ranking,
            width="stretch",
            hide_index=True,
            column_config={
                "score": st.column_config.ProgressColumn(
                    "Score", min_value=0, max_value=7, format="%.1f",
                ),
                "match_count":   st.column_config.NumberColumn("Matches"),
                "expired_count": st.column_config.NumberColumn("Expired"),
            },
        )

        # ---- Top 3 rationale ----
        st.subheader("Top 3 rationale")
        for rank_idx, (_, row) in enumerate(ranking.head(3).iterrows(), start=1):
            emp_id = row["employee_id"]
            person = rationale[rationale["employee_id"] == emp_id]
            st.markdown(
                f"**{rank_idx}. {row['name']} "
                f"({row['dept']} / {row['title']}) — score {row['score']:.1f}**"
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
            st.dataframe(
                person[display_cols].style.apply(style_row, axis=1),
                hide_index=True,
                width="stretch",
            )

        # ---- Explainer ----
        with st.expander("How scoring works (점수 산정 방식)"):
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
