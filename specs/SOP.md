# Feature Build SOP - Gazette Mistral Pipeline

## Purpose

This document defines the standard workflow for building features in this repo.

Follow it before making package changes.

## Stage 1: Discovery

1. Read `PROGRESS.md`.
2. Locate the current `Next` feature.
3. Read the canonical docs relevant to that feature:
   - `docs/library-contract-v1.md`
   - `docs/library-roadmap-v1.md`
   - `docs/data-quality-confidence-scoring.md`
   - `docs/known-issues.md`
4. Read existing notebook or package code that the feature touches.
5. Do not start a feature that is not marked `Next` unless the user explicitly says so.

## Stage 2: Create Or Update Spec

Every feature must have `specs/FXX-kebab-case-name.md`.

The spec must include:

1. Goal.
2. Input/output contract.
3. Links to canonical docs.
4. Test case matrix.
5. Integration point.
6. Pass/fail criteria.
7. Definition of Done.
8. Open questions and risks.

If the spec has unresolved questions, ask the user before implementing.

## Stage 3: Implement

Implement only the approved feature scope.

Rules:

- Keep changes small and feature-bound.
- Prefer lightweight stdlib implementations.
- Do not add runtime dependencies unless the spec explicitly allows them.
- Keep live Mistral calls out of normal tests.
- Update docs when public behavior changes.
- Preserve user changes in the working tree.

## Stage 4: Test

Run the feature's tests.

Minimum expectations:

- Unit tests for new pure functions.
- Mocked or replayed Mistral responses for API features.
- Schema validation when envelope shape changes.
- Regression checks against cached real Mistral responses when parsing changes.

If a test cannot be run, record why in the build report.

## Stage 5: Review And Close

Before marking a feature complete:

- Verify Definition of Done.
- Update `PROGRESS.md`.
- Add or update Known Debt if needed.
- Add a Session Log row.
- Report test results.

Do not mark a feature complete if required tests failed.

## Agent Workflow

The repo can use three roles:

- Agent 1: Spec Creator.
- Agent 2: Builder and Tester.
- Agent 3: Senior Reviewer.

Optional orchestrator:

- Agent 0 can run the spec/build/review flow when the user says `kick off FXX` or `build FXX`.

The orchestrator must pause for user approval after the spec and before implementation.

## Spec Template

```markdown
# FXX Spec: Feature Name

## 1. Goal

One sentence.

## 2. Input/Output Contract

| Aspect | Specification |
|--------|---------------|
| Function or module | |
| Input source | |
| Output shape | |
| Error handling | |

## 3. Links To Canonical Docs

| Doc | Why it matters |
|-----|----------------|
| `docs/library-contract-v1.md` | |
| `docs/library-roadmap-v1.md` | |
| `PROGRESS.md` | |

## 4. Test Case Matrix

| ID | Scenario | Input | Expected |
|----|----------|-------|----------|
| TC1 | Happy path | | |
| TC2 | Degraded input | | |
| TC3 | Edge case | | |
| TC4 | Regression fixture | | |
| TC5 | Error handling | | |

## 5. Integration Point

- Called by:
- Calls:
- Side effects:
- Model fields populated:

## 6. Pass/Fail Criteria

| Check | How to verify |
|-------|---------------|
| | |

## 7. Definition Of Done

- [ ] Implemented in specified location.
- [ ] Tests pass.
- [ ] Integration verified.
- [ ] Docs updated if needed.
- [ ] `PROGRESS.md` updated.

## 8. Open Questions And Risks

List any unresolved items.
```
