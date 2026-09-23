"""Unit tests for text chunking."""

from app.services.chunker import (
    _OVERLAP_CHARS,
    _TARGET_CHARS,
    chunk_text,
    estimate_tokens,
)

# ── estimate_tokens ───────────────────────────────────────────────────────────


def test_estimate_tokens_empty():
    assert estimate_tokens("") == 1  # max(1, 0)


def test_estimate_tokens_approximate():
    # 400 chars ≈ 100 tokens
    text = "a" * 400
    assert estimate_tokens(text) == 100


def test_estimate_tokens_unicode():
    # Unicode chars may be multi-byte but Python len() counts code points.
    text = "café " * 100  # 500 chars
    assert estimate_tokens(text) == 125


# ── chunk_text: edge cases ────────────────────────────────────────────────────


def test_empty_text_returns_empty_list():
    assert chunk_text("") == []


def test_whitespace_only_returns_empty_list():
    assert chunk_text("   \n\n   ") == []


def test_short_text_returns_single_chunk():
    text = "This is a short document."
    result = chunk_text(text)
    assert result == [text]


def test_text_exactly_at_limit_returns_single_chunk():
    text = "a" * _TARGET_CHARS
    result = chunk_text(text)
    assert len(result) == 1
    assert result[0] == text


def test_text_one_char_over_limit_splits():
    # Two equal paragraphs, each half the limit — together they exceed target.
    para = "a" * (_TARGET_CHARS // 2 + 1)
    text = para + "\n\n" + para
    result = chunk_text(text)
    assert len(result) >= 2


# ── chunk_text: large documents ───────────────────────────────────────────────


def test_large_text_produces_multiple_chunks():
    # 10× the target size — must produce many chunks.
    text = ("word " * 400 + "\n\n") * 10  # many paragraphs
    result = chunk_text(text)
    assert len(result) > 1


def test_chunk_size_within_reasonable_bound():
    # No chunk should exceed target_chars by more than one unit (~500 chars for a sentence).
    text = ("word " * 400 + "\n\n") * 10
    result = chunk_text(text)
    for chunk in result:
        assert len(chunk) <= _TARGET_CHARS * 2  # generous upper bound


def test_all_content_preserved():
    """Every paragraph should appear in at least one chunk."""
    paragraphs = [f"Paragraph number {i} with some content here." for i in range(20)]
    text = "\n\n".join(paragraphs)
    result = chunk_text(text)
    combined = " ".join(result)
    for para in paragraphs:
        assert para in combined


# ── chunk_text: overlap ───────────────────────────────────────────────────────


def test_overlap_between_consecutive_chunks():
    """The last unit(s) of chunk[i] should appear at the start of chunk[i+1]."""
    # Build text where paragraphs are large enough to force splits.
    para_size = _TARGET_CHARS // 3  # 3 paragraphs fit in one chunk
    paras = ["p" * para_size for _ in range(12)]
    text = "\n\n".join(paras)

    result = chunk_text(text)
    assert len(result) >= 2

    # The last ~overlap_chars of chunk[i] should appear somewhere in chunk[i+1].
    for i in range(len(result) - 1):
        tail = result[i][-_OVERLAP_CHARS:]
        # At least some overlap text should be in the next chunk.
        assert any(word in result[i + 1] for word in tail.split() if word)


# ── chunk_text: long paragraphs ───────────────────────────────────────────────


def test_long_paragraph_split_by_sentences():
    """A paragraph longer than target_chars must be split at sentence boundaries."""
    # Build a paragraph of many sentences.
    sentence = "This is a sentence with several words. "
    long_para = sentence * ((_TARGET_CHARS // len(sentence)) + 5)
    result = chunk_text(long_para)
    assert len(result) >= 2
    # Each chunk should not dramatically exceed target.
    for chunk in result:
        assert len(chunk) <= _TARGET_CHARS * 2


# ── chunk_text: Unicode ───────────────────────────────────────────────────────


def test_unicode_text_handled():
    para = "日本語のテキスト。これはテストです。" * 100
    text = (para + "\n\n") * 5
    result = chunk_text(text)
    # Should not raise; content preserved.
    assert len(result) >= 1
    assert all(isinstance(c, str) for c in result)


# ── chunk_text: determinism ───────────────────────────────────────────────────


def test_output_is_deterministic():
    text = "Some paragraph text here.\n\n" * 30
    assert chunk_text(text) == chunk_text(text)


# ── chunk_text: custom parameters ─────────────────────────────────────────────


def test_custom_target_chars():
    # With tiny target, every paragraph becomes its own chunk.
    paras = ["Short para."] * 5
    text = "\n\n".join(paras)
    result = chunk_text(text, target_chars=15, overlap_chars=0)
    assert len(result) >= 5


def test_chunk_index_ordering():
    """chunk_text output list should be in document order."""
    sentences = [f"Sentence {i}." for i in range(50)]
    text = " ".join(sentences)
    result = chunk_text(text, target_chars=200, overlap_chars=0)
    # First sentence in first chunk, last sentence in last chunk.
    assert "Sentence 0" in result[0]
    assert "Sentence 49" in result[-1]
