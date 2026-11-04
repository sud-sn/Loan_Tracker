"""Application-level encryption (PRD section 12).

Aadhaar numbers (and TOTP secrets) are encrypted with AES-256-GCM using a fresh data key per
record. The data key is wrapped by a master key from the keyring file, which lives outside the
data and backup folders. Rotation adds a new master key and re-wraps the data keys; record
ciphertexts never change.

Blob layout: ``b"LT1" | kid_len (1) | kid | wrap_nonce (12) | wrapped_dek (48) | nonce (12) | ct``
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import get_settings

MAGIC = b"LT1"


class KeyringError(RuntimeError):
    pass


@dataclass(frozen=True)
class Keyring:
    active: str
    keys: dict[str, bytes]

    @classmethod
    def load(cls, path: Path) -> Keyring:
        try:
            raw = json.loads(path.read_text())
        except FileNotFoundError as exc:
            raise KeyringError(f"keyring file not found at {path}; run `python -m app.cli init-secrets`") from exc
        keys = {kid: base64.b64decode(val) for kid, val in raw["keys"].items()}
        if raw["active"] not in keys or any(len(k) != 32 for k in keys.values()):
            raise KeyringError("keyring is invalid: active key missing or a key is not 32 bytes")
        return cls(active=raw["active"], keys=keys)

    @staticmethod
    def generate(kid: str | None = None) -> dict[str, object]:
        kid = kid or f"k{secrets.token_hex(4)}"
        return {"active": kid, "keys": {kid: base64.b64encode(AESGCM.generate_key(bit_length=256)).decode()}}


@lru_cache
def keyring() -> Keyring:
    return Keyring.load(get_settings().keyring_file)


def encrypt(plaintext: str, purpose: bytes, ring: Keyring | None = None) -> bytes:
    ring = ring or keyring()
    kid = ring.active.encode()
    dek = AESGCM.generate_key(bit_length=256)
    wrap_nonce, nonce = os.urandom(12), os.urandom(12)
    wrapped = AESGCM(ring.keys[ring.active]).encrypt(wrap_nonce, dek, b"dek|" + purpose)
    ct = AESGCM(dek).encrypt(nonce, plaintext.encode(), purpose)
    return MAGIC + bytes([len(kid)]) + kid + wrap_nonce + wrapped + nonce + ct


def _split(blob: bytes) -> tuple[str, bytes, bytes, bytes, bytes]:
    if not blob.startswith(MAGIC):
        raise KeyringError("unknown ciphertext format")
    n = blob[3]
    kid = blob[4 : 4 + n].decode()
    rest = blob[4 + n :]
    return kid, rest[:12], rest[12:60], rest[60:72], rest[72:]


def decrypt(blob: bytes, purpose: bytes, ring: Keyring | None = None) -> str:
    ring = ring or keyring()
    kid, wrap_nonce, wrapped, nonce, ct = _split(blob)
    if kid not in ring.keys:
        raise KeyringError(f"master key {kid} is not in the keyring")
    dek = AESGCM(ring.keys[kid]).decrypt(wrap_nonce, wrapped, b"dek|" + purpose)
    return AESGCM(dek).decrypt(nonce, ct, purpose).decode()


def rewrap(blob: bytes, purpose: bytes, ring: Keyring | None = None) -> bytes:
    """Re-wrap the data key under the active master key (key rotation)."""
    ring = ring or keyring()
    kid, wrap_nonce, wrapped, nonce, ct = _split(blob)
    if kid == ring.active:
        return blob
    dek = AESGCM(ring.keys[kid]).decrypt(wrap_nonce, wrapped, b"dek|" + purpose)
    new_kid = ring.active.encode()
    new_nonce = os.urandom(12)
    new_wrapped = AESGCM(ring.keys[ring.active]).encrypt(new_nonce, dek, b"dek|" + purpose)
    return MAGIC + bytes([len(new_kid)]) + new_kid + new_nonce + new_wrapped + nonce + ct


def key_id(blob: bytes) -> str:
    return _split(blob)[0]


AADHAAR = b"aadhaar"
TOTP = b"totp"


def aadhaar_hmac(number: str) -> bytes:
    """Keyed hash used only to detect duplicates; its secret is separate from the master key."""
    secret = get_settings().aadhaar_hmac_secret
    if len(secret) < 32:
        raise KeyringError("LT_AADHAAR_HMAC_SECRET must be set (at least 32 characters)")
    return hmac.new(secret.encode(), number.encode(), hashlib.sha256).digest()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
