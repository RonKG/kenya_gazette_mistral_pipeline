# F02 Spec: Package Skeleton

## 1. Goal

Create the minimal lightweight, Git-installable Python package shell for `gazette_mistral_pipeline` with public API stubs and packaging metadata, without moving notebook logic yet.

## 2. Input/Output Contract

| Aspect | Specification |
|--------|---------------|
| Feature scope | Package scaffold only; no Mistral calls, no parsing, no Pydantic models |
| Package import name | `gazette_mistral_pipeline` |
| Distribution name | `gazette-mistral-pipeline` |
| Version | `0.1.0` |
| Public stubs | `parse_file`, `parse_url`, `parse_source`, `write_envelope` |
| Schema stubs | `get_envelope_schema`, `validate_envelope_json` |
| Output files | `gazette_mistral_pipeline/__init__.py`, `gazette_mistral_pipeline/__version__.py`, `gazette_mistral_pipeline/py.typed`, `pyproject.toml`, `README.md`, `LICENSE`, basic tests |
| Error handling | Public parse/write/schema stubs raise `NotImplementedError` with messages naming the feature where real implementation lands |
| Runtime dependencies | None for F02; `pydantic` and `jsonschema` land in later features |

F02 must not modify the notebooks or existing `prototype_outputs`.

## 3. Links To Canonical Docs

| Doc | Why it matters |
|-----|----------------|
| `PROGRESS.md` | F02 is the current `Next` item and defines package skeleton scope |
| `docs/library-contract-v1.md` | Defines target public API names and Mistral-only contract |
| `docs/library-roadmap-v1.md` | Places F02 before models, source loading, Mistral API, and parsing |
| `docs/known-issues.md` | Confirms API keys and live Mistral calls must not appear in scaffolding/tests |
| `specs/SOP.md` | Requires spec-first feature build and testable Definition of Done |

## 4. Test Case Matrix

| ID | Scenario | Input | Expected |
|----|----------|-------|----------|
| TC1 | Import smoke | `from gazette_mistral_pipeline import __version__, parse_file, parse_url, parse_source, write_envelope` | Import succeeds; `__version__ == "0.1.0"` |
| TC2 | Stub behavior | Call each public stub with minimal dummy inputs | Each raises `NotImplementedError`; message names the relevant future feature |
| TC3 | Package metadata | Inspect `pyproject.toml` | Setuptools backend, distribution name `gazette-mistral-pipeline`, Python `>=3.10`, no runtime deps |
| TC4 | Type marker and license | Check package files | `py.typed` exists; `LICENSE` exists and is Apache-2.0 |
| TC5 | Editable install smoke | `python -m pip install -e .` | Install succeeds; package imports from environment |

## 5. Integration Point

- Called by: future features F03-F13 and external users after install.
- Calls: no internal logic yet.
- Side effects: creates package files, metadata, docs, and tests only.
- Model fields populated: none; Pydantic models land in F03.

Target package tree after F02:

```text
gazette_mistral_pipeline/
  __init__.py
  __version__.py
  py.typed
pyproject.toml
README.md
LICENSE
tests/
  test_package_skeleton.py
```

Target `__all__` in `gazette_mistral_pipeline/__init__.py`:

```python
__all__ = [
    "__version__",
    "parse_file",
    "parse_url",
    "parse_source",
    "write_envelope",
    "get_envelope_schema",
    "validate_envelope_json",
]
```

Stub implementation rule:

```python
def parse_file(path, *, config=None):
    raise NotImplementedError("parse_file is an F02 package skeleton stub; real implementation lands in F10 after F04-F09.")
```

Use analogous messages for the other stubs:

- `parse_url`: real implementation lands in F10 after F04-F09.
- `parse_source`: real implementation lands in F10 after F04-F09.
- `write_envelope`: real implementation lands in F10.
- `get_envelope_schema`: real implementation lands in F11.
- `validate_envelope_json`: real implementation lands in F11.

## 6. Pass/Fail Criteria

| Check | How to verify |
|-------|---------------|
| Package imports | `python -c "import gazette_mistral_pipeline; print(gazette_mistral_pipeline.__version__)"` |
| Stubs are loud | `pytest tests/test_package_skeleton.py` verifies `NotImplementedError` |
| Install metadata valid | `python -m pip install -e .` exits 0 |
| No heavy runtime deps | `pyproject.toml` has no `dependencies` or has `dependencies = []` |
| No live API | No tests call Mistral or require `MISTRAL_API_KEY` |
| Progress updated | `PROGRESS.md` marks F02 Complete and F03 Next only after tests pass |

## 7. Definition Of Done

- [x] Package directory `gazette_mistral_pipeline/` created.
- [x] `__version__.py` contains `__version__ = "0.1.0"`, `LIBRARY_VERSION`, and `SCHEMA_VERSION`.
- [x] Root package exports the seven F02 public names.
- [x] Public API stubs raise clear `NotImplementedError`.
- [x] `py.typed` exists.
- [x] `pyproject.toml` supports editable install with setuptools.
- [x] `README.md` explains current alpha skeleton status and planned pipeline.
- [x] `LICENSE` contains Apache License 2.0.
- [x] `tests/test_package_skeleton.py` covers imports, stubs, metadata, and file existence.
- [x] `python -m pytest tests/test_package_skeleton.py` passes.
- [x] `python -m pip install -e .` passes.
- [x] `PROGRESS.md` updated with F02 complete, F03 next, Gate 3 partial/import status if appropriate, and a session log row.

## 8. Open Questions And Risks

Q1. Should F02 include `pydantic` and `jsonschema` runtime dependencies now, or defer them to F03/F11?

Recommended answer: defer. F02 should be as small as possible and prove only install/import scaffolding. Add `pydantic` in F03 and `jsonschema` in F11.

Q2. Should `parse_file` already accept local PDFs even though it is a stub?

Recommended answer: yes. Keep the final public call shape now, but raise `NotImplementedError` until implementation lands.

Q3. Should the license match the Docling package?

Recommended answer: yes. Use Apache-2.0 for consistency and permissive reuse.

Q4. Should F02 create a `tests/` folder even though most real tests arrive later?

Recommended answer: yes. Start pytest structure now so F03+ can add tests incrementally.
