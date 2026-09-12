import pytest

from app.crypto import CredentialDecryptionError, decrypt_credential, encrypt_credential


def test_encrypt_then_decrypt_round_trips():
    token = encrypt_credential("sk_live_real_looking_secret_value")
    assert decrypt_credential(token) == "sk_live_real_looking_secret_value"


def test_encrypted_value_does_not_contain_the_plaintext():
    token = encrypt_credential("a-very-specific-secret-string")
    assert b"a-very-specific-secret-string" not in token


def test_a_corrupted_token_fails_to_decrypt():
    token = encrypt_credential("x")
    corrupted = token[:-4] + b"gggg"
    with pytest.raises(CredentialDecryptionError):
        decrypt_credential(corrupted)
