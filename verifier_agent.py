"""Run this small proof-of-control agent on each authorized game server."""

from __future__ import annotations

import logging
import os
import socket

from dotenv import load_dotenv

from target_verification import (
    DEFAULT_VERIFIER_PORT,
    REQUEST_PREFIX,
    RESPONSE_PREFIX,
    create_proof,
)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
)
LOGGER = logging.getLogger(__name__)


def main() -> None:
    load_dotenv()
    secret = os.getenv("VERIFICATION_SECRET", "").strip()
    port = int(os.getenv("VERIFIER_PORT", str(DEFAULT_VERIFIER_PORT)))
    if len(secret) < 32 or secret == "replace-with-a-long-random-secret":
        raise SystemExit("VERIFICATION_SECRET must be a random value of at least 32 characters.")
    if not 1 <= port <= 65535:
        raise SystemExit("VERIFIER_PORT must be between 1 and 65535.")

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("0.0.0.0", port))
        LOGGER.info("Verification agent listening on UDP %d", port)
        while True:
            payload, address = sock.recvfrom(512)
            if not payload.startswith(REQUEST_PREFIX):
                continue
            nonce = payload[len(REQUEST_PREFIX):]
            if not nonce or len(nonce) > 128:
                continue
            sock.sendto(RESPONSE_PREFIX + create_proof(secret, nonce), address)


if __name__ == "__main__":
    main()
