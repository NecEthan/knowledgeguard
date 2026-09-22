"""Deterministic text chunking for document processing.

Target: ~500 tokens per chunk, ~50 tokens overlap.
Approximation: 1 token ≈ 4 characters.
"""

import re

_TARGET_CHARS = 2000  # ~500 tokens
_OVERLAP_CHARS = 200  # ~50 tokens


def estimate_tokens(text: str) -> int:
    """Rough token estimate: 1 token ≈ 4 characters."""
    return max(1, len(text) // 4)


def chunk_text(
    text: str,
    target_chars: int = _TARGET_CHARS,
    overlap_chars: int = _OVERLAP_CHARS,
) -> list[str]:
    """Split text into overlapping chunks of approximately target_chars characters.

    - Empty text returns [].
    - Text shorter than target_chars returns [text].
    - Splits on paragraph breaks; falls back to sentence breaks for very long
      paragraphs.
    - Overlap is maintained by carrying trailing units into the next window.
    - Output is deterministic.
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= target_chars:
        return [text]

    units = _build_units(text, target_chars)
    if not units:
        return [text]

    chunks: list[str] = []
    window: list[str] = []
    window_len = 0

    for unit in units:
        unit_len = len(unit)

        if window and window_len + unit_len > target_chars:
            chunks.append("\n\n".join(window))
            # Build overlap from the tail of the current window.
            overlap: list[str] = []
            overlap_len = 0
            for u in reversed(window):
                if overlap_len + len(u) > overlap_chars:
                    break
                overlap.insert(0, u)
                overlap_len += len(u)
            window = overlap
            window_len = overlap_len

        window.append(unit)
        window_len += unit_len

    if window:
        chunks.append("\n\n".join(window))

    return chunks


def _build_units(text: str, max_unit_chars: int) -> list[str]:
    """Return a flat list of paragraphs (or sentences for long paragraphs)."""
    units: list[str] = []
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        if len(para) <= max_unit_chars:
            units.append(para)
        else:
            # Long paragraph: split by sentence boundaries.
            for sentence in re.split(r"(?<=[.!?])\s+", para):
                sentence = sentence.strip()
                if sentence:
                    units.append(sentence)
    return units
