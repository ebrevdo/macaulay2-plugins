# macaulay2-plugins

Plugins for working with Macaulay2 packages, packaged for both Claude Code and OpenAI Codex.

## Plugins

### m2-package-review

The skill `m2-package-review` reviews any Macaulay2 package for software quality. It covers:

- public API contracts across overloads and options;
- boundary-case and invariant correctness;
- whether tests actually test;
- input validation and session side effects;
- documentation accuracy and external-tool handling.

Its passes are tiered Required, Important, and Optional; findings are rated by severity, and every
quoted excerpt is checked against the source. For large or widely used packages, it runs an
independent second reviewer and verifies that reviewer's findings.

It bundles:

- `scripts/m2_package_scan.py`, a static triage scanner (standard-library Python). It maps the code
  Macaulay2 actually loads and lists candidate locations of recurring defects for the reviewer to
  verify.
- `scripts/render_report.py`, which renders the review from its JSON. It quotes every excerpt
  verbatim from the cited lines, and validates the review before writing anything.
- `scripts/md_to_pdf.py`, which turns a report into a formatted PDF. It uses pandoc or Python-Markdown,
  and headless Chrome/Chromium/Edge, WeasyPrint, or wkhtmltopdf.
- `references/checklist.md`, the per-pass questions and real defect shapes.
- `references/report-template.md`, the review JSON schema and the rendered report structure.
- `references/second-reviewer.md`, the second-reviewer pass, its verification, and how to merge the results.
- `references/style-guide.md`, a snapshot of the official
  [Package Writing Style Guide](https://github.com/Macaulay2/M2/wiki/Package-Writing-Style-Guide).
  The wiki is the source of truth.
- `references/calibration.md`, the evidence behind the skill's priorities: the 24-package study,
  the audits, and the second-reviewer trial.

## Install

**Claude Code:**

```
/plugin marketplace add ebrevdo/macaulay2-plugins
/plugin install m2-package-review@macaulay2-plugins
```

**Codex:**

```
codex plugin marketplace add ebrevdo/macaulay2-plugins
codex plugin add m2-package-review@macaulay2-plugins
```

Either tool also accepts a local clone's path in place of `ebrevdo/macaulay2-plugins`. In Codex, `/plugins`
opens the plugin browser.

**The skill alone, in either tool:** copy or symlink
`plugins/m2-package-review/skills/m2-package-review` into `~/.claude/skills/` (Claude Code) or
`~/.agents/skills/` (Codex).

Then ask, for example, "review the package in ~/src/M2/M2/Macaulay2/packages/MyPackage.m2".

## Repository layout

```
.claude-plugin/marketplace.json     Claude Code marketplace
.agents/plugins/marketplace.json    Codex marketplace (same plugins, Codex schema)
plugins/<plugin>/
  .claude-plugin/plugin.json        Claude Code manifest
  plugin.json                       Codex manifest (agent-plugins schema)
  skills/<skill>/                   shared skill folder (SKILL.md, references/, scripts/, agents/openai.yaml)
  tests/                            regression tests for the scripts and the packaging
```

The two manifests are kept separate because the formats differ; the tests check that their names
and versions agree.

## Development

Run the regression tests, which cover the scanner, the renderer, and the packaging:

```
python3 -I plugins/m2-package-review/tests/run_tests.py
```

The scanner can also be run on its own:

```
python3 -I plugins/m2-package-review/skills/m2-package-review/scripts/m2_package_scan.py path/to/MyPackage.m2
```

## License

Apache License 2.0; see `LICENSE`. `NOTICE` covers the one piece of third-party content: the
style-guide copy is the Macaulay2 project's text.

Reviews produced with the skill, and their PDFs, are outputs rather than part of this repository, and
`.gitignore` keeps them out.
