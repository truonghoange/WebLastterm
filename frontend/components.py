"""Small shared visual components; never compute application scores."""
from html import escape

import streamlit as st


def surface(key: str):
    """A native, accessible container with a stable design-system surface class."""
    return st.container(border=True, key=f"surface_{key}")


def page_header(title: str, subtitle: str = "", eyebrow: str = ""):
    if eyebrow:
        st.markdown(f'<div class="cv-kicker">{escape(eyebrow)}</div>', unsafe_allow_html=True)
    st.title(title)
    if subtitle:
        st.markdown(f'<div class="cv-page-subtitle">{escape(subtitle)}</div>', unsafe_allow_html=True)


def metric_card(label: str, value: str, detail: str, *, compact_value: bool = False):
    classes = "cv-metric cv-metric-status" if compact_value else "cv-metric"
    st.markdown(f'<div class="cv-card"><div class="cv-label">{escape(label)}</div>'
                f'<div class="{classes}">{escape(value)}</div><div class="cv-sub">{escape(detail)}</div></div>',
                unsafe_allow_html=True)


def badge(label: str, tone: str = "neutral"):
    tone = tone if tone in {"primary", "success", "warning", "danger", "neutral"} else "neutral"
    st.markdown(f'<span class="cv-badge cv-badge-{tone}">{escape(label)}</span>', unsafe_allow_html=True)


def mode_notice(title: str, description: str):
    st.markdown(f'<div class="cv-mode"><strong>{escape(title)}</strong><p>{escape(description)}</p></div>', unsafe_allow_html=True)


def upload_status(filename: str, detail: str):
    st.markdown(f'<div class="cv-inline-status"><span aria-hidden="true">✓</span>'
                f'<div><strong>{escape(filename)}</strong><small>{escape(detail)}</small></div></div>', unsafe_allow_html=True)


def evidence_quote(quote: str):
    st.markdown(f'<blockquote class="cv-evidence">{escape(quote)}</blockquote>', unsafe_allow_html=True)


def empty_state(title: str, description: str = ""):
    st.markdown(f'<div class="cv-empty"><div class="cv-empty-title">{escape(title)}</div>'
                f'<div class="cv-empty-copy">{escape(description)}</div></div>', unsafe_allow_html=True)


def count_row(label: str, count: int, unit: str = ""):
    suffix = f" {unit}" if unit else ""
    st.markdown(f'<div class="cv-count-row"><span class="cv-count-label">{escape(label)}</span>'
                f'<span class="cv-count-value">{count}{escape(suffix)}</span></div>', unsafe_allow_html=True)
