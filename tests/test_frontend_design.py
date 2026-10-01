from pathlib import Path
from unittest.mock import patch

import pytest
import toml
from streamlit.testing.v1 import AppTest

from frontend.components import evidence_quote, metric_card
from frontend.theme import COLORS, stylesheet

ROOT = Path(__file__).resolve().parents[1]


def contrast(foreground, background):
    def luminance(color):
        rgb = [int(color[index:index+2], 16) / 255 for index in (1, 3, 5)]
        linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4 for value in rgb]
        return sum(value * weight for value, weight in zip(linear, (.2126, .7152, .0722)))
    high, low = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (high + .05) / (low + .05)


@pytest.mark.parametrize("foreground,background", [
    ("text", "background"), ("text_secondary", "surface"), ("text_secondary", "surface_alt"),
    ("text_muted", "surface"), ("text_muted", "surface_alt"), ("surface", "primary"),
    ("surface", "primary_hover"), ("primary_hover", "primary_soft"),
    ("success", "success_soft"), ("warning", "warning_soft"), ("danger", "danger_soft"),
    ("sidebar_text", "sidebar"), ("sidebar_muted", "sidebar"), ("surface", "sidebar_surface"),
])
def test_normal_text_palette_meets_aa(foreground, background):
    assert contrast(COLORS[foreground], COLORS[background]) >= 4.5


def test_native_widgets_and_custom_components_share_the_light_theme():
    theme = toml.load(ROOT / ".streamlit/config.toml")["theme"]
    assert theme["base"] == "light"
    for native, token in (("backgroundColor", "background"), ("textColor", "text"),
                          ("primaryColor", "primary"), ("secondaryBackgroundColor", "surface_alt")):
        assert theme[native] == COLORS[token]
    assert theme["sidebar"]["textColor"] == COLORS["sidebar_text"]
    assert "[data-testid=\"stSidebar\"] *" not in stylesheet()


def test_verified_quotes_and_score_cards_escape_user_content():
    with patch("frontend.components.st.markdown") as markdown:
        evidence_quote('<img src=x onerror="bad()">')
        metric_card("CV", "83/100", "<script>bad()</script>")
    rendered = "\n".join(call.args[0] for call in markdown.call_args_list)
    assert "<img" not in rendered
    assert "<script>" not in rendered
    assert "83/100" in rendered


@pytest.mark.parametrize("page,active", [("Analyzer", "Analyzer"), ("Results", "Analyzer"),
    ("My CVs", "My CVs"), ("Jobs", "Jobs"), ("Applications", "Applications"), ("Insights", "Insights")])
def test_navigation_has_one_active_readable_destination(page, active):
    app = AppTest.from_file(str(ROOT / "app.py"))
    app.session_state["page"] = page
    app.run(timeout=20)
    assert not app.exception
    selected = [button.label for button in app.sidebar.button if button.proto.type == "primary"]
    assert selected == [active]
