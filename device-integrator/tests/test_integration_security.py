import pytest

pytest.importorskip("cryptography")  # runs in CI where cryptography is installed

from integration.security import sign, verify  # noqa: E402


def test_sign_verify_roundtrip():
    key = b"a-shared-device-key-0123456789ab"
    msg = b'{"device":"temp-01","tempC":25.4}'
    sig = sign(key, msg)
    assert verify(key, msg, sig) is True


def test_tampered_message_fails():
    key = b"a-shared-device-key-0123456789ab"
    sig = sign(key, b'{"tempC":25.4}')
    assert verify(key, b'{"tempC":999.0}', sig) is False   # payload changed
    assert verify(b"the-wrong-key-000000000000000000", b'{"tempC":25.4}', sig) is False
