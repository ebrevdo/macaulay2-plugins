#!/usr/bin/env python3
"""Regression tests for the review scripts. Run: python3 -I tests/run_tests.py (from the plugin directory)."""
import json, os, re, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.environ.get('M2REVIEW_SCRIPTS') or os.path.join(HERE, '..', 'skills', 'm2-package-review', 'scripts')
PKGS = os.path.join(HERE, 'fixtures', 'pkgs')
failures = []

def check(name, cond, detail=''):
    print(('ok   ' if cond else 'FAIL ') + name + ('' if cond else f'  ({detail})'))
    if not cond:
        failures.append(name)

def run(script, *args):
    return subprocess.run([sys.executable, '-I', os.path.join(SCRIPTS, script), *args], capture_output=True, text=True)

# --- scanner: lexical context, terminators, test accounting, package ownership
r = run('m2_package_scan.py', os.path.join(PKGS, 'Foo.m2'), '--json')
check('scanner exits 0', r.returncode == 0, r.stderr[-300:])
j = json.loads(r.stdout); s = j['summary']
check('load inside a TEST body is not a package load', s['loaded_files'] == ['Foo.m2'], s['loaded_files'])
check('load inside a block comment is not followed', 'Foo/blockhelper.m2' in s['m2_files_not_loaded'], s['m2_files_not_loaded'])
check('file loaded by a TEST is reported as such', s['files_loaded_by_tests'] == ['Foo/helper.m2'], s['files_loaded_by_tests'])
check('"-*" inside a string does not hide later code', s['exported_functions'] == 2, s['exported_functions'])
check('indented `end` stops loading', [p['line'] for p in s['not_loaded_after_end']] == [17], s['not_loaded_after_end'])
check('TEST after `end` is not counted', s['tests'] == 2, s['tests'])
check('assert inside a block comment is not counted', s['asserts'] == 1 and s['tests_without_assert'] == 1, (s['asserts'], s['tests_without_assert']))
check('T1 flags the test whose only assert is commented out',
      [h['loc'] for k, v in j['candidates'].items() if k.startswith('T1') for h in v] == ['Foo.m2:9'])
check('sibling packages are not reported as unloaded package files', 'Bar.m2' not in s['m2_files_not_loaded'], s['m2_files_not_loaded'])

# --- scanner: brackets and strings, deferred loads, test helpers, coverage, doc size
r = run('m2_package_scan.py', os.path.join(PKGS, 'Baz.m2'), '--json')
check('scanner exits 0 on Baz', r.returncode == 0, r.stderr[-300:])
j = json.loads(r.stdout); s = j['summary']
check('a "(" inside a string does not hide a top-level end', [p['line'] for p in s['not_loaded_after_end']] == [28], s['not_loaded_after_end'])
check('a load inside a function body is deferred, not followed', s['loaded_files'] == ['Baz.m2', 'Baz/conditional.m2'], s['loaded_files'])
check('deferred loads are reported', s['deferred_loads'] == ['Baz.m2:7 -> ./Baz/deferred.m2'], s['deferred_loads'])
check('exports of an unexecuted helper are not counted', s['exports'] == 2, s['exports'])
check('test helpers are parsed end-aware, following nested loads', s['tests'] == 2 and s['asserts'] == 1, (s['tests'], s['asserts']))
check('"assert" inside a string literal is not an assertion', s['tests_without_assert'] == 1 and
      [h['loc'] for k, v in j['candidates'].items() if k.startswith('T1') for h in v] == ['Baz.m2:22'])
check('functions exercised only in test helpers count as tested', s['exported_functions_never_in_tests'] == ['lazy'], s['exported_functions_never_in_tests'])
check('files reached from TEST helpers are listed', s['files_loaded_by_tests'] == ['Baz/helper.m2', 'Baz/nested.m2'], s['files_loaded_by_tests'])
check('documentation contents count toward doc size', s['doc_lines'] >= 7, s['doc_lines'])

r = run('m2_package_scan.py', os.path.join(PKGS, 'Qux.m2'), '--json')
s = json.loads(r.stdout)['summary']
check('a "..." string spanning lines does not unbalance brackets', [p['line'] for p in s['not_loaded_after_end']] == [6] and s['tests'] == 0,
      (s['not_loaded_after_end'], s['tests']))

# --- scanner: option coverage, tests registered from files, skipped tests, runs of slashes
r = run('m2_package_scan.py', os.path.join(PKGS, 'Opts.m2'), '--json')
check('scanner exits 0 on Opts', r.returncode == 0, r.stderr[-300:])
j = json.loads(r.stdout); s = j['summary']
check('TEST get(...) counts as a test, with the asserts in its file', s['tests'] == 4 and s['asserts'] == 6, (s['tests'], s['asserts']))
check('files registered by TEST get(...) are not reported as unloaded', s['m2_files_not_loaded'] == [] and
      s['files_loaded_by_tests'] == ['Opts/test-get.m2', 'Opts/test-aux.m2'], (s['m2_files_not_loaded'], s['files_loaded_by_tests']))
check('a no-check-flag test is counted as skipped and flagged T6', s['tests_skipped'] == 1 and
      [h['loc'] for k, v in j['candidates'].items() if k.startswith('T6') for h in v] == ['Opts.m2:15'])
check('a function used only in a skipped test counts as untested', s['exported_functions_never_in_tests'] == ['optC'], s['exported_functions_never_in_tests'])
check('options: only top-level keys count, and diagnostic options are exempt', s['exported_options'] == 4, s['exported_options'])
check('options never set in any TEST are listed', s['options_never_in_tests'] == ['optA: Never'], s['options_never_in_tests'])
check('options set only on another method are listed', s['options_set_elsewhere_in_tests'] == ['optA: Elsewhere'], s['options_set_elsewhere_in_tests'])
check('C6 does not mistake TypicalValue or a nested key for an option',
      not [h for k, v in j['candidates'].items() if k.startswith('C6') for h in v if 'TypicalValue' in h['note'] or 'Inner' in h['note']])
check('an even run of slashes does not end a /// string', not [k for k in j['candidates'] if k.startswith('T4')] and s['tests'] == 4, list(j['candidates']))

# --- scanner: test coverage table
r = run('m2_package_scan.py', os.path.join(PKGS, 'Opts.m2'), '--test-coverage')
check('--test-coverage exits 0', r.returncode == 0, r.stderr[-300:])
tc = json.loads(r.stdout); cov = {t['function']: t for t in tc['functions']}
check('coverage counts running and skipped tests', (tc['running'], tc['skipped']) == (3, 1), (tc['running'], tc['skipped']))
check('coverage leaves the timing for the reviewer', tc['total_time'] is None and tc['slowest_test'] is None)
check('every exported function gets a coverage row', sorted(cov) == ['optA', 'optB', 'optC', 'optD', 'optE'], sorted(cov))
check('a function counts as tested by a running TEST, a TEST get file, or an auxiliary file',
      [cov[f]['running_tests'] for f in ('optA', 'optD', 'optE')] == [1, 1, 1], cov)
check('a function used only in a skipped test has no running test, and no assertion', cov['optC']['running_tests'] == 0 and cov['optC']['asserts_on_result'] == 'no', cov['optC'])
check('options set on the call are told apart from the rest, and diagnostic options are left out',
      (cov['optA']['options_set_in_tests'], cov['optA']['options_not_set']) == (['Tested'], ['Elsewhere', 'Never']), cov['optA'])
check('sorting options is left to the reviewer, unless there are none', cov['optA']['options_tested'] is None and cov['optC']['options_tested'] == [], cov['optC'])

# --- scanner: documentation audit, in both documentation formats
r = run('m2_package_scan.py', os.path.join(PKGS, 'Docs.m2'), '--doc-audit')
check('--doc-audit exits 0', r.returncode == 0, r.stderr[-300:])
au = {t['function']: t for t in json.loads(r.stdout)}
check('every exported function gets a table', sorted(au) == ['docA', 'docB', 'docC', 'docD'], sorted(au))
check('an option page keyed by method counts as documented and described',
      [(it['documented'], it['described']) for it in au['docD']['items'] if it['item'] == 'OwnPage'] == [('yes', 'yes')], au['docD']['items'])
rows = {(it['kind'], it['item']): (it['documented'], it['described']) for it in au['docA']['items']}
check('a SimpleDoc option with text is described', rows[('option', 'Written')] == ('yes', 'yes'), rows)
check('a SimpleDoc option with only a type is listed but not described', rows[('option', 'NameOnly')] == ('yes', 'no'), rows)
check('a declared option missing from the docs is not documented', rows[('option', 'Absent')] == ('no', 'no'), rows)
check('a SimpleDoc input with text is described', rows[('input', 'n')] == ('yes', 'yes'), rows)
check('a SimpleDoc output with only a type is not described', rows[('output', 'ZZ')] == ('yes', 'no'), rows)
rows = {(it['kind'], it['item']): (it['documented'], it['described']) for it in au['docB']['items']}
check('an old-style input with text is described', rows[('input', 'n')] == ('yes', 'yes'), rows)
check('an old-style output with only a type is not described', rows[('output', 'ZZ')] == ('yes', 'no'), rows)
check('examples and canned examples are counted', (au['docA']['examples'], au['docA']['canned_examples'], au['docB']['examples']) == (2, 1, 1),
      (au['docA']['examples'], au['docA']['canned_examples'], au['docB']['examples']))
check('See also: own and imported functions count; itself, listed ones, comments and preloaded packages do not',
      au['docA']['see_also_missing'] == ['bar'], au['docA']['see_also_missing'])
check('See also: an old-format page is checked too', au['docB']['see_also_missing'] == ['docA'], au['docB']['see_also_missing'])
check('a function with no page has undocumented items and no example',
      au['docC']['examples'] == 0 and all(it['documented'] == 'no' for it in au['docC']['items']) and {it['kind'] for it in au['docC']['items']} == {'input', 'output'}, au['docC'])
check('judgment cells are left for the reviewer', all(it['limits'] is None and it['correct'] is None for it in au['docA']['items'])
      and au['docA']['examples_correct'] is None)

# --- renderer: validation before writing, also_at checks, atomic outputs
good = {"package": "Foo", "summary": "Fixture.", "snapshot": "0.1", "executed": False,
        "passes": {"required": ["R1"], "important": [], "optional": []},
        "findings": [{"id": "F01", "severity": 2, "certainty": "definite", "kind": "api-contract", "title": "t",
                      "evidence": [{"file": "Foo.m2", "start_line": 4, "end_line": 5}],
                      "also_at": ["Foo.m2:6", {"file": "Foo.m2", "start_line": 2, "end_line": 2, "note": "export"}],
                      "what_happens": "w", "why_it_matters": "y", "confirm_or_fix": "z"}],
        "boundary_sweep": [{"function": "fooA", "case": "zero", "outcome": "finding", "finding": "F01"}],
        "strengths": [], "limitations": ["fixture"]}
with tempfile.TemporaryDirectory() as d:
    jp, mp = os.path.join(d, 'r.json'), os.path.join(d, 'r.md')
    json.dump(good, open(jp, 'w'))
    r = run('render_report.py', jp, '--root', PKGS, '--out', mp)
    check('renderer accepts a valid review', r.returncode == 0, r.stderr[-300:])
    out = json.load(open(jp))
    check('renderer quotes excerpts verbatim', out['findings'][0]['evidence'][0]['excerpt'] == 'fooA = method()\nfooA ZZ := ZZ => n -> n + 1')
    check('boundary sweep is rendered', '## Boundary sweep' in open(mp).read())
    before = (open(jp).read(), open(mp).read())
    for label, mutate in [('non-string text field', lambda f: f.update(what_happens=['x'])),
                          ('also_at to a missing file', lambda f: f.update(also_at=[{"file": "Nope.m2", "start_line": 1, "end_line": 1}])),
                          ('also_at with a bad range', lambda f: f.update(also_at=['Foo.m2:999'])),
                          ('also_at that is not a citation', lambda f: f.update(also_at=['somewhere in the docs'])),
                          ('evidence longer than the quote limit', lambda f: f.update(evidence=[{"file": "Foo.m2", "start_line": 1, "end_line": 20}]))]:
        bad = json.loads(json.dumps(good)); mutate(bad['findings'][0]); json.dump(bad, open(jp, 'w'))
        r = run('render_report.py', jp, '--root', PKGS, '--out', mp)
        check(f'renderer rejects {label}', r.returncode != 0, r.stdout[-200:])
        check(f'rejected review leaves the previous report untouched ({label})', open(mp).read() == before[1])
        open(jp, 'w').write(before[0])
    bad = json.loads(json.dumps(good)); bad['executed'] = 'false'; json.dump(bad, open(jp, 'w'))
    r = run('render_report.py', jp, '--root', PKGS, '--out', mp)
    check('renderer rejects a non-boolean "executed"', r.returncode != 0, r.stdout[-200:])
    open(jp, 'w').write(before[0])

    # report layout: severity word only, limitations and coverage apart, one table per exported function
    row = {"item": "n", "kind": "input", "type": "ZZ", "documented": "yes", "described": "yes", "limits": "n/a", "correct": "yes"}
    table = {"function": "fooA", "examples": 1, "examples_correct": "yes", "see_also_missing": [], "items": [row]}
    audited = json.loads(json.dumps(good)); audited['coverage'] = ['Read everything.']; audited['doc_audit'] = [table]
    json.dump(audited, open(jp, 'w'))
    r = run('render_report.py', jp, '--root', PKGS, '--out', mp)
    rep = open(mp).read()
    check('renderer accepts a documentation audit', r.returncode == 0, r.stderr[-300:])
    check('severity is shown as a word, without its number', '**Severity:** Major ·' in rep and '2 Major' not in rep)
    check('a finding explains itself before showing where it is',
          rep.index('**What happens.**') < rep.index('**Why it matters.**') < rep.index('**Confirm / fix.**') < rep.index('**Where:**') < rep.index('```m2') < rep.index('**Also at:**'))
    check('limitations and coverage are separate sections', '## Limitations' in rep and '## Review coverage' in rep and 'Coverage and limitations' not in rep)
    check('the audit table is rendered before the coverage section', rep.index('### `fooA`') < rep.index('## Review coverage') and '| `n` | input, ZZ | yes |' in rep)
    check('renderer warns about an exported function with no table', 'fooB' in r.stderr, r.stderr[-300:])
    audited['doc_audit'] = [dict(table, function='fooB'), table]
    json.dump(audited, open(jp, 'w'))
    r = run('render_report.py', jp, '--root', PKGS, '--out', mp)
    check('no warning once every exported function has a table', 'no table' not in r.stderr, r.stderr[-300:])
    for label, change in [('an unfilled cell', lambda t: t['items'][0].update(limits=None)),
                          ('a "no" with no finding', lambda t: t['items'][0].update(described='no')),
                          ('a finding that does not exist', lambda t: t['items'][0].update(described='no', finding='F99')),
                          ('a See-also gap with no finding', lambda t: t.update(see_also_missing=['bar'])),
                          ('a function with no example and no finding', lambda t: t.update(examples=0, examples_correct='n/a')),
                          ('an unknown item kind', lambda t: t['items'][0].update(kind='return'))]:
        bad = json.loads(json.dumps(audited)); change(bad['doc_audit'][0]); json.dump(bad, open(jp, 'w'))
        r = run('render_report.py', jp, '--root', PKGS, '--out', mp)
        check(f'renderer rejects {label}', r.returncode != 0, r.stdout[-200:])
    bad = json.loads(json.dumps(audited)); bad['doc_audit'][0]['items'][0].update(described='no', finding=['F01']); json.dump(bad, open(jp, 'w'))
    r = run('render_report.py', jp, '--root', PKGS, '--out', mp)
    check('a "no" pointing at a real finding is accepted', r.returncode == 0, r.stderr[-300:])

    # test coverage table: every exported function has a row, gaps point to findings
    cov_row = {"function": "fooA", "running_tests": 1, "asserts_on_result": "yes", "options_tested": [], "options_not_tested": []}
    covered = json.loads(json.dumps(audited))
    covered['test_coverage'] = {"running": 1, "skipped": 0, "total_time": "0.1 s", "slowest_test": "0.1 s (check 0)", "functions": [cov_row]}
    json.dump(covered, open(jp, 'w'))
    r = run('render_report.py', jp, '--root', PKGS, '--out', mp)
    rep = open(mp).read()
    check('renderer accepts a test coverage table', r.returncode == 0, r.stderr[-300:])
    check('the test coverage section comes before the documentation audit', '## Test coverage' in rep and rep.index('## Test coverage') < rep.index('## Documentation audit'))
    check('the suite line and a row are rendered', '**Tests:** 1 running, 0 skipped · **Total:** 0.1 s · **Slowest:** 0.1 s (check 0)' in rep and '| `fooA` | 1 | yes | none | none |' in rep, rep[-600:])
    check('renderer warns about an exported function with no coverage row', 'test_coverage has no row for exported function(s): fooB' in r.stderr, r.stderr[-300:])
    for label, change in [('a null timing', lambda c: c.update(total_time=None)),
                          ('an unfilled assertion cell', lambda c: c['functions'][0].update(asserts_on_result=None)),
                          ('unsorted options', lambda c: c['functions'][0].update(options_tested=None)),
                          ('a function with no running test and no finding', lambda c: c['functions'][0].update(running_tests=0)),
                          ('an untested option with no finding', lambda c: c['functions'][0].update(options_not_tested=['Opt'])),
                          ('a coverage finding that does not exist', lambda c: c['functions'][0].update(options_not_tested=['Opt'], finding='F99')),
                          ('coverage that is not an object', lambda c: c.clear())]:
        bad = json.loads(json.dumps(covered)); change(bad['test_coverage'])
        if not bad['test_coverage']:
            bad['test_coverage'] = ['not an object']
        json.dump(bad, open(jp, 'w'))
        r = run('render_report.py', jp, '--root', PKGS, '--out', mp)
        check(f'renderer rejects {label}', r.returncode != 0, r.stdout[-200:])
    bad = json.loads(json.dumps(covered)); bad['test_coverage']['functions'][0].update(options_not_tested=['Opt'], finding='F01'); json.dump(bad, open(jp, 'w'))
    r = run('render_report.py', jp, '--root', PKGS, '--out', mp)
    check('an untested option pointing at a real finding is accepted', r.returncode == 0, r.stderr[-300:])
    open(jp, 'w').write(before[0]); open(mp, 'w').write(before[1])
    r = run('render_report.py', jp, '--root', PKGS, '--out', os.path.join(d, 'missing-dir', 'r.md'))
    check('an unwritable report path fails without touching the JSON', r.returncode != 0 and open(jp).read() == before[0], r.stderr[-200:])
    fenced = json.loads(json.dumps(good)); fenced['findings'][0]['confirm_or_fix'] = '```m2\nfooA 1\n```\nFix: guard it.'
    json.dump(fenced, open(jp, 'w'))
    r = run('render_report.py', jp, '--root', PKGS, '--out', mp)
    check('a fenced code block in a text field starts on its own line', r.returncode == 0 and '**Confirm / fix.**\n\n```m2' in open(mp).read(), r.stderr[-200:])
    open(jp, 'w').write(before[0])
    for label, text in [('text after a closing fence', 'Run:\n```m2\nfooA 1\n``` Then guard it.'),
                        ('a fence written mid-line', 'Run: ```m2\nfooA 1\n```\nThen guard it.'),
                        ('an unclosed fence', '```m2\nfooA 1')]:
        bad = json.loads(json.dumps(good)); bad['findings'][0]['confirm_or_fix'] = text; json.dump(bad, open(jp, 'w'))
        r = run('render_report.py', jp, '--root', PKGS, '--out', mp)
        out = open(mp).read()
        body = out[out.index('**Confirm / fix.**'):]
        fences = [l for l in body.split('\n') if l.strip().startswith('```')]
        check(f'renderer normalizes {label}', r.returncode == 0 and len(fences) % 2 == 0 and all(l.strip() in ('```', '```m2') for l in fences), fences)
        open(jp, 'w').write(before[0])
    check('no temporary files left behind', not [f for f in os.listdir(d) if '.tmp-' in f], os.listdir(d))

# --- md_to_pdf: styled HTML always; a real PDF when a PDF engine is installed
with tempfile.TemporaryDirectory() as d:
    md = os.path.join(d, 'r.md')
    open(md, 'w').write('# Title\n\n| a | b |\n|---|---|\n| 1 | `x` |\n\n```m2\nf = x -> x\n```\n')
    r = run('md_to_pdf.py', md, '--html')
    page = open(os.path.join(d, 'r.html')).read() if r.returncode == 0 else ''
    check('md_to_pdf writes styled HTML with tables and code', '<table' in page and '<pre' in page and '@page' in page, r.stderr[-200:])
    rep = os.path.join(d, 'rep.md')
    open(rep, 'w').write('# R\n\n**Findings:** 1 critical · 1\nminor\n\n## Findings\n\n### Critical\n\n'
                         '#### F01. Bad thing\n\n**Severity:** Critical · **Certainty:** definite · **Kind:** correctness\n'
                         '**Where:** `Foo.m2:4-5`\n\nRelated to F02.\n\n### Minor\n\n#### F02. Small thing\n\n'
                         '**Severity:** 4 Minor · **Certainty:** probable\n')
    r = run('md_to_pdf.py', rep, '--html', '--source-url', 'https://example.org/pkgs/')
    page = open(os.path.join(d, 'rep.html')).read() if r.returncode == 0 else ''
    check('md_to_pdf wraps findings in severity-colored cards', 'class="finding sev-1"' in page and 'class="finding sev-4"' in page)
    check('md_to_pdf shows the severity word only, in new and old reports', '>Critical</span>' in page and '>Minor</span>' in page and '4 Minor' not in page)
    check('md_to_pdf links finding ids in running text', 'class="xref" href="#f02"' in page)
    check('md_to_pdf links file:line citations to the source', 'href="https://example.org/pkgs/Foo.m2#L4-L5"' in page)
    check('md_to_pdf links severity counts, even across a line break', 'href="#critical"' in page and 'href="#minor"' in page)
    r = run('md_to_pdf.py', md)
    if r.returncode == 2:
        print('skip md_to_pdf PDF check (no PDF engine installed)')
    else:
        pdf = os.path.join(d, 'r.pdf')
        check('md_to_pdf writes a PDF', r.returncode == 0 and open(pdf, 'rb').read(5) == b'%PDF-', r.stderr[-200:])
    # a browser that is installed but can't run (as in a sandbox) is not the same as no engine
    src = open(os.path.join(SCRIPTS, 'md_to_pdf.py')).read()
    first = re.search(r"BROWSERS\s*=\s*[\(\[]\s*'([^']+)'", src).group(1)
    bindir = os.path.join(d, 'bin'); os.mkdir(bindir)
    fake = os.path.join(bindir, os.path.basename(first))
    open(fake, 'w').write('#!/bin/sh\nexit 1\n'); os.chmod(fake, 0o755)
    os.remove(os.path.join(d, 'r.html')) if os.path.exists(os.path.join(d, 'r.html')) else None
    r = subprocess.run([sys.executable, '-I', os.path.join(SCRIPTS, 'md_to_pdf.py'), md, '-o', os.path.join(d, 'blocked.pdf')],
                       capture_output=True, text=True, env=dict(os.environ, PATH=bindir + os.pathsep + os.environ.get('PATH', '')))
    if r.returncode == 2:
        check('md_to_pdf says a browser is installed but failed, not that none was found',
              'could not make a PDF here' in r.stderr and 'no PDF engine found' not in r.stderr, r.stderr[-300:])
        check('md_to_pdf falls back to HTML when the browser fails', os.path.exists(os.path.join(d, 'blocked.html')))
    else:
        print('skip blocked-browser check (another PDF engine is installed)')

# --- packaging: both marketplaces, both manifests, versions in sync, skill frontmatter
REPO = os.path.normpath(os.path.join(HERE, '..', '..', '..'))
claude_mk = json.load(open(os.path.join(REPO, '.claude-plugin', 'marketplace.json')))
codex_mk = json.load(open(os.path.join(REPO, '.agents', 'plugins', 'marketplace.json')))
check('both marketplaces list the same plugins', sorted(e['name'] for e in claude_mk['plugins']) == sorted(e['name'] for e in codex_mk['plugins']))
for entry in claude_mk['plugins']:
    pdir = os.path.normpath(os.path.join(REPO, entry['source']))
    cm = json.load(open(os.path.join(pdir, '.claude-plugin', 'plugin.json')))
    xm = json.load(open(os.path.join(pdir, 'plugin.json')))
    name = entry['name']
    check(f'{name}: Claude marketplace source starts with ./ and exists', entry['source'].startswith('./') and os.path.isdir(pdir))
    check(f'{name}: plugin names agree across manifests and folder', cm['name'] == xm['name'] == name == os.path.basename(pdir), (cm['name'], xm['name']))
    check(f'{name}: Claude and Codex manifest versions are in sync', cm['version'] == xm['version'], (cm['version'], xm['version']))
    cx = next(e for e in codex_mk['plugins'] if e['name'] == name)
    check(f'{name}: Codex entry points at the same folder', os.path.normpath(os.path.join(REPO, cx['source']['path'])) == pdir and cx['source']['path'].startswith('./'))
    check(f'{name}: Codex entry has policy and category', all(k in cx.get('policy', {}) for k in ('installation', 'authentication')) and bool(cx.get('category')))
    for sk in sorted(os.listdir(os.path.join(pdir, 'skills'))):
        text = open(os.path.join(pdir, 'skills', sk, 'SKILL.md')).read()
        fm = text.split('---')[1] if text.startswith('---') else ''
        check(f'{name}/{sk}: SKILL.md frontmatter has name matching its folder and a description',
              f'name: {sk}' in fm and 'description:' in fm)

print(f'\n{len(failures)} failure(s)' if failures else '\nall tests passed')
sys.exit(1 if failures else 0)
