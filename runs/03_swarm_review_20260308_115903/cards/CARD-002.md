# P1-CARD-002: Force ChatGPT headers with case-insensitive replacement and tests

## 📋 Description
Given ChatGPT backend requests must present canonical `Origin`, `Referer`, and `User-Agent` values, when inbound client headers use different casing or conflicting values, then the proxy must replace those headers case-insensitively and tests must lock the behavior.

## 🌍 Context
The current change improved security by switching from `setdefault(...)` to forced assignment. But direct assignment to `Origin`, `Referer`, and `User-Agent` still leaves lowercase variants such as `origin` or `user-agent` alive in the forwarded header map. That means the branch still allows ambiguous duplicate headers and lacks direct regression coverage.

## 📍 Location
File: `src/cdx_proxy_cli_v2/proxy/server.py`
Lines: `400-409`
File: `tests/proxy/test_server.py`
Lines: `213-239`

## 🔴 Current Code (ACTUAL, not placeholder)
```python
if chatgpt_backend:
    base_headers["Origin"] = "https://chatgpt.com"
    base_headers["Referer"] = "https://chatgpt.com/"
    base_headers["User-Agent"] = "codex-cli"
```

## 🟢 Fixed Code (copy-paste ready)
```python
if chatgpt_backend:
    set_header_case_insensitive(base_headers, "Origin", "https://chatgpt.com")
    set_header_case_insensitive(base_headers, "Referer", "https://chatgpt.com/")
    set_header_case_insensitive(base_headers, "User-Agent", "codex-cli")
```

```python
def test_chatgpt_backend_headers_are_replaced_case_insensitively(...):
    # lower-case inbound values are replaced with canonical ChatGPT headers
    ...
```

## ⚠️ Risk Assessment
| Risk | Level | Mitigation |
|------|-------|------------|
| Unexpected header-shape change for ChatGPT backend | L | Limit change to the existing `chatgpt_backend` branch only |
| Regression in non-ChatGPT upstreams | M | Add a negative test that non-ChatGPT paths preserve caller headers |
| Test gap around forwarded request assembly | M | Exercise the proxy request path rather than helper functions alone |

## ✅ Acceptance Criteria
- [ ] ChatGPT backend requests replace `Origin`, `Referer`, and `User-Agent` case-insensitively
- [ ] Lowercase inbound duplicates do not survive the forwarded header map
- [ ] Non-ChatGPT upstream behavior remains unchanged
- [ ] Targeted proxy tests cover the new behavior

## 🧪 Verification
```bash
python3 -m pytest -q tests/proxy/test_server.py
python3 -m pytest -q tests/cli/test_main.py tests/proxy/test_server.py
python3 -m pytest -q
```

## 🔄 Rollback
```bash
git restore --source=HEAD~1 -- src/cdx_proxy_cli_v2/proxy/server.py tests/proxy/test_server.py
```

## 📝 Commit Message
```
fix(proxy): casefold forced chatgpt headers

Card: CARD-002
Fixes: proxy.chatgpt_header_casefold_override
```
