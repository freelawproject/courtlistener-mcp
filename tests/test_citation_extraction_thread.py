"""eyecite runs in a worker thread, so a long extraction doesn't stall
the event loop."""

import asyncio
import threading
import time
from unittest.mock import patch

import pytest

from courtlistener_mcp.exceptions import ToolArgumentValidationError
from courtlistener_mcp.lib import citation_analysis
from courtlistener_mcp.lib.citation_analysis import find_citations
from courtlistener_mcp.tools import MCP_TOOLS

TEXT = (
    "Brown v. Board of Education, 347 U.S. 483 (1954). "
    "Id. at 495. See Gideon v. Wainwright, 372 U.S. 335 (1963)."
)


@pytest.mark.asyncio
async def test_extraction_runs_off_the_event_loop():
    loop_thread = threading.get_ident()
    seen: list[int] = []
    real = citation_analysis.get_citations

    def recording(text):
        seen.append(threading.get_ident())
        return real(text)

    with patch.object(citation_analysis, "get_citations", recording):
        cites, resolutions = await find_citations(TEXT)

    assert seen and seen[0] != loop_thread
    assert len(cites) == 3
    assert len(resolutions) == 2


@pytest.mark.asyncio
async def test_event_loop_keeps_running_during_extraction():
    """A slow extraction leaves the loop free for other requests."""
    ticks = 0
    done = asyncio.Event()

    async def ticker():
        nonlocal ticks
        while not done.is_set():
            ticks += 1
            await asyncio.sleep(0.01)

    def slow(text):
        time.sleep(0.3)
        return []

    task = asyncio.create_task(ticker())
    with patch.object(citation_analysis, "get_citations", slow):
        await find_citations("anything")
    done.set()
    await task
    assert ticks >= 5


@pytest.mark.asyncio
async def test_no_resolution_when_not_asked():
    cites, resolutions = await find_citations(TEXT, resolve=False)
    assert len(cites) == 3
    assert resolutions == {}


@pytest.mark.asyncio
async def test_extract_citations_tool_output():
    tool = MCP_TOOLS["extract_citations"]
    resolved = await tool.call({"text": TEXT})
    assert "Found 3 citation(s) referencing 2 unique case(s)" in resolved
    flat = await tool.call({"text": TEXT, "resolve": False})
    assert flat.startswith("Found 3 citation(s):")
    assert await tool.call({"text": "no cites here"}) == (
        "No citations found."
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name", ["extract_citations", "analyze_citations"]
)
async def test_text_over_the_limit_is_rejected(tool_name):
    tool = MCP_TOOLS[tool_name]
    too_long = "x" * (citation_analysis.MAX_TEXT_LENGTH + 1)
    with pytest.raises(ToolArgumentValidationError) as raised:
        await tool.call({"text": too_long})
    message = str(raised.value)
    assert "1,000,001 characters" in message
    assert "1,000,000" in message
    assert too_long not in message
    assert raised.value.argument_names == ["text"]


@pytest.mark.asyncio
async def test_text_at_the_limit_is_accepted():
    tool = MCP_TOOLS["extract_citations"]
    text = "x" * citation_analysis.MAX_TEXT_LENGTH
    assert await tool.call({"text": text}) == "No citations found."
