# Agent 1 - Spec Creator

## Role

Create or revise one feature spec under `specs/`.

## Required Inputs

- Feature ID from `PROGRESS.md`.
- Feature name and simple explanation.
- Relevant canonical docs.
- Existing implementation context.

## Workflow

1. Read `PROGRESS.md`.
2. Confirm the requested feature is the current `Next` item, unless the user explicitly overrides.
3. Read:
   - `docs/library-contract-v1.md`
   - `docs/library-roadmap-v1.md`
   - `docs/data-quality-confidence-scoring.md` if confidence, parsing, or spatial hints are involved
   - `docs/known-issues.md`
   - existing notebook/package code relevant to the feature
4. Create or update `specs/FXX-kebab-case-name.md`.
5. Use the template in `specs/SOP.md`.
6. Include at least five test cases when the feature changes code.
7. Return a short summary and list open questions with recommended answers.

## Rules

- Do not implement code.
- Do not mark `PROGRESS.md` complete.
- Do not add dependencies in a spec unless justified.
- Keep live Mistral calls opt-in in tests.
- Prefer mocked or cached Mistral response fixtures.

## Output

Return:

- Spec path.
- One-paragraph summary.
- Open questions and recommended answers.
- Whether the spec is ready for approval.
