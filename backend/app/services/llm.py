import json
import time

import openai
import structlog
from fastapi import HTTPException
from openai import AsyncOpenAI
from pydantic import ValidationError

from app.config import settings
from app.schemas.query import LLMAnswer

logger = structlog.get_logger(__name__)

_SYSTEM_PROMPT = (
    "You are a knowledge assistant. Answer questions using ONLY the provided context.\n"
    "Rules:\n"
    "- Answer only using information present in the context below.\n"
    "- Do not use any outside knowledge or information not present in the context.\n"
    "- If the answer cannot be determined from the context, set answer to "
    '"I don\'t have enough information to answer that question." and citations to [].\n'
    "- In citations, include only sources that directly support your answer.\n"
    "- Respond ONLY with valid JSON in this exact format:\n"
    '{"answer": "...", "citations": [{"document_title": "...", "version_number": N}]}'
)


def _estimate_cost(prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate OpenAI cost in USD using configured per-token pricing."""
    return (
        prompt_tokens * settings.llm_input_cost_per_1m_tokens / 1_000_000
        + completion_tokens * settings.llm_output_cost_per_1m_tokens / 1_000_000
    )


async def generate_answer(question: str, context_text: str) -> LLMAnswer:
    """Call OpenAI chat completion and parse structured response."""
    user_prompt = f"Context:\n{context_text}\n\nQuestion: {question}"
    start = time.monotonic()
    try:
        oai_client = AsyncOpenAI(api_key=settings.openai_api_key)
        completion = await oai_client.chat.completions.create(
            model=settings.chat_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
    except openai.OpenAIError as exc:
        logger.warning("openai_error", error=str(exc))
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    duration_ms = round((time.monotonic() - start) * 1000, 1)
    _log_llm_call(completion, duration_ms)

    raw = (completion.choices[0].message.content or "{}").strip()
    try:
        llm_data = json.loads(raw)
        return LLMAnswer.model_validate(llm_data)
    except (json.JSONDecodeError, ValidationError):
        logger.warning("llm_invalid_json", preview=raw[:200])
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")


def _log_llm_call(completion, duration_ms: float) -> None:
    """Log LLM latency, token usage, and estimated cost.  Never logs prompts or keys."""
    try:
        usage = completion.usage
        prompt_tokens = int(usage.prompt_tokens)
        completion_tokens = int(usage.completion_tokens)
        total_tokens = prompt_tokens + completion_tokens
        estimated_cost_usd = round(
            _estimate_cost(prompt_tokens, completion_tokens), 8
        )
        logger.info(
            "llm_call",
            model=settings.chat_model,
            duration_ms=duration_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=estimated_cost_usd,
        )
    except (TypeError, ValueError, AttributeError):
        # usage data unavailable (e.g. in tests with MagicMock completions)
        logger.info("llm_call", model=settings.chat_model, duration_ms=duration_ms)
