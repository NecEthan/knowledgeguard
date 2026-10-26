"""OpenAI embedding generation."""

import logging
import random

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_MODEL = "text-embedding-3-small"
_BATCH_SIZE = 100


async def generate_embeddings(chunks: list[str], max_retries: int = 2) -> list[list[float]]:
    """Generate 1536-dimension embeddings for a list of chunks.

    Batches requests to stay within OpenAI API limits.
    Returns a list of embeddings in the same order as the input.
    """
    if not chunks:
        return []

    if settings.mock_llm:
        return [[random.uniform(-0.1, 0.1) for _ in range(1536)] for _ in chunks]

    client = AsyncOpenAI(api_key=settings.openai_api_key, max_retries=max_retries)
    all_embeddings: list[list[float]] = []

    for i in range(0, len(chunks), _BATCH_SIZE):
        batch = chunks[i : i + _BATCH_SIZE]
        response = await client.embeddings.create(model=_MODEL, input=batch)
        # response.data is sorted by index so order is preserved.
        all_embeddings.extend(item.embedding for item in response.data)

    return all_embeddings
