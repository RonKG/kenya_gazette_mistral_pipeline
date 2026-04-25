# F16 Spec: Exclude Post-Notice Tail

## 1. Goal

Keep non-official post-notice material in joined markdown, but exclude it from parsed `Notice` objects so advertisements, catalogues, subscription notes, and Government Printer boilerplate do not become part of the final gazette notice.

## 2. Input/Output Contract

| Aspect | Specification |
|--------|---------------|
| Function or module | `gazette_mistral_pipeline.notice_parsing` |
| Input source | F06 stitched joined markdown, ideally after F15 page running-header cleanup |
| Output shape | Same `ParsedMarkdownResult` and `Notice` models; final notice `raw_markdown` and `text` stop before detected non-notice tail |
| Joined markdown behavior | Preserve full joined markdown unchanged, including advertisements and subscription pages |
| Raw cache behavior | Do not mutate `.raw.json` |
| Parser behavior | Only exclude tail material from notices; do not delete actual `GAZETTE NOTICE NO...` sections |

## 3. Links To Canonical Docs

| Doc | Why it matters |
|-----|----------------|
| `docs/library-contract-v1.md` | Notices are a public bundle output and should contain official notice content |
| `docs/library-roadmap-v1.md` | F07 notice parsing defines notice boundaries |
| `docs/known-issues.md` | Parser limitations should be documented and tested conservatively |
| `specs/F15-clean-page-running-headers.md` | F15 should run first because page headers can confuse final notice boundary detection |
| `PROGRESS.md` | Tracks F16 as a planned cleanup feature after F15 |

## 4. Observed Problem

Many Kenya Gazette PDFs include non-notice material after the last gazette notice. In the 2009 cached OCR output, the last official detected notice is:

```text
GAZETTE NOTICE NO. 13493

CHANGE OF NAME
...
MOSI & COMPANY,
Advocates for Hellen Lily Namvua Hendriks,
formerly known as Hellen Lily Namvua Mbelle.
```

After that, `joined.md` continues with publication sales/catalogue and subscriber information:

```text
## Index 61

THE KENYA GAZETTE
11th December, 2009

NATIONAL DEVELOPMENT PLAN 2002-2008
...
Price: KSh. 750
...
## Index 62

# NOW ON SALE
...
## Index 63

# NOW ON SALE
...
# IMPORTANT NOTICE TO SUBSCRIBERS TO THE KENYA GAZETTE
...
## SUBSCRIPTION AND ADVERTISEMENT CHARGES
...
Government Printer.
```

Because the parser currently slices the final notice from its `GAZETTE NOTICE NO...` heading to end-of-document, the final notice can absorb this unrelated tail.

## 5. Proposed Boundary Rules

The parser should identify a post-notice tail boundary after the last detected gazette notice.

Conservative rules:

- Apply only to content after the last detected `GAZETTE NOTICE NO...` section.
- Prefer cutting at an F06 page boundary (`---` plus `## Index N`) after the final notice.
- Cut only when the candidate tail contains strong non-notice markers and no later gazette notice heading.
- Preserve all tail content in joined markdown.
- Do not apply this logic to earlier notices unless a later feature explicitly expands the scope.

Strong non-notice markers:

- `NOW ON SALE`
- `IMPORTANT NOTICE TO SUBSCRIBERS`
- `SUBSCRIPTION AND ADVERTISEMENT CHARGES`
- `ADVERTISEMENT CHARGES`
- `SUBSCRIPTION CHARGES`
- `Government Printer`
- `Catalogue of Government Publications`
- repeated publication price-list patterns such as many `Price: KSh.` entries

Avoid treating normal notice content as tail:

- `CHANGE OF NAME` notices are official notices when preceded by `GAZETTE NOTICE NO...`.
- Probate notices, transfer notices, environmental notices, and loss/change notices may look commercial but must remain notices when they have a gazette notice number.
- A single `Price:` occurrence is not enough by itself; use it only as supporting evidence with catalogue/subscriber markers or repeated price-list structure.

## 6. Test Case Matrix

| ID | Scenario | Input | Expected |
|----|----------|-------|----------|
| TC1 | Final notice followed by sales pages | Last notice then page boundary and `NOW ON SALE` | Final notice excludes sales pages |
| TC2 | Final notice followed by subscriber notes | Last notice then `IMPORTANT NOTICE TO SUBSCRIBERS` | Subscriber notes excluded |
| TC3 | Final official notice is `CHANGE OF NAME` | `GAZETTE NOTICE NO...` plus `CHANGE OF NAME` body | Change of name remains a notice |
| TC4 | Commercial-looking official notice | `GAZETTE NOTICE NO...` plus transfer/business/public comments text | Remains in notice |
| TC5 | Tail without page boundary | Last notice followed by strong marker without `## Index` | Parser may cut if marker is strong and line position is after notice body |
| TC6 | Body mentions Government Printer | Notice text mentions Government Printer but not in post-notice tail context | Body preserved |
| TC7 | Regression fixture | `tests/fixtures/gazette_2009-12-11_103.raw.json` | Last parsed notice excludes `NOW ON SALE`, subscriber notes, and ad charges |
| TC8 | Determinism | Same input parsed twice | Notice IDs and hashes are stable |

## 7. Integration Point

- Called by: `parse_joined_markdown(...)` during notice slicing.
- Likely location: add a helper that computes `effective_end` for the final notice span before `_trim_line_span(...)`.
- Candidate helper: `_post_notice_tail_start(lines: list[str], *, last_notice_start: int) -> int | None`.
- Side effects: Last notice `raw_markdown`, `text`, `content_sha256`, and possibly `notice_id` can change. This is expected for F16.
- Raw and joined artifacts: unchanged.

## 8. Pass/Fail Criteria

| Check | How to verify |
|-------|---------------|
| Official final notice is preserved | Unit tests in `tests/test_notice_parsing.py` |
| Tail material excluded from final notice | Unit and regression tests |
| Joined markdown remains complete | Tests parse from joined markdown but do not remove source text |
| No live Mistral calls | Regression uses cached raw JSON only |
| Full suite remains green | `python -m pytest` |

## 9. Definition Of Done

- [ ] Implement conservative final-notice tail detection in F07 notice parsing.
- [ ] Add unit tests for sales, subscriber, and advertisement tails.
- [ ] Add regression coverage using cached 2009 OCR fixture.
- [ ] Update docs/progress with changed notice-boundary behavior.
- [ ] Run the full test suite.

## 10. Open Questions And Risks

- Some non-notice material might be useful downstream. F16 should exclude it from `notices` only; a later feature can expose it as a separate `non_notice_tail` bundle if needed.
- Tail markers may vary across years. Start with observed examples and add more only with fixtures.
- If the final official notice genuinely contains words like "advertisement charges", an aggressive rule could truncate real content. Favor page-boundary plus strong-marker evidence.
- F16 should ideally be implemented after F15 so repeated page headers do not confuse the tail detector.
