# Calibration: what 24 package reviews showed

The source for the claims in SKILL.md, kept so the skill's priorities can be re-examined later.

## Setup

- **Snapshot:** Macaulay2 1.26.06 (commit `a5ff8d7e`).
- **"Top" group:** 12 packages chosen as the best 4 per category by a static score: 30·doc coverage,
  20·examples per export, 20·TESTs per kLOC, 15·hygiene, 10·certification, 5·recent activity.
- **"Other" group:** 12 packages drawn at random from pools of uncertified, rarely used, unmaintained,
  or self-described experimental packages.
- **Reviews:** one fresh-context agent per package, with identical instructions and no knowledge of
  the grouping. Static only: M2 was never run. 10–14 findings each, 305 in total.
- **Severity ratings:** the 167 weakness findings were rated by another agent working blind
  (package names removed, findings shuffled) on the 1–4 rubric in SKILL.md.
- **Static metrics:** computed over loaded code only.
- **Statistics:** AUC and a permutation test per axis, with Benjamini–Hochberg correction across the
  non-circular axes.

## Results

| Axis | Top median | Other median | AUC | Separates? |
|---|---|---|---|---|
| Major-or-worse findings per review (blind) | 3.5 | 3 | 0.57 | no |
| Critical findings per review (blind) | 1 | 0 | 0.69 | no (top slightly *more*) |
| Mean severity of weaknesses (blind) | 2.35 | 2.65 | 0.38 | no |
| Strength share of findings | 0.50 | 0.46 | 0.63 | no |
| Asserts per TEST | 3.1 | 3.1 | 0.56 | no |
| Immutable-append density | 5.4/kLOC | 5.0/kLOC | 0.55 | no |
| `error` calls per kLOC of implementation | 32 | 8 | **0.90** (q≈0.01) | **yes** (20/24 by one threshold) |
| Documentation lines per export | 41 | 19 | 0.81 | weak (q≈0.15) |
| Exports | 32 | 11 | 0.79 | weak; mostly size |
| Certified (a selection input) | 10/12 | 1/12 | 0.88 | circular |
| Examples per export (a selection input) | 2.1 | 0.7 | 0.89 | circular |

## Interpretation

- The curated ranking captures **polish**: documentation, examples, certification, and explicit
  validation. Measured by blind review it does not capture **freedom from consequential defects**.
  Every top package had at least one major-or-worse finding.
- The "other" group was more uneven, not uniformly worse. It contained the single most
  defect-dense package, a certification package with four critical arithmetic and contract
  findings. It also contained very small packages with little surface for defects.
- Caveats:
  - The samples are small (12 vs 12).
  - Reviews were capped at about 14 findings, so counts saturate. A large package with many defects
    and a small package with a few both report about 7 weaknesses.
  - A single blind rater did the severity scoring.
  - Everything was static.

## Where severe defects actually were (blind ratings, 80 findings at severity 1–2)

- **Correctness at boundaries and in representation invariants** (the largest group). Examples:
  edgeless graphs, zero-dimensional varieties, degree-zero generators, coordinates in non-final
  positions, lineality spaces ignored, a missing sum-of-idempotents relation, non-conservative
  interval norms.
- **API contracts between wrappers and implementations.** Examples: dropped or partially forwarded
  options, a wrapper that returns `null` on its default path, a hash key the producer never writes,
  return shapes that change under an option.
- **Documentation that misdirects.** Examples: the wrong return shape or type, a Usage line calling
  another function, overview prose contradicting the method signature.
- **Tests that look like coverage but aren't.** Examples: an unregistered `///TEST`, a comparison
  that is never asserted, strategy comparisons that run the same code path because of a misspelling,
  option tests insensitive to the option.
- **Session side effects.** Examples: a core `random` method replaced at load time, `use` in package
  code, global flags whose value depends on call history.

## Scanner validation

On these 24 packages the triage scanner flagged all 37 mechanical defects the reviewers had reported
that are within its reach. It also flagged one they missed: an internal overload reading the string
key `"Vertices"` from an object that stores the symbol key `Vertices`.

## Audits of the reviews (October 2026)

Three static audits checked samples of the reviews: two of the original study, and one of six reviews
written with this skill. They found no disproved bug claims; reviews were precise. Recall was the
problem: every audited review missed at least one defect. The misses clustered in:

- **Boundary inputs:** a ring with no variables, a zero-dimensional factor, a one-term complex, a
  one-row matrix, empty systems, a function's own output fed back in.
- **Overload and transformation seams:** sibling overloads with different edge handling, operators
  returning plain lists, ring maps dropping a map's degree, refinement dropping the ambient system.
- **Representation round trips and caches:** offsets lost in matrix conversion, quotient relations
  lost by lifting, a mutator that clears some caches but not others.
- **Dependency seams:** a reinstalled method of an imported package.

Calibration errors were mostly under-rating: global side effects and broken output contracts rated
Moderate or Minor. These led to the Required boundary sweep, "name the assumption", the transformation
and closure rules, the severity self-check, and scanner checks C9, C10, S7, S8 and S9. On the 30
packages examined, those checks catch every instance of their patterns that the audits identified.

Audits can be wrong too. One audit claim, that a Normaliz version check comparing `"3.9.4" < "3.10"`
was false, was itself wrong: M2 compares digit runs in strings numerically (`strnumcmp` in
`d/scclib.c`). That case is why R4 asks for the language semantics behind a claim to be confirmed,
and why there is no scanner check for version-string comparisons.

## Second-reviewer trial (October 2026; the pass is now I6)

The second-reviewer pass was run on two packages that already had a first review, DGAlgebras and MultiprojectiveVarieties.
A fresh agent saw only the package and the first review's finding titles. A second fresh agent then
verified the new critical and major claims (and most moderate ones) against the source.

| | DGAlgebras | MultiprojectiveVarieties |
|---|---|---|
| First review | 20 findings | 16 findings |
| New findings in the second pass | 10 (1 critical, 6 major, 3 moderate) | 6 (1 major, 4 moderate, 1 minor) |
| Verified | 7 of 7 checked confirmed | 4 confirmed, 1 partly (mechanism wrong) of 5 checked |
| Severity changed by the verifier | 3 (one up to critical, two down) | 1 (down) |
| Cost (pass + verification) | ~640k tokens | ~535k tokens |

The second pass found more than the outside audit had. The audit's one miss per package reappeared
among the new findings, but those two are contaminated: the skill had gained rules aimed at them.
The uncontaminated gains include two verified critical defects in DGAlgebras:

- `semifreeResolution` documents H₀(F) = M, which is impossible over the default Koszul DG algebra
  unless mM = 0.
- DG submodules compute the homology of a free cover of their generators.

They also include a verified major defect in MultiprojectiveVarieties: base change to positive
characteristic copies dominance and birationality flags that reduction can invalidate.

None of the 12 checked claims was refuted. But a third of the severities moved and one mechanism
was wrong, so the second pass's findings deserve the same verification before they are trusted.
