# Review checklist

Questions to ask in each pass, with the shapes real defects took in published Macaulay2 packages.
The snippets are illustrative reductions of actual findings. Don't pattern-match them blindly: use
them to recognize the *kind* of problem, then verify it in context.

Contents

- [R1 Public API contracts](#r1-public-api-contracts)
- [R2 Boundary and invariant correctness](#r2-boundary-and-invariant-correctness)
- [R3 Test effectiveness](#r3-test-effectiveness)
- [R4 Verification discipline](#r4-verification-discipline)
- [I1 Input validation and errors](#i1-input-validation-and-errors)
- [I2 Session state, side effects, and output](#i2-session-state-side-effects-and-output)
- [I3 Documentation accuracy and usability](#i3-documentation-accuracy-and-usability)
- [I4 External tools and files](#i4-external-tools-and-files)
- [I5 Execution](#i5-execution)
- [O1–O3 Performance, maintainability, style](#o1o3-performance-maintainability-style)
- [Scanner check codes](#scanner-check-codes)

---

## R1 Public API contracts

Build an overload table for each exported method, e.g. with `grep -n "^\s*methodName\b"` across the
loaded files.

| signature | options handler? | delegates to | forwards opts? | returns (each branch) | documented as |
|---|---|---|---|---|---|

Ask:

- **Is every option forwarded through every wrapper?** Typical shapes:
  ```m2
  f(List,ZZ) := opts -> (L,r) -> f(L_0, L_1, L_2, r)          -- opts dropped entirely
  f(Ideal,RingElement) := o -> (I,a) -> f(module I, a, Trim => o.Trim)   -- only one option survives
  g(System) := o -> P -> g(P, x0)                               -- Verbose/tolerance lost
  ```
  Delegating with `opts` where the callee declares a different option set needs `>>` or explicit
  selection. Check that the call still dispatches.
- **Does every overload of an option-taking method accept options?** For
  `h = method(Options => {...})`, an overload written `h(List,List) := (G,S) -> ...` (with no `opts ->`)
  is inconsistent with its siblings and may fail at dispatch.
- **Does every branch return the documented kind of thing?**
  ```m2
  f(List,ZZ) := opts -> (L,r) -> (
      if opts.InputType === "A" then ( computeA(...) );   -- value discarded: not the last expression
      if opts.InputType === "B" then ( computeB(...) )    -- last expression; null when the type is "A"
  )
  ```
  Also: a branch that `print`s and falls through; an enumerated option whose unknown values fall off
  the end of a function declared `=> ZZ`; a "not implemented yet" branch inside a Boolean method.
- **Is any dispatch signature installed twice?** The later `f(ZZ,ZZ,List,ZZ) := ...` silently replaces
  the earlier one, often because two input shapes such as `{V,F,E}` and `{V,F}` were meant to share a
  signature without a length check.
- **Does an option change a callee's return shape?** For example `ReturnMingens => true` returns a
  pair instead of a hash table, and a wrapper forwards the option and then treats the result as the
  default shape.
- **Do explicit algorithm or strategy options bypass preconditions** that automatic selection
  checks? For instance, forcing the "Monomial" algorithm discards the inequations that the automatic
  path refuses to drop.
- **Do equivalent representations behave identically?** Compare List vs Graph inputs, Ideal vs
  Module, Matrix vs point, bundled vs expanded arguments, and integer vs rational parameters.
- **Do producers and consumers agree?** A consumer may read a hash key the producer never writes
  (`ac#"certifiedSolutions"` where the producer writes `"certifiedRegular"`). It may read a string key
  where a symbol key was written (`HG#"Vertices"` vs `HG.Vertices`). Or a cached value may be the
  operator alone where the consumer destructures `(operator, norm)`.
- **Do declared types match reality?** Compare the installed `:= Matrix =>` annotation, the Outputs
  section, and what is actually built (`image ...` is a Module; `map ...` is a RingMap). Check also:
  - Usage lines destructuring `(p, sols) = f(p, P)` when that overload returns one object;
  - docs saying List when the code returns PointArray, MutableHashTable, or Sequence;
  - "a single row" when the code requires a column;
  - "d-by-d" when the loops build (d+1)-by-(d+1);
  - "returns an ideal" when it returns a quotient ring;
  - "a list of elements of B" when the code returns `{element, index}` pairs.

## R2 Boundary and invariant correctness

**Degenerate inputs to try, in your head or in M2.** Choose the ones that fit the domain:

| Domain | Cases |
|---|---|
| Collections | empty list or set; singleton; duplicates; unsorted input |
| Algebra | zero ideal; unit ideal; zero module; free module; one variable; constants and degree-zero generators; the ambient-space case (e.g. a Hilbert polynomial of the whole ring); non-reduced; quotient rings; coefficient rings that aren't fields (ZZ, ZZ/n with composite n); characteristic 2 and small p |
| Combinatorics and graphs | edgeless graph; isolated vertices; disconnected input; non-pure complexes; maximal elements of mixed dimension; impossible counts (more generators requested than exist) |
| Geometry and polyhedra | lower-dimensional or not full-dimensional objects; nonzero lineality space; empty polytope; a point; ambient dimension 0 |
| Numerics | zero tolerance; exactly singular Jacobian; zero-crossing intervals; empty solution sets; numerically failed sub-steps |
| Positions and permutations | an auxiliary coordinate in a non-final position; the first vs a later term of a multi-term object |
| Searches and loops | a target that doesn't exist (unbounded doubling search); retry budgets; depth limits; windows or truncations that don't include the origin |
| Rings and spaces | a ring with no variables (`QQ[]`); a factor of dimension zero in a product of spaces; quotient rings whose relations matter to the answer |
| Complexes and maps | a complex concentrated in one degree (no differentials); maps of nonzero degree; the zero complex |
| Matrices and arrays | one row or one column; zero rows or zero columns; shapes the internal representation treats specially |
| Self-application | the function's own output fed back in (apply the operation twice, or convert there and back) |
| Seed data | user-supplied starting objects that an option is meant to constrain (a non-squarefree generator under a squarefree option) |

**Macaulay2 traps at boundaries** (silent, so easy to miss):

- **Constructors on empty lists lose the ring or the type.** `ideal {}` is an ideal of ZZ, not of the
  user's ring; `sum {}` and `product {}` are the integers 0 and 1; `complex {}` fails. When the list
  can be empty (a filter, a decomposition, the differentials of a one-term complex), the code must
  supply the ring or the zero object explicitly. A wrapper that converts its input and redispatches
  can recurse forever if the conversion returns a plain 0 for the zero case.
- **A `-1` "not found" sentinel used as an index selects the last element**, because negative indices
  count from the end. `L#(findIndex x)` silently returns a wrong element when `findIndex` returns -1.
- **Lifting drops quotient relations.** `lift`, `sub(f, ambient R)`, `exponents`, `listForm`, and `terms`
  work in the ambient ring, so tests like invariance or equality done there can reject classes that
  are equal in the quotient.
- **Internal layouts must hold for every shape.** If a type stores real and imaginary parts as rows, or
  degrees as an offset plus a matrix, every operation (scalar multiplication, products, conversions)
  must respect that layout, including one-row and empty cases.

**Defining invariants a representation must keep.** These all came up in real findings:

- A product ring `R^k` modelled with idempotents needs `sum e_i = 1`, not just `e_i^2 = e_i` and `e_i e_j = 0`.
- Zeroth powers must be the identity. Building it as `matrixCCi(id, id)` gives `1 + i` on the diagonal.
- Bounds used in certification must be conservative. A magnitude must use `max(|left|, |right|)`, not `max(left, right)`.
- Random coordinate changes must be invertible. Check the determinant or rank, or retry.
- Every trial of a modular computation shares one prime, so agreement across trials says nothing about bad reduction.
- Equality must compare every component (both fans' lineality spaces), and products must carry every component (the factors' lineality).
- Reinserting a removed coordinate at position c needs a shift, not a swap with the last position.
- Pruning by a symmetry group is valid only when the candidate set is invariant under that group.
- Truncating a table to a window must not change the meaning of the entries that remain. Check state that is initialized only when the loop starts at the origin.
- A sentinel cached for a failed computation (`rankFunction = null`) must not be used later as a value.
- Round trips must preserve offsets and shifts. Converting a Betti table to a matrix drops its lowest
  degree, and rebuilding it with the default offset moves every entry.
- Mutators must invalidate every cache entry that depends on what they change. A setter that resets some
  derived caches but not a cached product or base change leaves later calls built from the old data.

**Name the assumption behind every search or shortcut.** Doubling-then-bisection is correct only for
a monotone predicate. "Smallest a such that aD is globally generated" is not monotone in general:
Weierstrass gaps make some multiples fail after smaller ones succeed. Early exits, symmetry pruning,
and "generic case" fast paths each rely on a property; write it down and check that it holds on the
documented domain.

**Mechanical slips** (the scanner finds the first four):

```m2
if opts.TimeLimit === 0 then opts.TimeLimit === 24*60*60;     -- comparison, not assignment
for i to n-1 do if p i then ( append(acc, x) );                -- result of append discarded
assert(... Strategy => "DerkesenGandini" ...)                  -- misspelling falls back to the default strategy
x := HG#"Vertices"                                             -- string key; the object stores symbol Vertices
b := if instance(Bias, ZZ) then 1.0/Bias else Bias;  ... random 1.0 < opts.Bias   -- normalized b unused
I = 0; while H === null and I < limit do (...; I = I - 1)      -- counter moves away from its bound
if not isPolynomialRing P and isField kk then error ...        -- guard logic wrong (should be `or not`)
ok := rangeOK(d, lo, hi);  -- ...result never consulted before indexing
Real := if R =!= CC then (...);  ... apply(Real, ...)          -- unset on the default (CC) path
v := var_(ii-1)   -- in a branch where ii was never bound
```

Also look for:

- guards placed *after* the first dereference they protect;
- `last L`, `first L`, `L#0`, or `max L` on a possibly empty list;
- results that depend on the order of earlier calls.

## R3 Test effectiveness

| Question | Weak shape seen in reviews | Stronger alternative |
|---|---|---|
| Is the test registered? | `///TEST ... ///` (a string, not a test); a TEST below `end`; a test file that is never loaded | `TEST /// ... ///` in loaded code; confirm with `check` |
| Is the result asserted? | a bare `G == map(...)` as the last line; `time saturate(...)` with nothing compared | `assert(...)`, or compare the strategies' outputs to each other |
| How strong is the oracle? | `assert(#result == 4)`; `assert instance(x, Ideal)`; residuals summed over an empty result | explicit expected objects; known identities (Catalan and Bell counts, `reg O(d) = -d`, `chi2 = 2^c·length`); an alternative algorithm; reconstruction (`value decomposition == B`) |
| Would it notice the feature being removed? | testing an option by checking only the return type; checking a quantity the option can't change; comparing a strategy with itself | a fixture where the option provably changes the output, with that difference asserted |
| Does the negative test check the reason? | `assert(try (f x; false) else true)` passes on *any* error | check the message, or narrow what's inside the `try` |
| Is it robust to valid randomness? | indexing `L#1#2` of a random sample that may be shorter; requiring degree = group order when smaller degrees are valid | seed it *and* assert only properties every valid output has |
| Does it reach the risky paths? | only the expanded-argument form tested; only default options; only non-degenerate fixtures; external adapters never exercised | one test per wrapper or option seam found in R1, per boundary case found in R2, and fixture-based parsing tests for adapters |

Shared implementation weakens an oracle. When "two routes agree" but both call the same helper, say
so. A test that encodes the current wrong behavior, e.g. asserting an empty result that the docs say
should be non-empty, is a finding about the test.

## R4 Verification discipline

- Trace each candidate through its guards, its callers (including documentation examples), and the
  tests that touch it. Many apparent bugs are handled one level up.
- A private helper without a check is fine if every caller checks. Report only reachable failures.
- Distinguish:
  - *documented restriction* (fine; say so);
  - *documented restriction, not enforced, leading to silent nonsense* (a validation finding);
  - *contradicted promise* (a contract finding).
- Don't treat TODO or FIXME, "not written" comments, version numbers below 1, or low test counts as
  evidence of a defect.
- **Confirm the language semantics a claim depends on.** M2 compares strings with digit runs compared
  numerically (`strnumcmp`), so `"3.9.4" < "3.10"` and `"1.26.06" < "1.4"` evaluate correctly:
  version checks written with `<` are not a bug. When unsure, look for other code relying on the same
  behavior, the documentation, or the interpreter source before reporting.
- **Absolute claims** ("always", "never", "only Verbose shows it", "hidden") need every path checked:
  `net`, `expression`, printing, Verbose levels, cached and fresh calls, every overload.
- **Repros must use documented-valid input.** A start point that isn't a solution of the start system,
  or an ideal outside the stated domain, shows misuse rather than a defect.
- **Proposed fixes must respect the whole contract.** Check a fix against the documented domain and the
  other call sites; a check that also constrains cases outside the requested range is a new bug. If
  unsure, state the requirement instead of a patch.
- When you claim a mathematical consequence, give the concrete input you reasoned about (e.g. "over
  `QQ[x,y]`, `B=(x+y)` and `B=(x-y)` are indistinguishable to this branch") and say whether you ran it.

## I1 Input validation and errors

- Public boundaries should validate cheaply and report clearly: ring compatibility, matrix shapes,
  column counts, nonempty inputs, element types, and *every* element of a collection. The bug pattern
  is checking only `first G`.
- Enumerated string options need an explicit `else error "expected one of ..."`.
- Numeric options need domain checks: a tolerance must be positive before `1/toll`, and a trial count
  must be at least 1.
- Domain restrictions stated in the overview, such as "characteristic ≠ 2", should be enforced at the
  public entry points or repeated as a caveat on each affected method.
- Impossible or invalid requests must not look like success. Watch for:
  - an exhausted search returning `{zero ideal}`;
  - negative entries producing an empty decomposition;
  - `print "wrong inputs"` followed by returning `null`.
- Library code should not prompt (`read "Are you sure?"`) or depend on interactive answers.

## I2 Session state, side effects, and output

- `use R` inside package code rebinds the user's variables. Ring construction should use
  `getSymbol`/`monoid` so that names exposed in returned objects are accessible; `a := local a; QQ[a]`
  is not. If M2 is available, verify with `listUserSymbols` before and after.
- **Global behavior changes.** Watch for:
  - reinstalling core methods (`old = lookup(random, Type); random Type := ...`);
  - installing a broad core signature with package-specific semantics, e.g. a real-valued `matrix(BettiTally,ZZ,ZZ)`;
  - load-time `needsPackage(..., Configuration => ...)` for another package;
  - eager loading of an optional backend.
- **History-dependent state.** Examples:
  - a global flag that an earlier call sets but nothing resets;
  - a global tolerance assigned *after* objects that captured the old value were built;
  - a cache entry that only some calls populate (a function reading `P.cache.x` that it never computes).
- **Dependency seams.** A method installed on a function and on types the package doesn't own can
  replace a method that Core or an imported package already defines (e.g. a package reinstalling its
  dependency's `matrix(BettiTally,ZZ,ZZ)` to return real matrices changes that dependency's behavior for
  everyone). Check each such install against the imports (scanner S7 does this when their sources
  are available). When a finding depends on a dependency's behavior, read the dependency.
- **Caches.** Is the key complete? Are partial results (limits like DegreeLimit) kept apart from
  complete ones? When an object is transformed, are orientation-dependent entries converted or
  dropped? Are sentinel values handled?
- **Randomness.** `setRandomSeed` belongs only behind an explicit option. Randomized results need a
  validation step and a bounded number of retries.
- **Output.** `print` and `<<` should sit behind `Verbose` or `debugLevel`, and warnings belong on
  stderr. A degraded result, such as multiplicities replaced by 1 after a numerical failure, should be
  represented in the return value, not only in printed text.

## I3 Documentation accuracy and usability

- Every exported function, type, and option has a node, and every node has an affordable example.
- Outputs say what the object *is* mathematically, not just its class, and use multiple entries only
  for sequences.
- **Cross-check for contradictions:**
  - the Outputs type against the actual return;
  - the overview prose against the method page (e.g. "mode is an integer" vs String dispatch);
  - example comments against the text ("there are 244" vs "333 orbits");
  - Usage lines that call a *different* function;
  - stale statements ("partial computations are not yet cached" when they are);
  - off-by-one geometric language ("projective n-space" for n variables).
- Disclosures belong on the method's own page: probabilistic answers, preconditions whose violation
  loops forever, unsupported coefficient rings, expensive validation, and cases where the
  implementation returns less than the full object (e.g. terminal nodes printed but not returned).
- **Helpful patterns to recognize as strengths:** showing how to verify or consume a result
  (`value C == B`), explaining conventions that differ between similar APIs, stating sign and
  orientation conventions.

## I4 External tools and files

- Is the program discovered with `findProgram` and a minimum version? Are format changes between
  tool versions handled in one place?
- **Command construction:** strings concatenated into `run`, or `get "!..."`, with no quoting, breaks
  on spaces and shell metacharacters. Check for an unchecked `cd`, ignored exit status, and stderr that
  isn't captured.
- **Temporary files:** are names unique? Is cleanup done on success *and* on failure? Is there a
  documented retention option? Watch for printing a temp path as the only way to find the file.
- **Parsing:** look at empty sections, header-only sections, a header on the last line (index past
  the end), and optional row/column headers. `value` on file text evaluates code, so prefer a
  constrained parser or document the trust boundary.
- **Round trips:** can the serializer represent everything the constructors build (e.g. `null` for a
  missing property)? Is there a write→read test?
- Batch calls should skip the external process when nothing remains to compute.

## I5 Execution

If `M2` is on the PATH:

```m2
-- repro.m2  (run: M2 --script repro.m2)
needsPackage "MyPackage"
x = someCall(...)            -- the minimal failing input from the finding
print x                      -- or: assert(...) with the expected value
```

- Run the package tests with `check "MyPackage"`, or `check(n, "MyPackage")` for test n.
- Build and inspect docs with `installPackage "MyPackage"` and `viewHelp`.
- For side effects, compare `listUserSymbols` before and after the call.
- Record the exact output in the finding and update its certainty.

Without M2, include the repro so the maintainer can run it.

## O1–O3 Performance, maintainability, style

- **Performance (static).** Watch for:
  - `L = append(L, x)` or `L = L | {x}` in loops, and `L = delete(x, L)` per item (quadratic);
  - `drop(queue, 1)` used as a queue;
  - building all of `subsets`, `permutations`, or a degree slice before choosing a few;
  - evaluating the same expensive predicate twice in an `if/else if`;
  - recomputing overlapping sums;
  - building a large tower or group up front on every call.

  Separate avoidable overhead from intrinsic cost. Caching can amortize a factorial structure but
  can't make it small.
- **Maintainability.** Look for:
  - the same geometric decomposition copied into several constructors;
  - commented-out superseded implementations;
  - helpers that are defined but never used;
  - values constructed and never read;
  - magic limits (`for i to 12` prebuilding 13 levels with no bounds check).
- **Style.** See `style-guide.md` for naming, argument order, `instance(x,T)` rather than
  `class x === T`, multiple returns as sequences, no `return` on the last line, documentation prose
  rules, and JSAG requirements.

## Scanner check codes

`scripts/m2_package_scan.py` groups candidates by code. Typical precision on the 24 calibration
packages:

| Code | Lead | Precision |
|---|---|---|
| C1 | comparison used as a statement | high |
| C2 | discarded `append` or `delete` result | high |
| C3 | overload of an option-taking method without a handler | high |
| C4 | delegation that drops or narrows options | medium (forwarding via a merged table is fine) |
| C5 | duplicate dispatch signature | high |
| C6 | declared option never referenced | medium |
| C7 | string key read but never written | medium (keys produced by external tools are fine) |
| C8 | option value in tests or docs that the implementation never recognizes | high |
| C9 | a `-1` sentinel (returned or assigned) used as an index | high |
| C10 | `complex`, `ideal`, `sum`, or `product` built from a list that can be empty | medium |
| D1 | doc Outputs disagree with the declared return type (`:= T =>` or `TypicalValue`) | high |
| D2 | documentation node without an example | high as a pattern, low severity |
| V1 | exported function (taking options or several arguments) with no `error` on any path it reaches | medium; a function that reaches some `error` may still skip validating its options |
| T1 | TEST without assert | medium |
| T2 | bare comparison in a TEST | high |
| T3 | catch-all negative test | high as a pattern, low severity |
| T4 | `///TEST` | high |
| T5 | timed computation never checked | medium |
| S1 | `use` | high |
| S2 | ungated output | medium |
| S3 | override of a core method or of Type/Thing | high |
| S4 | shared configuration or random-state change | medium |
| S5 | `class x === T` | high, style |
| S6 | `local` ring symbols | low |
| S7 | reinstalls a method an imported package already defines | high (when the import's source is available) |
| S8 | a mutator (`set…`, `add…`, `force…`, …) changes an argument in a package that caches derived results | medium |
| S9 | a cache key the package's own invalidation routine never clears | medium-high |
| X1 | shell string concatenation | high |
| X2 | temp files never removed | medium |
| X3 | `value` on text | low |
| P1 | immutable growth by reassignment | high as a pattern, usually minor |
| P2 | full combinatorial enumeration | low |

The header summary also lists files after `end` that contain TEST or doc blocks, and the exported
functions that no TEST mentions (use it to direct test sampling and find coverage gaps), and methods
installed on functions and types the package doesn't own that it couldn't check against an import.
