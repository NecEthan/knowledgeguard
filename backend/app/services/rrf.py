"""Reciprocal Rank Fusion — combines two ranked result lists into one."""

import uuid


def rrf_combine(
    vector_results: list[tuple[uuid.UUID, int]],
    fts_results: list[tuple[uuid.UUID, int]],
    k: int = 60,
) -> list[tuple[uuid.UUID, float]]:
    """Combine two ranked lists using Reciprocal Rank Fusion.

    RRF score = Σ 1 / (k + rank)

    Args:
        vector_results: [(chunk_id, rank), ...] from vector search (rank 1-based).
        fts_results:    [(chunk_id, rank), ...] from full-text search (rank 1-based).
        k:              RRF constant (default 60, standard value from literature).

    Returns:
        [(chunk_id, rrf_score), ...] sorted descending by score.
        Equal scores are broken deterministically by chunk_id string representation.
    """
    scores: dict[uuid.UUID, float] = {}
    for chunk_id, rank in vector_results:
        scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    for chunk_id, rank in fts_results:
        scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: (-x[1], str(x[0])))
