"""Central presentation tokens. Native widget colors mirror .streamlit/config.toml."""
from string import Template

import streamlit as st

COLORS = {
    "background": "#F7F9FC", "surface": "#FFFFFF", "surface_alt": "#F1F5F9",
    "text": "#0F172A", "text_secondary": "#475569", "text_muted": "#596579",
    "border": "#DEE5EE", "primary": "#4F46E5", "primary_hover": "#4338CA",
    "primary_soft": "#EEF2FF", "success": "#15803D", "success_soft": "#F0FDF4",
    "warning": "#92400E", "warning_soft": "#FFFBEB",
    "danger": "#B91C1C", "danger_soft": "#FEF2F2",
    "sidebar": "#111C30", "sidebar_surface": "#1E2E48", "sidebar_text": "#D5DEEC",
    "sidebar_muted": "#A8B7CE", "sidebar_accent": "#A5B4FC",
}
LAYOUT = {"max_width": 1280, "card_radius": 14, "control_radius": 9}

_CSS = Template("""
<style>
:root { color-scheme: light; }
html, body, .stApp { background: $background; color: $text; }
body, .stApp, h1, h2, h3, h4, input, textarea, button {
    font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}
[data-testid="stHeader"] { background: $background; }
[data-testid="stMainBlockContainer"] {
    max-width: ${max_width}px; padding: 2.8rem 2.5rem 4rem;
}
[data-testid="stHeading"] h1 { font-size: 2.25rem; font-weight: 750; line-height: 1.2; letter-spacing: -.04em; overflow-wrap: anywhere; }
[data-testid="stHeading"] h2 { font-size: 1.5rem; letter-spacing: -.025em; line-height: 1.35; }
[data-testid="stHeading"] h3 { font-size: 1.3rem; letter-spacing: -.02em; line-height: 1.4; }
.stMarkdown p, .stMarkdown li { font-size: .96rem; line-height: 1.65; overflow-wrap: anywhere; }
[data-testid="stCaptionContainer"] p { color: $text_secondary; font-size: .85rem; line-height: 1.55; }
[data-testid="stWidgetLabel"] p { color: $text_secondary; font-size: .875rem; font-weight: 550; }
.stMarkdown a { color: $primary; text-underline-offset: 3px; }
hr { border-color: $border; margin: 1rem 0; }
[class*="st-key-surface_"] {
    background: $surface; border-color: $border; border-radius: ${card_radius}px;
}
[class*="st-key-surface_"] h3 { font-size: 1.1rem; }
[data-testid="stForm"] { background: $surface; border-color: $border; border-radius: ${card_radius}px; }
[data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea,
[data-testid="stNumberInput"] input, [data-testid="stDateInput"] input {
    background: $surface; color: $text; caret-color: $text; border-radius: ${control_radius}px;
}
[data-testid="stTextInput"] input::placeholder,
[data-testid="stTextArea"] textarea::placeholder { color: $text_muted; opacity: 1; }
[data-testid="stSelectbox"] [role="combobox"] { color: $text; }
[data-testid="stTextInput"] input:disabled,
[data-testid="stTextArea"] textarea:disabled,
[data-testid="stSelectbox"] [role="combobox"]:disabled { color: $text_muted; -webkit-text-fill-color: $text_muted; }
button[kind="primary"], button[kind="secondary"], button[kind="tertiary"] {
    min-height: 42px; border-radius: ${control_radius}px; font-weight: 600; box-shadow: none;
}
button[kind="primary"] { background: $primary; color: $surface; border-color: $primary; }
button[kind="primary"]:hover { background: $primary_hover; border-color: $primary_hover; color: $surface; }
button[kind="secondary"] { background: $surface; color: $text; border-color: $border; }
button[kind="secondary"]:hover { color: $primary_hover; border-color: $primary; background: $primary_soft; }
button:disabled { background: $surface_alt; color: $text_muted; border-color: $border; opacity: 1; }
button:disabled p { color: $text_muted; }
button:focus-visible, summary:focus-visible, [role="tab"]:focus-visible {
    outline: 3px solid $primary; outline-offset: 3px;
}
[class*="st-key-delete_confirm_delete_"] button,
[class*="st-key-confirm_delete_"][class*="_yes"] button {
    color: $danger; background: $surface; border-color: $border;
}
[class*="st-key-delete_confirm_delete_"] button:hover,
[class*="st-key-confirm_delete_"][class*="_yes"] button:hover {
    background: $danger_soft; color: $danger; border-color: $danger;
}
[data-testid="stFileUploaderDropzone"] {
    background: $surface_alt; border: 1px dashed $border; border-radius: 12px; padding: 1rem;
}
[data-testid="stFileUploaderDropzone"] small { color: $text_secondary; }
[data-testid="stExpander"] details {
    background: $surface; border: 1px solid $border; border-radius: 10px;
}
[data-testid="stExpander"] summary p { color: $text; white-space: normal; overflow-wrap: anywhere; line-height: 1.5; }
[data-testid="stTabs"] [role="tablist"] { gap: 1.4rem; border-bottom: 1px solid $border; }
[data-testid="stTabs"] [role="tab"] { color: $text_secondary; font-size: .95rem; }
[data-testid="stTabs"] [role="tab"][aria-selected="true"] { color: $primary; font-weight: 650; }
[data-testid="stProgress"] { margin-bottom: .55rem; }
[data-testid="stMetric"] {
    background: $surface; border: 1px solid $border; border-radius: ${card_radius}px; padding: 1.1rem 1.2rem;
}
[data-testid="stMetricLabel"] p { color: $text_secondary; font-size: .82rem; }
[data-testid="stMetricValue"] { color: $text; font-size: 2rem; font-weight: 700; }
[data-testid="stAlert"] p { color: $text; }
[data-testid="stDataFrame"], [data-testid="stTable"] { color: $text; }
[data-testid="stCode"] pre { background: $surface_alt; color: $text; }
[data-testid="stText"] { white-space: pre-wrap; overflow-wrap: anywhere; color: $text_secondary; line-height: 1.6; font-family: inherit; }
.cv-kicker { color: $primary; font-size: .76rem; font-weight: 650; letter-spacing: .09em; text-transform: uppercase; margin: .25rem 0 .45rem; }
.cv-page-subtitle { color: $text_secondary; font-size: 1rem; line-height: 1.65; max-width: 780px; margin: -.35rem 0 1.2rem; }
.cv-card { background: $surface; border: 1px solid $border; border-radius: ${card_radius}px; padding: 1.3rem; min-height: 145px; }
.cv-label { font-size: .76rem; font-weight: 650; color: $text_secondary; letter-spacing: .055em; text-transform: uppercase; }
.cv-metric { font-size: 2.3rem; font-weight: 750; color: $text; line-height: 1.2; letter-spacing: -.04em; margin: .5rem 0; }
.cv-metric-status { font-size: 1.25rem; letter-spacing: -.02em; padding: .35rem 0; }
.cv-sub { color: $text_secondary; font-size: .85rem; line-height: 1.5; overflow-wrap: anywhere; }
.cv-badge { display: inline-flex; align-items: center; gap: .4rem; border-radius: 7px; padding: .25rem .65rem; font-size: .8rem; font-weight: 600; line-height: 1.5; margin: 0 .4rem .4rem 0; }
.cv-badge-primary { color: $primary_hover; background: $primary_soft; }
.cv-badge-success { color: $success; background: $success_soft; }
.cv-badge-warning { color: $warning; background: $warning_soft; }
.cv-badge-danger { color: $danger; background: $danger_soft; }
.cv-badge-neutral { color: $text_secondary; background: $surface_alt; }
.cv-inline-status { display: flex; gap: .65rem; background: $success_soft; color: $success; border-radius: 9px; padding: .7rem .8rem; font-size: .86rem; margin: .5rem 0; overflow-wrap: anywhere; }
.cv-inline-status strong { font-weight: 600; }
.cv-inline-status small { display: block; color: $text_secondary; font-size: .8rem; margin-top: .2rem; }
.cv-mode { background: $primary_soft; border-radius: 12px; padding: .8rem 1rem; margin: .25rem 0 .6rem; }
.cv-mode strong { color: $primary_hover; font-size: .94rem; }
.cv-mode p { color: $text_secondary; font-size: .86rem; margin: .2rem 0 0; line-height: 1.55; }
.cv-evidence { border-left: 3px solid $border; background: $surface_alt; border-radius: 0 8px 8px 0; color: $text_secondary; padding: .75rem .9rem; font-size: .9rem; line-height: 1.6; margin: .6rem 0; overflow-wrap: anywhere; }
.cv-empty { background: $surface; border: 1px dashed $border; border-radius: ${card_radius}px; padding: 2rem; text-align: center; margin: .5rem 0 1rem; }
.cv-empty-title { color: $text; font-size: 1.08rem; font-weight: 650; margin-bottom: .45rem; }
.cv-empty-copy { color: $text_secondary; font-size: .94rem; line-height: 1.6; }
.cv-count-row { display: flex; align-items: start; justify-content: space-between; gap: 1rem; border-bottom: 1px solid $border; padding: .7rem 0; color: $text; font-size: .92rem; }
.cv-count-label { overflow-wrap: anywhere; }
.cv-count-value { color: $text_secondary; white-space: nowrap; font-size: .86rem; }
.cv-nav-group { color: $sidebar_muted; font-size: .7rem; font-weight: 650; text-transform: uppercase; letter-spacing: .09em; padding: .75rem .4rem 0; }
.cv-brand { display: flex; align-items: center; gap: .7rem; margin: .3rem 0 .4rem; }
.cv-brand-mark { display: grid; place-items: center; background: $primary; color: $surface; width: 34px; height: 34px; border-radius: 10px; font-size: 1rem; font-weight: 750; }
.cv-brand-name { color: $surface; font-size: 1.35rem; font-weight: 700; letter-spacing: -.035em; }
.cv-brand-subtitle { color: $sidebar_muted; font-size: .79rem; margin: .5rem 0 1.5rem; }
.cv-sidebar-footer { color: $sidebar_muted; border-top: 1px solid $sidebar_surface; padding-top: 1.1rem; margin-top: 1.6rem; font-size: .78rem; line-height: 1.6; }
[data-testid="stSidebar"] { background: $sidebar; border-right: 1px solid $sidebar_surface; }
[data-testid="stSidebar"] .stButton button {
    justify-content: flex-start; text-align: left; padding: .65rem .8rem; min-height: 44px;
    color: $sidebar_text; background: transparent; border: 0; border-left: 3px solid transparent;
}
[data-testid="stSidebar"] .stButton button p { color: $sidebar_text; font-size: .9rem; }
[data-testid="stSidebar"] .stButton button:hover { color: $surface; background: $sidebar_surface; }
[data-testid="stSidebar"] .stButton button:hover p { color: $surface; }
[data-testid="stSidebar"] .stButton button[kind="primary"] { background: $sidebar_surface; border-left-color: $sidebar_accent; color: $surface; }
[data-testid="stSidebar"] .stButton button[kind="primary"] p { color: $surface; }
[data-testid="stSidebar"] .stButton button:focus-visible { outline-color: $sidebar_accent; }
[data-testid="stSidebar"] [data-testid="stIconMaterial"] { color: $sidebar_text; }
@media (max-width: 1250px) {
    .st-key-result_metrics [data-testid="stHorizontalBlock"],
    .st-key-dashboard_metrics [data-testid="stHorizontalBlock"],
    .st-key-insights_metrics [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
    .st-key-result_metrics [data-testid="stColumn"],
    .st-key-dashboard_metrics [data-testid="stColumn"],
    .st-key-insights_metrics [data-testid="stColumn"] { flex: 1 1 calc(50% - 1rem); min-width: 0; }
}
@media (max-width: 900px) {
    [data-testid="stMainBlockContainer"] { padding: 2.2rem 1.35rem 3rem; }
    [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] { flex: 1 1 100%; min-width: 0; }
    [data-testid="stHeading"] h1 { font-size: 2rem; }
}
@media (max-width: 600px) {
    [data-testid="stMainBlockContainer"] { padding: 1.6rem 1rem 2.5rem; }
    .st-key-result_metrics [data-testid="stColumn"],
    .st-key-dashboard_metrics [data-testid="stColumn"],
    .st-key-insights_metrics [data-testid="stColumn"] { flex: 1 1 100%; }
    .cv-card { min-height: 120px; }
    .cv-empty { padding: 1.3rem; }
    [data-testid="stHeading"] h1 { font-size: 1.9rem; }
}
</style>
""")


def stylesheet() -> str:
    return _CSS.substitute(**COLORS, **LAYOUT)


def apply_theme():
    st.markdown(stylesheet(), unsafe_allow_html=True)
