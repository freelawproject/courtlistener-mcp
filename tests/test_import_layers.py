"""Enforce the import rule in docs/DEVELOPER.md (Code Layout): imports
flow one way, from ``server/`` down to the foundation modules."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE = "courtlistener_mcp"
PACKAGE_DIR = Path(__file__).resolve().parents[1] / PACKAGE

FOUNDATION = {"settings", "exceptions", "tokens"}
SERVICES = {"session", "metrics"}

# What each layer may import from, besides itself. Foundation modules
# import nothing else from the package, not even each other.
ALLOWED = {
    "foundation": set(),
    "services": {"foundation"},
    "lib": {"foundation", "services"},
    "tools": {"foundation", "services", "lib"},
    "auth": {"foundation", "services", "lib"},
    "server": {"foundation", "services", "lib", "tools", "auth"},
}


def layer(module: str) -> str:
    """The layer of a module, given as its path inside the package."""
    top = module.split(".")[0]
    if top in FOUNDATION:
        return "foundation"
    if top in SERVICES:
        return "services"
    if top in ("lib", "tools", "auth", "server"):
        return top
    raise AssertionError(
        f"{PACKAGE}.{module} isn't in any layer. Put it in a package "
        "(lib, tools, auth, server), or add it to FOUNDATION or SERVICES "
        "here and to the Code Layout section of docs/DEVELOPER.md."
    )


def package_modules() -> list[str]:
    modules = []
    for path in sorted(PACKAGE_DIR.rglob("*.py")):
        parts = path.relative_to(PACKAGE_DIR).with_suffix("").parts
        if parts == ("__init__",):
            continue
        if parts[-1] == "__init__":
            parts = parts[:-1]
        modules.append(".".join(parts))
    return modules


def imported_modules(module: str) -> set[str]:
    """Package modules that *module* imports, anywhere in its source."""
    path = PACKAGE_DIR / module.replace(".", "/")
    path = path / "__init__.py" if path.is_dir() else path.with_suffix(".py")
    found = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == PACKAGE:
                # `from courtlistener_mcp import settings`
                found.update(alias.name for alias in node.names)
            elif node.module.startswith(f"{PACKAGE}."):
                found.add(node.module.removeprefix(f"{PACKAGE}."))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(f"{PACKAGE}."):
                    found.add(alias.name.removeprefix(f"{PACKAGE}."))
    return found


@pytest.mark.parametrize("module", package_modules())
def test_imports_flow_down_the_layers(module):
    own = layer(module)
    wrong = sorted(
        imported
        for imported in imported_modules(module)
        if layer(imported) != own
        and layer(imported) not in ALLOWED[own]
        or (own == "foundation" and imported != module)
    )
    assert not wrong, (
        f"{PACKAGE}.{module} ({own}) imports {', '.join(wrong)}, against "
        "the import rule in docs/DEVELOPER.md."
    )
