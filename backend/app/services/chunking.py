"""Deterministic document chunking (Phase 7, FR-21).

Chunks are cut by fixed rules (never the LLM): split into paragraphs, group
paragraphs up to `max_chars`, then hard-split any still-oversized paragraph
at word boundaries. Overlap is deliberately avoided (a paragraph belongs to
exactly one chunk) so each retrieved chunk is a self-contained unit and
citations point at a stable source span.

Returns (start_char, end_char) spans into the original text so the UI can
show "from character X of document Y" and answers can cite precisely.
"""

import re
from dataclasses import dataclass

DEFAULT_MAX_CHARS = 1200


@dataclass(frozen=True)
class Chunk:
    content: str
    start_char: int
    end_char: int


def _paragraphs(text: str) -> list[tuple[str, int, int]]:
    """Split text into non-empty paragraphs with their source spans.
    Paragraphs are separated by one or more blank lines. The span is the
    trimmed paragraph's position in the original text.
    """
    out: list[tuple[str, int, int]] = []
    start = 0
    for match in re.finditer(r"\n\s*\n", text):
        raw = text[start : match.start()]
        para = raw.strip()
        if para:
            leading = len(raw) - len(raw.lstrip())
            out.append((para, start + leading, start + leading + len(para)))
        start = match.end()
    raw = text[start:]
    para = raw.strip()
    if para:
        leading = len(raw) - len(raw.lstrip())
        out.append((para, start + leading, start + leading + len(para)))
    return out


def _hard_split(paragraph: str, para_start: int, max_chars: int) -> list[tuple[str, int, int]]:
    """Split one paragraph at word boundaries into <= max_chars pieces,
    preserving exact source spans. Walks each token (from `re.finditer`,
    which reports exact offsets even with repeated words / odd whitespace).
    """
    pieces: list[tuple[str, int, int]] = []
    current: list[tuple[str, int, int]] = []
    current_len = 0
    for match in re.finditer(r"\S+", paragraph):
        word = match.group(0)
        w_start = para_start + match.start()
        w_end = para_start + match.end()
        sep = 1 if current else 0
        if current and current_len + sep + len(word) > max_chars:
            pieces.append((paragraph[current[0][1] - para_start : current[-1][2] - para_start], current[0][1], current[-1][2]))
            current = [(word, w_start, w_end)]
            current_len = len(word)
        else:
            current.append((word, w_start, w_end))
            current_len += len(word) + sep
    if current:
        pieces.append((paragraph[current[0][1] - para_start : current[-1][2] - para_start], current[0][1], current[-1][2]))
    return pieces


def chunk_text(text: str, *, max_chars: int = DEFAULT_MAX_CHARS) -> list[Chunk]:
    """Cut `text` into deterministic chunks with source spans."""
    result: list[Chunk] = []
    for para, para_start, _ in _paragraphs(text):
        if len(para) <= max_chars:
            result.append(Chunk(para, para_start, para_start + len(para)))
            continue
        for piece, piece_start, piece_end in _hard_split(para, para_start, max_chars):
            result.append(Chunk(piece, piece_start, piece_end))
    return result