import sys
from unittest.mock import MagicMock

from dotenv import load_dotenv

# Stub native-build MCP deps only when they are not installed, so
# tests that don't need them (e.g. test_auth) can still be collected.
# When the real packages ARE installed, they are used as-is.
for _mod in ("eyecite", "eyecite.models", "tiktoken"):
    try:
        __import__(_mod)
    except ImportError:
        sys.modules[_mod] = MagicMock()

load_dotenv()
