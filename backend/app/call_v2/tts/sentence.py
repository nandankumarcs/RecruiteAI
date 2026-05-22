"""Sentence splitting for sentence-level parallel TTS.

Splits agent response text into chunks that can each be synthesised
independently.  The only guarantee this module makes is:

    " ".join(split_sentences(text)) ≈ text   (whitespace-normalised)

Rules
-----
* Split at sentence-terminal punctuation (. ! ?) followed by whitespace and
  an uppercase letter, or at end-of-string.
* Never split inside known abbreviations: Mr, Mrs, Dr, Prof, Sr, Jr, vs, etc,
  Inc, Ltd, Corp, initials (single capital followed by a period).
* Never split inside decimal numbers (e.g. 3.5).
* Short-sentence batching: if the resulting chunk would be shorter than
  `min_chars`, it is joined with the next chunk.  This prevents gaps where
  a very short spoken chunk finishes before the next TTS call completes.
"""

from __future__ import annotations

import re

# Terminal punctuation followed by space + capital, or end of string.
_SPLIT_PATTERN = re.compile(r'(?<=[.!?])(\s+)(?=[A-Z])|(?<=[.!?])\s*$')

# Tokens that should NOT be followed by a split even if they end with a period.
_NO_SPLIT_ABBREVS = frozenset({
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "rev",
    "vs", "etc", "approx", "dept", "est",
    "inc", "ltd", "corp", "co", "llc", "llp",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
    "mon", "tue", "wed", "thu", "fri", "sat", "sun",
    "no", "vol", "pg", "pp", "fig", "eq",
})

# Decimal number: digit(s) followed by a period and more digits.
_DECIMAL_RE = re.compile(r'\d+\.\d')

# Single capital initial: one uppercase letter followed by a period.
_INITIAL_RE = re.compile(r'\b[A-Z]\.$')


def split_sentences(text: str, min_chars: int = 20) -> list[str]:
    """Split *text* into sentence chunks suitable for individual TTS calls.

    Parameters
    ----------
    text:
        The full agent spoken text to split.
    min_chars:
        Minimum character length for a standalone chunk.  Chunks shorter than
        this threshold are joined with the following chunk to avoid the gap
        problem: if a chunk's audio plays faster than the next TTS call
        completes the candidate hears silence.  Default 20 covers most short
        phrases at Sarvam's ~950 ms minimum latency.

    Returns
    -------
    list[str]
        At least one non-empty string.  Whitespace is normalised within each
        chunk.  The concatenation of all chunks with a single space
        reconstructs the original text (whitespace-normalised).
    """
    text = " ".join(text.split())   # normalise internal whitespace
    if not text:
        return []

    raw_chunks = _split_at_boundaries(text)
    return _apply_min_chars(raw_chunks, min_chars)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _split_at_boundaries(text: str) -> list[str]:
    """Split text at sentence boundaries, respecting abbreviations."""
    candidates: list[int] = []   # character offsets where a split is allowed

    for match in _SPLIT_PATTERN.finditer(text):
        pos = match.start()
        preceding = text[:pos].rstrip()
        if _is_abbreviation(preceding):
            continue
        candidates.append(pos)

    if not candidates:
        return [text]

    chunks: list[str] = []
    prev = 0
    for pos in candidates:
        # Include the punctuation but not the following whitespace.
        chunk = text[prev:pos + 1].strip()
        if chunk:
            chunks.append(chunk)
        prev = pos + 1 + len(text[pos + 1:]) - len(text[pos + 1:].lstrip())
    tail = text[prev:].strip()
    if tail:
        chunks.append(tail)
    return [c for c in chunks if c]


def _is_abbreviation(token_text: str) -> bool:
    """Return True if *token_text* ends with an abbreviation or decimal."""
    if not token_text:
        return False
    # Decimal number: "3.5" → no split at "3."
    if _DECIMAL_RE.search(token_text):
        return True
    # Single initial: "J." → no split
    if _INITIAL_RE.search(token_text):
        return True
    # Known abbreviation word: strip trailing punctuation and check list
    last_word = re.split(r'\s+', token_text)[-1].rstrip('.').lower()
    return last_word in _NO_SPLIT_ABBREVS


def _apply_min_chars(chunks: list[str], min_chars: int) -> list[str]:
    """Join any chunk shorter than *min_chars* with the next chunk."""
    if min_chars <= 0 or len(chunks) <= 1:
        return chunks

    result: list[str] = []
    pending = ""
    for chunk in chunks:
        if pending:
            combined = pending + " " + chunk
            pending = ""
            chunk = combined
        if len(chunk) < min_chars:
            pending = chunk
        else:
            result.append(chunk)

    if pending:
        if result:
            result[-1] = result[-1] + " " + pending
        else:
            result.append(pending)

    return result or chunks
