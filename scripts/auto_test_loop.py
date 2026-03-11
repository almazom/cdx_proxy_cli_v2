#!/usr/bin/env python3
"""Automated testing loop for cdx proxy - runs without human intervention."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class TestResult:
    timestamp: str
    success: bool
    duration_ms: int
    error: Optional[str] = None
    response_preview: Optional[str] = None


@dataclass
class TestSession:
    start_time: str
    results: List[TestResult] = field(default_factory=list)

    def add_result(self, result: TestResult) -> None:
        self.results.append(result)

    @property
    def success_rate(self) -> float:
        if not self.results:
            return 0.0
        successes = sum(1 for r in self.results if r.success)
        return (successes / len(self.results)) * 100

    @property
    def total_tests(self) -> int:
        return len(self.results)

    @property
    def recent_errors(self) -> List[str]:
        """Get last 5 unique errors."""
        errors = []
        seen = set()
        for r in reversed(self.results):
            if r.error and r.error not in seen:
                errors.append(r.error)
                seen.add(r.error)
                if len(errors) >= 5:
                    break
        return errors


def run_codex_test(prompt: str = "say hello", timeout: int = 60) -> TestResult:
    """Run a single codex exec test."""
    start = time.time()
    timestamp = datetime.now().isoformat()

    cmd = [
        "codex", "exec",
        "-s", "danger-full-access",
        "--enable", "multi_agent",
        prompt
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        duration_ms = int((time.time() - start) * 1000)

        stdout = result.stdout or ""
        stderr = result.stderr or ""

        # Check for success indicators
        if result.returncode == 0 and "error" not in stderr.lower():
            return TestResult(
                timestamp=timestamp,
                success=True,
                duration_ms=duration_ms,
                response_preview=stdout[:200] if stdout else "OK"
            )

        # Check for specific error patterns
        error = None
        if "stream disconnected" in stderr.lower():
            error = "STREAM_DISCONNECT"
        elif "reconnecting" in stderr.lower():
            error = "RECONNECT_LOOP"
        elif "rate limit" in stderr.lower() or "429" in stderr:
            error = "RATE_LIMIT"
        elif "401" in stderr or "403" in stderr:
            error = "AUTH_ERROR"
        elif result.returncode != 0:
            error = f"EXIT_{result.returncode}"
        else:
            error = "UNKNOWN"

        return TestResult(
            timestamp=timestamp,
            success=False,
            duration_ms=duration_ms,
            error=error,
            response_preview=stderr[:200] if stderr else "No error output"
        )

    except subprocess.TimeoutExpired:
        return TestResult(
            timestamp=timestamp,
            success=False,
            duration_ms=timeout * 1000,
            error="TIMEOUT"
        )
    except Exception as exc:
        return TestResult(
            timestamp=timestamp,
            success=False,
            duration_ms=int((time.time() - start) * 1000),
            error=f"EXCEPTION: {type(exc).__name__}"
        )


def check_proxy_health() -> Dict[str, any]:
    """Check if proxy is healthy."""
    try:
        result = subprocess.run(
            ["cdx", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
        return {"healthy": False, "error": "status command failed"}
    except Exception as exc:
        return {"healthy": False, "error": str(exc)}


def print_report(session: TestSession) -> None:
    """Print current test report."""
    print("\n" + "=" * 60)
    print(f"AUTOMATED TEST REPORT | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print(f"Total tests:  {session.total_tests}")
    print(f"Success rate: {session.success_rate:.1f}%")
    print(f"Duration:     {session.start_time} -> now")

    if session.recent_errors:
        print("\nRecent error types:")
        for err in session.recent_errors:
            count = sum(1 for r in session.results if r.error == err)
            print(f"  - {err}: {count} occurrences")

    # Last 5 results
    print("\nLast 5 tests:")
    for r in session.results[-5:]:
        status = "✓" if r.success else "✗"
        error_str = f" ({r.error})" if r.error else ""
        print(f"  {status} {r.timestamp[11:19]} {error_str}")

    print("=" * 60)


def main():
    """Main automated test loop."""
    session = TestSession(start_time=datetime.now().isoformat())
    test_prompts = [
        "say hello and exit",
        "print the current date",
        "list files in current directory",
        "what is 2+2",
        "echo test",
    ]

    print("Starting automated test loop...")
    print("Press Ctrl+C to stop")
    print()

    iteration = 0
    consecutive_failures = 0

    while True:
        iteration += 1
        prompt = test_prompts[iteration % len(test_prompts)]

        # Check proxy health before test
        health = check_proxy_health()
        if not health.get("healthy"):
            print(f"[WARN] Proxy unhealthy: {health.get('error', 'unknown')}")
            time.sleep(5)
            continue

        # Run test
        result = run_codex_test(prompt=prompt)
        session.add_result(result)

        if result.success:
            consecutive_failures = 0
        else:
            consecutive_failures += 1

        # Print progress every 5 tests or on failure
        if iteration % 5 == 0 or not result.success:
            print_report(session)

        # Backoff if too many consecutive failures
        if consecutive_failures >= 3:
            print(f"[WARN] {consecutive_failures} consecutive failures, backing off...")
            time.sleep(30)
        else:
            time.sleep(2)  # Small delay between tests


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest loop stopped by user")
        sys.exit(0)
