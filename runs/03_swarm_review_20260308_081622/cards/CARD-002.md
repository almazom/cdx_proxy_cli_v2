# P1-CARD-002: Align CLI command and request contracts

## 📋 Description
Given operators use the documented `cdx2` workflow and targeted reset commands, when they install the package or pass special characters or invalid ports, then the CLI must expose the documented entrypoint, URL-encode reset filters, and fail fast on invalid `--port` values.

## 🌍 Context
The docs and CLI epilog advertise `cdx2`, but only `cdx` was registered in packaging metadata. The `reset` command manually concatenated query parameters, allowing file names with `&` or `=` to alter query semantics. CLI `--port` accepted values above `65535`, which failed later instead of returning a clear user error.

## 📍 Location
File: `pyproject.toml`
Lines: `30-32`
File: `src/cdx_proxy_cli_v2/cli/main.py`
Lines: `363-388`
File: `src/cdx_proxy_cli_v2/config/settings.py`
Lines: `191-199`
File: `tests/cli/test_main.py`
Lines: `170-280`

## 🔴 Current Code (ACTUAL, not placeholder)
```toml
[project.scripts]
cdx = "cdx_proxy_cli_v2.cli.main:main"
```

```python
params = []
name = getattr(args, "name", None)
state = getattr(args, "state", None)
if name:
    params.append(f"name={name}")
if state:
    params.append(f"state={state}")

path = "/reset"
if params:
    path += "?" + "&".join(params)
```

```python
resolved_port = resolve_numeric_setting(
    cli_value=port,
    env_key=ENV_PORT,
    default=0,
    env_parser=parse_port,
    min_cli_value=0,
)
```

## 🟢 Fixed Code (copy-paste ready)
```toml
[project.scripts]
cdx = "cdx_proxy_cli_v2.cli.main:main"
cdx2 = "cdx_proxy_cli_v2.cli.main:main"
```

```python
params: Dict[str, str] = {}
if name:
    params["name"] = str(name)
if state:
    params["state"] = str(state)

path = "/reset"
if params:
    path += "?" + urlencode(params)
```

```python
resolved_port = resolve_numeric_setting(
    cli_value=port,
    env_key=ENV_PORT,
    default=0,
    env_parser=parse_port,
    min_cli_value=0,
)
if not (0 <= resolved_port <= 65535):
    raise ValueError("port must be between 0 and 65535")
```

## ⚠️ Risk Assessment
| Risk | Level | Mitigation |
|------|-------|------------|
| Packaging alias conflicts with existing installs | L | Keep `cdx` intact and add `cdx2` as alias only |
| Query encoding changes existing tests | L | Add exact regression assertion for encoded reserved characters |
| Port validation may reject previously-clamped inputs | L | This is the desired CLI contract; main already maps `ValueError` to exit code `2` |

## ✅ Acceptance Criteria
- [x] Editable install metadata exposes both `cdx` and `cdx2`
- [x] `reset` uses encoded query parameters for names with reserved characters
- [x] `main(["status", "--port", "70000"])` returns exit code `2` with a clear message

## 🧪 Unit Tests
```python
assert mock_fetch.call_args.kwargs["path"] == "/reset?name=foo%26state%3Dblacklist.json&state=probation"

result = main(["status", "--port", "70000"])
assert result == 2

scripts = data["project"]["scripts"]
assert scripts["cdx2"] == "cdx_proxy_cli_v2.cli.main:main"
```

## 🧪 Verification
```bash
python3 -m pytest -q tests/cli/test_main.py
python3 -m pytest -q tests/runtime/test_service.py tests/cli/test_main.py tests/auth/test_keyring_store.py
python3 -m pytest -q
```

## 🔄 Rollback
```bash
git restore --source=e117211 -- pyproject.toml src/cdx_proxy_cli_v2/cli/main.py src/cdx_proxy_cli_v2/config/settings.py tests/cli/test_main.py
```

## 📝 Commit Message
```
fix(cli): align packaged command and reset contract

Card: CARD-002
Fixes: api.command_name_drift, api.reset_query_encoding, api.cli_port_validation
```
