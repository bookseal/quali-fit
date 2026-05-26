import streamlit as st
import db

st.set_page_config(page_title="quali-fit", layout="wide")

url_choice = st.query_params.get("svc", db.KNOWN_TABLES[0])
if url_choice not in db.KNOWN_TABLES:
    url_choice = db.KNOWN_TABLES[0]

choice = st.segmented_control(
    "Service",
    db.KNOWN_TABLES,
    default = url_choice,
    label_visibility="collapsed",
)

if choice and choice != st.query_params.get("svc"):
    st.query_params["svc"] = choice

if choice:
    st.subheader(choice)
    df = db.fetch_all(choice)
    st.dataframe(df, width="stretch", hide_index=True)