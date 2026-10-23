---
name: m2-package-review
description: Review a Macaulay2 (M2) package for software quality and correctness and produce an evidence-backed report whose findings are ranked by severity — public API contracts across overloads and options, mathematical boundary cases and invariants, whether tests actually test, input validation, side effects on the user's session, documentation accuracy, and external-tool handling. Use this whenever the user asks to review, audit, critique, assess, sanity-check, or find bugs in a Macaulay2 package, a .m2 file, or a change/PR to one; to prepare a package for submission to Macaulay2 or JSAG; or to compare packages' quality — even if they don't say "review" (e.g. "is this package any good?", "what's wrong with MyPackage.m2?", "anything I should fix before submitting?").
---

# Macaulay2 package review

The goal is a review a maintainer can act on. Every finding is a concrete claim about this package's
code, docs, or tests, backed by an exact excerpt with file and line numbers. Each finding states its
consequence at a calibrated strength and says how to confirm or fix it. A few consequential,
verified findings are worth more than many generic ones.

## Why the review is shaped this way

This skill distills 24 independent package reviews (305 findings), half of them on packages ranked
"best" by documentation coverage, examples, test density, and certification, and half on weaker
packages. Three results drive the design (details in `references/calibration.md`):

- **Surface metrics did not predict defects.** The top-ranked packages had as many critical and major
  findings as the others. A blind severity rating gave a median of 3.5 major-or-worse findings per review
  for the top group versus 3 for the rest. Test counts, doc coverage, certification, version
  numbers, and reputation tell you little about correctness, so don't grade by them. Read the code.
- **Severe defects cluster in a few places.** These are degenerate and boundary inputs, the seams between
  convenience overloads or wrappers and the implementation they delegate to, documentation that
  misstates a return shape, tests that don't check what they claim to, and the defining
  invariants of mathematical representations. The Required passes target exactly these.
- **The one static trait that tracked curated quality was explicit validation.** Top-ranked packages
  call `error` about four times as often per line of implementation. Missing boundary checks are worth
  looking for deliberately.

## Tiers

- **Required** — every review, whatever its size. A review that skips one is incomplete; if the
  user's scope forces a skip, say so in the report.
- **Important** — do by default. Skip only when the user narrowed the scope or the package has
  nothing relevant (e.g. no external tools), and list what you skipped.
- **Optional** — do when asked, when time allows, or when an earlier pass points at something that
  deserves a deeper look.

Effort should follow consequence: most of the time goes into the Required passes. Detailed questions
and real defect shapes for every pass are in `references/checklist.md`. Read the section for a pass
before doing it.

## Step 1 — Map the package (Required)

Run the triage scanner on the entry file or package directory:

```bash
python3 -I <skill-dir>/scripts/m2_package_scan.py path/to/MyPackage.m2      # or the directory
python3 -I <skill-dir>/scripts/m2_package_scan.py path/to/MyPackage --json  # machine-readable
```

It follows `load`/`needs` from the entry file and stops each file at a top-level `end`, because that
is what Macaulay2 actually loads. It reports:

- the loaded files, plus material after `end` or never loaded;
- exports and which have no documentation `Key`;
- methods that take options;
- TEST blocks and their assertions;
- `error` density;
- external and file operations;
- doc nodes whose Outputs disagree with the declared return type (D1), or that have no example (D2);
- exported functions that no TEST mentions;
- candidate locations for recurring mechanical defects.

**Treat every candidate as a lead, not a finding.** The scanner exists because a holistic read misses
one-character slips buried in long files. Examples: `===` typed for `=`, a misspelled strategy string in a
test, `///TEST` instead of `TEST ///`, a string key read where a symbol key was written. It cannot
see semantic defects, and those are most of the severe ones.

Then:

1. Read the `newPackage` header: version, certification, `PackageImports`/`PackageExports`,
   `Configuration` options, `AuxiliaryFiles`.
2. Check whether execution is possible with `command -v M2`. This decides whether pass I5 can run. If
   M2 isn't on the PATH, treat it as unavailable unless the user says where it is. Don't search the
   filesystem for it: a `find /` can run for many minutes and stalls the review.
3. Plan the reading by size.
   - **Up to ~1,500 implementation lines:** read all implementation, all tests, and the docs of every export.
   - **Larger packages:** read every overload of every exported method, the core algorithms, and all
     test registration. Docs and tests usually can't all be read, so direct the sampling instead of
     reading whatever comes first. Without direction, reviewers of large packages read a few dozen of
     several hundred doc nodes and skipped whole test files. See "Directed sampling" below.
     Record what you read and what you sampled; it goes in the report's limitations.

**Directed sampling (large packages).** Do these in addition to any random sample:

- **Docs.**
  - Read the doc node of every function that has a finding or a scanner candidate. Its documented
    contract is part of judging that finding.
  - Read every node the scanner flags with D1 or D2, the package overview, and the nodes of the
    main entry points: the functions the overview and the examples call most.
  - For every other exported method, still compare its Outputs and Usage with the code (shape,
    type, number of outputs). That check is quick even when you don't read the prose.
- **Tests.**
  - Read every TEST block that mentions a function with a finding, so you can say whether the
    defect is covered and whether the test encodes the wrong behavior.
  - Use the scanner's "never mentioned in any TEST" list for coverage. Report the risky entries;
    don't list them all.
  - Sample the remaining blocks for oracle strength.
4. Code after `end` and files never loaded are not package behavior; don't report their code as
   defects. Tests or docs stranded there **are** a finding: they never run or install.

## Step 2 — Required passes

**R1. Public API contracts.** For each exported method, list every installed overload: signature,
whether it has an options handler, what it delegates to, and what each branch returns. Then check:

- Options are accepted and forwarded through every wrapper, not dropped or forwarded only partially.
- Every branch returns the declared and documented kind of object. Watch for a final `if` with no `else`, or `print` used where `error` belongs.
- No dispatch signature is installed twice (the later one silently wins).
- An option that changes a callee's return shape is handled by its callers.
- Equivalent input forms (List vs Graph, Ideal vs Module, bundled vs expanded arguments) behave the same.
- Inputs, Outputs, and Usage in the docs match the actual shape: sequence vs list vs hash table, ring vs ideal, row vs column, dimensions, index base.
- Producers and consumers agree on keys and tuple shapes.
- Sibling overloads share guards and edge handling: if the two-argument form handles constants, zero, or empty input, the one-argument form should too.
- Operations on the package's types are closed: arithmetic and other operators on a package type return that type, not a plain List or Matrix that loses its behavior.
- Transformations carry every attribute: applying a ring map, base change, simplification, or copy keeps the degree, ring, ambient data, options, and metadata the result needs. Feeding a function its own output (applying it twice) is a cheap way to test this.
- Option constraints also apply to data the user supplies: if `MonomialType => "SquareFree"` restricts generated monomials, a non-squarefree starting ideal must be rejected or documented.

**R2. Boundary and invariant correctness.** For each public operation, ask what happens on the
degenerate inputs of its domain:

- empty, zero, and unit cases;
- edgeless or isolated elements;
- one variable, dimension zero, degree zero;
- the ambient or whole-space case;
- non-final positions;
- characteristic 2 or small p;
- non-pure, lower-dimensional, or non-generic data;
- a search whose target doesn't exist;
- a cached `null`.

Check that representations keep their defining invariants. Examples:

- the idempotents of a product ring sum to 1;
- `M^0` is the identity;
- interval bounds are conservative;
- random coordinate changes are invertible;
- equality and products account for every component of the object;
- symmetry pruning is applied only to a symmetric search space.

Also look for the mechanical slips the scanner flags, and the ones it can't flag: a normalized value
computed but the raw one used, a counter moving away from its bound, a variable set on only one branch,
a validation result computed and then ignored.

*Boundary sweep (Required for the central functions).* Audits of earlier reviews found that
boundary cases were the most common miss, even though the cases were on the checklist: reviewers
applied the list from memory rather than systematically.

- Pick the 5–10 central exported functions: those the overview and examples use, and the
  constructors everything else builds on.
- Walk each one through the degenerate cases in the checklist's boundary table. Include the
  function's own output fed back in, and user-supplied seed data that an option is supposed to
  constrain.
- Record each function-case pair with its outcome in the review JSON's `boundary_sweep`: `ok`
  (traced, handled), `finding` (give the id), `unclear` (couldn't trace), or `n/a`. The table makes the
  coverage auditable; a row saying `ok` is a claim you traced.

*Name the assumption.* For every search or shortcut (doubling, bisection, early exit, symmetry
pruning, a "generic" fast path), write down the property it relies on, such as monotonicity,
termination, or invariance, and check that the mathematics guarantees it on the documented domain.
For every representation round trip (to a matrix and back, lift and push forward, serialize and
read), check that offsets, degree shifts, the ring, quotient relations, and attributes survive.

**R3. Test effectiveness.** Evaluate tests; don't count them.

- **Registration:** are they registered at all, or stranded after `end` or in unloaded files?
- **Assertion:** does each block assert its comparisons, or does it compute a result (or just `time` it) and check nothing?
- **Oracle strength:** independent expected values, known identities, or an alternative algorithm are strong. Round trips and invariants are medium. Counts, types, and "no error" are weak.
- **Sensitivity:** would the test still pass if the option were ignored, the branch deleted, or both strategy names resolved to the same code path?
- **Negative tests:** do they check for the intended error, or accept any exception?
- **Randomness:** are seeds fixed? Do assertions assume a result size or property that valid output need not have?
- **Coverage:** does it reach the risky paths found in R1 and R2, such as wrappers, non-default options, and boundary inputs?

**R4. Verify before reporting.** For every candidate, from the scanner or your own reading:

- Follow it through guards, callers, and docs before claiming it.
- Read enough surrounding code to rule out a check performed elsewhere.
- Never infer a bug from a TODO, an old comment, a low test count, or an unusual idiom alone.
- A documented, explained restriction is a design choice. Report it only if the code contradicts the documented promise, or if it is an unenforced restriction that leads to silent wrong answers.
- State certainty honestly. **Definite** means it follows directly from the text or control flow. **Probable** means a strong static argument whose observable effect still needs a run. **Speculative** means a plausible risk only.
- Static inspection never proves correctness or passing tests. Say "not executed".
- **Check the language semantics a claim depends on.** For example, M2 compares strings with digit
  runs compared numerically, so `"3.9.4" < "3.10"` is true and version checks with `<` are correct.
  If a claim rests on semantics you haven't confirmed, look for evidence before reporting it: other
  code that relies on the same behavior, the documentation, or the interpreter source. Otherwise
  mark it probable.
- **Absolute claims need every path checked.** Before writing "always", "never", "only", or "hidden",
  check every route: printing, `net`/`expression`, Verbose output, cached and fresh calls, and every
  overload.
- **A repro must use documented-valid input.** A failure on input that violates a stated
  precondition shows misuse, not a defect.
- **Check a proposed fix against the whole contract.** A fix that over-constrains other call sites
  or the documented domain is worse than describing the requirement and leaving the patch to the
  maintainer.

**R5. Calibrate and report.** Assign each finding a severity (rubric below) and a certainty. Then
self-check, because under-rating was the most common calibration error in audits. These are at least
**Major**: global side effects on code outside the package, documented options or limits silently
ignored, wrong results on documented input, and a broken output contract of a public function. Re-read
every Moderate or Minor finding in those categories against the rubric. Include
the strengths worth preserving, such as good tests, careful validation, or clear contracts.
Maintainers need to know what not to break. There are no quotas: don't invent weaknesses for
balance, and don't pad with style nits.

Write the review as JSON following `references/report-template.md`. Cite evidence as file and line
ranges, then render it:

```bash
python3 -I <skill-dir>/scripts/render_report.py review.json --root <dir containing the package> --out review.md
```

The renderer quotes every excerpt verbatim from the source, writes the excerpts back into the JSON,
validates the fields, and produces the Markdown report. Don't type excerpts by hand or write your own
generator. Each finding's quoted evidence is at most 8 lines: for a longer citation, set
`quote_start`/`quote_end` to the lines that show the problem, or put the location in `also_at`.
If the renderer reports errors, fix the JSON and rerun it; it writes nothing until the review is valid.

## Step 3 — Important passes

**I1. Input validation and errors.**

- Public entry points should reject malformed input with `error`, and the message should name the requirement.
- Check every element, not just the first, and check before dereferencing.
- Enumerated option values need a final `else error`.
- Numeric options need their domain checked (positive tolerance, positive count).
- An impossible request must not return a valid-looking result, such as a zero ideal or an empty decomposition.
- Library code should never `read` from the terminal.
- The scanner lists exported functions with no `error` on any path they reach, and flags those that take
  options or several arguments (V1). Start with those, but also check the options of functions that do
  raise errors elsewhere: reaching an `error` somewhere is not the same as validating every input.

**I2. Session state, side effects, and output.**

- `use` in package code; ring variables the user can't access (built from `local` symbols instead of `getSymbol` or `monoid`).
- Overrides of core methods (e.g. reinstalling `random Type`), and session or global flags whose current value depends on earlier calls.
- Configuration of other packages at load time.
- Caches: what keys them, whether partial results are kept apart from complete ones, and whether derived objects inherit stale or sentinel entries. Check also whether every mutator (`set…`, `add…`, `force…`) invalidates every cache entry that depends on what it changes. The scanner's S8 and S9 point at candidates.
- Dependency seams. A method installed on a function and on types the package doesn't own may
  replace an existing method in Core or an imported package, changing it for every user. The
  scanner's S7 reports collisions it can confirm in the imported packages' sources and lists the
  rest for you to check. When a finding depends on a dependency's behavior, read that dependency's
  code rather than assuming it.
- `setRandomSeed` called without the user asking.
- Output not gated by `Verbose`/`debugLevel`, and degraded or partial results signalled only by printed text.

**I3. Documentation accuracy and usability.**

- Every export (functions, types, options) has a page with an example.
- Outputs give the mathematical meaning as well as the type.
- No contradictions: docs vs code, overview vs method page, example comment vs prose, a Usage line that calls a different function.
- Probabilistic answers, termination preconditions, unsupported domains, and cost warnings appear on the method's own page.
- Examples show how to interpret or verify a result.

**I4. External tools and files** (when the package shells out or writes files).

- Program discovery and version gating.
- Commands assembled from unquoted strings; exit status not checked.
- Temporary files never removed, or removed only on success.
- Parsers that break on empty sections or end-of-file.
- `value` applied to file contents (code execution).
- Serializers that can't represent what the constructors build.
- External calls made even when there is no work.

**I5. Confirm by execution** (only if `M2` is available). Write a minimal repro for each candidate
of severity 1 or 2 and run it. Use `M2 --script repro.m2`, or run the package tests with `check "Pkg"`.
For side effects, compare `listUserSymbols` before and after. Record the observed output in the finding
and upgrade or downgrade its certainty. Without M2, put the repro in the finding so the maintainer can
run it.

**I6. Second reviewer, then verification.** Important for packages with more than about 2,000
implementation lines (the scanner's count), packages that other packages import, and any package
headed for publication or a JSAG submission. For other packages it's optional: run it if the user asks
for a thorough review or the first pass found little.

Independent reviewers miss different things, and a reviewer can't see its own blind spots. In a trial
on two packages that already had a first review, a second pass added 6 and 10 findings, including two
verified critical defects. A verifier then changed a third of those findings' severities and corrected
one mechanism, so the second pass is only trustworthy once it has been checked.

1. After rendering your review (R5), spawn a fresh agent that gets only the package path and your
   findings' titles, and follows `references/second-reviewer.md`.
2. Spawn another fresh agent to verify every critical and major finding of the second pass (moderate
   ones too if the budget allows), following that file's "Verification" section.
3. Merge the verified findings into your review as described there, and re-render it.

If you can't spawn agents, say so in the report and skip I6. Doing the second pass yourself repeats your
own blind spots, which defeats its purpose. Budget about 1.5 times the first review. The second pass
costs about as much as the first review, and verification adds about 40% of a first review on top. On
packages of about 5,000 loaded lines, the first review took 350–430k tokens, the second pass 380–450k,
and verification 160–185k.

## Step 4 — Optional passes

- **O1. Performance and scalability (static).** Look for immutable lists or matrices grown in loops, repeated single-item `delete`, full enumeration (`subsets`, `permutations`) before a small selection, repeated identical expensive calls, and recomputation of loop invariants. Report these as static observations, and raise severity only on main paths with realistically large inputs.
- **O2. Maintainability and design.** Look for duplicated logic across related constructors, dead or commented-out code, unused helpers, magic numbers and hard-coded limits, functions doing two jobs, and intermediate results without a proper type.
- **O3. Language-specific style guide.** Check conformance with `references/style-guide.md`, a local copy of the official guide; prefer the URL in its header when you can fetch it. This covers naming, argument order, multiple returns as sequences, layout, documentation prose, and JSAG rules. Report these as a short separate list unless the user asked for a style review.
- **O4. Independent oracles.** Cross-check a combinatorial or mathematical claim by brute force, for example a small Python enumeration, or by comparing two strategies in M2.
- **O5. Fixes.** Propose regression tests or patches for confirmed findings, but don't edit the package unless asked.

## Severity rubric

Judge each finding by its consequence for a user calling the public API as documented, assuming the
finding is true.

| Severity | Meaning |
|---|---|
| **1 Critical** | A plausibly wrong mathematical or numerical result, an unsound certificate, or silent data loss on supported input; or a main documented path that returns nothing or crashes on ordinary input. |
| **2 Major** | A broken public contract users will hit. Examples: a crash or wrong shape on supported but less common input or option combinations; options or resource limits silently ignored; global side effects on unrelated code; docs that direct users to misuse a function; a test that fails to enforce its intended check on an important path. |
| **3 Moderate** | Poor diagnostics for invalid input, unsolicited output, leaked temp files, low-consequence doc errors or gaps, weak tests on secondary paths, avoidable work with a plausible real cost. |
| **4 Minor** | Allocation overhead with no evidence it dominates, dead code, cosmetic maintainability issues. |

## Calibration reminders

- Separate what the code does from what it means for users. Say "static observation; not measured"
  for performance, and "candidate; requires execution" for mathematical consequences you couldn't run.
- Quote exact lines. Don't paraphrase code inside an excerpt or silently elide part of it.
- Prefer one well-traced finding over three shallow variants of it. Group repeated instances of a
  pattern into one finding that lists all their locations.
- Package names and references belong in the report. Absolute paths from your scratch area don't.
