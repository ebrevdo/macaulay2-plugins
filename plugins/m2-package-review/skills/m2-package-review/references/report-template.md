# Report template

Write the review as JSON, then render it with `scripts/render_report.py`. The renderer quotes
every excerpt from the source, validates the JSON, and writes the Markdown report described at the
end of this file. Cite lines; never type excerpts by hand.

```bash
python3 -I <skill-dir>/scripts/render_report.py review.json --root <dir containing the package> --out review.md
python3 -I <skill-dir>/scripts/render_report.py review.json --root <dir> --check   # verify only
```

`--root` is the directory the evidence paths are relative to: for a package at
`.../packages/MyPackage.m2` with auxiliary files in `.../packages/MyPackage/`, pass `.../packages` and
cite paths like `MyPackage.m2` or `MyPackage/core.m2`.

## JSON schema

```json
{
  "package": "MyPackage",
  "snapshot": "1.2 (path or commit)",
  "executed": false,
  "execution_note": "optional: what was run, or why nothing was",
  "passes": {
    "required": ["R1", "R2", "R3", "R4", "R5"],
    "important": ["I1", "I2", "I3", "I6"],
    "optional": [],
    "skipped": {"I4": "no external tools or file I/O", "I5": "M2 not available"}
  },
  "summary": "3-5 sentences: what the package does well, the most consequential problems, what to fix first. No numeric grade.",
  "findings": [
    {
      "id": "F01",
      "severity": 2,
      "certainty": "definite",
      "certainty_note": "optional: what would confirm it",
      "kind": "api-contract",
      "title": "The claim itself, not the topic",
      "evidence": [
        {"file": "MyPackage.m2", "start_line": 120, "end_line": 126},
        {"file": "MyPackage.m2", "start_line": 300, "end_line": 340, "quote_start": 312, "quote_end": 315, "note": "the caller"}
      ],
      "also_at": [{"file": "MyPackage/tests.m2", "start_line": 88, "end_line": 88, "note": "test asserting the wrong value"}],
      "what_happens": "What the code, docs, or tests actually do, traced through guards and callers.",
      "why_it_matters": "The consequence for a user or maintainer, at the strength the evidence supports.",
      "confirm_or_fix": "How to confirm it (observed output, if executed) and a suggested fix or regression test.",
      "repro": "optional M2 code:\nneedsPackage \"MyPackage\"\nf(...)"
    }
  ],
  "strengths": [
    {"title": "Tests compare against independent expected values", "note": "optional", "evidence": [{"file": "MyPackage.m2", "start_line": 900, "end_line": 910}]}
  ],
  "boundary_sweep": [
    {"function": "myConstructor", "case": "empty list", "outcome": "ok"},
    {"function": "myConstructor", "case": "ring with no variables", "outcome": "finding", "finding": "F03"},
    {"function": "transform", "case": "own output fed back in", "outcome": "unclear", "note": "depends on Core's prune"}
  ],
  "style_notes": ["optional (pass O3): `MyPackage.m2:40` uses class x === T; use instance"],
  "limitations": [
    "Read in full: ... Sampled: ... (which doc nodes and test blocks). Not read: ...",
    "Static only; M2 not executed. Dependencies not inspected beyond ..."
  ],
  "next_steps": ["Ordered by severity and ease: the fixes and regression tests that retire the most risk."]
}
```

Field rules (the renderer enforces them and writes nothing until they hold):

- **Required finding fields:** `id`, `severity`, `certainty`, `kind`, `title`, `evidence`,
  `what_happens`, `why_it_matters`, `confirm_or_fix`.
- **`severity`:** 1 Critical, 2 Major, 3 Moderate, 4 Minor (rubric in SKILL.md).
- **`certainty`:** `definite`, `probable`, or `speculative`.
- **`kind`:** one of correctness, api-contract, documentation, tests, robustness-validation,
  state-side-effects, performance, external-lifecycle, maintainability.
- **`evidence`:** each item quotes at most 8 lines. For a longer cited range, set
  `quote_start`/`quote_end` (inside the range) to the lines that show the problem, or move the
  location to `also_at`, which is listed but not quoted. `also_at` entries are citation objects or
  `"file:line"` / `"file:a-b"` strings, and they are validated against the source like evidence.
  Strength evidence is listed by location only.
- **Text fields** (`title`, `what_happens`, `why_it_matters`, `confirm_or_fix`, `repro`, `summary`, and the
  entries of `limitations` and `next_steps`) must be strings. A review that fails validation leaves any
  previously rendered files untouched.
- **`boundary_sweep`:** one row per (central function, degenerate case) traced in R2. `outcome` is
  `ok`, `finding` (with the finding's `id`), `unclear`, or `n/a`. The renderer warns if the sweep is missing.
- **`excerpt` fields:** the renderer fills them in. A hand-written excerpt that differs from the
  source is replaced, with a warning.

Guidance:

- Order doesn't matter in the JSON; the renderer sorts by severity, then certainty.
- One finding per root cause. List every location of a repeated pattern under that finding
  (`evidence` for the ones worth quoting, `also_at` for the rest) instead of repeating the finding.
- Use package-relative paths and 1-based inclusive line ranges.
- Keep the summary honest when the package is good: "no critical issues found in the parts
  reviewed" is a valid result, provided `limitations` says what those parts were.

## What the renderer produces

~~~markdown
# <Package> — package review

**Snapshot:** … · **Executed:** no
**Passes completed:** Required R1, …; Important …; Optional …
**Skipped:** I5 (M2 not available); …

**Findings:** 1 critical · 3 major · 5 moderate · 2 minor

## Summary
…

## Findings

### Major

#### F01. <title>
**Severity:** 2 Major · **Certainty:** definite · **Kind:** api-contract
**Where:** `MyPackage.m2:120-126`, `MyPackage.m2:300-340` — the caller

```m2
<exact lines>
```

**Also at:** `MyPackage/tests.m2:88` — test asserting the wrong value
**What happens.** …
**Why it matters.** …
**Confirm / fix.** …

## Boundary sweep
| Function | Case | Outcome | Note |
…

## Strengths worth preserving
- **<title>** (`MyPackage.m2:900-910`)

## Style-guide notes
## Coverage and limitations
## Suggested next steps
~~~
