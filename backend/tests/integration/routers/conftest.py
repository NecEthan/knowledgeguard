"""Router integration test fixtures.

Requires postgres running (docker compose up -d postgres).
MinIO and Redis are mocked per test via mock_pool / storage patches.

Fixtures are split by concern in tests/fixtures/:
  fixtures/db.py   — db session, override_db (autouse)
  fixtures/auth.py — test_user, auth_cookies, client, auth_client
  fixtures/arq.py  — mock_pool
"""
