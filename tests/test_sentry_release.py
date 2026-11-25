"""The Sentry release follows the build's ``GIT_SHA``."""

import pytest

from courtlistener_mcp.settings import sentry_release


def test_release_is_the_commit_sha():
    assert sentry_release("15e16b0") == "15e16b0"


@pytest.mark.parametrize("git_sha", ["unknown", ""])
def test_no_release_without_a_build_sha(git_sha):
    assert sentry_release(git_sha) is None
