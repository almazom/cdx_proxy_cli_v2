# P0-CARD-001: Harden service lifecycle ownership and secret handling

## 📋 Description
Given a reused PID or an occupied port, when the service lifecycle code attempts recovery, then it must only talk to and terminate a verified `cdx_proxy_cli_v2 run-server` process for the same auth dir, and it must not expose the management key in child argv.

## 🌍 Context
This project manages a localhost proxy as a background process. Before this fix, stale-port recovery could POST `/shutdown` with `X-Management-Key` to whatever listener occupied the configured port and could terminate an unrelated PID. The spawn path also placed the management key directly into the child process command line.

## 📍 Location
File: `src/cdx_proxy_cli_v2/runtime/service.py`
Lines: `231-375`
File: `src/cdx_proxy_cli_v2/runtime/service.py`
Lines: `489-515`
File: `tests/runtime/test_service.py`
Lines: `91-257`

## 🔴 Current Code (ACTUAL, not placeholder)
```python
def _kill_stale_proxy_on_port(host: str, port: int, management_key: str) -> bool:
    base_url = f"http://{host}:{port}"
    try:
        fetch_json(
            base_url=base_url,
            path="/shutdown",
            method="POST",
            headers=_management_headers(management_key),
            timeout=2.0,
        )
    except Exception:
        pass

    stale_pid = _find_pid_using_port(host, port)
    if stale_pid:
        _terminate_pid(stale_pid, timeout_seconds=5.0)
        return not _is_port_in_use(host, port)
    return False

def _spawn(settings: Settings, *, port: int, management_key: str) -> subprocess.Popen[bytes]:
    argv = [
        sys.executable,
        "-m",
        "cdx_proxy_cli_v2",
        "run-server",
        "--auth-dir",
        settings.auth_dir,
        "--host",
        settings.host,
        "--port",
        str(port),
        "--upstream",
        settings.upstream,
        "--management-key",
        management_key,
    ]
```

## 🟢 Fixed Code (copy-paste ready)
```python
def _is_expected_proxy_process(pid: Optional[int], auth_dir: str) -> bool:
    if not _is_pid_running(pid):
        return False
    cmdline = _read_process_cmdline(pid)
    if not cmdline:
        return False
    normalized_auth_dir = str(resolve_path(auth_dir))
    return (
        "cdx_proxy_cli_v2" in cmdline
        and "run-server" in cmdline
        and normalized_auth_dir in cmdline
    )


def _kill_stale_proxy_on_port(host: str, port: int, management_key: str, auth_dir: str) -> bool:
    stale_pid = _find_pid_using_port(host, port)
    if not _is_expected_proxy_process(stale_pid, auth_dir):
        return False

    base_url = f"http://{host}:{port}"
    try:
        fetch_json(
            base_url=base_url,
            path="/shutdown",
            method="POST",
            headers=_management_headers(management_key),
            timeout=2.0,
        )
        time.sleep(0.5)
        if not _is_port_in_use(host, port):
            return True
    except Exception:
        pass

    _terminate_pid(stale_pid, timeout_seconds=5.0)
    time.sleep(0.3)
    return not _is_port_in_use(host, port)


def _spawn(settings: Settings, *, port: int, management_key: str) -> subprocess.Popen[bytes]:
    argv = [
        sys.executable,
        "-m",
        "cdx_proxy_cli_v2",
        "run-server",
        "--auth-dir",
        settings.auth_dir,
        "--host",
        settings.host,
        "--port",
        str(port),
        "--upstream",
        settings.upstream,
        "--trace-max",
        str(settings.trace_max),
        "--request-timeout",
        str(settings.request_timeout),
    ]
```

## ⚠️ Risk Assessment
| Risk | Level | Mitigation |
|------|-------|------------|
| Process verification false negative blocks cleanup | M | Fallback is safe: use a new port or report not running rather than killing arbitrary processes |
| Linux-specific `/proc` lookup is unavailable | L | Fallback to `ps -o command=` keeps behavior portable enough for local environments |
| Lifecycle regressions | M | Add regression tests for spawn secrecy, stale listener skip, start/stop PID verification |

## ✅ Acceptance Criteria
- [x] Service recovery sends `X-Management-Key` only to a verified proxy process for the same auth dir
- [x] `stop_service` never terminates an unrelated reused PID
- [x] Spawned child process does not receive `--management-key` in argv

## 🧪 Unit Tests
```python
with patch('cdx_proxy_cli_v2.runtime.service._find_pid_using_port', return_value=4242):
    with patch('cdx_proxy_cli_v2.runtime.service._is_expected_proxy_process', return_value=False):
        result = service_module._kill_stale_proxy_on_port("127.0.0.1", 8080, "secret-key", "/tmp/auths")
        assert result is False

with patch('cdx_proxy_cli_v2.runtime.service.subprocess.Popen') as mock_popen:
    service_module._spawn(settings, port=8080, management_key="secret-key")
    argv = mock_popen.call_args.args[0]
    assert "--management-key" not in argv
```

## 🧪 Verification
```bash
python3 -m pytest -q tests/runtime/test_service.py
python3 -m pytest -q tests/runtime/test_service.py tests/cli/test_main.py tests/auth/test_keyring_store.py
python3 -m pytest -q
```

## 🔄 Rollback
```bash
git restore --source=e117211 -- src/cdx_proxy_cli_v2/runtime/service.py tests/runtime/test_service.py
```

## 📝 Commit Message
```
fix(runtime): harden service lifecycle ownership checks

Card: CARD-001
Fixes: security.stale_port_cleanup, security.management_key_argv
```
