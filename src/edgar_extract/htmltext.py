"""HTML to plain text.

Filing documents are HTML — often iXBRL with heavy inline markup. Sending
that to the model burns input tokens on tags and measurably hurts
extraction quality. Strip it here so the LLM step never sees markup.

Stdlib only. A dependency like BeautifulSoup would work, but this is
~60 lines and the filings are structurally simple.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

# Elements whose content is never prose. ix:header carries iXBRL fact
# metadata (context refs, unit declarations, raw CIKs) that renders as
# stray tokens like "iso4217:USD" at the top of the document.
_SKIP = {"script", "style", "head", "meta", "link", "ix:header", "ix:hidden"}

# Elements that imply a line break when they close.
_BLOCK = {
    "p", "div", "br", "tr", "table", "li", "ul", "ol",
    "h1", "h2", "h3", "h4", "h5", "h6", "td", "th", "section",
}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _SKIP:
            self._skip_depth += 1
        elif tag == "br":
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in _BLOCK:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        # Collapse the source's own soft wraps. Filing HTML breaks lines
        # mid-phrase ("Victory\nCapital Holdings"), and preserving those
        # newlines splits company names and phone numbers across lines —
        # which breaks both verbatim-name extraction and eval string
        # matching. Line structure should come from block tags only.
        self._parts.append(re.sub(r"\s+", " ", data))

    def text(self) -> str:
        return "".join(self._parts)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    text = parser.text()

    # Non-breaking spaces are pervasive in filings and confuse tokenizers
    # and downstream string matching alike.
    text = text.replace("\xa0", " ")

    # Collapse runs of spaces/tabs, then runs of blank lines. Filings are
    # full of layout whitespace that carries no meaning.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
