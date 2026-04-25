# Data Quality And Confidence Scoring

## Purpose

Confidence scoring flags risky parser output without making the parser heavy or dependent on LLMs.

Scores are diagnostic. They should help downstream users decide what needs review.

## Principles

- Prefer fast deterministic rules.
- Do not call external services for scoring in version 1.0.
- Keep per-notice scores explainable.
- Add reasons whenever a score is reduced.
- Preserve raw markdown so low-confidence notices can be reviewed.

## Score Groups

Per-notice scoring should cover:

- Notice number shape.
- Notice boundary quality.
- Notice body structure.
- Table extraction quality.
- OCR/text quality signals.
- Optional spatial hint quality.

Document-level scoring should aggregate:

- Mean notice confidence.
- Minimum notice confidence.
- Notice count.
- Warning count.
- OCR quality signals.
- Spatial hint availability.

## Notice Number Score

High confidence:

- Numeric notice number with a typical length.
- Header matches `GAZETTE NOTICE NO.` or common OCR variants.

Lower confidence:

- Missing notice number.
- Single-digit notice number.
- Very long number.
- Non-numeric number.
- Header recovered from noisy OCR.

## Boundary Score

Signals that reduce confidence:

- Notice body is very short.
- Notice does not end cleanly.
- Large gap to next notice.
- Header was inferred instead of matched.
- Same notice number appears multiple times.

## Structure Score

Positive signals:

- Legal marker such as `IN EXERCISE`, `IT IS NOTIFIED`, `WHEREAS`, or `TAKE NOTICE`.
- Date line.
- Signature or office holder line.
- Extracted table.

Negative signals:

- No legal marker, date, signature, or table.
- Only header text.
- Very long notice that may have swallowed multiple notices.

## Table Score

Table confidence should consider:

- Header row present.
- Consistent column count.
- Non-empty rows.
- Continuation rows merged cleanly.
- Raw markdown table preserved.

Tables should remain attached to the notice that contains them.

## Optional Spatial Hints

Mistral response JSON may include:

- Page dimensions.
- Image coordinates.
- Table coordinates.
- Other positioned elements depending on response shape.

These hints can improve confidence and traceability, but they do not replace markdown parsing.

Spatial hint scoring should record:

- Whether coordinates are available.
- Count of positioned elements.
- Page dimensions.
- Any inferred relation between images/tables and page or notice context.

If coordinates are absent, set spatial availability to false and do not penalize the core parser heavily.

## Confidence Bands

Suggested bands:

- High: `0.85` to `1.00`
- Medium: `0.60` to `<0.85`
- Low: `<0.60`

These thresholds are initial defaults and should be calibrated against real gazette samples.

## Regression Rule

Regression tests should track:

- Notice count.
- Notice IDs.
- Table count.
- Warning count.
- Mean confidence.
- Minimum confidence.

Small confidence shifts can be acceptable if notice boundaries and IDs remain stable. Any ID instability must be reviewed.
