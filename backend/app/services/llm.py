import json
import logging

import openai
from fastapi import HTTPException
from openai import AsyncOpenAI
from pydantic import ValidationError

from app.config import settings
from app.schemas.query import LLMAnswer

logger = logging.getLogger(__name__)

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


async def generate_answer(question: str, context_text: str) -> LLMAnswer:
    """Call OpenAI chat completion and parse structured response."""
    user_prompt = f"Context:\n{context_text}\n\nQuestion: {question}"
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
        logger.warning("OpenAI chat completion error: %s", exc)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    raw = (completion.choices[0].message.content or "{}").strip()
    try:
        llm_data = json.loads(raw)
        return LLMAnswer.model_validate(llm_data)
    except (json.JSONDecodeError, ValidationError):
        logger.warning("LLM returned invalid JSON: %.200s", raw)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
