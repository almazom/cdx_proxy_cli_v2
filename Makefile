PYTHON ?= python3
PYTEST ?= $(PYTHON) -m pytest

UNIT_TEST_PATHS = \
	tests/auth \
	tests/cli \
	tests/config \
	tests/observability \
	tests/proxy \
	tests/runtime \
	tests/security \
	tests/taad \
	tests/test_health_snapshot.py

.PHONY: test-unit test-integration test-integration-codex-wp test-e2e test-e2e-codex-wp test-all

test-unit:
	$(PYTEST) -q $(UNIT_TEST_PATHS)

test-integration:
	$(PYTEST) -q tests/integration

test-integration-codex-wp:
	$(PYTEST) -q tests/integration/test_codex_wp_green_path.py

test-e2e:
	$(PYTEST) -q tests/e2e

test-e2e-codex-wp:
	$(PYTEST) -q tests/integration/test_codex_wp_green_path.py

test-all:
	$(PYTEST) -q
