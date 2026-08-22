"""Python client for adapters/tbc/simserver/simserver.exe - a persistent
version of `wowsimcli sim` that loads the embedded item DB once instead of
per call (see NOTES.md, "speed up the full sweep further" / simserver.exe
build). A single persistent process is inherently serial (one request line
in, one response line out) - concurrency comes from running a small POOL
of them, one per worker thread, not from pipelining one shared process.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIMSERVER_EXE = os.path.join(REPO_ROOT, "adapters", "tbc", "simserver", "simserver.exe")


class SimServerProcess:
    """One persistent simserver.exe. NOT thread-safe on its own - callers
    must serialize access to a given instance (SimServerPool does this by
    handing each instance to only one thread at a time)."""

    def __init__(self):
        self.proc = subprocess.Popen(
            [SIMSERVER_EXE],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )
        ready = self.proc.stderr.readline()
        if "ready" not in ready:
            raise RuntimeError(f"simserver failed to start: {ready!r}")

    def run(self, raid_sim_request: dict) -> dict:
        line = json.dumps(raid_sim_request, separators=(",", ":"))
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()
        out = self.proc.stdout.readline()
        if not out:
            err = self.proc.stderr.read()
            raise RuntimeError(f"simserver produced no output (process died?): {err}")
        return json.loads(out)

    def close(self):
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        self.proc.wait(timeout=5)


class SimServerPool:
    """N persistent simserver processes, checked out/in like a connection
    pool. Started lazily on first use."""

    def __init__(self, size: int):
        self.size = size
        self._servers: list[SimServerProcess] = []
        self._lock = threading.Lock()
        self._available = threading.Semaphore(0)
        self._pool: list[SimServerProcess] = []

    def _ensure_started(self):
        with self._lock:
            if self._servers:
                return
            for _ in range(self.size):
                s = SimServerProcess()
                self._servers.append(s)
                self._pool.append(s)
            self._available = threading.Semaphore(self.size)

    def run(self, raid_sim_request: dict) -> dict:
        self._ensure_started()
        self._available.acquire()
        with self._lock:
            server = self._pool.pop()
        try:
            return server.run(raid_sim_request)
        finally:
            with self._lock:
                self._pool.append(server)
            self._available.release()

    def close(self):
        for s in self._servers:
            s.close()


_default_pool: SimServerPool | None = None


def get_pool(size: int = 4) -> SimServerPool:
    global _default_pool
    if _default_pool is None:
        _default_pool = SimServerPool(size)
    return _default_pool
