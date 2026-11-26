"""The server's web files, under ``assets/``: pages in ``html/``, styles in
``css/``, scripts in ``js/`` and icons in ``icons/``.

A page is served whole. Hosts show MCP App views in sandboxed frames that
can't load other files without extra CSP setup, so pages pull in what they
share by placeholder instead of linking to it: ``{{ css/base.css }}``
inlines that file when the page is rendered. Text files (CSS, JS, HTML) are
inlined as they are, HTML rendered first so pages can share pieces; images
become data URIs, for ``src`` and ``href`` attributes.

An inlined script can't be imported, so a JS module's closing ``export
{...}`` becomes globals instead: a vendored bundle such as the MCP Apps SDK
then works from an inline ``<script type="module">``, and the page's own
module script after it finds its exports (``App``) on ``globalThis``.
"""

import base64
import mimetypes
import re
from functools import cache
from pathlib import Path

from courtlistener_mcp.settings import BASE_DIR

ASSETS_DIR = BASE_DIR / "assets"

PLACEHOLDER = re.compile(r"\{\{\s*([\w./-]+)\s*\}\}")
TEXT_SUFFIXES = {".css", ".js", ".html"}
EXPORTS = re.compile(r"\bexport\s*\{([^}]*)\};?\s*$")


def asset_path(name: str) -> Path:
    """The file at ``name``, a path under ``assets/`` such as
    ``icons/favicon.svg``."""
    path = (ASSETS_DIR / name).resolve()
    if not path.is_relative_to(ASSETS_DIR.resolve()) or not path.is_file():
        raise FileNotFoundError(f"No asset at {name!r}")
    return path


@cache
def data_uri(name: str) -> str:
    """The asset at ``name`` as a ``data:`` URI."""
    path = asset_path(name)
    mime_type = mimetypes.guess_type(path.name)[0]
    if mime_type is None:
        raise ValueError(f"Unknown type for asset {name!r}")
    encoded = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime_type};base64,{encoded}"


def exports_to_globals(script: str) -> str:
    """``script`` with its closing ``export {a as A, b}`` turned into
    ``Object.assign(globalThis, {A: a, b: b})``."""
    match = EXPORTS.search(script)
    if match is None:
        return script
    pairs = []
    for spec in filter(None, (s.strip() for s in match.group(1).split(","))):
        local, _, exported = spec.partition(" as ")
        pairs.append(f"{(exported or local).strip()}: {local.strip()}")
    assign = f"Object.assign(globalThis, {{{', '.join(pairs)}}});\n"
    return script[: match.start()] + assign


@cache
def render(name: str) -> str:
    """The asset at ``name`` with every ``{{ path }}`` placeholder in it
    replaced by the asset at that path. What's inlined isn't searched for
    placeholders again, except that an inlined page is rendered first."""

    def fill(match: re.Match) -> str:
        included = match.group(1)
        if Path(included).suffix == ".html":
            return render(included)
        if Path(included).suffix == ".js":
            return exports_to_globals(asset_path(included).read_text())
        if Path(included).suffix in TEXT_SUFFIXES:
            return asset_path(included).read_text()
        return data_uri(included)

    return PLACEHOLDER.sub(fill, asset_path(name).read_text())
