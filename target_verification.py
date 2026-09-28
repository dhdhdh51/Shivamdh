"""Proof-of-control verification and persistent target registry."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import socket
import tempfile
from pathlib import Path

REQUEST_PREFIX = b"GAME_LOAD_VERIFY_V1:"
RESPONSE_PREFIX = b"GAME_LOAD_PROOF_V1:"
DEFAULT_VERIFIER_PORT = 39001
REGISTRY_PATH = Path(".authorized_targets.json")


def create_proof(secret: str, nonce: bytes) -> bytes:
    return hmac.new(secret.encode(), nonce, hashlib.sha256).hexdigest().encode()


def verify_target(target: str, secret: str, port: int, timeout: float = 3.0) -> bool:
    """Verify that an agent possessing the shared secret controls target."""
    resolved_ip = socket.gethostbyname(target)
    nonce = secrets.token_hex(16).encode()
    request = REQUEST_PREFIX + nonce
    expected = RESPONSE_PREFIX + create_proof(secret, nonce)

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(request, (resolved_ip, port))
        response, address = sock.recvfrom(512)
    return address[0] == resolved_ip and hmac.compare_digest(response, expected)


def load_verified_targets() -> set[str]:
    try:
        data = json.loads(REGISTRY_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return set()
    return {str(item).strip().lower() for item in data if str(item).strip()}


def save_verified_target(target: str) -> None:
    targets = sorted(load_verified_targets() | {target.strip().lower()})
    fd, temporary = tempfile.mkstemp(prefix=".targets-", dir=REGISTRY_PATH.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(targets, handle, indent=2)
            handle.write("\n")
        os.replace(temporary, REGISTRY_PATH)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
