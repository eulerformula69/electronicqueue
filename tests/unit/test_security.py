from app.security import get_password_hash, verify_password


def test_password_hash_and_verify_round_trip():
    password = "secret-queue-pass"
    hashed = get_password_hash(password)

    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("wrong-password", hashed)


def test_password_hash_produces_different_salts():
    password = "same-password"
    assert get_password_hash(password) != get_password_hash(password)
