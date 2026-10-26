import pytest

from app.services.auth import hash_password, verify_password


async def test_hash_password_produces_bcrypt_hash():
    result = await hash_password("password123")
    assert result.startswith("$2b$")


async def test_verify_password_correct():
    hashed = await hash_password("password123")
    assert await verify_password("password123", hashed) is True


async def test_verify_password_wrong():
    hashed = await hash_password("password123")
    assert await verify_password("wrongpassword", hashed) is False


async def test_hash_is_unique_per_call():
    assert await hash_password("same") != await hash_password("same")
