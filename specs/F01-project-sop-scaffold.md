# F01 Spec: Project SOP Scaffold

## 1. Goal

Create the Docling-style planning, progress, specification, and agent workflow documents required before package implementation begins.

## 2. Input/Output Contract

| Aspect | Specification |
|--------|---------------|
| Feature input | Existing notebook prototype and agreed architecture |
| Feature output | Project docs, SOP, initial progress tracker, and agent prompts |
| Error handling | Missing docs are explicit failure; no package code is changed |
| Side effects | Adds documentation files only |

## 3. Links To Canonical Docs

| Doc | Why it matters |
|-----|----------------|
| `PROGRESS.md` | Becomes the session-start source of truth |
| `docs/library-contract-v1.md` | Defines public API and envelope contract |
| `docs/library-roadmap-v1.md` | Defines feature sequence and quality gates |
| `specs/SOP.md` | Defines how future features are built |

## 4. Test Case Matrix

| ID | Scenario | Input | Expected |
|----|----------|-------|----------|
| TC1 | Progress file exists | Workspace root | `PROGRESS.md` exists and lists F01-F13 |
| TC2 | Canonical docs exist | `docs/` | Contract, roadmap, confidence, known-issues docs exist |
| TC3 | SOP exists | `specs/` | `specs/SOP.md` exists with staged workflow |
| TC4 | Agent prompts exist | `.cursor/agents/` | Agent 0-3 prompt files exist |
| TC5 | Autoflow rule exists | `.cursor/rules/` | Feature build trigger rule exists |

## 5. Integration Point

- Called by: user and future agent sessions.
- Calls: no package code.
- Side effects: docs only.
- Model fields populated: none.

## 6. Pass/Fail Criteria

| Check | How to verify |
|-------|---------------|
| All planned docs exist | `Glob` or file tree inspection |
| No package code changed | Review changed files |
| Feature list is clear | `PROGRESS.md` lists F01-F13 |
| Next feature is F02 | `PROGRESS.md` Today block |

## 7. Definition Of Done

- [x] `PROGRESS.md` created.
- [x] Canonical docs created under `docs/`.
- [x] `specs/SOP.md` created.
- [x] `specs/F01-project-sop-scaffold.md` created.
- [x] Agent prompts created under `.cursor/agents/`.
- [x] Autoflow rule created under `.cursor/rules/`.
- [x] `PROGRESS.md` marks F01 complete and F02 next.

## 8. Open Questions And Risks

- Future feature specs may need expansion as implementation details are discovered.
- Agent prompts are intentionally lightweight and can be refined after first use.
