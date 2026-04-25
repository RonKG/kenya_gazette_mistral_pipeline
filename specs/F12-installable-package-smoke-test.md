# F12 Spec: Installable Package Smoke Test

## 1. Goal

Verify that the package can be installed into a fresh environment and used through its public API offline, with package metadata, type markers, and schema package data present after installation.

## 2. Input/Output Contract

| Aspect | Specification |
|--------|---------------|
| Feature scope | Add maintainable install smoke coverage for local path installs, package metadata, root imports, package data, and a minimal offline replay parse/write/schema flow from the installed package |
| Out of scope | Parser behavior changes, envelope shape changes, Mistral API behavior changes, notebook cleanup, historical `prototype_outputs` regression expansion, CLI work, PyPI publishing, runtime dependency additions, `.env` reads, live Mistral calls, commits, and marking `PROGRESS.md` complete during spec creation |
| Primary smoke entry point | A standalone script such as `scripts/install_smoke.py` that creates a temporary virtual environment, installs the project from the local repository path, runs isolated checks inside that environment, and exits nonzero on failure |
| Pytest integration | A lightweight pytest wrapper such as `tests/test_install_smoke.py` may invoke the script behind an explicit marker, for example `pytest.mark.smoke` or `pytest.mark.slow`, so normal `python -m pytest` remains fast unless the team chooses to include the smoke in CI |
| Default test policy | Normal unit tests remain offline, do not require `MISTRAL_API_KEY`, do not read `.env`, do not make network requests, do not execute notebooks, and do not scan historical `prototype_outputs` |
| Install sources | Required: install from the local repository path into a fresh venv. Optional: install from a Git URL only when an explicit safe input is provided, such as `F12_GIT_URL`, and never as a default network action |
| Windows/local compatibility | The smoke must work on Windows and PowerShell by using the current Python executable to create the venv, deriving the venv Python path portably, and avoiding shell-specific activation scripts |
| CI compatibility | The smoke must also run on CI without secrets or network by default. It should accept a repo path and temporary work directory, write all generated files under temp directories, and clean up unless a debug flag requests preservation |
| Public imports to verify | Installed root imports must include `parse_file`, `parse_url`, `parse_source`, `write_envelope`, `get_envelope_schema`, `validate_envelope_json`, `Envelope`, `PdfSource`, `MistralMetadata`, `Notice`, `ExtractedTable`, `Corrigendum`, `ConfidenceScores`, `Provenance`, `Stats`, `LayoutInfo`, `DocumentConfidence`, `PipelineWarning`, `Bundles`, `GazetteConfig`, `MistralOptions`, and `RuntimeOptions` |
| Version check | Import `gazette_mistral_pipeline.__version__`, confirm it equals the installed distribution metadata version from `importlib.metadata.version("gazette-mistral-pipeline")`, and confirm both match `pyproject.toml` |
| Package data checks | Verify `gazette_mistral_pipeline/py.typed` and `gazette_mistral_pipeline/schemas/envelope.schema.json` are available through the installed package, preferably via `importlib.resources`, not repository-relative paths |
| Metadata checks | Inspect installed distribution metadata and `pyproject.toml` expectations: project name `gazette-mistral-pipeline`, Python requirement `>=3.10`, Apache-2.0 license text, runtime dependency list remains lightweight with `pydantic>=2.0`, and no runtime dependency is added unless this spec is revised with justification |
| Package contents checks | Confirm the installed distribution includes package modules, `py.typed`, and schema JSON, while docs, specs, tests, notebooks, `.env`, and `prototype_outputs` are not intentionally packaged as runtime files |
| Offline replay fixture | Use a tiny raw Mistral OCR JSON fixture generated inline by the smoke or stored under `tests/fixtures` if implementation prefers. It must contain one page of markdown with one notice and, if practical, one simple table |
| Minimal parse/write flow | From the fresh install, call `parse_url(...)` or `parse_file(...)` with `GazetteConfig(runtime={"replay_raw_json_path": <fixture>, "output_dir": <tmp stage dir>})`, then call `write_envelope(...)` into a temp output directory and `validate_envelope_json(...)` on the written envelope JSON |
| Local PDF handling | A temp local PDF may be used only with replay mode. The smoke must not attempt live local upload or pass a local path as `document_url` |
| Network and secret boundary | The smoke must avoid all live Mistral calls by default, must not require or read `MISTRAL_API_KEY`, must not read `.env`, and should run with environment variables cleared or guarded where practical |
| Runtime dependencies | No new runtime dependency is expected. Use stdlib, existing Pydantic dependency, existing package APIs, `venv`, `subprocess`, `importlib.metadata`, and `importlib.resources`. Dev-only helpers are acceptable only if already present or clearly isolated from runtime |

Suggested implementation shape:

```text
scripts/
  install_smoke.py      # standalone fresh-venv smoke runner
tests/
  test_install_smoke.py # optional marked wrapper that invokes the script
```

Suggested standalone runner behavior:

```text
python scripts/install_smoke.py --repo-path . --mode local-path
python scripts/install_smoke.py --repo-path . --mode wheel
python scripts/install_smoke.py --git-url <url> --mode git-url   # optional, explicit only
```

The exact command-line interface may differ, but the runner must avoid shell activation and should invoke the venv interpreter directly.

## 3. Links To Canonical Docs

| Doc | Why it matters |
|-----|----------------|
| `PROGRESS.md` | Identifies F12 as the current `Next` item and records Gate 3/Gate 5 expectations for installed import readiness |
| `docs/library-contract-v1.md` | Defines the package-root public API, envelope contract, schema helpers, bundle writer, and Git-installable target |
| `docs/library-roadmap-v1.md` | Places F12 after schema export and before notebook cleanup, with fresh venv install as the proxy for Git-install readiness |
| `docs/known-issues.md` | Requires no secret leakage, no live tests by default, explicit replay/offline behavior, and avoidance of stale notebook/output assumptions |
| `specs/SOP.md` | Requires spec-first work, standard test matrix, pass/fail criteria, Definition of Done, and no completion update before implementation/test closure |
| `specs/F10-public-api-and-bundle-writer.md` | Defines the installed parse/write behavior that the smoke verifies without changing parser or writer semantics |
| `specs/F11-json-schema-export.md` | Defines schema helper behavior and package-data requirements that the smoke verifies after install |
| `pyproject.toml` | Defines package metadata, package-data configuration, package exclusions, Python requirement, and lightweight runtime dependencies |
| `README.md` | Documents current installation expectations and public usage examples that should not drift from install smoke behavior |
| `gazette_mistral_pipeline/__init__.py` | Defines root exports that must import correctly from an installed distribution |
| `gazette_mistral_pipeline/py.typed` | Type marker that must be included in installed package data |
| `gazette_mistral_pipeline/schemas/envelope.schema.json` | Checked-in schema resource that must be accessible after install |
| `tests/test_package_skeleton.py` | Existing metadata/root import checks to preserve and extend at install boundary |
| `tests/test_public_api.py` | Existing offline replay parse behavior that the install smoke should exercise minimally from a fresh environment |
| `tests/test_schema_export.py` | Existing schema resource and validation behavior that the install smoke should verify after install |
| `tests/test_bundle_writer.py` | Existing deterministic bundle writer behavior that the install smoke should exercise in a small end-to-end path |

## 4. Test Case Matrix

| ID | Scenario | Input | Expected |
|----|----------|-------|----------|
| TC1 | Fresh local path install smoke | `python scripts/install_smoke.py --repo-path <repo> --mode local-path` on Windows/PowerShell or CI shell | Creates a temp venv, upgrades or uses available pip tooling only as needed, installs the local repository path, imports `gazette_mistral_pipeline`, confirms `__version__` and distribution metadata match, and exits zero without API key, network, `.env`, notebook, or `prototype_outputs` access |
| TC2 | Root public API import surface after install | Python executed inside the smoke venv imports all root public names from `gazette_mistral_pipeline` | All required functions and model/config exports are importable from the installed package root; `__all__` contains the same public names; imports do not depend on current working directory being the repo root |
| TC3 | Package data and schema resource after install | Installed package inspected through `importlib.resources` and `get_envelope_schema()` | `py.typed` and `schemas/envelope.schema.json` are present in installed package data; `get_envelope_schema()` loads the checked-in schema resource; schema metadata matches package constants; no repository-relative file lookup is needed |
| TC4 | Metadata, dependency, and package content inspection | Installed distribution metadata, `pyproject.toml`, and package files from `importlib.metadata.files(...)` | Project name/version/Python requirement/license metadata are correct; runtime requirements remain lightweight and include `pydantic>=2.0`; package files include modules, `py.typed`, and schema JSON; package files do not intentionally include docs, specs, notebooks, `.env`, tests, or `prototype_outputs` |
| TC5 | Wheel install or wheel artifact inspection | Build a wheel with `python -m pip wheel --no-deps --wheel-dir <tmp> <repo>` and install that wheel into a fresh venv, or inspect the wheel contents if a second venv would be too slow | Wheel contains package modules, `py.typed`, and `schemas/envelope.schema.json`; wheel excludes docs/specs/notebooks/historical outputs; installed wheel supports the same import and schema resource checks as TC2 and TC3 |
| TC6 | Minimal offline replay parse/write/schema validation from installed package | Tiny raw JSON fixture and temp output dirs created by the smoke, then installed-package code calls `parse_url(...)`, `write_envelope(...)`, and `validate_envelope_json(...)` | Returns an `Envelope` with one parsed notice, writes selected bundles under temp dirs, validates the written envelope JSON, and performs no network call, no live Mistral call, no API key lookup, no `.env` read, and no notebook execution |
| TC7 | Editable install remains useful for development | Optional smoke mode or pytest check runs `python -m pip install -e <repo>` in a temp venv | Editable install imports the same root names and loads `py.typed` and schema resources. This may be a separate marked check if keeping the default smoke faster matters |
| TC8 | Optional Git URL smoke is explicit and safe | `python scripts/install_smoke.py --git-url <url> --mode git-url` or CI job with explicit `F12_GIT_URL` | Only runs when the URL is explicitly supplied; installs from Git into a fresh venv and runs TC2, TC3, and TC6. It is skipped, not failed, when no URL is configured for offline local development |
| TC9 | Failure boundary: no secrets or live network | Smoke environment lacks `MISTRAL_API_KEY`; optional monkeypatch/subprocess guard or no-replay negative check calls `parse_url(...)` without replay and default config | The no-replay call fails before API key resolution or network access with the existing `allow_live_mistral` error. The positive smoke path never reads `.env`, never requires `MISTRAL_API_KEY`, and never calls live Mistral |
| TC10 | Failure boundary: package data omission is caught | Temporarily simulated missing resource in a focused unit test, or assertion against installed resources during smoke | Missing `py.typed` or schema JSON causes a clear smoke failure naming the missing package data instead of silently passing due to repo-root files |

Normal `python -m pytest` should remain offline and reasonably fast. If the full fresh-venv install smoke is too slow for every local run, keep it as a standalone script plus a marked pytest wrapper, and document the exact invocation in the test or README update performed during implementation.

## 5. Integration Point

- Called by:
  - Developers before closing F12.
  - CI or local release-readiness checks that need a fresh install proxy for `pip install git+...`.
  - Later F13 notebook cleanup, which can rely on installed package readiness but must not be implemented in F12.

- Calls:
  - Python stdlib `venv`, `subprocess`, `sys`, `pathlib`, `tempfile`, `json`, `importlib.metadata`, and `importlib.resources`.
  - `pip install <repo>` or `pip install <wheel>` inside the temporary venv.
  - Installed package root exports from `gazette_mistral_pipeline`.
  - Existing F10 public API and bundle writer behavior.
  - Existing F11 schema resource and validation helpers.

- Side effects:
  - Creates temporary virtual environments, raw replay fixtures, temporary local PDFs if used, stage directories, wheel directories, and bundle output directories under temp paths.
  - May create a wheel artifact under a temporary directory for inspection.
  - Does not modify package code behavior, parser logic, checked-in schema contents, notebooks, `.env`, historical `prototype_outputs`, `PROGRESS.md`, dependencies, or Git history.

- Model fields populated:
  - The smoke does not define new model fields.
  - The minimal replay flow should assert only stable envelope fields already covered by F10/F11: `source.run_name`, `mistral.raw_json_path`, `stats.page_count`, `stats.notice_count`, `notices`, `tables` when included in the fixture, `document_confidence`, `layout_info`, and `warnings`.

- Quality gate contribution:
  - F12 completion should update Gate 3 from partial to reached because root `parse_file`, `parse_url`, `parse_source`, `write_envelope`, `get_envelope_schema`, and `validate_envelope_json` work after install.
  - F12 completion should update Gate 5 from not reached to reached because fresh virtual environment install works as a proxy for Git install.
  - Gate 1 and Gate 2 may remain partial unless implementation explicitly adds broader cached-response regression fixtures, which is not required for F12.

## 6. Pass/Fail Criteria

| Check | How to verify |
|-------|---------------|
| Local path fresh install works | Run the standalone smoke against the local repo path; it creates a temp venv, installs successfully, and imports the package without relying on repo-root imports |
| Windows/PowerShell compatible | Runner invokes the venv Python executable directly and passes on Windows without using POSIX activation or shell-only syntax |
| Root API is available after install | Smoke imports and checks all required root public functions, schema helpers, model exports, config exports, and `__all__` entries |
| Version metadata is consistent | Smoke compares `gazette_mistral_pipeline.__version__`, `importlib.metadata.version("gazette-mistral-pipeline")`, and `pyproject.toml` version |
| Package data is installed | Smoke loads `py.typed` and `schemas/envelope.schema.json` through installed package resources and calls `get_envelope_schema()` |
| Package exclusions hold | Smoke or focused test confirms installed distribution does not intentionally include docs, specs, notebooks, `.env`, tests, or `prototype_outputs` as package/runtime files |
| Runtime dependencies remain lightweight | Review and tests confirm no runtime dependency is added beyond existing `pydantic>=2.0` unless this spec is revised with a clear justification |
| Wheel/package data check passes | Wheel build or inspection confirms package modules, `py.typed`, and schema JSON are present and non-package files are excluded |
| Offline replay E2E passes after install | Installed package parses a tiny replay fixture, writes selected bundles, and validates the written envelope JSON entirely under temp dirs |
| Network and secret boundaries hold | Smoke passes with no `MISTRAL_API_KEY`, does not read `.env`, does not call live Mistral, and uses explicit replay mode for parse/write checks |
| Normal test suite remains offline | `python -m pytest` still passes without API keys, network, notebook execution, or historical outputs; full smoke is marked or standalone if too slow for default runs |
| Existing behavior is preserved | Existing `tests/test_package_skeleton.py`, `tests/test_public_api.py`, `tests/test_schema_export.py`, and `tests/test_bundle_writer.py` continue passing |
| Progress gates are updated only after build/test closure | Builder updates Gate 3 and Gate 5 when F12 passes, while Gate 1/Gate 2 remain partial unless regression fixtures are deliberately added |

## 7. Definition Of Done

- [x] `specs/F12-installable-package-smoke-test.md` is approved before implementation starts.
- [x] A standalone fresh-venv install smoke runner exists and works from a local repository path without shell activation.
- [x] The smoke is suitable for Windows/PowerShell and CI/local use.
- [x] Full install smoke execution is either standalone or behind an explicit pytest marker so normal unit tests remain fast and offline.
- [x] Local path install verifies package import, version metadata, root public API names, model/config exports, `__all__`, `py.typed`, and schema package data.
- [x] Wheel build/install or wheel content inspection verifies package data and runtime package exclusions.
- [x] Optional Git URL smoke is explicit and skipped by default when no safe URL is configured.
- [x] Installed-package offline replay parse/write/schema validation works using only tiny temp fixtures and temp output directories.
- [x] Tests prove the smoke does not require `MISTRAL_API_KEY`, read `.env`, call live Mistral, execute notebooks, or depend on `prototype_outputs`.
- [x] Existing package skeleton, public API, schema export, and bundle writer tests still pass.
- [x] No runtime dependency is added unless this spec is revised with a clear justification.
- [x] F12 does not edit notebooks, implement F13 cleanup, change parser behavior, change envelope schema behavior, run live Mistral calls, commit changes, or mark `PROGRESS.md` complete during spec creation.
- [x] After implementation and successful tests, `PROGRESS.md` is updated to mark F12 complete, update Gate 3 and Gate 5, add a session log row, and leave Gate 1/Gate 2 partial unless broader regression fixtures were intentionally added.

## 8. Open Questions And Risks

Q1. Should F12 implement the smoke as pytest, a script, or both?

Recommended answer: both, but with clear separation. Use a standalone `scripts/install_smoke.py` as the canonical fresh-venv runner, and add a small marked pytest wrapper only if it helps CI discovery. Keep the full venv smoke out of unmarked fast tests if runtime is noticeable.

Q2. Should the smoke install from a Git URL by default?

Recommended answer: no. A local path fresh-venv install is the required offline proxy for Git-install readiness. Git URL install should be optional and run only when an explicit URL or CI variable is provided, because it requires network and may be branch/remote dependent.

Q3. Should F12 add `build` as a development or runtime dependency for wheel/sdist checks?

Recommended answer: no runtime dependency. Prefer `python -m pip wheel --no-deps --wheel-dir <tmp> <repo>` for a wheel/package-data check, because pip already handles the PEP 517 build environment. If a helper dependency is later desired, keep it dev-only and revise the spec first.

Q4. Should the smoke use editable install, regular local path install, wheel install, or all three?

Recommended answer: regular local path install is required because it best matches user installs. Wheel build/install or wheel inspection is strongly recommended for package-data verification. Editable install is optional as a developer convenience check and may be marked separately.

Q5. Should the offline replay smoke use `parse_url` or `parse_file`?

Recommended answer: use `parse_url` as the primary path because Git-install users are most likely to start from a URL and it avoids live local upload ambiguity. Add a temp local PDF replay check only if it stays small and does not slow the smoke materially.

Q6. Should F12 update README installation docs?

Recommended answer: yes during implementation if the smoke command or current installed API differs from the stale F02 README language. Keep the doc update narrow and do not document notebook cleanup or F13 behavior.

Q7. What is the main implementation risk?

Recommended answer: accidentally passing because imports resolve from the repository checkout instead of the installed distribution. The smoke should run installed-package checks from a temp working directory outside the repo and inspect installed distribution files/resources directly.

Q8. Are there unresolved questions that should block implementation?

Recommended answer: no. The recommended answers above are sufficient for implementation if approved.
