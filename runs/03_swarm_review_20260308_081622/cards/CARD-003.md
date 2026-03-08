# P1-CARD-003: Tighten auth symlink containment

## 📋 Description
Given auth JSON discovery walks a local auth directory, when a symlink points to a sibling path like `/auth2/...`, then the loader must reject it instead of treating it as inside `/auth`.

## 🌍 Context
The auth loader protected against path traversal with a string-prefix comparison. That works for many cases but fails for confusable sibling directories where the outside path shares the same textual prefix.

## 📍 Location
File: `src/cdx_proxy_cli_v2/auth/store.py`
Lines: `23-38`
File: `tests/auth/test_keyring_store.py`
Lines: `67-104`

## 🔴 Current Code (ACTUAL, not placeholder)
```python
def iter_auth_json_files(auth_dir: str) -> List[Path]:
    root = Path(os.path.expanduser(auth_dir)).resolve()
    files: List[Path] = []
    for entry in entries:
        resolved = entry.resolve()
        if not str(resolved).startswith(str(root)):
            continue
        if resolved.is_file() and resolved.suffix.lower() == ".json":
            files.append(resolved)
```

## 🟢 Fixed Code (copy-paste ready)
```python
def iter_auth_json_files(auth_dir: str) -> List[Path]:
    root = Path(os.path.expanduser(auth_dir)).resolve()
    files: List[Path] = []
    for entry in entries:
        resolved = entry.resolve()
        if os.path.commonpath([str(root), str(resolved)]) != str(root):
            continue
        if resolved.is_file() and resolved.suffix.lower() == ".json":
            files.append(resolved)
```

## ⚠️ Risk Assessment
| Risk | Level | Mitigation |
|------|-------|------------|
| Platform-specific symlink behavior in tests | L | Skip only if symlinks are unavailable in the environment |
| False rejection of legitimate files | L | `commonpath` still accepts real descendants of the auth root |

## ✅ Acceptance Criteria
- [x] Legitimate JSON files inside the auth dir are still discovered
- [x] Symlinks to sibling roots like `/auth2/evil.json` are rejected
- [x] Existing auth-loader tests continue to pass

## 🧪 Unit Tests
```python
files = [path.name for path in iter_auth_json_files(str(auth_dir))]
assert "legit.json" in files
assert "link.json" not in files
```

## 🧪 Verification
```bash
python3 -m pytest -q tests/auth/test_keyring_store.py
python3 -m pytest -q tests/runtime/test_service.py tests/cli/test_main.py tests/auth/test_keyring_store.py
python3 -m pytest -q
```

## 🔄 Rollback
```bash
git restore --source=e117211 -- src/cdx_proxy_cli_v2/auth/store.py tests/auth/test_keyring_store.py
```

## 📝 Commit Message
```
fix(auth): tighten auth json path containment

Card: CARD-003
Fixes: security.auth_path_containment
```
