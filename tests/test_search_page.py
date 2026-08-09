from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from shiliu.app import Application
from shiliu.web import create_web_app


def test_search_page_route_and_required_surface(app_paths) -> None:
    core = Application(app_paths)
    core.db.create_favorite_source(folder_id=42, folder_title="工程学习")
    client = TestClient(create_web_app(core))

    response = client.get("/search")

    assert response.status_code == 200
    text = response.text
    for marker in (
        'data-search-form', 'name="mode"', 'name="scope"',
        'data-filter-container', 'data-result-list', 'data-loading-state',
        'data-empty-state', 'data-error-state',
    ):
        assert marker in text
    assert '<option value="lexical">关键词</option>' in text
    assert '<option value="auto" selected>自动</option>' in text
    assert '<option value="all">全部内容</option>' in text
    assert "工程学习" in text
    assert "/static/search.css?v=4" in text
    assert "/static/search.js?v=6" in text
    assert 'name="uploader_contains"' in text


def test_navigation_links_to_separate_search_page(app_paths) -> None:
    client = TestClient(create_web_app(Application(app_paths)))
    home = client.get("/")
    assert home.status_code == 200
    assert '<a href="/search">搜索证据</a>' in home.text
    assert "data-search-page" not in home.text


def test_search_template_escapes_folder_names_and_script_uses_safe_dom(app_paths) -> None:
    core = Application(app_paths)
    core.db.create_favorite_source(folder_id=7, folder_title='<script>alert("x")</script>')
    response = TestClient(create_web_app(core)).get("/search")
    assert '<script>alert("x")</script>' not in response.text
    assert "&lt;script&gt;" in response.text

    source = (
        Path(__file__).parents[1]
        / "src" / "shiliu" / "static" / "search.js"
    ).read_text(encoding="utf-8")
    assert ".innerHTML" not in source
    assert "textContent" in source and "createElement" in source


def test_search_page_preserves_url_state_for_client_restore(app_paths) -> None:
    client = TestClient(create_web_app(Application(app_paths)))
    response = client.get(
        "/search?q=MCP&mode=auto&scope=transcript_chunk&reading_state=unread&marked=true"
    )
    assert response.status_code == 200
    script = client.get("/static/search.js?v=6").text
    assert "new URLSearchParams(location.search)" in script
    assert "pushState" in script and "popstate" in script
    assert "AbortController" in script and "requestSequence" in script
    assert "event.key !== 'Enter'" in script


def test_frontend_initial_mode_and_first_request_payload_are_auto(app_paths) -> None:
    client = TestClient(create_web_app(Application(app_paths)))
    page = client.get("/search").text
    script = client.get("/static/search.js?v=6").text
    assert '<option value="auto" selected>自动</option>' in page
    assert "mode: form.elements.mode.value || 'auto'" in script
    assert "params.get('mode') : 'auto'" in script
    assert "query: state.q, mode: state.mode" in script
    for mode in ("auto", "lexical", "dense", "hybrid"):
        assert f"value=\"{mode}\"" in page


def test_product_ui_sends_contains_field_without_overloading_exact_uploader(
    app_paths,
) -> None:
    client = TestClient(create_web_app(Application(app_paths)))
    page = client.get("/search").text
    script = client.get("/static/search.js?v=6").text

    assert 'name="uploader_contains"' in page
    assert 'name="uploader"' not in page
    assert "filters.uploader_contains = state.uploader_contains" in script
    assert "filters.uploader = state.uploader" not in script


def test_cover_layout_centers_search_and_library_portraits() -> None:
    static = Path(__file__).parents[1] / "src" / "shiliu" / "static"
    search_css = (static / "search.css").read_text(encoding="utf-8")
    search_js = (static / "search.js").read_text(encoding="utf-8")
    library_css = (static / "library.css").read_text(encoding="utf-8")
    app_js = (static / "app.js").read_text(encoding="utf-8")

    assert ".result-cover" in search_css and "align-self:center" in search_css
    assert "object-position:50% 50%" in search_css
    assert ".result-cover.is-portrait-cover" in search_css
    assert "image.naturalHeight > image.naturalWidth * 1.08" in search_js
    assert ".cover-wrap { background: var(--card); }" in library_css
    assert "--cover-zoom" in library_css
    assert "classifyLibraryCover" in app_js
    assert "is-pillarboxed" in app_js
