"""Enforce rule 5 in docs/DEVELOPER.md (Code Layout): every module starts
with a docstring, except tool modules, whose class docstring is the tool's
description."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE_DIR = Path(__file__).resolve().parents[1] / "courtlistener_mcp"
TOOLS_DIR = PACKAGE_DIR / "tools"


def needs_docstring(path: Path) -> bool:
    is_tool_module = path.parent == TOOLS_DIR and path.stem not in (
        "__init__",
        "base",
    )
    return not is_tool_module


MODULES = sorted(
    path for path in PACKAGE_DIR.rglob("*.py") if needs_docstring(path)
)


@pytest.mark.parametrize(
    "path", MODULES, ids=lambda p: str(p.relative_to(PACKAGE_DIR))
)
def test_module_has_a_docstring(path):
    assert ast.get_docstring(ast.parse(path.read_text())), (
        f"{path.relative_to(PACKAGE_DIR.parent)} has no module docstring "
        "(rule 5 in docs/DEVELOPER.md)."
    )
