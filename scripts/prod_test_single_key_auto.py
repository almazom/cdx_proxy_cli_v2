#!/usr/bin/env python3
"""Automated production test: Run codex exec with proxy and single key.

This script:
1. Starts the proxy server (if not running)
2. Blacklists all but one auth key (auto-selects first key)
3. Runs codex exec in headless mode 3 times
4. Monitors trace/events
5. Reports observations
6. Restores keys
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def get_auth_dir() -> Path:
    """Get auth directory from environment or default."""
    return Path(os.environ.get("CLIPROXY_AUTH_DIR", Path.home() / ".codex" / "_auths"))


def load_auth_files(auth_dir: Path) -> List[Dict[str, Any]]:
    """Load all auth files."""
    auths = []
    for auth_file in auth_dir.glob("*.json"):
        if (
            auth_file.name.startswith(".")
            or "state" in auth_file.name
            or "pid" in auth_file.name
        ):
            continue
        try:
            data = json.loads(auth_file.read_text())
            auths.append(
                {
                    "file": auth_file.name,
                    "email": data.get("email", "unknown"),
                    "token_present": bool(data.get("access_token")),
                }
            )
        except Exception as e:
            print(f"⚠️  Failed to load {auth_file.name}: {e}")
    return auths


def blacklist_keys(auth_dir: Path, exclude: str) -> List[str]:
    """Move all keys except 'exclude' to .blacklisted suffix."""
    blacklisted = []
    for auth_file in auth_dir.glob("*.json"):
        if auth_file.name == exclude or auth_file.name.startswith("."):
            continue
        if "state" in auth_file.name or "pid" in auth_file.name:
            continue

        blacklisted_name = auth_file.name.replace(".json", ".blacklisted.json")
        blacklisted_path = auth_dir / blacklisted_name

        try:
            auth_file.rename(blacklisted_path)
            blacklisted.append(auth_file.name)
            print(f"  ⚫  Blacklisted: {auth_file.name}")
        except Exception as e:
            print(f"  ⚠️  Failed to blacklist {auth_file.name}: {e}")

    return blacklisted


def restore_keys(auth_dir: Path, blacklisted: List[str]) -> None:
    """Restore blacklisted keys."""
    for name in blacklisted:
        blacklisted_name = name.replace(".json", ".blacklisted.json")
        blacklisted_path = auth_dir / blacklisted_name
        original_path = auth_dir / name

        try:
            if blacklisted_path.exists():
                blacklisted_path.rename(original_path)
                print(f"  ⚪  Restored: {name}")
        except Exception as e:
            print(f"  ⚠️  Failed to restore {name}: {e}")


def check_proxy_running() -> Optional[Dict[str, Any]]:
    """Check if proxy is running."""
    auth_dir = get_auth_dir()
    pid_file = auth_dir / "rr_proxy_v2.pid"

    if not pid_file.exists():
        return None

    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 0)  # Check if process exists

        # Get health
        health = get_proxy_health()
        return {"pid": pid, "health": health}
    except (ProcessLookupError, ValueError):
        pass

    return None


def start_proxy() -> Optional[Dict[str, Any]]:
    """Start proxy server if not running."""
    existing = check_proxy_running()
    if existing:
        print(f"✅ Proxy already running (PID {existing['pid']})")
        return existing

    print("🚀 Starting proxy server...")

    subprocess.Popen(
        ["cdx", "proxy"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid,
    )

    time.sleep(3)

    state = check_proxy_running()
    if state:
        print(f"✅ Proxy started (PID {state['pid']})")
        return state

    print("⚠️  Proxy may not have started correctly")
    return None


def run_codex_exec(
    prompt: str = "Say hello in one word",
) -> subprocess.CompletedProcess:
    """Run codex exec in headless mode."""
    print(f"  💬 codex exec '{prompt}'")

    result = subprocess.run(
        ["codex", "exec", prompt],
        capture_output=True,
        text=True,
        timeout=60,
    )

    return result


def get_proxy_health() -> Optional[Dict[str, Any]]:
    """Get proxy health status."""
    import http.client

    # Get port from cdx status
    try:
        result = subprocess.run(
            ["cdx", "status", "--json"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            status = json.loads(result.stdout)
            port = status.get("port", 8080)
            mgmt_key = os.environ.get("CLIPROXY_MANAGEMENT_KEY", "")

            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            conn.request("GET", "/health", headers={"X-Management-Key": mgmt_key})
            response = conn.getresponse()

            if response.status == 200:
                return json.loads(response.read().decode())
    except Exception:
        pass

    return None


def get_trace_events(limit: int = 20) -> List[Dict[str, Any]]:
    """Get recent trace events."""
    import http.client

    # Get port from cdx status
    try:
        result = subprocess.run(
            ["cdx", "status", "--json"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            status = json.loads(result.stdout)
            port = status.get("port", 8080)
            mgmt_key = os.environ.get("CLIPROXY_MANAGEMENT_KEY", "")

            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            conn.request(
                "GET", f"/trace?limit={limit}", headers={"X-Management-Key": mgmt_key}
            )
            response = conn.getresponse()

            if response.status == 200:
                data = json.loads(response.read().decode())
                return data.get("events", [])
    except Exception:
        pass

    return []


def print_health(health: Optional[Dict[str, Any]]) -> None:
    """Print health status."""
    if not health:
        print("❌ Proxy health: UNREACHABLE")
        return

    print("\n  ┌" + "─" * 56 + "┐")
    print("  │ 📊 PROXY HEALTH STATUS" + " " * 31 + "│")
    print("  ├" + "─" * 56 + "┤")

    accounts = health.get("accounts", [])
    for acc in accounts:
        status = acc.get("status", "UNK")
        email = (acc.get("email") or acc.get("file") or "unknown")[:25]
        acc.get("file", "unknown")[:20]

        status_icon = {
            "OK": "🟢",
            "COOLDOWN": "🟡",
            "BLACKLIST": "⚫",
            "PROBATION": "🟣",
        }.get(status, "⚪")
        print(f"  │ {status_icon} {email:25} {status:12} │")

    print("  └" + "─" * 56 + "┘\n")


def print_trace(events: List[Dict[str, Any]]) -> None:
    """Print recent trace events."""
    if not events:
        print("  📭 No trace events")
        return

    print("  ┌" + "─" * 56 + "┐")
    print("  │ 📈 RECENT TRACE EVENTS" + " " * 33 + "│")
    print("  ├" + "─" * 56 + "┤")

    for event in events[-8:]:
        event_type = event.get("event", "unknown")[:20]
        message = (event.get("message") or "")[:30]
        status = event.get("status", "")

        icon = "📝"
        if "blacklist" in event_type:
            icon = "⚫"
        elif "heal" in event_type:
            icon = "💚"
        elif "cooldown" in event_type:
            icon = "🟡"
        elif "exhausted" in event_type:
            icon = "🔴"
        elif status and int(status) < 400:
            icon = "🟢"
        elif status:
            icon = "🔴"

        print(f"  │ {icon} {event_type:20} {message:30} │")

    print("  └" + "─" * 56 + "┘\n")


def main() -> int:
    """Main test runner."""
    print("\n" + "=" * 60)
    print("🧪 PRODUCTION TEST: Auto-Heal with Single Available Key")
    print("=" * 60 + "\n")

    auth_dir = get_auth_dir()
    print(f"📁 Auth directory: {auth_dir}\n")

    # Load auth files
    auths = load_auth_files(auth_dir)
    if len(auths) < 2:
        print(f"❌ Need at least 2 auth keys, found {len(auths)}")
        return 1

    print(f"📦 Found {len(auths)} auth keys:\n")
    for i, auth in enumerate(auths):
        icon = "🔑"
        email_display = auth.get("email", "unknown")[:30]
        print(f"  [{i + 1}] {icon} {email_display:30} ({auth['file']})")
    print()

    # Auto-select first key
    active_key = auths[0]["file"]
    print(f"✅ Auto-selected active key: {active_key}\n")

    # Start proxy
    proxy_state = start_proxy()
    if not proxy_state:
        print("❌ Could not start proxy")
        print("   Run: cdx proxy")
        return 1

    # Blacklist all other keys
    print("\n⚫  Blacklisting keys...")
    blacklisted = blacklist_keys(auth_dir, active_key)
    print(f"⚫  Blacklisted {len(blacklisted)} keys\n")

    # Wait for proxy to reload
    print("⏳ Waiting for proxy to detect changes...")
    time.sleep(2)

    # Check health
    print("\n📊 Initial health check:")
    health = get_proxy_health()
    print_health(health)

    # Run codex exec multiple times
    print("\n" + "=" * 60)
    print("🚀 RUNNING CODEX EXEC TESTS")
    print("=" * 60 + "\n")

    test_prompts = [
        "Say hello in one word",
        "What is 2+2? Answer with number only",
        "Name one color",
    ]

    results = []
    for i, prompt in enumerate(test_prompts, 1):
        print(f"[Test {i}/{len(test_prompts)}]")

        try:
            result = run_codex_exec(prompt)

            success = result.returncode == 0
            results.append(
                {
                    "prompt": prompt,
                    "success": success,
                    "returncode": result.returncode,
                }
            )

            if success:
                print(f"  ✅ SUCCESS (exit code {result.returncode})")
                first_line = (
                    result.stdout.splitlines()[0] if result.stdout else "(no output)"
                )
                print(f"     Output: {first_line[:60]}")
            else:
                print(f"  ❌ FAILED (exit code {result.returncode})")
                if result.stderr:
                    print(f"     Error: {result.stderr[:100]}")

        except subprocess.TimeoutExpired:
            print("  ⏱️  TIMEOUT (>60s)")
            results.append(
                {
                    "prompt": prompt,
                    "success": False,
                    "returncode": -1,
                    "error": "timeout",
                }
            )
        except KeyboardInterrupt:
            print("\n⚠️  Interrupted")
            break
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            results.append(
                {"prompt": prompt, "success": False, "returncode": -1, "error": str(e)}
            )

        time.sleep(1)

    # Final health check
    print("\n\n📊 Final health check:")
    health = get_proxy_health()
    print_health(health)

    # Show trace
    print("📈 Recent trace events:")
    trace = get_trace_events()
    print_trace(trace)

    # Summary
    print("\n" + "=" * 60)
    print("📋 TEST SUMMARY")
    print("=" * 60)

    success_count = sum(1 for r in results if r["success"])
    total = len(results)

    print(
        f"\nTests: {success_count}/{total} passed ({100 * success_count / total:.0f}%)"
        if total > 0
        else "No tests run"
    )

    for i, r in enumerate(results, 1):
        icon = "✅" if r["success"] else "❌"
        print(f"  {icon} Test {i}: {r['prompt'][:50]}")

    # Restore keys
    print("\n" + "=" * 60)
    print("🔄 RESTORING KEYS")
    print("=" * 60 + "\n")

    restore_keys(auth_dir, blacklisted)
    print(f"✅ Restored {len(blacklisted)} keys")

    # Final observation
    print("\n" + "=" * 60)
    print("🔍 OBSERVATIONS")
    print("=" * 60)

    if health:
        accounts = health.get("accounts", [])
        ok_count = sum(1 for a in accounts if a.get("status") == "OK")
        blacklist_count = sum(1 for a in accounts if a.get("status") == "BLACKLIST")

        print(f"\n  • Active keys at end: {ok_count}")
        print(f"  • Blacklisted keys: {blacklist_count}")

        if ok_count == 1:
            print("  ✅ System correctly used single available key")
        elif ok_count == 0:
            print("  ⚠️  No keys available - active key may have been exhausted")
        else:
            print(f"  ℹ️  {ok_count} keys available - auto-heal may have restored some")

    # Check for auto-heal events
    heal_events = [e for e in trace if "auto_heal" in e.get("event", "")]
    if heal_events:
        print(f"\n  💚 Auto-heal events: {len(heal_events)}")
        for e in heal_events[-3:]:
            msg = (e.get("event") or "") + ": " + (e.get("message") or "")[:50]
            print(f"     • {msg}")

    # Key insight
    print("\n" + "=" * 60)
    if success_count > 0:
        print("✅ CONCLUSION: System works with single available key!")
    else:
        print("⚠️  CONCLUSION: Tests failed - review trace events")
    print("=" * 60 + "\n")

    return 0 if success_count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
