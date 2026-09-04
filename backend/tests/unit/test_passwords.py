import pytest

from app.security.passwords import hash_password, verify_password


def test_hash_password_is_not_plaintext():
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert hashed.startswith("$2b$")


def test_verify_password_accepts_correct_password():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed) is True


def test_verify_password_rejects_wrong_password():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("wrong password", hashed) is False


def test_hash_password_rejects_overlong_input():
    too_long = "a" * 100
    with pytest.raises(ValueError):
        hash_password(too_long)


def test_verify_password_rejects_overlong_input_without_raising():
    hashed = hash_password("a normal password")
    assert verify_password("a" * 100, hashed) is False


def test_same_password_hashes_differently_each_time():
    # bcrypt salts each hash, so two hashes of the same password must differ
    # (this is what makes rainbow-table attacks against the DB infeasible).
    first = hash_password("same password")
    second = hash_password("same password")
    assert first != second
    assert verify_password("same password", first)
    assert verify_password("same password", second)
