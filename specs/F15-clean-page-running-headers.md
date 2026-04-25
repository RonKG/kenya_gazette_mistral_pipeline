# F15 Spec: Clean Page Running Headers

## 1. Goal

Remove repeated PDF running headers and footers from stitched markdown before notice parsing, so page headers such as `THE KENYA GAZETTE`, publication dates, and printed page numbers do not pollute parsed notices.

## 2. Input/Output Contract

| Aspect | Specification |
|--------|---------------|
| Function or module | `gazette_mistral_pipeline.page_normalization` |
| Input source | Mistral OCR page markdown after `normalize_mistral_pages(...)` |
| Output shape | Joined markdown with F06 document/index separators preserved, but per-page running header/footer lines removed at page boundaries |
| Raw cache behavior | Do not mutate `.raw.json` or `NormalizedPage.markdown`; raw Mistral output remains the audit source |
| Parser impact | `parse_joined_markdown(...)` should receive cleaner stitched markdown, reducing false notice tail content |
| Configuration | Default behavior should be enabled for normal package parsing unless tests show unacceptable false positives |

## 3. Links To Canonical Docs

| Doc | Why it matters |
|-----|----------------|
| `docs/library-contract-v1.md` | Joined markdown and notices are public bundle outputs |
| `docs/library-roadmap-v1.md` | F06 normalization/stitching feeds the rest of the parser |
| `docs/data-quality-confidence-scoring.md` | Intentional notice boundary changes may require review and re-pinning of notice IDs/content hashes |
| `docs/known-issues.md` | Parser limitations and OCR ordering artifacts are known operational risks |
| `PROGRESS.md` | Tracks F15 as the next feature before implementation |

## 4. Observed Problem

Mistral includes printed page running headers inside each page's `markdown`, for example:

```text
3508
THE KENYA GAZETTE
11th December, 2009
```

or:

```text
11th December, 2009
THE KENYA GAZETTE
3509
```

or:

```text
THE KENYA GAZETTE
11th December, 2009
```

When `stitch_markdown_pages(...)` joins pages unchanged, these lines appear after each `## Index N` separator. Because `parse_joined_markdown(...)` slices notices from one `GAZETTE NOTICE` heading to the next, a running header at the top of a new page can become the tail of the previous parsed notice.

Example seen in generated notices:

```text
GAZETTE NOTICE NO. 13175
...
J. N. MICHUKI,
Minister for Environment and Mineral Resources.

---

## Index 2

11th December, 2009
THE KENYA GAZETTE
3509
```

The final three lines should not be part of notice text.

## 5. Proposed Cleanup Rules

The cleaner should be conservative:

- Strip only from the first few non-empty lines or final few non-empty lines of each page markdown.
- Strip only recognizable running-header/footer tokens, not arbitrary body content.
- Preserve F06 separators such as `---`, `# Document: ...`, and `## Index N`.
- Preserve the title/contents page masthead when it is document content, especially index 0, unless a later test proves it should be removed.
- Preserve raw `.raw.json` exactly as returned by Mistral.

Initial recognizable tokens:

- `THE KENYA GAZETTE`
- Gazette publication dates such as `11th December, 2009`
- printed page numbers such as `3508`, `3509`, `3551`, when they appear together with a nearby `THE KENYA GAZETTE` token at a page boundary

Avoid removing a standalone number unless the same boundary block also contains a gazette title/date marker.

## 6. Test Case Matrix

| ID | Scenario | Input | Expected |
|----|----------|-------|----------|
| TC1 | Top header with number/title/date | Page starts `3508`, `THE KENYA GAZETTE`, date, then notice | Stitched page starts at the notice heading |
| TC2 | Top header with date/title/number | Page starts date, title, number, then notice | Header block removed |
| TC3 | Top header without page number | Page starts title, date, then notice | Header block removed |
| TC4 | Footer header at page end | Page body ends with date/title/number | Footer block removed |
| TC5 | Title page masthead | First page starts with real gazette title page and contents table | Masthead and contents page are preserved |
| TC6 | Body content mentions Kenya Gazette | Notice body says "published in the Kenya Gazette" away from boundary | Body content preserved |
| TC7 | Regression fixture | `tests/fixtures/gazette_2009-12-11_103.raw.json` | Parsed notices no longer include boundary `THE KENYA GAZETTE` header fragments in `text` |
| TC8 | Determinism | Same raw fixture processed twice | Joined markdown, notice IDs, and content hashes are deterministic |

## 7. Integration Point

- Called by: `parse_source(...)` after `normalize_mistral_pages(...)` and before `parse_joined_markdown(...)`.
- Likely location: `stitch_markdown_pages(...)` should render cleaned page markdown by default.
- Helper candidate: `clean_page_running_headers(markdown: str, *, page_index: int) -> str`.
- Side effects: Cleaner changes joined markdown, parsed notice text, notice content hashes, and notice IDs for affected pages; this is expected for F15.
- Stats: `char_count_markdown` should describe the post-cleanup joined markdown that is written to `_joined.md` and parsed into notices.
- Raw artifacts: `.raw.json` cache stays unchanged.

## 8. Pass/Fail Criteria

| Check | How to verify |
|-------|---------------|
| Boundary headers are removed from joined markdown | Unit tests in `tests/test_page_normalization.py` |
| Notice pollution is reduced | Regression test using committed 2009 cached OCR fixture |
| Existing cached fixtures remain valid | Re-run Gate 1 and Gate 2 coverage for all committed fixtures in `tests/test_cached_mistral_regression.py`; re-pin only intentional notice IDs/content hashes if needed |
| No live Mistral calls | Tests use cached raw JSON only |
| Raw cache remains unchanged | Tests assert source raw fixture is not rewritten |
| Full suite remains green | `python -m pytest` |

## 9. Definition Of Done

- [x] Implement conservative boundary cleaner in F06 normalization/stitching.
- [x] Add unit tests for known header permutations.
- [x] Add regression test on cached 2009 gazette OCR fixture.
- [x] Re-validate all committed cached regression fixtures affected by joined-markdown cleanup.
- [x] Update docs/progress with changed joined-markdown behavior.
- [x] Run the full test suite.

## 10. Open Questions And Risks

- Different gazette years may use different date/title/page-number order. Start with observed examples and add patterns only when test evidence supports them.
- Removing page headers changes notice hashes and IDs because current IDs include content hashes and line/page position. This is acceptable for a new unshipped feature branch but should be documented.
- Some pages begin with continuation text rather than a notice heading. The cleaner must remove only header tokens and leave the continuation body intact.
- If Mistral emits the printed header as part of a table or paragraph rather than standalone lines, F15 should not attempt complex layout repair.
