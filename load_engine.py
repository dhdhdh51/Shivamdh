"""Bounded UDP game-server load simulation engine."""

from __future__ import annotations

import socket
import threading
import time
from dataclasses import dataclass

MAX_PPS = 200
MAX_DURATION_SECONDS = 600
MAX_TOTAL_PACKETS = 24_000
PACKET_SIZE = 64


@dataclass(frozen=True)
class LoadSnapshot:
    running: bool
    elapsed_seconds: float
    remaining_seconds: float
    packets_sent: int
    send_errors: int
    actual_pps: float


class UdpLoadTest:
    """Send a small, recognizable UDP probe at a bounded rate."""

    def __init__(self, target: str, port: int, pps: int, duration: int) -> None:
        if not 1 <= port <= 65535:
            raise ValueError("Port must be between 1 and 65535.")
        if not 1 <= pps <= MAX_PPS:
            raise ValueError(f"PPS must be between 1 and {MAX_PPS}.")
        if not 1 <= duration <= MAX_DURATION_SECONDS:
            raise ValueError(
                f"Duration must be between 1 and {MAX_DURATION_SECONDS} seconds."
            )
        if pps * duration > MAX_TOTAL_PACKETS:
            max_duration = MAX_TOTAL_PACKETS // pps
            raise ValueError(
                f"This rate allows at most {max_duration} seconds "
                f"({MAX_TOTAL_PACKETS} packets total)."
            )

        self.target = target
        self.port = port
        self.pps = pps
        self.duration = duration
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._started_at = 0.0
        self._finished_at = 0.0
        self._packets_sent = 0
        self._send_errors = 0

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> LoadSnapshot:
        resolved_ip = socket.gethostbyname(self.target)
        interval = 1.0 / self.pps
        payload = b"GAME_LOAD_TEST_V1".ljust(PACKET_SIZE, b"\0")
        self._started_at = time.monotonic()
        deadline = self._started_at + self.duration
        next_send = self._started_at

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            while not self._stop_event.is_set():
                now = time.monotonic()
                if now >= deadline:
                    break
                if now < next_send:
                    self._stop_event.wait(min(next_send - now, 0.05))
                    continue

                try:
                    sock.sendto(payload, (resolved_ip, self.port))
                    with self._lock:
                        self._packets_sent += 1
                except OSError:
                    with self._lock:
                        self._send_errors += 1

                # Never burst to catch up after the process is paused.
                next_send = max(next_send + interval, time.monotonic())

        self._finished_at = time.monotonic()
        return self.snapshot()

    def snapshot(self) -> LoadSnapshot:
        now = time.monotonic()
        if not self._started_at:
            elapsed = 0.0
            running = False
        else:
            end = self._finished_at or now
            elapsed = min(end - self._started_at, float(self.duration))
            running = not self._finished_at and not self._stop_event.is_set()

        with self._lock:
            sent = self._packets_sent
            errors = self._send_errors

        return LoadSnapshot(
            running=running,
            elapsed_seconds=max(0.0, elapsed),
            remaining_seconds=max(0.0, self.duration - elapsed),
            packets_sent=sent,
            send_errors=errors,
            actual_pps=sent / elapsed if elapsed > 0 else 0.0,
        )
