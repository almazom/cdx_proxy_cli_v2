# Proposed Changes to START.md for v4.0.19

This document shows specific YAML blocks from v4.0.18 with proposed modifications for v4.0.19.

---

## 1. ADD: Execution Mode Selection (New Section)

**Location:** After `start_only_entrypoint_contract`

```yaml
# PROPOSED NEW SECTION for v4.0.19
execution_mode_selection:
  description: "Explicit mode selection - honest about capabilities"
  modes:
    analysis:
      description: "Generate review cards only (single agent)"
      phases: [0.0, 0.1, 1, 2, 5, 6, 6.5, 7, 9]
      agents_required: 1
      infrastructure: "none"
      output: "trello_cards/"
      
    implementation:
      description: "Implement cards with multi-agent swarm"
      phases: [8.1, 8.2, 8.2.1, 8.2.2, 8.4, 8.5, 8.6, 8.9, 9]
      agents_required: 3
      infrastructure: 
        - "Multiple AI agents available (codex, qwen, kimi)"
        - "Git worktree support"
        - "Agent spawn capability"
      output: "implemented_code/ + PR"
      
    full:
      description: "Analysis + Implementation (requires infrastructure)"
      phases: "all"
      agents_required: "1 for analysis, 3+ for implementation"
      
  default_mode: "analysis"
  mode_flag: "--mode={analysis|implementation|full}"
  
  # Honest about what happens with limited agents
  agent_unavailable_behavior:
    if_mode_is_full_and_agents_unavailable:
      action: "fallback_to_analysis_mode"
      message: "Multi-agent infrastructure not available. Running analysis mode only."
      continue: true
      fabricate_evidence: false  # NEW: Don't fake multi-agent execution
```

---

## 2. MODIFY: Reduce Preflight Gates

**Current (v4.0.18):**
```yaml
# CURRENT - 10 gates
mandatory_phase_span: "0.0->9"
```

**Proposed (v4.0.19):**
```yaml
# PROPOSED - 3 gates + mode-specific gates
preflight:
  common_gates:
    - 0.0.1: { name: "environment_check", required: true }
    - 0.0.2: { name: "version_lock", required: true }
    - 0.0.3: { name: "mode_validation", required: true }
    
  mode_specific_gates:
    implementation:
      - 0.0.4: { name: "agent_availability", required: true }
      - 0.0.5: { name: "git_worktree_ready", required: true }
    
    analysis: []  # No additional gates needed
```

---

## 3. MODIFY: Remove Fabricated Evidence

**Current (v4.0.18):**
```yaml
# CURRENT - Requires impossible evidence
live_execution_evidence_contract:
  expert_swarm:
    required_expert_count: 6
    required_distinct_sessions: 6
  implementation_swarm:
    required_lane_count: 3
    required_distinct_subagent_sessions: 3
```

**Proposed (v4.0.19):**
```yaml
# PROPOSED - Evidence based on actual execution
evidence_contract:
  analysis_mode:
    required:
      - card_files_exist
      - template_sections_complete
      - ssot_tasks_defined
    optional:
      - human_review_completed
      
  implementation_mode:
    required:
      - git_commits_exist
      - test_results_pass
      - pr_created_or_commits_pushed
    # Only required if mode=implementation
```

---

## 4. MODIFY: Honest Agent Topology

**Current (v4.0.18):**
```yaml
# CURRENT - Deception about compensated lanes
agent_availability:
  on_agent_unavailable:
    activate_compensated_lanes: true
    compensated_lane_profiles:
      - strict_correctness
      - balanced_maintainability
      - test_heavy_regression_guard
```

**Proposed (v4.0.19):**
```yaml
# PROPOSED - Honest about single-agent limitations
agent_topology:
  analysis_mode:
    single_agent_sufficient: true
    strategy_variations:  # Renamed from "compensated_lanes"
      description: "Same agent with different system prompts"
      count: 3
      note: "Not parallel execution - sequential with different perspectives"
      
  implementation_mode:
    requires:
      minimum_agents: 3
      recommended_agents: [codex, qwen, kimi]
    single_agent_fallback:
      allowed: false
      reason: "Implementation mode requires genuine multi-agent comparison"
      action: "exit_with_error_or_switch_mode"
```

---

## 5. MODIFY: Reduce Artifact Burden

**Current (v4.0.18):**
```yaml
# CURRENT - 32+ artifacts
required_subdirs:
  - artefacts/trello_cards
  - reports/card_validation
  - reports/traceability
  - reports/execution
  - reports/comparison
  - reports/observability
  - reports/live/expert_swarm
  - reports/live/worktrees
  - reports/live/comparison
  - reports/live/review
  - reports/live/pr
  - logs/stream
```

**Proposed (v4.0.19):**
```yaml
# PROPOSED - ~10 artifacts
output_structure:
  analysis_mode:
    required:
      - artefacts/trello_cards/     # The actual output
      - runs/RUN_METADATA.yaml      # What we did
      - reports/validation.yaml     # What passed/failed
    optional:
      - logs/pipeline.ndjson        # Execution trace
      
  implementation_mode:
    required:
      - implemented_code/           # The actual output
      - runs/RUN_METADATA.yaml
      - reports/test_results.yaml
      - reports/pr_info.yaml
```

---

## 6. MODIFY: Realistic Quality Metrics

**Current (v4.0.18):**
```yaml
# CURRENT - Self-reported scores
quality_gate_pack:
  threshold: 95
  gates:
    - gate_id: template_structure_conformance
      pass_condition: "template_compliance_percent >= 95"
```

**Proposed (v4.0.19):**
```yaml
# PROPOSED - Honest about measurement limitations
quality_assessment:
  automated_checks:
    template_structure:
      - check: "required_sections_present"
        binary: true  # Pass/fail, not percentage
      - check: "no_placeholder_variables"
        binary: true
      - check: "files_parse_correctly"
        binary: true
        
  subjective_quality:
    note: "Automated systems cannot judge solution quality"
    recommendation: "Human review required for:"
      - "Solution appropriateness"
      - "Code correctness"
      - "Test coverage adequacy"
      
  final_score:
    note: "REMOVED - No automated quality percentage"
    replaced_with: 
      - "automated_checks_passed: {count}/{total}"
      - "human_review_status: {pending|completed}"
```

---

## 7. ADD: Failure Mode Documentation

**New Section for v4.0.19:**
```yaml
failure_modes:
  common_issues:
    - code: "AGENT_UNAVAILABLE"
      scenario: "Mode=implementation but < 3 agents available"
      resolution: "Switch to --mode=analysis or wait for agent availability"
      
    - code: "TEMPLATE_NON_COMPLIANT"
      scenario: "Generated cards missing required sections"
      resolution: "Review and fix cards manually, or regenerate"
      
    - code: "NO_GIT_REPO"
      scenario: "Not in a git repository"
      resolution: "Run 'git init' or use --no-git flag (analysis mode only)"
      
    - code: "WORKTREE_UNSUPPORTED"
      scenario: "Git worktrees not supported in environment"
      resolution: "Use --mode=analysis, or implement single-worktree strategy"
      
    - code: "IMPLEMENTATION_FAILED"
      scenario: "Tests fail after implementation"
      resolution: "Review reports/test_results.yaml, fix manually, or retry"
```

---

## 8. MODIFY: Phase Map Honesty

**Current (v4.0.18):**
```yaml
# CURRENT - Implies all phases always execute
full_phase_map:
  - Phase 3: Expert reviews in read-only mode
  - Phase 3.5: Expert swarm fusion
  - Phase 8.2: Multi-agent implementation
```

**Proposed (v4.0.19):**
```yaml
# PROPOSED - Conditional phase execution
phase_execution_map:
  common_phases:  # Always execute
    - 0.0: "Preflight"
    - 0.1: "Run structure"
    - 1: "SSOT init"
    - 2: "Context collection"
    - 6: "Card generation"
    - 9: "Completion"
    
  analysis_mode_only:  # Skip in implementation mode
    - 5: "Task extraction"
    - 6.5: "Template validation"
    - 7: "Card validation"
    
  implementation_mode_only:  # Skip in analysis mode
    - 3: "Expert reviews"
    - 3.5: "Expert fusion"
    - 8.1: "Worktree setup"
    - 8.2: "Multi-agent implementation"
    - 8.2.1: "Quorum gate"
    - 8.4: "Comparison"
    - 8.5: "Fusion"
    - 8.9: "PR creation"
    
  not_implemented:  # Mark as future/optional
    - 0.2: "Budget estimator (requires historical data)"
    - 8.6.1: "Live codex review (requires codex agent)"
```

---

## Summary of Changes

| Aspect | v4.0.18 | v4.0.19 Proposal |
|--------|---------|------------------|
| Phases | 36 (assumed all execute) | 12 common + mode-specific |
| Preflight Gates | 10 | 3 common + 2 for implementation |
| Artifacts | 32+ | ~10 |
| Modes | Implied single mode | Explicit analysis/implementation/full |
| Multi-Agent | Assumed, faked if unavailable | Explicit requirement with fallback |
| Quality Score | Self-reported percentage | Binary checks + human review |
| Evidence | Often fabricated | Only what actually executed |

---

## Migration Path

1. **v4.0.19 (Conservative):**
   - Add `--mode` flag
   - Remove fabricated evidence
   - Reduce preflight to 3 gates
   - Keep single flow structure

2. **v5.0 (Breaking):**
   - Split into `03_swarm_analysis` and `03_swarm_implementation`
   - Remove all multi-agent concepts from analysis flow
   - Make implementation flow require explicit agent flags
   - Rename "swarm_review" to reflect single-agent reality
