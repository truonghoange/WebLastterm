import streamlit as st
from frontend.review_ui import render_analyzer, render_results
from frontend.workspace_ui import render_workspace
from frontend.theme import apply_theme
from constants import MATCH_SCORE_LABELS, CV_SCORE_LABELS

st.set_page_config(page_title="CVision", page_icon="◈", layout="wide", initial_sidebar_state="expanded")

apply_theme()

defaults = {
    "page":"Dashboard","cv_text":"","jd_text":"","industry":"General / Auto","target_position":"",
    "cv_document":None,"analysis_result":None,"review_result":None,"rewrite_suggestions":[],
}
for k,v in defaults.items():
    if k not in st.session_state: st.session_state[k]=v

def go(page):
    st.session_state.page=page
    st.rerun()

def score_label(score, mode):
    for lo,hi,label,icon in (MATCH_SCORE_LABELS if mode == "job_match" else CV_SCORE_LABELS):
        if lo <= score <= hi: return f"{icon} {label}"
    return "Match" if mode == "job_match" else "CV quality"

with st.sidebar:
    st.markdown('<div class="cv-brand"><span class="cv-brand-mark">C</span><span class="cv-brand-name">CVision</span></div>'
                '<div class="cv-brand-subtitle">AI Career Intelligence</div>', unsafe_allow_html=True)
    current = st.session_state.page
    active = {"Results": "Analyzer", "CV Detail": "My CVs", "Job Detail": "Jobs", "New Job": "Jobs",
              "Edit Job": "Jobs", "Compare": "Jobs", "Application Detail": "Applications", "New Application": "Applications"}.get(current, current)
    groups = [("Overview", [("Dashboard", "dashboard"), ("Analyzer", "description")]),
              ("Workspace", [("My CVs", "folder_open"), ("Jobs", "work_outline"),
                             ("Applications", "view_kanban"), ("Insights", "insights")])]
    for group, items in groups:
        st.markdown(f'<div class="cv-nav-group">{group}</div>', unsafe_allow_html=True)
        for page, icon in items:
            if st.button(page, icon=f":material/{icon}:", key=f"nav_{icon}",
                         type="primary" if page == active else "secondary", use_container_width=True):
                go(page)
    st.markdown('<div class="cv-sidebar-footer">Evidence-based CV analysis</div>', unsafe_allow_html=True)

if st.session_state.page=="Analyzer":
    render_analyzer(go)

elif st.session_state.page=="Results":
    render_results(go, score_label)

else:
    render_workspace(st.session_state.page, go)
