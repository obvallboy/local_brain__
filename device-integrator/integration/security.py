"""Signed telemetry with the ``cryptography`` library (HMAC-SHA256).

Devices sign their messages; the engine rejects anything unsigned or tampered —
defense in depth on top of the data-integrity checks. Requires ``cryptography``.
"""

from __future__ import annotations

from cryptography.hazmat.primitives import hashes, hmac


def sign(key: bytes, message: bytes) -> bytes:
    """Return the HMAC-SHA256 tag for ``message`` under ``key``."""
    h = hmac.HMAC(key, hashes.SHA256())
    h.update(message)
    return h.finalize()


def verify(key: bytes, message: bytes, signature: bytes) -> bool:
    """Constant-time verify. Returns ``False`` on any mismatch rather than raising."""
    h = hmac.HMAC(key, hashes.SHA256())
    h.update(message)
    try:
        h.verify(signature)
        return True
    except Exception:
        return False
