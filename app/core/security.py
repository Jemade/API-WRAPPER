"""Security utilities for API key generation, hashing, and HMAC webhook signing."""

import hashlib
import hmac
import secrets


def generate_raw_api_key() -> str:
    """Generate a high-entropy, prefixed API key for clients."""
    token = secrets.token_urlsafe(32)
    return f"gw_live_{token}"


def hash_api_key(raw_key: str) -> str:
    """Compute a deterministic SHA-256 hash of an API key for storage and fast indexed lookup.

    We use SHA-256 because high-entropy 256-bit random keys cannot be brute-forced
    via rainbow tables, and fast indexed lookups in PostgreSQL are required on every HTTP request.
    """
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def extract_key_prefix(raw_key: str) -> str:
    """Extract a safe prefix (e.g. 'gw_live_abcd...') for display and audit logging."""
    if len(raw_key) > 16:
        return raw_key[:12] + "..."
    return raw_key[:6] + "..."


def verify_api_key(raw_key: str, expected_hash: str) -> bool:
    """Perform constant-time comparison of hashed API key."""
    computed_hash = hash_api_key(raw_key)
    return secrets.compare_digest(computed_hash, expected_hash)


def compute_webhook_signature(payload_bytes: bytes, secret: str) -> str:
    """Compute HMAC-SHA256 signature for a webhook payload."""
    mac = hmac.new(
        key=secret.encode("utf-8"),
        msg=payload_bytes,
        digestmod=hashlib.sha256,
    )
    return mac.hexdigest()


def verify_webhook_signature(payload_bytes: bytes, secret: str, expected_signature: str) -> bool:
    """Verify HMAC-SHA256 signature using constant-time comparison."""
    computed = compute_webhook_signature(payload_bytes, secret)
    return secrets.compare_digest(computed, expected_signature)
