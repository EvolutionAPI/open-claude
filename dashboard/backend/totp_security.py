from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import struct
import time
import urllib.parse


TOTP_ISSUER = "EvoNexus"


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def provisioning_uri(secret: str, account_name: str, issuer: str = TOTP_ISSUER) -> str:
    label = urllib.parse.quote(f"{issuer}:{account_name}")
    params = urllib.parse.urlencode({
        "secret": secret,
        "issuer": issuer,
        "algorithm": "SHA1",
        "digits": 6,
        "period": 30,
    })
    return f"otpauth://totp/{label}?{params}"


def normalize_totp_code(code: str | None) -> str:
    return re.sub(r"\s+", "", str(code or "")).strip()


def _decode_secret(secret: str) -> bytes:
    normalized = re.sub(r"\s+", "", secret or "").strip().upper()
    padding = "=" * ((8 - len(normalized) % 8) % 8)
    return base64.b32decode(normalized + padding, casefold=True)


def _hotp(secret: str, counter: int, digits: int = 6) -> str:
    key = _decode_secret(secret)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(binary % (10 ** digits)).zfill(digits)


def generate_totp_code(secret: str, *, interval: int = 30, digits: int = 6, for_time: float | None = None) -> str:
    now = for_time if for_time is not None else time.time()
    counter = int(now // interval)
    return _hotp(secret, counter, digits=digits)


def verify_totp_code(
    secret: str,
    code: str | None,
    *,
    interval: int = 30,
    digits: int = 6,
    window: int = 1,
    last_used_step: int | None = None,
    for_time: float | None = None,
) -> dict[str, object]:
    normalized = normalize_totp_code(code)
    if not normalized.isdigit() or len(normalized) != digits:
        return {"valid": False, "step": None}

    now = for_time if for_time is not None else time.time()
    current_step = int(now // interval)
    for step in range(current_step - window, current_step + window + 1):
        if last_used_step is not None and step <= last_used_step:
            continue
        if _hotp(secret, step, digits=digits) == normalized:
            return {"valid": True, "step": step}
    return {"valid": False, "step": None}
