from pathlib import Path
import re

from app import app


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_mobile_menu_markup_preserves_full_primary_and_utility_navigation():
    response = app.test_client().get("/")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert re.search(
        r'<button[^>]*id="mobile-menu-toggle"[^>]*aria-label="Open navigation menu"'
        r'[^>]*aria-controls="primary-navigation"[^>]*aria-expanded="false"',
        html,
        re.DOTALL,
    )
    assert 'id="navigation-panel"' in html
    for href in (
        'href="/"',
        'href="/career-guide"',
        'href="/resume-analyzer"',
        'href="/job-description"',
        'href="/interview-simulator"',
        'href="/dashboard"',
        'href="/#how-it-works"',
    ):
        assert href in html


def test_mobile_menu_javascript_supports_toggle_selection_escape_and_outside_click():
    script = (PROJECT_ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")

    assert "menuToggle.setAttribute('aria-expanded', String(open))" in script
    assert "menuToggle.setAttribute('aria-label', open ? 'Close navigation menu' : 'Open navigation menu')" in script
    assert "menuToggle.addEventListener('click'" in script
    assert "navigationPanel.querySelectorAll('a')" in script
    assert "event.key === 'Escape'" in script
    assert "navigationPanel.contains(event.target)" in script
    assert "menuToggle.focus()" in script


def test_navigation_css_keeps_desktop_links_and_expands_panel_on_tablet_and_mobile():
    stylesheet = (PROJECT_ROOT / "static" / "css" / "style.css").read_text(encoding="utf-8")

    assert ".navigation-panel {\n  display: contents;" in stylesheet
    assert ".navigation-panel.is-open {\n    display: block;" in stylesheet
    assert "@media (max-width: 900px)" in stylesheet
    assert ".mobile-menu-toggle {\n    display: block;" in stylesheet
    assert ".nav {\n    display: grid;" in stylesheet
    assert ".nav {\n    display: none;" not in stylesheet


def test_dashboard_and_local_storage_behavior_remain_linked_to_existing_helpers():
    dashboard_script = (PROJECT_ROOT / "static" / "js" / "dashboard.js").read_text(encoding="utf-8")
    base_template = (PROJECT_ROOT / "templates" / "base.html").read_text(encoding="utf-8")
    storage_source = (PROJECT_ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")

    assert "window.appStorage.removeKeys(keys)" in dashboard_script
    assert "id=\"clear-saved-data\"" in (PROJECT_ROOT / "templates" / "dashboard.html").read_text(encoding="utf-8")
    assert "window.appStorage = {" in storage_source
    assert 'id="mobile-menu-toggle"' in base_template
