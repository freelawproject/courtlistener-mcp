"""Tests for the server's web files and their routes."""

import httpx
import pytest

from courtlistener_mcp import web
from courtlistener_mcp.server import ICONS, create_mcp_server


@pytest.fixture
def assets(tmp_path, monkeypatch):
    """An assets folder of our own, with the render caches cleared."""
    (tmp_path / "css").mkdir()
    (tmp_path / "html").mkdir()
    (tmp_path / "icons").mkdir()
    (tmp_path / "css" / "base.css").write_text("a { color: red; }")
    (tmp_path / "icons" / "logo.svg").write_text("<svg/>")
    monkeypatch.setattr(web, "ASSETS_DIR", tmp_path)
    web.render.cache_clear()
    web.data_uri.cache_clear()
    yield tmp_path
    web.render.cache_clear()
    web.data_uri.cache_clear()


class TestRender:
    def test_inlines_what_the_placeholders_name(self, assets):
        (assets / "html" / "page.html").write_text(
            "<style>{{ css/base.css }}</style><img src='{{icons/logo.svg}}'>"
        )
        assert web.render("html/page.html") == (
            "<style>a { color: red; }</style>"
            "<img src='data:image/svg+xml;base64,PHN2Zy8+'>"
        )

    def test_renders_an_inlined_page_first(self, assets):
        (assets / "html" / "header.html").write_text(
            "<header>{{ css/base.css }}</header>"
        )
        (assets / "html" / "page.html").write_text("{{ html/header.html }}!")
        assert web.render("html/page.html") == (
            "<header>a { color: red; }</header>!"
        )

    def test_leaves_what_it_inlines_alone(self, assets):
        (assets / "css" / "base.css").write_text("/* {{ html/page.html }} */")
        (assets / "html" / "page.html").write_text("{{ css/base.css }}")
        assert web.render("html/page.html") == "/* {{ html/page.html }} */"

    @pytest.mark.parametrize("name", ["css/missing.css", "../secret.css"])
    def test_refuses_a_file_that_is_not_an_asset(self, assets, name):
        (assets / "html" / "page.html").write_text(f"{{{{ {name} }}}}")
        with pytest.raises(FileNotFoundError):
            web.render("html/page.html")


def test_every_page_renders():
    for page in sorted((web.ASSETS_DIR / "html").glob("*.html")):
        assert "{{" not in web.render(f"html/{page.name}"), page.name


@pytest.mark.asyncio
class TestRoutes:
    @pytest.fixture
    def http(self):
        app = create_mcp_server().http_app()
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        )

    async def test_the_homepage_carries_the_shared_styles(self, http):
        response = await http.get("/")
        assert response.headers["content-type"].startswith("text/html")
        assert web.asset_path("css/base.css").read_text() in response.text

    @pytest.mark.parametrize("name", ICONS)
    async def test_serves_each_icon(self, http, name):
        response = await http.get(f"/{name}")
        assert response.status_code == 200
        assert response.content == web.asset_path(f"icons/{name}").read_bytes()
        assert response.headers["cache-control"] == "public, max-age=86400"
