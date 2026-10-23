#!/usr/bin/env python3
"""Regression tests for the review scripts. Run: python3 -I tests/run_tests.py (from the plugin directory)."""
import json, os, subprocess, sys, tempfile
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
    r = run('render_report.py', jp, '--root', PKGS, '--out', os.path.join(d, 'missing-dir', 'r.md'))
    check('an unwritable report path fails without touching the JSON', r.returncode != 0 and open(jp).read() == before[0], r.stderr[-200:])
    check('no temporary files left behind', not [f for f in os.listdir(d) if '.tmp-' in f], os.listdir(d))

# --- md_to_pdf: styled HTML always; a real PDF when a PDF engine is installed
with tempfile.TemporaryDirectory() as d:
    md = os.path.join(d, 'r.md')
    open(md, 'w').write('# Title\n\n| a | b |\n|---|---|\n| 1 | `x` |\n\n```m2\nf = x -> x\n```\n')
    r = run('md_to_pdf.py', md, '--html')
    page = open(os.path.join(d, 'r.html')).read() if r.returncode == 0 else ''
    check('md_to_pdf writes styled HTML with tables and code', '<table' in page and '<pre' in page and '@page' in page, r.stderr[-200:])
    r = run('md_to_pdf.py', md)
    if r.returncode == 2:
        print('skip md_to_pdf PDF check (no PDF engine installed)')
    else:
        pdf = os.path.join(d, 'r.pdf')
        check('md_to_pdf writes a PDF', r.returncode == 0 and open(pdf, 'rb').read(5) == b'%PDF-', r.stderr[-200:])

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
