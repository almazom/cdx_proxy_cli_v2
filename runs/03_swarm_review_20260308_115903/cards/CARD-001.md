# P0-CARD-001: Finish the `cdx`-only contract atomically

## 📋 Description
Given the package now exposes only `cdx`, when users read docs, see runtime guidance, or run tracked tests, then every surface must consistently use `cdx`, the tracked contract tests must stop expecting `cdx2`, and the scratch wrapper/test artifacts must be removed instead of becoming the new enforcement path.

## 🌍 Context
The live worktree is midway through a rename from `cdx2` to `cdx`. Right now `pyproject.toml` exposes only `cdx`, but tracked tests, README/runbook text, runtime stale-process warnings, dashboard titles, and one scratch HTML report still mention `cdx2`. That makes the branch red and gives users broken instructions.

## 📍 Location
File: `pyproject.toml`
Lines: `30-31`
File: `tests/cli/test_main.py`
Lines: `290-296`
File: `README.md`
Lines: `31-63`
File: `docs/operations/runbook.md`
Lines: `8-26`
File: `src/cdx_proxy_cli_v2/runtime/service.py`
Lines: `458-483`
File: `src/cdx_proxy_cli_v2/observability/all_dashboard.py`
Lines: `202-212`
File: `proxy_debug_report.html`
Lines: `277-277`
File: `scripts/cdx_wrapper.py`
Lines: `1-53`
File: `tests/test_cdx_only.py`
Lines: `1-242`

## 🔴 Current Code (ACTUAL, not placeholder)
```toml
[project.scripts]
cdx = "cdx_proxy_cli_v2.cli.main:main"
```

```python
def test_pyproject_registers_cdx_and_cdx2_scripts(self):
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    scripts = data["project"]["scripts"]
    assert scripts["cdx"] == "cdx_proxy_cli_v2.cli.main:main"
    assert scripts["cdx2"] == "cdx_proxy_cli_v2.cli.main:main"
```

```python
warnings.warn(
    f"Port {requested_port} was in use, using port {port} instead. "
    f"Run 'cdx2 stop' to clean up stale processes.",
    RuntimeWarning,
)
```

```text
cdx2 proxy
eval "$(cdx2 proxy --print-env-only)"
cdx2 trace
cdx2 stop
```

## 🟢 Fixed Code (copy-paste ready)
```toml
[project.scripts]
cdx = "cdx_proxy_cli_v2.cli.main:main"
```

```python
def test_pyproject_registers_cdx_script_only(self):
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    scripts = data["project"]["scripts"]
    assert scripts == {"cdx": "cdx_proxy_cli_v2.cli.main:main"}
```

```python
warnings.warn(
    f"Port {requested_port} was in use, using port {port} instead. "
    f"Run 'cdx stop' to clean up stale processes.",
    RuntimeWarning,
)
```

```text
cdx proxy
eval "$(cdx proxy --print-env-only)"
cdx trace
cdx stop
```

```text
Delete scratch files:
- scripts/cdx_wrapper.py
- tests/test_cdx_only.py
```

## ⚠️ Risk Assessment
| Risk | Level | Mitigation |
|------|-------|------------|
| Breaking users who still rely on `cdx2` | M | Make the rename atomic across docs/tests/runtime so the repo truth is clear and validated |
| Missing one stale `cdx2` string | M | Sweep tracked files + scratch HTML report with search before final verification |
| Removing scratch files hides useful coverage | L | Fold only deterministic assertions into the tracked pytest suite |

## ✅ Acceptance Criteria
- [ ] The tracked pytest suite no longer expects `cdx2`
- [ ] README, runbook, runtime warnings, dashboard titles, and scratch HTML report use `cdx`
- [ ] `scripts/cdx_wrapper.py` and `tests/test_cdx_only.py` are removed from the change set
- [ ] Search over tracked + scoped scratch files finds no remaining operational `cdx2` references

## 🧪 Verification
```bash
python3 -m pytest -q tests/cli/test_main.py
rg -n "cdx2" README.md docs src tests pyproject.toml proxy_debug_report.html
python3 -m pytest -q tests/cli/test_main.py tests/proxy/test_server.py
```

## 🔄 Rollback
```bash
git restore --source=HEAD~1 -- pyproject.toml tests/cli/test_main.py README.md docs/operations/runbook.md src/cdx_proxy_cli_v2/runtime/service.py src/cdx_proxy_cli_v2/observability/all_dashboard.py proxy_debug_report.html
```

## 📝 Commit Message
```
refactor(cli): finish cdx-only contract migration

Card: CARD-001
Fixes: cli.cdx_contract_drift
```
