"""Tests for the wiki tools that create and edit pages."""

import logging

import pytest
from fastmcp.server.auth.auth import AccessToken

from courtlistener_mcp import session as session_module
from courtlistener_mcp.exceptions import (
    ToolArgumentValidationError,
    WikiAPIError,
    WikiToolError,
)
from courtlistener_mcp.lib import wiki as wiki_module
from courtlistener_mcp.lib import wiki_edits
from courtlistener_mcp.lib.web import asset_path
from courtlistener_mcp.lib.wiki_edits import (
    PROPOSAL_META_KEY,
    RETRY_HINT,
    apply_edits,
)
from courtlistener_mcp.session import InMemorySession, set_session
from courtlistener_mcp.tokens import TokenKind
from courtlistener_mcp.tools import wiki_confirm_edit, wiki_edit_page
from courtlistener_mcp.tools.wiki_confirm_edit import WikiConfirmEditTool
from courtlistener_mcp.tools.wiki_create_page import WikiCreatePageTool
from courtlistener_mcp.tools.wiki_edit_page import WikiEditPageTool

PAGE = {
    "path": "eng/deploys",
    "title": "Deploys",
    "description": "…",
    "content": "# Deploys\n\nShip on Tuesdays.\n",
    "revision": 3,
    "can_edit": True,
    "data_source_url": "",
    "data_source_ttl": 300,
}


def access_token(user="alice", kind=TokenKind.OAUTH):
    return AccessToken(
        token=f"token-{user}",
        client_id="c",
        scopes=["openid", "api", "wiki", "profile", "email"],
        claims={"token_kind": kind, "user_hash": user},
    )


def set_wiki_write(monkeypatch, write):
    """Send the tools' writes and previews to *write*."""
    for module in (wiki_edits, wiki_confirm_edit):
        monkeypatch.setattr(module, "wiki_write", write)


@pytest.fixture
def sign_in(monkeypatch):
    """Signed in with OAuth as alice; call it to sign in as someone else."""

    def use(token):
        for module in (wiki_module, session_module):
            monkeypatch.setattr(module, "get_access_token", lambda: token)

    use(access_token())
    set_session(InMemorySession())
    yield use
    set_session(None)


@pytest.fixture
def wiki(monkeypatch):
    """Stand in for the wiki: GETs answer with ``PAGE``, previews render
    their content, and every write is recorded."""

    class Wiki:
        def __init__(self):
            self.page = dict(PAGE)
            self.gets = []
            self.writes = []

        async def get(self, path, **params):
            self.gets.append((path, params))
            return dict(self.page)

        async def write(self, method, path, body):
            self.writes.append((method, path, body))
            if path == "preview/":
                return {"html": f"<p>{body['content']}</p>"}
            return {**self.page, **body, "revision": self.page["revision"] + 1}

    fake = Wiki()
    monkeypatch.setattr(wiki_edit_page, "wiki_get", fake.get)
    set_wiki_write(monkeypatch, fake.write)
    return fake


def saves(wiki):
    return [w for w in wiki.writes if w[1] != "preview/"]


async def propose(arguments):
    result = await WikiEditPageTool().call(
        {"path": "eng/deploys", "base_revision": 3, "change_message": "x"}
        | arguments
    )
    return result, result.meta[PROPOSAL_META_KEY]


class TestApplyEdits:
    def test_applies_each_edit_in_order(self):
        assert apply_edits("a b c", [{"old": "a", "new": "x"}]) == "x b c"
        # Each edit sees the text as the edits before it left it.
        edits = [{"old": "a", "new": "b"}, {"old": "bb", "new": "z"}]
        assert apply_edits("ab", edits) == "z"

    @pytest.mark.parametrize(
        "old, problem",
        [("missing", "isn't in the page source"), ("o", "occurs 2 times")],
    )
    def test_refuses_an_old_that_is_not_there_exactly_once(self, old, problem):
        with pytest.raises(ToolArgumentValidationError, match=problem):
            apply_edits("foo", [{"old": old, "new": "x"}])


@pytest.mark.asyncio
class TestPropose:
    async def test_proposes_without_saving(self, sign_in, wiki):
        result, proposal = await propose(
            {"edits": [{"old": "Tuesdays", "new": "Wednesdays"}]}
        )
        assert saves(wiki) == []
        assert wiki.gets == [("pages/eng/deploys", {"raw": "true"})]
        assert "nothing is saved" in result.content[0].text
        assert "token" not in result.content[0].text
        assert proposal["new_source"] == "# Deploys\n\nShip on Wednesdays.\n"
        assert proposal["old_source"] == PAGE["content"]
        assert "-Ship on Tuesdays." in proposal["diff"]
        assert "+Ship on Wednesdays." in proposal["diff"]
        assert proposal["new_preview"].startswith("<p># Deploys")
        assert proposal["old_preview"].startswith("<p># Deploys")

    async def test_refuses_a_stale_revision(self, sign_in, wiki):
        wiki.page = {**PAGE, "revision": 4}
        with pytest.raises(WikiAPIError, match="changed since you read it"):
            await propose({"content": "new"})

    async def test_refuses_a_page_you_cannot_edit(self, sign_in, wiki):
        wiki.page = {**PAGE, "can_edit": False}
        with pytest.raises(WikiAPIError, match="can't edit"):
            await propose({"content": "new"})

    @pytest.mark.parametrize(
        "arguments, problem",
        [
            ({}, "Nothing to change"),
            ({"content": PAGE["content"]}, "already has that title"),
            (
                {"content": "x", "edits": [{"old": "a", "new": "b"}]},
                "not both",
            ),
        ],
    )
    async def test_refuses_a_proposal_that_changes_nothing(
        self, sign_in, wiki, arguments, problem
    ):
        with pytest.raises(ToolArgumentValidationError, match=problem):
            await propose(arguments)

    async def test_carries_only_the_data_source_settings_that_change(
        self, sign_in, wiki
    ):
        url = "https://www.courtlistener.com/api/rest/v4/wiki-data/"
        _, proposal = await propose(
            {"data_source_url": url, "data_source_ttl": 300}
        )
        assert proposal["data_source"] == {
            "data_source_url": {"old": "", "new": url}
        }
        # The new preview is filled from the new data source.
        previews = [w[2] for w in wiki.writes if w[1] == "preview/"]
        assert {"content": PAGE["content"]} in previews
        assert {"content": PAGE["content"], "data_source_url": url} in (
            previews
        )

    async def test_previews_once_when_nothing_rendered_changes(
        self, sign_in, wiki
    ):
        _, proposal = await propose({"title": "Deploy schedule"})
        assert len([w for w in wiki.writes if w[1] == "preview/"]) == 1
        assert proposal["new_title"] == "Deploy schedule"

    async def test_a_failed_preview_still_proposes(
        self, sign_in, wiki, monkeypatch
    ):
        async def broken(method, path, body):
            raise WikiAPIError("nope", "500")

        set_wiki_write(monkeypatch, broken)
        _, proposal = await propose({"content": "new"})
        assert proposal["new_preview"] is None


@pytest.mark.asyncio
class TestConfirm:
    async def test_saves_the_proposal_once(self, sign_in, wiki):
        _, proposal = await propose({"content": "new"})
        page = await WikiConfirmEditTool().call({"token": proposal["token"]})
        assert saves(wiki) == [
            (
                "PATCH",
                "pages/eng/deploys",
                {
                    "base_revision": 3,
                    "change_message": "x",
                    "content": "new",
                    "title": "Deploys",
                },
            )
        ]
        assert page["revision"] == 4
        with pytest.raises(WikiAPIError, match="expired or was already"):
            await WikiConfirmEditTool().call({"token": proposal["token"]})

    async def test_refuses_an_unknown_token(self, sign_in, wiki):
        with pytest.raises(WikiAPIError, match="expired or was already"):
            await WikiConfirmEditTool().call({"token": "guess"})
        assert saves(wiki) == []


def test_only_the_review_view_can_confirm():
    meta = WikiConfirmEditTool().meta
    assert meta["ui"]["visibility"] == ["app"]


CREATE = {
    "directory": "eng/",
    "title": "Deploys",
    "content": "# Deploys",
    "change_message": "Add deploy notes",
}


@pytest.mark.asyncio
class TestCreate:
    async def test_proposes_without_saving(self, sign_in, wiki):
        result = await WikiCreatePageTool().call(
            CREATE | {"data_source_url": "https://x.test/d.json"}
        )
        proposal = result.meta[PROPOSAL_META_KEY]
        assert saves(wiki) == []
        assert "Create" in result.content[0].text
        assert proposal["action"] == "create"
        assert proposal["path"] == "eng"
        assert proposal["new_preview"] == "<p># Deploys</p>"
        assert proposal["data_source"] == {
            "data_source_url": {"old": None, "new": "https://x.test/d.json"}
        }
        assert wiki.writes == [
            (
                "POST",
                "preview/",
                {
                    "content": "# Deploys",
                    "data_source_url": "https://x.test/d.json",
                },
            )
        ]

    async def test_the_review_view_creates_it_once(self, sign_in, wiki):
        result = await WikiCreatePageTool().call(CREATE)
        token = result.meta[PROPOSAL_META_KEY]["token"]
        await WikiConfirmEditTool().call({"token": token})
        assert saves(wiki) == [
            ("POST", "pages/", CREATE | {"directory": "eng"})
        ]
        with pytest.raises(WikiAPIError, match="expired or was already"):
            await WikiConfirmEditTool().call({"token": token})

    async def test_refuses_the_top_level(self, sign_in, wiki):
        with pytest.raises(ToolArgumentValidationError, match="top level"):
            await WikiCreatePageTool().call(CREATE | {"directory": "/"})
        assert wiki.writes == []


CRLF_PAGE = PAGE | {
    "content": "# Deploys\r\n\r\nShip on Tuesdays.\r\nNot Fridays.\r\n"
}


@pytest.mark.asyncio
class TestLineEndings:
    """The wiki stores CRLFs; reads give the model LFs."""

    async def test_a_multi_line_edit_applies_to_a_crlf_page(
        self, sign_in, wiki
    ):
        wiki.page = dict(CRLF_PAGE)
        edit = {"old": "Ship on Tuesdays.\nNot Fridays.", "new": "Ship daily."}
        _, proposal = await propose({"edits": [edit]})
        assert proposal["new_source"] == "# Deploys\n\nShip daily.\n"
        await WikiConfirmEditTool().call({"token": proposal["token"]})
        # The save keeps the page's own line endings.
        assert (
            saves(wiki)[0][2]["content"] == "# Deploys\r\n\r\nShip daily.\r\n"
        )

    async def test_the_same_content_with_lfs_changes_nothing(
        self, sign_in, wiki
    ):
        wiki.page = dict(CRLF_PAGE)
        content = CRLF_PAGE["content"].replace("\r\n", "\n")
        with pytest.raises(
            ToolArgumentValidationError, match="Nothing to change"
        ):
            await propose({"content": content})


@pytest.mark.asyncio
class TestNulls:
    """A null optional argument means it wasn't sent, as some clients send
    every optional argument. Calls go through ``_handle``, as real ones do."""

    async def test_null_content_beside_edits_is_ignored(self, sign_in, wiki):
        result = await WikiEditPageTool()._handle(
            {
                "path": "eng/deploys",
                "base_revision": 3,
                "change_message": "x",
                "edits": [{"old": "Tuesdays", "new": "Wednesdays"}],
                "content": None,
                "title": None,
                "data_source_url": None,
                "data_source_ttl": None,
            }
        )
        proposal = result.meta[PROPOSAL_META_KEY]
        assert "Wednesdays" in proposal["new_source"]
        assert proposal["new_title"] == "Deploys"
        assert proposal["data_source"] == {}

    async def test_nulls_leave_the_data_source_alone(self, sign_in, wiki):
        wiki.page = PAGE | {"data_source_url": "https://x.test/d.json"}
        result = await WikiEditPageTool()._handle(
            {
                "path": "eng/deploys",
                "base_revision": 3,
                "change_message": "x",
                "content": "new",
                "data_source_url": None,
            }
        )
        token = result.meta[PROPOSAL_META_KEY]["token"]
        await WikiConfirmEditTool().call({"token": token})
        assert "data_source_url" not in saves(wiki)[0][2]

    async def test_null_optionals_on_create_are_ignored(self, sign_in, wiki):
        result = await WikiCreatePageTool()._handle(
            CREATE | {"data_source_url": None, "data_source_ttl": None}
        )
        assert result.meta[PROPOSAL_META_KEY]["data_source"] == {}


@pytest.mark.asyncio
class TestSignIn:
    @pytest.mark.parametrize(
        "tool, arguments",
        [
            (
                WikiEditPageTool(),
                {
                    "path": "eng/deploys",
                    "base_revision": 3,
                    "change_message": "x",
                    "content": "new",
                },
            ),
            (WikiCreatePageTool(), CREATE),
        ],
        ids=["edit", "create"],
    )
    async def test_an_api_token_is_told_it_needs_oauth(
        self, sign_in, wiki, tool, arguments
    ):
        sign_in(access_token(kind=TokenKind.API))
        with pytest.raises(WikiAPIError, match="needs an OAuth sign-in"):
            await tool.call(arguments)
        assert wiki.gets == [] and wiki.writes == []

    async def test_another_user_cannot_save_the_proposal(self, sign_in, wiki):
        _, proposal = await propose({"content": "new"})
        sign_in(access_token("mallory"))
        with pytest.raises(WikiAPIError, match="expired or was already"):
            await WikiConfirmEditTool().call({"token": proposal["token"]})
        assert saves(wiki) == []
        # It's still alice's to save.
        sign_in(access_token("alice"))
        await WikiConfirmEditTool().call({"token": proposal["token"]})
        assert len(saves(wiki)) == 1


@pytest.mark.asyncio
class TestFailedSave:
    def fail_saves(self, wiki, monkeypatch, error):
        write = wiki.write

        async def failing(method, path, body):
            if path != "preview/":
                raise error
            return await write(method, path, body)

        set_wiki_write(monkeypatch, failing)
        return lambda: set_wiki_write(monkeypatch, write)

    @pytest.mark.parametrize(
        "error",
        [
            WikiAPIError("locked", "409", code="locked"),
            WikiAPIError("slow down", "429"),
            WikiAPIError("down", "503"),
            WikiAPIError("unreachable", "connection"),
        ],
        ids=["locked", "rate-limited", "down", "unreachable"],
    )
    async def test_a_save_that_may_work_later_keeps_the_proposal(
        self, sign_in, wiki, monkeypatch, error
    ):
        _, proposal = await propose({"content": "new"})
        restore = self.fail_saves(wiki, monkeypatch, error)
        with pytest.raises(WikiAPIError) as exc:
            await WikiConfirmEditTool().call({"token": proposal["token"]})
        assert str(exc.value).endswith(RETRY_HINT)
        restore()
        await WikiConfirmEditTool().call({"token": proposal["token"]})
        assert len(saves(wiki)) == 1

    @pytest.mark.parametrize(
        "error",
        [
            WikiAPIError("changed", "409", code="conflict"),
            WikiAPIError("no", "403"),
        ],
        ids=["conflict", "forbidden"],
    )
    async def test_a_final_refusal_uses_up_the_proposal(
        self, sign_in, wiki, monkeypatch, error
    ):
        _, proposal = await propose({"content": "new"})
        self.fail_saves(wiki, monkeypatch, error)
        with pytest.raises(WikiAPIError) as exc:
            await WikiConfirmEditTool().call({"token": proposal["token"]})
        assert RETRY_HINT not in str(exc.value)
        with pytest.raises(WikiAPIError, match="expired or was already"):
            await WikiConfirmEditTool().call({"token": proposal["token"]})


@pytest.mark.asyncio
async def test_the_proposal_reaches_the_view_through_handle(sign_in, wiki):
    result = await WikiEditPageTool()._handle(
        {
            "path": "eng/deploys",
            "base_revision": 3,
            "change_message": "x",
            "content": "new",
        }
    )
    assert result.meta[PROPOSAL_META_KEY]["token"]
    assert (
        result.meta[PROPOSAL_META_KEY]["token"] not in result.content[0].text
    )


@pytest.mark.asyncio
async def test_a_removed_rule_counts_as_a_removed_line(sign_in, wiki):
    wiki.page = PAGE | {"content": "a\n---\nb\n"}
    result, proposal = await propose({"content": "a\nb\n"})
    assert "removes 1 lines" in result.content[0].text
    assert "\n----\n" in f"\n{proposal['diff']}\n"


@pytest.mark.parametrize(
    "status, level",
    [("409", logging.WARNING), ("401", logging.ERROR), ("503", logging.ERROR)],
)
def test_wiki_refusals_are_warnings_and_outages_errors(status, level):
    assert WikiToolError("x", "wiki_edit_page", status).log_level == level


def test_the_view_looks_for_the_retry_hint():
    html = asset_path("html/wiki-edit.html").read_text()
    hint = html.split('const RETRY_HINT = "', 1)[1].split('"', 1)[0]
    assert RETRY_HINT.endswith(hint)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error, kept",
    [
        (WikiAPIError("slow down", "429"), True),
        (WikiAPIError("notify failed", "500"), False),
        (WikiAPIError("read timeout", "connection"), False),
    ],
    ids=["rate-limited", "server-error", "timeout"],
)
async def test_a_create_is_retried_only_after_a_rate_limit(
    sign_in, wiki, monkeypatch, error, kept
):
    """A 5xx or a timeout can come after the wiki made the page, and a
    second create would make a duplicate."""
    result = await WikiCreatePageTool().call(CREATE)
    token = result.meta[PROPOSAL_META_KEY]["token"]

    async def failing(method, path, body):
        raise error

    set_wiki_write(monkeypatch, failing)
    with pytest.raises(WikiAPIError) as exc:
        await WikiConfirmEditTool().call({"token": token})
    assert str(exc.value).endswith(RETRY_HINT) is kept
