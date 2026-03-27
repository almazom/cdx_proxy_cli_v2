# Implementation Plan: codex_wp plan Command

## Executive Summary

Add codex_wp plan subcommand to generate implementation plans non-interactively.

**Confidence Level: 95%**

## Architecture

1. CLI Parser (bin/codex_wp)
2. Plan Mode Injector (src/cdx_proxy_cli_v2/plan/)
3. codex exec (headless, read-only sandbox)
4. Output Parser (extract <proposed_plan>)
5. Formatter & Validator

## Module Structure

src/cdx_proxy_cli_v2/plan/
- __init__.py
- injector.py
- parser.py
- formatter.py
- validator.py
- exceptions.py
- runner.py
- templates/plan_mode.txt
- tests/

## Key Implementation Steps

### 1. Create Plan Mode Template
File: templates/plan_mode.txt
Content: Plan Mode instructions with <proposed_plan> format requirements

### 2. Implement Injector
Class: PlanModeInjector
Methods: inject(), _build_context()
Handles: Template loading, context file inclusion, size limits

### 3. Implement Parser
Class: ProposedPlanParser
Methods: parse(), fallback_extract()
Handles: JSONL parsing, regex extraction, fallback strategies

### 4. Implement Formatter
Class: PlanFormatter
Methods: format()
Output: Clean markdown with frontmatter

### 5. Implement Validator
Class: PlanValidator
Methods: validate()
Checks: Required sections, content quality

### 6. Implement Runner
Function: main()
Orchestrates: Inject -> Exec -> Parse -> Validate -> Format -> Write

### 7. Integrate with bin/codex_wp
Add: plan case in argument parser
Function: run_plan_command()

## CLI Interface

codex_wp plan PROMPT [OPTIONS]
Options:
  --output, -o FILE     Output file (default: plan.md)
  --file, -f FILE       Context file(s)
  --model MODEL         Model override
  --reasoning-effort L  Reasoning level

## Error Handling

1. TemplateError: Template file missing
2. ContextError: Context files too large
3. ExtractionError: No <proposed_plan> found
4. ValidationError: Plan structure invalid

## Fallback Strategy

Tier 1: Parse JSONL events for proposed_plan
Tier 2: Regex extract <proposed_plan> tags
Tier 3: Use entire output as raw plan

## Testing Strategy

Unit tests: injector, parser, formatter, validator
Integration tests: Full plan generation
E2E tests: Against real codex exec

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| codex exec changes | Pin to tested version |
| No <proposed_plan> | 3-tier fallback |
| Context too large | Size limits + truncation |
| Template drift | Version template with code |

## Implementation Order

1. Create module structure
2. Implement exceptions + template
3. Implement injector + tests
4. Implement parser + tests
5. Implement formatter + tests
6. Implement validator + tests
7. Implement runner
8. Integrate with bin/codex_wp
9. Add integration tests
10. Run make test-e2e
