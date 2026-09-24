"""Unit tests for the RRF (Reciprocal Rank Fusion) service.

These tests have no database dependency — pure Python only.
"""

import uuid

import pytest

from app.services.rrf import rrf_combine

# Stable UUIDs for deterministic tests.
A = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
B = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")
C = uuid.UUID("cccccccc-0000-0000-0000-000000000003")
D = uuid.UUID("dddddddd-0000-0000-0000-000000000004")


def test_empty_both_lists():
    assert rrf_combine([], []) == []


def test_only_vector_results():
    results = rrf_combine([(A, 1), (B, 2), (C, 3)], [])
    ids = [r[0] for r in results]
    assert ids == [A, B, C]  # rank 1 scores highest


def test_only_fts_results():
    results = rrf_combine([], [(A, 1), (B, 2)])
    ids = [r[0] for r in results]
    assert ids == [A, B]


def test_overlap_boosts_score():
    # B appears in both lists — should score higher than A (vector only) and C (FTS only).
    vector = [(A, 1), (B, 2)]
    fts = [(B, 1), (C, 2)]
    results = rrf_combine(vector, fts)
    ids = [r[0] for r in results]
    assert ids[0] == B  # double appearance → highest score


def test_rrf_score_formula():
    k = 60
    vector = [(A, 1)]
    fts = [(A, 1)]
    results = rrf_combine(vector, fts, k=k)
    score = results[0][1]
    expected = 1.0 / (k + 1) + 1.0 / (k + 1)
    assert abs(score - expected) < 1e-10


def test_chunk_only_in_vector_results():
    results = rrf_combine([(A, 1)], [(B, 1)])
    ids = [r[0] for r in results]
    # Both appear in results even if in different lists.
    assert A in ids
    assert B in ids


def test_chunk_only_in_fts_results():
    results = rrf_combine([], [(D, 3)])
    assert results[0][0] == D


def test_ordering_by_rrf_score_descending():
    # rank 1 > rank 2 > rank 3 in score.
    vector = [(A, 1), (B, 2), (C, 3)]
    results = rrf_combine(vector, [])
    scores = [s for _, s in results]
    assert scores == sorted(scores, reverse=True)


def test_deterministic_tie_breaking():
    # A and B each appear once at rank 1 — same score, tie broken by str(uuid).
    results = rrf_combine([(A, 1)], [(B, 1)])
    ids = [r[0] for r in results]
    # Order is deterministic: str(A) < str(B) alphabetically.
    assert ids[0] == (A if str(A) < str(B) else B)
    assert ids[1] == (B if str(A) < str(B) else A)


def test_custom_k_parameter():
    k = 1
    vector = [(A, 1)]
    results = rrf_combine(vector, [], k=k)
    expected_score = 1.0 / (k + 1)
    assert abs(results[0][1] - expected_score) < 1e-10


def test_returns_all_unique_chunk_ids():
    vector = [(A, 1), (B, 2)]
    fts = [(B, 1), (C, 2), (D, 3)]
    results = rrf_combine(vector, fts)
    ids = {r[0] for r in results}
    assert ids == {A, B, C, D}
