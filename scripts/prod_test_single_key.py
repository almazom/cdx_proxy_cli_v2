#!/usr/bin/env python3
"""Manual production test: Run codex exec with proxy and observe auto-heal behavior.

This script:
1. Starts the proxy server
2. Blacklists all but one auth key
3. Runs codex exec in headless mode
4. Monitors trace/events in real-time
5. Reports observations
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
        if auth_file.name.startswith("."):
            continue
        try:
            data = json.loads(auth_file.read_text())
            auths.append({
                "file": auth_file.name,
                "email": data.get("email", "unknown"),
                "token": data.get("access_token", "")[:20] + "...",
            })
        except Exception as e:
            print(f"⚠️  Failed to load {auth_file.name}: {e}")
    return auths


def blacklist_keys(auth_dir: Path, exclude: str) -> List[str]:
    """Move all keys except 'exclude' to blacklist state.
    
    We do this by adding a .blacklisted suffix to the filename.
    The proxy will skip these files.
    """
    blacklisted = []
    for auth_file in auth_dir.glob("*.json"):
        if auth_file.name == exclude or auth_file.name.startswith("."):
            continue
        
        # Rename to .blacklisted.json
        blacklisted_name = auth_file.name.replace(".json", ".blacklisted.json")
        blacklisted_path = auth_dir / blacklisted_name
        
        try:
            auth_file.rename(blacklisted_path)
            blacklisted.append(auth_file.name)
            print(f"⚫  Blacklisted: {auth_file.name} → {blacklisted_name}")
        except Exception as e:
            print(f"⚠️  Failed to blacklist {auth_file.name}: {e}")
    
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
                print(f"⚪  Restored: {blacklisted_name} → {name}")
        except Exception as e:
            print(f"⚠️  Failed to restore {name}: {e}")


def check_proxy_running() -> Optional[Dict[str, Any]]:
    """Check if proxy is running."""
    auth_dir = get_auth_dir()
    state_file = auth_dir / "rr_proxy_v2.state.json"
    pid_file = auth_dir / "rr_proxy_v2.pid"
    
    if not pid_file.exists():
        return None
    
    try:
        pid = int(pid_file.read_text().strip())
        # Check if process exists
        os.kill(pid, 0)
        
        if state_file.exists():
            state = json.loads(state_file.read_text())
            state["pid"] = pid
            return state
    except (ProcessLookupError, ValueError, json.JSONDecodeError):
        pass
    
    return None


def start_proxy() -> Optional[Dict[str, Any]]:
    """Start proxy server if not running."""
    # Check if already running
    existing = check_proxy_running()
    if existing:
        print(f"✅ Proxy already running (PID {existing['pid']})")
        return existing
    
    print("🚀 Starting proxy server...")
    
    # Start proxy in background
    subprocess.Popen(
        ["cdx", "proxy"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid,
    )
    
    # Wait for proxy to start
    time.sleep(3)
    
    # Verify it's running
    state = check_proxy_running()
    if state:
        print(f"✅ Proxy started (PID {state['pid']})")
        return state
    
    print("⚠️  Proxy may not have started correctly")
    return None


def run_codex_exec(prompt: str = "Say hello in one word") -> subprocess.CompletedProcess:
    """Run codex exec in headless mode."""
    print(f"💬 Running codex exec: '{prompt}'")
    
    result = subprocess.run(
        ["codex", "-p", prompt],
        capture_output=True,
        text=True,
        timeout=60,
    )
    
    return result


def get_proxy_health(base_url: str = "http://127.0.0.1:8080") -> Optional[Dict[str, Any]]:
    """Get proxy health status."""
    import http.client
    
    try:
        conn = http.client.HTTPConnection("127.0.0.1", 8080, timeout=2)
        conn.request("GET", "/health", headers={"X-Management-Key": os.environ.get("CLIPROXY_MANAGEMENT_KEY", "")})
        response = conn.getresponse()
        
        if response.status == 200:
            return json.loads(response.read().decode())
    except Exception:
        pass
    
    return None


def get_trace_events(limit: int = 20) -> List[Dict[str, Any]]:
    """Get recent trace events."""
    import http.client
    
    try:
        conn = http.client.HTTPConnection("127.0.0.1", 8080, timeout=2)
        mgmt_key = os.environ.get("CLIPROXY_MANAGEMENT_KEY", "")
        conn.request("GET", f"/trace?limit={limit}", headers={"X-Management-Key": mgmt_key})
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
    
    print("\n" + "=" * 60)
    print("📊 PROXY HEALTH STATUS")
    print("=" * 60)
    
    accounts = health.get("accounts", [])
    for acc in accounts:
        status = acc.get("status", "UNKNOWN")
        email = acc.get("email", "unknown")
        file = acc.get("file", "unknown")
        
        status_icon = {"OK": "🟢", "COOLDOWN": "🟡", "BLACKLIST": "⚫", "PROBATION": "🟣"}.get(status, "⚪")
        print(f"  {status_icon} {email:30} {status:12} ({file})")
    
    print("=" * 60 + "\n")


def print_trace(events: List[Dict[str, Any]]) -> None:
    """Print recent trace events."""
    if not events:
        print("📭 No trace events")
        return
    
    print("\n" + "=" * 60)
    print("📈 RECENT TRACE EVENTS")
    print("=" * 60)
    
    for event in events[-10:]:  # Last 10 events
        ts = event.get("ts", "")
        event_type = event.get("event", "unknown")
        message = event.get("message", "")
        status = event.get("status", "")
        
        # Icon by event type
        icon = "📝"
        if "blacklist" in event_type:
            icon = "⚫"
        elif "heal" in event_type:
            icon = "💚"
        elif "cooldown" in event_type:
            icon = "🟡"
        elif "exhausted" in event_type:
            icon = "🔴"
        elif status:
            icon = "🟢" if int(status) < 400 else "🔴"
        
        print(f"  {icon} [{ts}] {event_type}: {message}")
    
    print("=" * 60 + "\n")


def main() -> int:
    """Main test runner."""
    print("\n" + "=" * 60)
    print("🧪 PRODUCTION TEST: Auto-Heal with Single Available Key")
    print("=" * 60 + "\n")
    
    auth_dir = get_auth_dir()
    print(f"📁 Auth directory: {auth_dir}")
    
    # Load auth files
    auths = load_auth_files(auth_dir)
    if len(auths) < 2:
        print("❌ Need at least 2 auth keys for this test")
        return 1
    
    print(f"📦 Found {len(auths)} auth keys:\n")
    for auth in auths:
        print(f"  • {auth['email']:30} ({auth['file']})")
    print()
    
    # Choose which key to keep active
    print("Which key should remain active?")
    for i, auth in enumerate(auths):
        print(f"  [{i + 1}] {auth['email']}")
    
    try:
        choice = int(input("\nEnter choice (1-based): ")) - 1
        if not 0 <= choice < len(auths):
            print("❌ Invalid choice")
            return 1
    except (ValueError, KeyboardInterrupt):
        print("\n❌ Cancelled")
        return 1
    
    active_key = auths[choice]["file"]
    print(f"\n✅ Keeping active: {active_key}")
    
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
        print(f"\n[Test {i}/{len(test_prompts)}]")
        
        try:
            result = run_codex_exec(prompt)
            
            success = result.returncode == 0
            results.append({
                "prompt": prompt,
                "success": success,
                "returncode": result.returncode,
                "stdout_lines": len(result.stdout.splitlines()),
                "stderr_lines": len(result.stderr.splitlines()),
            })
            
            if success:
                print(f"✅ SUCCESS (exit code {result.returncode})")
                # Show first line of output
                first_line = result.stdout.splitlines()[0] if result.stdout else "(no output)"
                print(f"   Output: {first_line[:80]}")
            else:
                print(f"❌ FAILED (exit code {result.returncode})")
                if result.stderr:
                    print(f"   Error: {result.stderr[:200]}")
        
        except subprocess.TimeoutExpired:
            print("⏱️  TIMEOUT (>60s)")
            results.append({
                "prompt": prompt,
                "success": False,
                "returncode": -1,
                "error": "timeout",
            })
        except KeyboardInterrupt:
            print("\n⚠️  Interrupted")
            break
        except Exception as e:
            print(f"❌ ERROR: {e}")
            results.append({
                "prompt": prompt,
                "success": False,
                "returncode": -1,
                "error": str(e),
            })
        
        time.sleep(1)  # Between tests
    
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
    
    print(f"\nTests: {success_count}/{total} passed ({100*success_count/total:.0f}%)" if total > 0 else "No tests run")
    
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
            print("  ⚠️  No keys available - check if active key was exhausted")
        else:
            print("  ℹ️  Multiple keys available - auto-heal may have restored some")
    
    # Check for auto-heal events
    heal_events = [e for e in trace if "auto_heal" in e.get("event", "")]
    if heal_events:
        print(f"\n  💚 Auto-heal events: {len(heal_events)}")
        for e in heal_events[-3:]:
            print(f"     • {e.get('event')}: {e.get('message', '')[:60]}")
    
    print("\n" + "=" * 60)
    print("✅ TEST COMPLETE")
    print("=" * 60 + "\n")
    
    return 0 if success_count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
