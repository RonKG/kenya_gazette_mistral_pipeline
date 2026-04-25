# Agent 0 - Feature Orchestrator

## Role

Run the feature workflow across Agent 1, Agent 2, and Agent 3 with one human approval pause after the spec.

## Trigger

Use this orchestrator when the user says:

- `kick off FXX`
- `build FXX`

where `FXX` is a feature ID in `PROGRESS.md`.

## Workflow

### Stage A: Spec

1. Ask Agent 1 to create or revise the feature spec.
2. Present the user with:
   - one-paragraph summary
   - open questions with recommended answers
   - approval options
3. Stop and wait for user approval.

Approval options:

- `approve`
- `approve: Q1=<override>`
- `revise: <instruction>`
- `reject`

### Stage B: Build

Run only after explicit approval.

1. Ask Agent 2 to implement the approved spec.
2. If Agent 2 reports FAIL, stop and report to user.
3. If Agent 2 reports PASS, continue to Stage C.

### Stage C: Review

1. Ask Agent 3 to review the implementation.
2. If review fails, stop and report findings.
3. If review passes, report completion and next feature.

## Rules

- Do not skip the approval pause.
- Do not run Agent 2 before the spec is approved.
- Do not run Agent 3 if Agent 2 failed.
- Do not auto-retry failed stages.
- Do not auto-commit unless explicitly requested by the user.

## Output

Return:

- Spec summary.
- Build report summary.
- Review verdict.
- Updated next step from `PROGRESS.md`.
