"""ARQ pool fixtures for router integration tests."""

from unittest.mock import AsyncMock

import pytest

from app.dependencies import get_arq_pool
from app.main import app


@pytest.fixture(autouse=True)
def _arq_app_state():
    """Set app.state.arq_pool so get_arq_pool doesn't crash (lifespan doesn't run in tests)."""
    pool = AsyncMock()
    pool.enqueue_job = AsyncMock(return_value=None)
    app.state.arq_pool = pool
    yield
    try:
        del app.state._state["arq_pool"]
    except KeyError:
        pass


@pytest.fixture
def mock_pool():
    """Override the arq_pool dependency for tests that assert on enqueue_job calls."""
    pool = AsyncMock()
    pool.enqueue_job = AsyncMock(return_value=None)
    app.dependency_overrides[get_arq_pool] = lambda: pool
    yield pool
    app.dependency_overrides.pop(get_arq_pool, None)
