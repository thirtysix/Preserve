"""Incremental, placeholder-aware restoration for streamed responses.

A streamed completion arrives in fragments, so a placeholder like ``[EMAIL_1]``
can be split across chunks (``...[EMA`` then ``IL_1]...``). Restoring each
fragment naively would emit a half-token. PlaceholderStreamRestorer holds back a
trailing fragment that could still be an in-progress placeholder, releasing
(and restoring) it only once it is known to be complete.
"""

from __future__ import annotations

import re
from typing import Callable

# A trailing run that could still grow into a [TYPE_N] placeholder: an unclosed
# '[' followed only by characters that are legal inside a placeholder body.
_PARTIAL = re.compile(r"\[[A-Z0-9_]*$")


class PlaceholderStreamRestorer:
    def __init__(self, restore: Callable[[str], str]) -> None:
        self._restore = restore
        self._buf = ""

    def feed(self, text: str) -> str:
        """Add a fragment; return the portion safe to emit (already restored)."""
        if text:
            self._buf += text
        m = _PARTIAL.search(self._buf)
        if m:
            emit, self._buf = self._buf[: m.start()], self._buf[m.start():]
        else:
            emit, self._buf = self._buf, ""
        return self._restore(emit) if emit else ""

    def flush(self) -> str:
        """Return any held-back remainder (restored). Call at end of stream."""
        out = self._restore(self._buf) if self._buf else ""
        self._buf = ""
        return out
