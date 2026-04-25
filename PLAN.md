# Gazette OCR ETL Plan

## Purpose

Build a Python ETL library for processing gazette PDFs using Mistral OCR.

The library takes PDFs, sends them through Mistral OCR, stitches the returned page markdown together, and parses that markdown into a structured JSON envelope that can be loaded into a database or another downstream system.

## 1. Input

The pipeline starts with PDFs only.

PDFs may come from:

- A PDF URL
- A local PDF file
- A folder of local PDFs
- A manifest listing PDF URLs or local PDF paths

## 2. OCR With Mistral

Each PDF is sent to the Mistral OCR API.

Mistral returns OCR JSON containing page-level markdown and metadata.

## 3. OCR JSON Handoff

The Mistral OCR JSON is the handoff between OCR and Python processing.

It may be:

- Kept in memory
- Written to disk
- Stored elsewhere

The best option depends on the run size, debugging needs, and whether the output needs to be reused without calling Mistral again.

## 4. Stitch Markdown

Python reads the Mistral OCR JSON, extracts each page's markdown, orders the pages, and stitches them into a single markdown document.

The stitched markdown can include page separators or page index headers to make debugging and review easier.

## 5. Parse Markdown To Envelope JSON

Python parses the stitched markdown into a structured JSON envelope.

The envelope should capture:

- Gazette notice numbers
- Dates
- Notice text and raw markdown
- Tables where possible
- Source metadata
- Processing stats
- Other gazette attributes added later

## 6. Downstream Use

The final envelope JSON is the stable output of the ETL.

It can then be sent to:

- A database
- Object storage
- A search index
- Any other downstream system

## Core Idea

PDFs go into Mistral. Mistral returns OCR JSON. Python stitches the markdown and parses it into a structured envelope. The envelope is the load-ready artifact.
