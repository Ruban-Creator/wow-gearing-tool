"""Python client for adapters/tbc/simserver/simserver.exe - a persistent
version of `wowsimcli sim` that loads the embedded item DB once instead of
per call (see NOTES.md, "speed up the full sweep further" / simserver.exe
build). A single persistent process is inherently serial (one request line
in, one response line out) - concurrency comes from running a small POOL
of them, one per worker thread, not from pipelining one shared process.
"""
from __future__ import annotations

import collections
import json
import os
import subprocess
import sys
import threading

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIMSERVER_EXE = os.path.join(REPO_ROOT, "adapters", "tbc", "simserver", "simserver.exe")

# See valuation.py's own copy of this comment - the packaged (windowed,
# console-less) GUI has nowhere to attach a child console, so Windows pops
# a new visible one for every subprocess call here unless told not to.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


class SimServerProcess:
    """One persistent simserver.exe. NOT thread-safe on its own - callers
    must serialize access to a given instance (SimServerPool does this by
    handing each instance to only one thread at a time)."""

    def __init__(self):
        self.proc = subprocess.Popen(
            [SIMSERVER_EXE],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1, creationflags=_NO_WINDOW,
        )
        ready = self.proc.stderr.readline()
        if "ready" not in ready:
            raise RuntimeError(f"simserver failed to start: {ready!r}")
        # Real root cause of the "dies/hangs at exactly call #34" bug (found
        # 2026-08-24 via a live goroutine dump, not guessed - see NOTES.md):
        # simserver.exe logs 2 lines per call ("Running N iterations...",
        # "All N sims finished successfully.") to stderr via Go's log
        # package. Nothing here ever read stderr after the startup line, so
        # the Windows anonymous pipe's small buffer filled after ~33 calls'
        # worth of log lines, and the child process blocked forever inside
        # log.Printf's own blocking write once the buffer was full - NOT a
        # resource exhaustion in the sim engine itself. This thread keeps
        # the pipe drained for the process's whole lifetime; the last 200
        # lines are kept (bounded, so a long-lived process's memory doesn't
        # grow unbounded) in case a real crash still needs reporting.
        self._stderr_tail = collections.deque(maxlen=200)
        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stderr_thread.start()

    def _drain_stderr(self):
        try:
            for line in self.proc.stderr:
                self._stderr_tail.append(line)
        except (ValueError, OSError):
            pass  # stream closed as the process exits - not an error here

    def run(self, raid_sim_request: dict) -> dict:
        line = json.dumps(raid_sim_request, separators=(",", ":"))
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()
        out = self.proc.stdout.readline()
        if not out:
            err = "".join(self._stderr_tail)
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
        """Self-healing: if the checked-out process has died (see NOTES.md,
        the overnight "simserver.exe crashes under sustained load" finding -
        confirmed not tied to a specific request, cause still unknown), a
        dead SimServerProcess left in rotation would fail EVERY future
        request through it forever, not just the one that killed it.
        Replaces it with a freshly-spawned process and retries once before
        giving up, so a single process death degrades to "one slow request"
        instead of silently wrecking the rest of a multi-hour run."""
        self._ensure_started()
        self._available.acquire()
        with self._lock:
            server = self._pool.pop()
        try:
            try:
                return server.run(raid_sim_request)
            except RuntimeError:
                server = SimServerProcess()  # replaces the dead one below
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
