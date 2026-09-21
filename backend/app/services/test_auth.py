from app.services.auth import hash_password, verify_password


def test_hash_password_produces_bcrypt_hash():
    assert hash_password("password123").startswith("$2b$")


def test_verify_password_correct():
    hashed = hash_password("password123")
    assert verify_password("password123", hashed) is True


def test_verify_password_wrong():
    hashed = hash_password("password123")
    assert verify_password("wrongpassword", hashed) is False


def test_hash_is_unique_per_call():
    assert hash_password("same") != hash_password("same")
