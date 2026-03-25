import streamlit as st
import pathlib

st.set_page_config(page_title="DROG — How To Use", page_icon="⚡", layout="wide")

html = pathlib.Path("pages/how_to_use.html").read_text(encoding="utf-8")
st.components.v1.html(html, height=1200, scrolling=True)
