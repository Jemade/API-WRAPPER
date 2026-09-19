"""Unit tests for security, API key hashing, and HMAC webhook verification."""

from app.core.security import (
    compute_webhook_signature,
    extract_key_prefix,
    generate_raw_api_key,
    hash_api_key,
    verify_api_key,
    verify_webhook_signature,
)


def test_api_key_generation_and_hashing() -> None:
    """Generated API keys have expected prefix and hash deterministically."""
    raw_key = generate_raw_api_key()
    assert raw_key.startswith("gw_live_")
    assert len(raw_key) > 30

    key_hash = hash_api_key(raw_key)
    assert len(key_hash) == 64  # SHA-256 produces 64-char hex string
    assert hash_api_key(raw_key) == key_hash


def test_api_key_verification() -> None:
    """API key verification succeeds with exact key and fails with modified key."""
    raw_key = generate_raw_api_key()
    key_hash = hash_api_key(raw_key)

    assert verify_api_key(raw_key, key_hash) is True
    assert verify_api_key(raw_key + "_tampered", key_hash) is False
    assert verify_api_key("gw_live_completelywrongkey", key_hash) is False


def test_key_prefix_extraction() -> None:
    """Safe key prefixes are extracted for logging and display."""
    key = "gw_live_1234567890abcdef"
    prefix = extract_key_prefix(key)
    assert prefix == "gw_live_1234..."
    assert "abcdef" not in prefix


def test_webhook_hmac_signing_and_verification() -> None:
    """HMAC-SHA256 signatures match and detect tampering."""
    secret = "my-secret-key-12345"
    payload = b'{"event":"test","data":"hello"}'

    signature = compute_webhook_signature(payload, secret)
    assert len(signature) == 64

    # Valid payload and secret
    assert verify_webhook_signature(payload, secret, signature) is True

    # Tampered payload fails
    tampered_payload = b'{"event":"test","data":"tampered"}'
    assert verify_webhook_signature(tampered_payload, secret, signature) is False

    # Wrong secret fails
    assert verify_webhook_signature(payload, "wrong-secret", signature) is False
