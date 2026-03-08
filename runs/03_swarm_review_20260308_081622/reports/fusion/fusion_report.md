# Fusion Report

## Summary

Шесть scout-агентов сошлись в одном: текущий HEAD стабилен и хорошо покрыт тестами, но в проекте остались три высокосигнальных зоны, которые можно безопасно закрыть за один непрерывный прогон.

## P0 / P1 / P2

### P0
1. **CARD-001 — Harden service lifecycle ownership checks**
   - Scope: `src/cdx_proxy_cli_v2/runtime/service.py`, `tests/runtime/test_service.py`
   - Why now: одновременно закрывает утечку management key в argv, отправку секрета на чужой listener и убийство неподтверждённого PID.

### P1
2. **CARD-002 — Align CLI/operator contract**
   - Scope: `pyproject.toml`, `src/cdx_proxy_cli_v2/cli/main.py`, `src/cdx_proxy_cli_v2/config/settings.py`, `tests/cli/test_main.py`
   - Why now: устраняет broken onboarding (`cdx2`), raw query concatenation и поздний отказ на неверном `--port`.

3. **CARD-003 — Fix auth symlink containment**
   - Scope: `src/cdx_proxy_cli_v2/auth/store.py`, `tests/auth/test_keyring_store.py`
   - Why now: дёшево закрывает локальный path-containment bypass.

### Deferred
- Connection pooling and logging-path performance work remain valuable but are deferred.
- Broader maintainability/simplicity refactors remain backlog until active lifecycle risks are reduced.

## Decision

Текущий run ограничивает card set до трёх implementable fixes. Все три карты выполняются в этом же run и закрываются тестами.
