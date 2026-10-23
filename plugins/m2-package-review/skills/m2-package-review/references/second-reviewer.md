# Second-reviewer pass and verification (I6)

You are a second, independent reviewer. A first review of this package exists; you see only its
finding titles, so that you don't repeat its work or inherit its blind spots. Your job is recall:
find consequential defects the first review missed, at the same evidence standard (R4).

Audits of first reviews found no false positives but at least one missed defect in every review.
The misses clustered in degenerate inputs, the seams between overloads and transformations,
representation round trips and caches, and dependency interactions. Spend your effort there.

## What to do

1. **Map the package** (Step 1 of SKILL.md): run the scanner and read its summary and candidates.
2. **Pick the central functions.** Choose 8–12 exported functions: constructors, the functions the
   overview and examples use, and anything other functions build on. Note which ones the first
   review's titles already cover, but don't skip them; covered functions can still have uncovered
   boundaries.
3. **Boundary sweep** (R2). For each central function, trace every applicable case in the checklist's
   boundary table and its "Macaulay2 traps" list, and record each case in `boundary_sweep`.
4. **Transformation and closure checks** (R1). For every operation that maps one package object to
   another (ring maps, base change, simplification, copying, refinement, conversion), check that the
   result keeps every attribute, that operators return package types, and that applying the operation
   to its own output works.
5. **Caches and mutators** (I2). For every mutator, check that it invalidates every cache entry that
   depends on what it changes (scanner S8, S9). For every cached value, check whether its key covers
   every input it depends on.
6. **Dependency seams** (I2). Check the scanner's S7 hits and its list of methods installed on functions
   and types the package doesn't own. For findings that depend on a dependency's behavior, read the
   dependency.
7. **Name the assumption** (R2) behind every search, early exit, or fast path in the central functions.

## What to report

- Only new findings. If a finding duplicates a first-review title, drop it. If it substantially extends
  one (a new failing input class, a higher severity justified by new evidence), report it and say which
  title it extends in `what_happens`.
- The usual JSON, rendered with `scripts/render_report.py`, with a `boundary_sweep` table covering every
  central function. In `limitations`, list the central functions you chose and what you did not reach.
- Prefer fewer well-traced findings. A static second pass that adds two verified major defects is a
  success; ten speculative ones are not.

## Verification

A second agent, fresh again, checks the second pass's findings before they join the review. It gets
the package path and the second pass's JSON (only the findings it should check). For each finding it:

- traces the cited code through callers, guards, and the documentation the finding is measured against;
- checks any mathematics the claim depends on, using a concrete input;
- gives a verdict (`confirmed`, `partially correct`, `refuted`, or `unclear`, saying what blocks a
  decision), its own severity on the rubric, the evidence, and a short explanation.

It writes a JSON list of `{"id", "verdict", "severity", "evidence", "explanation"}` and modifies nothing.

## Merging into the review

- **Confirmed:** add the finding to the review with the next free id. Use the verifier's severity when
  it differs, and set `certainty_note` to "found by the second reviewer and verified independently".
- **Partially correct:** add it with the corrected claim and mechanism from the verifier's explanation,
  and the verifier's severity.
- **Unclear:** add it only if it's consequential, with certainty `probable` or `speculative` and a note
  saying what would settle it.
- **Refuted:** drop it, and record it in `limitations` ("second-pass claim X was checked and refuted").
- **Rows:** merge the second pass's `boundary_sweep` rows into the review's table.
- **Pass list:** list I6 among the completed passes, and re-render.

## Prompts

Keep both prompts free of your own opinions about the package. The point is independent judgment.

Second reviewer:

> Run the second-reviewer pass (I6) of the m2-package-review skill on the Macaulay2 package <Name>.
> Read and follow <skill-dir>/SKILL.md and <skill-dir>/references/second-reviewer.md. The package entry
> file is <path>; its dependencies are in the same directory. The first review's finding titles are in
> <titles file>. Read only the package sources, the skill's files, and the titles file, and modify nothing.
> Write the review JSON to <out.json> and render it with the skill's render_report.py. Reply with the new
> findings per severity and the central functions you swept.

Verifier:

> Independently verify the findings <ids> of a static code review of the Macaulay2 package <Name>. The
> reviewer may be wrong; give an evidence-based verdict per finding. The sources are in <packages dir>,
> and the findings are in <second-review.json>; read only those findings. Trace each through its
> callers, guards, and documentation, and check the mathematics it depends on. Decide confirmed,
> partially correct, refuted, or unclear, and give your own severity (1 critical … 4 minor, per the
> skill's rubric). Modify nothing. Write a JSON list of {"id", "verdict", "severity", "evidence",
> "explanation"} to <verification.json>.
