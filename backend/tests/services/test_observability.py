"""Tests for observability: structured logging in LLM and worker code."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from structlog.testing import capture_logs

from app.config import settings
from app.services.llm import (
    _estimate_cost,
    generate_answer,
)

# ── Cost estimation ───────────────────────────────────────────────────────────


def test_estimate_cost_zero_tokens():
    assert _estimate_cost(0, 0) == 0.0


def test_estimate_cost_known_values():
    # 1_000_000 input tokens → exactly settings.llm_input_cost_per_1m_tokens USD
    cost = _estimate_cost(1_000_000, 0)
    assert abs(cost - settings.llm_input_cost_per_1m_tokens) < 1e-12


def test_estimate_cost_output_tokens():
    cost = _estimate_cost(0, 1_000_000)
    assert abs(cost - settings.llm_output_cost_per_1m_tokens) < 1e-12


def test_estimate_cost_combined():
    # 500 input @ $0.15/1M + 100 output @ $0.60/1M
    cost = _estimate_cost(500, 100)
    expected = (
        500 * settings.llm_input_cost_per_1m_tokens / 1_000_000
        + 100 * settings.llm_output_cost_per_1m_tokens / 1_000_000
    )
    assert abs(cost - expected) < 1e-12


# ── LLM structured log events ─────────────────────────────────────────────────


def _make_completion(prompt_tokens: int, completion_tokens: int, answer_json: str):
    """Build a mock OpenAI completion with proper usage attributes."""
    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens

    choice = MagicMock()
    choice.message.content = answer_json

    completion = MagicMock()
    completion.choices = [choice]
    completion.usage = usage
    return completion


async def test_generate_answer_logs_llm_call_event():
    """generate_answer emits an llm_call log event with timing and token counts."""
    answer_json = json.dumps({"answer": "42", "citations": []})
    completion = _make_completion(200, 50, answer_json)

    with patch("app.services.llm.AsyncOpenAI") as mock_cls:
        instance = MagicMock()
        mock_cls.return_value = instance
        instance.chat.completions.create = AsyncMock(return_value=completion)

        with capture_logs() as logs:
            result = await generate_answer("What is 6 × 7?", "Context: 6 × 7 = 42.")

    assert result.answer == "42"

    llm_events = [e for e in logs if e.get("event") == "llm_call"]
    assert len(llm_events) == 1, f"Expected 1 llm_call event, got: {logs}"
    ev = llm_events[0]

    assert ev["model"] == settings.chat_model
    assert isinstance(ev["duration_ms"], float)
    assert ev["duration_ms"] >= 0
    assert ev["prompt_tokens"] == 200
    assert ev["completion_tokens"] == 50
    assert ev["total_tokens"] == 250
    assert "estimated_cost_usd" in ev
    assert ev["estimated_cost_usd"] >= 0


async def test_generate_answer_logs_llm_call_without_usage_when_missing():
    """generate_answer still logs llm_call even when usage is unavailable."""
    answer_json = json.dumps({"answer": "ok", "citations": []})
    completion = MagicMock()
    completion.choices = [MagicMock()]
    completion.choices[0].message.content = answer_json
    # Simulate missing usage by making int() raise TypeError
    completion.usage.prompt_tokens = "not-an-int"
    completion.usage.completion_tokens = "not-an-int"

    with patch("app.services.llm.AsyncOpenAI") as mock_cls:
        instance = MagicMock()
        mock_cls.return_value = instance
        instance.chat.completions.create = AsyncMock(return_value=completion)

        with capture_logs() as logs:
            await generate_answer("q", "ctx")

    llm_events = [e for e in logs if e.get("event") == "llm_call"]
    assert len(llm_events) == 1
    ev = llm_events[0]
    assert "duration_ms" in ev
    # Token fields must NOT be present when usage parsing fails
    assert "prompt_tokens" not in ev
    assert "completion_tokens" not in ev


async def test_generate_answer_does_not_log_prompt_or_key():
    """No prompt text, context, or API key must appear in log events."""
    answer_json = json.dumps({"answer": "secret", "citations": []})
    completion = _make_completion(10, 5, answer_json)

    with patch("app.services.llm.AsyncOpenAI") as mock_cls:
        instance = MagicMock()
        mock_cls.return_value = instance
        instance.chat.completions.create = AsyncMock(return_value=completion)

        with capture_logs() as logs:
            await generate_answer("sensitive question", "sensitive context")

    for entry in logs:
        entry_str = str(entry)
        assert "sensitive question" not in entry_str
        assert "sensitive context" not in entry_str
        assert settings.openai_api_key not in entry_str or settings.openai_api_key == ""
