#!/usr/bin/env python3
"""Render a Macaulay2 package review from its JSON, quoting source excerpts exactly.

Write the review as JSON (schema in references/report-template.md) with evidence given as
file + line ranges; this script pulls each excerpt verbatim from the source, validates the
review, writes the excerpts back into the JSON, and renders the Markdown report. Never
hand-type excerpts: cite lines and let this script quote them.

Usage:
    python3 -I render_report.py review.json --root DIR [--out review.md] [--check]

--root   directory the evidence paths are relative to (e.g. the packages directory that holds
         MyPackage.m2 and MyPackage/); paths are also tried relative to DIR/<package>/.
--out    Markdown output path (default: the JSON path with .md).
--check  only verify that excerpts already in the JSON match the source; write nothing.
--max-lines N  quoted lines allowed per finding citation (default 8).

Exits non-zero, writing nothing, if any citation is invalid or a required field is missing.
"""
import argparse
import json
import os
import re
import subprocess
import sys

MAX_LINES = 8
SEVERITY = {1: 'Critical', 2: 'Major', 3: 'Moderate', 4: 'Minor'}
CERTAINTY = ('definite', 'probable', 'speculative')
KINDS = ('correctness', 'api-contract', 'documentation', 'tests', 'robustness-validation',
         'state-side-effects', 'performance', 'external-lifecycle', 'maintainability')
REQUIRED = ('id', 'severity', 'certainty', 'kind', 'title', 'evidence',
            'what_happens', 'why_it_matters', 'confirm_or_fix')
OUTCOMES = ('ok', 'finding', 'unclear', 'n/a')
AUDIT_CELLS = ('yes', 'no', 'unclear', 'n/a')
AUDIT_KINDS = ('input', 'output', 'option')


class Sources:
    def __init__(self, root, package):
        self.root, self.package, self.cache = root, package, {}

    def lines(self, rel):
        for cand in (os.path.join(self.root, rel), os.path.join(self.root, self.package, rel)):
            if os.path.isfile(cand):
                if cand not in self.cache:
                    with open(cand, encoding='utf-8', errors='replace') as f:
                        self.cache[cand] = f.read().split('\n')
                return self.cache[cand]
        return None


def quote_range(ev):
    """Lines to quote: quote_start..quote_end if given (quote_end defaults to quote_start), else the cited range."""
    qa = ev.get('quote_start', ev['start_line'])
    return qa, ev.get('quote_end', qa if 'quote_start' in ev else ev['end_line'])


def quote(src, ev, where, errors, strict):
    """Return (excerpt, truncated) for an evidence item, or None after recording an error.

    The cited range is start_line..end_line. The quoted lines are quote_start..quote_end when
    given (they must lie inside the cited range); otherwise the cited range itself. In strict
    mode (findings) the quoted lines may not exceed MAX_LINES, so a long citation must say which
    lines to quote; in lenient mode (strengths) the first MAX_LINES are quoted.
    """
    for k in ('file', 'start_line', 'end_line'):
        if k not in ev:
            errors.append(f'{where}: evidence needs file, start_line, end_line (missing {k})')
            return None
    lines = src.lines(ev['file'])
    if lines is None:
        errors.append(f"{where}: file not found under --root: {ev['file']}")
        return None
    a, b = ev['start_line'], ev['end_line']
    if not (isinstance(a, int) and isinstance(b, int) and 1 <= a <= b <= len(lines)):
        errors.append(f"{where}: bad line range {ev['file']}:{a}-{b} (file has {len(lines)} lines)")
        return None
    qa, qb = quote_range(ev)
    if not (isinstance(qa, int) and isinstance(qb, int) and a <= qa <= qb <= b):
        errors.append(f'{where}: quote_start/quote_end {qa}-{qb} must lie inside the cited range {a}-{b}')
        return None
    if strict and qb - qa + 1 > MAX_LINES:
        errors.append(f"{where}: {ev['file']}:{a}-{b} is {b - a + 1} lines; quote at most {MAX_LINES}. "
                      'Add quote_start/quote_end for the lines that show the problem, or move the long range to also_at.')
        return None
    chunk = lines[qa - 1:qb]
    truncated = len(chunk) > MAX_LINES
    text = '\n'.join(chunk[:MAX_LINES]).rstrip('\n')
    if not text.strip():
        errors.append(f"{where}: {ev['file']}:{a}-{b} is blank")
        return None
    return text, truncated


def check_location(src, x, where, errors):
    """Validate a location that is listed but not quoted (also_at, style notes)."""
    if isinstance(x, dict):
        if not all(k in x for k in ('file', 'start_line', 'end_line')):
            errors.append(f'{where}: needs file, start_line, end_line')
            return
        f, a, b = x['file'], x['start_line'], x['end_line']
    elif isinstance(x, str):
        m = re.fullmatch(r'`?([^`\s:]+):(\d+)(?:-(\d+))?`?(?:\s+.*)?', x.strip())
        if not m:
            errors.append(f'{where}: {x!r} is not a file:line citation; use {{"file", "start_line", "end_line", "note"}}')
            return
        f, a = m.group(1), int(m.group(2))
        b = int(m.group(3)) if m.group(3) else a
    else:
        errors.append(f'{where}: must be a citation object or a "file:line" string')
        return
    lines = src.lines(f)
    if lines is None:
        errors.append(f'{where}: file not found under --root: {f}')
    elif not (isinstance(a, int) and isinstance(b, int) and 1 <= a <= b <= len(lines)):
        errors.append(f'{where}: bad line range {f}:{a}-{b} (file has {len(lines)} lines)')


def check_types(review, errors):
    """Reject wrongly typed fields up front, so rendering cannot fail halfway."""
    def need(cond, msg):
        if not cond:
            errors.append(msg)
    for k in ('package', 'summary', 'snapshot', 'execution_note'):
        need(k not in review or isinstance(review[k], str), f'top level: "{k}" must be a string')
    need(not isinstance(review.get('passes'), (str, list)) , 'top level: "passes" must be an object')
    need('executed' not in review or isinstance(review['executed'], bool),
         'top level: "executed" must be true or false (a string like "false" would render as executed)')
    for k in ('limitations', 'coverage', 'next_steps', 'style_notes', 'strengths'):
        v = review.get(k)
        need(v is None or isinstance(v, (list, str)) and (k != 'strengths' or isinstance(v, list)), f'top level: "{k}" must be a list')
    for k in ('limitations', 'coverage', 'next_steps'):
        for x in review.get(k) or [] if isinstance(review.get(k), list) else []:
            need(isinstance(x, str), f'top level: every entry of "{k}" must be a string')
    for i, f in enumerate(review.get('findings') or []):
        if not isinstance(f, dict):
            errors.append(f'finding #{i + 1}: must be an object'); continue
        where = f"finding {f.get('id', '#' + str(i + 1))}"
        for k in ('id', 'title', 'what_happens', 'why_it_matters', 'confirm_or_fix', 'repro', 'certainty_note', 'kind'):
            need(k not in f or isinstance(f[k], str), f'{where}: "{k}" must be a string')
        need(isinstance(f.get('evidence', []), list), f'{where}: "evidence" must be a list')
        need(isinstance(f.get('also_at', []), list), f'{where}: "also_at" must be a list')
        for n, e in enumerate(f.get('evidence', []) if isinstance(f.get('evidence', []), list) else []):
            need(isinstance(e, dict), f'{where} evidence {n + 1}: must be an object')
    for j, s in enumerate(review.get('strengths') or [] if isinstance(review.get('strengths'), list) else []):
        need(isinstance(s, (dict, str)), f'strength {j + 1}: must be an object or a string')
        if isinstance(s, dict):
            need(isinstance(s.get('evidence', []), list), f'strength {j + 1}: "evidence" must be a list')
            for k in ('title', 'note'):
                need(k not in s or isinstance(s[k], str), f'strength {j + 1}: "{k}" must be a string')


def fence(text, lang='m2'):
    ticks = max([3] + [len(m) + 1 for m in re.findall(r'`{3,}', text)])
    return f"{'`' * ticks}{lang}\n{text}\n{'`' * ticks}"


def loc(ev):
    a, b = ev['start_line'], ev['end_line']
    return f"`{ev['file']}:{a}`" if a == b else f"`{ev['file']}:{a}-{b}`"


def quoted_loc(ev):
    qa, qb = quote_range(ev)
    if (qa, qb) == (ev['start_line'], ev['end_line']):
        return loc(ev)
    return f"`{ev['file']}:{qa}`" if qa == qb else f"`{ev['file']}:{qa}-{qb}`"


def also_loc(x):
    if isinstance(x, str):
        return f'`{x}`' if not x.startswith('`') else x
    s = loc(x) if all(k in x for k in ('file', 'start_line', 'end_line')) else f"`{x.get('file', '?')}`"
    return s + (f" — {x['note']}" if x.get('note') else '')


def finding_ids(x):
    """The finding ids a doc_audit table or row points to: one id or a list."""
    v = x.get('finding')
    return [] if v in (None, '') else v if isinstance(v, list) else [v]


def check_refs(where, x, needed, ids, errors):
    """A gap must point to a finding, and every finding it points to must exist."""
    refs = finding_ids(x)
    if needed and not refs:
        errors.append(f'{where}: a gap needs a "finding" id')
    for ref in refs:
        if ref not in ids:
            errors.append(f'{where}: finding {ref!r} does not exist')


def check_test_coverage(cov, ids, errors):
    """Every cell must be filled in, and every gap must point to a finding."""
    if not isinstance(cov, dict):
        errors.append('"test_coverage" must be an object with "running", "skipped", "total_time", "slowest_test", "functions"')
        return
    for k in ('running', 'skipped'):
        if not isinstance(cov.get(k), int) or cov[k] < 0:
            errors.append(f'test_coverage: "{k}" must be a count')
    for k in ('total_time', 'slowest_test'):
        if not isinstance(cov.get(k), str) or not cov[k].strip():
            errors.append(f'test_coverage: "{k}" must be text, such as "4.55 s", or "not measured"')
    rows = cov.get('functions')
    if not isinstance(rows, list):
        errors.append('test_coverage: "functions" must be a list')
        return
    for t in rows:
        if not isinstance(t, dict) or not t.get('function') or not isinstance(t['function'], str):
            errors.append('test_coverage: every row needs a "function"')
            continue
        where = f"test_coverage {t['function']}"
        if not isinstance(t.get('running_tests'), int) or t['running_tests'] < 0:
            errors.append(f'{where}: "running_tests" must be a count')
        if t.get('asserts_on_result') not in AUDIT_CELLS:
            errors.append(f"{where}: \"asserts_on_result\" must be one of {AUDIT_CELLS}, got {t.get('asserts_on_result')!r}")
        lists_ok = True
        for k in ('options_tested', 'options_not_tested'):
            if not isinstance(t.get(k), list) or not all(isinstance(x, str) for x in t[k]):
                errors.append(f'{where}: "{k}" must be a list of option names')
                lists_ok = False
        gap = t.get('running_tests') == 0 or t.get('asserts_on_result') == 'no' or (lists_ok and bool(t['options_not_tested']))
        check_refs(where, t, gap, ids, errors)


def check_doc_audit(audit, ids, errors):
    """Every cell must be filled in, and every problem must point to a finding."""
    if not isinstance(audit, list):
        errors.append('"doc_audit" must be a list of per-function tables')
        return

    def check_cell(where, name, value):
        if value not in AUDIT_CELLS:
            errors.append(f'{where}: "{name}" must be one of {AUDIT_CELLS}, got {value!r}')
    for t in audit:
        if not isinstance(t, dict) or not t.get('function') or not isinstance(t['function'], str):
            errors.append('doc_audit: every table needs a "function"')
            continue
        where = f"doc_audit {t['function']}"
        if not isinstance(t.get('examples'), int) or t['examples'] < 0:
            errors.append(f'{where}: "examples" must be a count')
        check_cell(where, 'examples_correct', t.get('examples_correct'))
        missing = t.get('see_also_missing', [])
        if not isinstance(missing, list) or not all(isinstance(x, str) for x in missing):
            errors.append(f'{where}: "see_also_missing" must be a list of names')
        check_refs(where, t, t.get('examples') == 0 or bool(missing) or t.get('examples_correct') == 'no', ids, errors)
        rows = t.get('items')
        if not isinstance(rows, list) or not rows:
            errors.append(f'{where}: "items" must list its inputs, outputs and options')
            continue
        for n, row in enumerate(rows):
            at = f'{where} item {n + 1}'
            if not isinstance(row, dict) or not row.get('item') or row.get('kind') not in AUDIT_KINDS:
                errors.append(f'{at}: needs "item", and a "kind" that is one of {AUDIT_KINDS}')
                continue
            for k in ('documented', 'described', 'limits', 'correct'):
                check_cell(at, k, row.get(k))
            check_refs(at, row, any(row.get(k) == 'no' for k in ('documented', 'described', 'limits', 'correct')), ids, errors)


def scanner_view(src, flag):
    """The scanner's prefilled table for this package, or None if it can't be had."""
    entry = next((c for c in (os.path.join(src.root, src.package + '.m2'), os.path.join(src.root, src.package, src.package + '.m2'))
                  if os.path.isfile(c)), None)
    scanner = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'm2_package_scan.py')
    if not entry or not os.path.isfile(scanner):
        return None
    try:
        r = subprocess.run([sys.executable, '-I', scanner, entry, flag], capture_output=True, text=True, timeout=120)
        return json.loads(r.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def test_coverage_gaps(cov, src):
    """Exported functions without a row, and options in none of a row's lists, according to the scanner."""
    expected = scanner_view(src, '--test-coverage')
    rows = cov.get('functions')
    if not expected or not isinstance(rows, list):
        return []
    have = {t.get('function'): t for t in rows if isinstance(t, dict)}
    gaps = []
    absent = [t['function'] for t in expected['functions'] if t['function'] not in have]
    if absent:
        gaps.append('test_coverage has no row for exported function(s): ' + ', '.join(absent))
    for t in expected['functions']:
        row = have.get(t['function'])
        if row:
            named = {x for k in ('options_tested', 'options_not_tested', 'options_exempt') for x in (row.get(k) or [])}
            lost = [o for o in t['options_set_in_tests'] + t['options_not_set'] if o not in named]
            if lost:
                gaps.append(f"test_coverage {t['function']}: option(s) in no list: " + ', '.join(lost))
    return gaps


def audit_gaps(audit, src):
    """Exported functions and declared options without a row, according to the scanner."""
    expected = scanner_view(src, '--doc-audit')
    if expected is None:
        return []
    tables = {t.get('function'): t for t in audit if isinstance(t, dict)}
    gaps = []
    absent = [t['function'] for t in expected if t['function'] not in tables]
    if absent:
        gaps.append('doc_audit has no table for exported function(s): ' + ', '.join(absent))
    for t in expected:
        have = tables.get(t['function'])
        if have and isinstance(have.get('items'), list):
            named = {row.get('item') for row in have['items'] if isinstance(row, dict)}
            lost = [it['item'] for it in t['items'] if it['kind'] == 'option' and it['item'] not in named]
            if lost:
                gaps.append(f"doc_audit {t['function']}: no row for option(s): " + ', '.join(lost))
    return gaps


def process(review, src, check_only):
    errors, warnings, mismatches = [], [], []
    check_types(review, errors)
    if errors:
        return errors, warnings, mismatches
    findings = review.get('findings')
    if not isinstance(findings, list):
        errors.append('top level: "findings" must be a list')
        findings = []
    for k in ('package', 'summary'):
        if not review.get(k):
            errors.append(f'top level: missing "{k}"')
    seen = set()
    for i, f in enumerate(findings):
        where = f"finding {f.get('id', '#' + str(i + 1))}"
        for k in REQUIRED:
            if k not in f or f[k] in (None, '', []):
                errors.append(f'{where}: missing "{k}"')
        if f.get('id') in seen:
            errors.append(f'{where}: duplicate id')
        seen.add(f.get('id'))
        if f.get('severity') not in SEVERITY:
            errors.append(f"{where}: severity must be 1-4, got {f.get('severity')!r}")
        if f.get('certainty') not in CERTAINTY:
            errors.append(f"{where}: certainty must be one of {CERTAINTY}, got {f.get('certainty')!r}")
        if f.get('kind') and f['kind'] not in KINDS:
            warnings.append(f"{where}: unusual kind {f['kind']!r} (expected one of {', '.join(KINDS)})")
    for f in findings:
        for n, x in enumerate(f.get('also_at') or []):
            check_location(src, x, f"finding {f.get('id')} also_at {n + 1}", errors)
    for n, x in enumerate(review.get('style_notes') or []):
        if isinstance(x, dict):
            check_location(src, x, f'style note {n + 1}', errors)
    items = [(f"finding {f.get('id')}", f, True) for f in findings]
    items += [(f"strength {j + 1}", s, False) for j, s in enumerate(review.get('strengths', [])) if isinstance(s, dict)]
    for where, item, strict in items:
        for n, ev in enumerate(item.get('evidence', []) or []):
            got = quote(src, ev, f'{where} evidence {n + 1}', errors, strict)
            if got is None:
                continue
            text, truncated = got
            if check_only:
                if ev.get('excerpt', '').rstrip('\n') != text:
                    mismatches.append(f'{where} evidence {n + 1} {loc(ev)}')
            else:
                if ev.get('excerpt') and ev['excerpt'].rstrip('\n') != text:
                    warnings.append(f'{where} evidence {n + 1} {loc(ev)}: replaced a hand-written excerpt that did not match the source')
                ev['excerpt'] = text
                if truncated:
                    ev['excerpt_truncated'] = True
                else:
                    ev.pop('excerpt_truncated', None)
    sweep = review.get('boundary_sweep')
    if sweep is None:
        warnings.append('no "boundary_sweep": the Required boundary sweep of the central functions is not recorded')
    elif not isinstance(sweep, list):
        errors.append('"boundary_sweep" must be a list of {function, case, outcome[, finding, note]}')
    else:
        ids = {f.get('id') for f in findings}
        for n, row in enumerate(sweep):
            where = f'boundary_sweep row {n + 1}'
            if not isinstance(row, dict) or not row.get('function') or not row.get('case'):
                errors.append(f'{where}: needs "function" and "case"')
                continue
            if row.get('outcome') not in OUTCOMES:
                errors.append(f"{where}: outcome must be one of {OUTCOMES}, got {row.get('outcome')!r}")
            if row.get('outcome') == 'finding' and row.get('finding') not in ids:
                errors.append(f"{where}: outcome 'finding' needs a \"finding\" id that exists, got {row.get('finding')!r}")
    audit = review.get('doc_audit')
    if audit is None:
        warnings.append('no "doc_audit": the per-function documentation tables (I3) are not recorded')
    else:
        check_doc_audit(audit, {f.get('id') for f in findings}, errors)
        if isinstance(audit, list):
            warnings.extend(audit_gaps(audit, src))
    cov = review.get('test_coverage')
    if cov is None:
        warnings.append('no "test_coverage": the report will have no test coverage table (R3)')
    else:
        check_test_coverage(cov, {f.get('id') for f in findings}, errors)
        if isinstance(cov, dict):
            warnings.extend(test_coverage_gaps(cov, src))
    if review.get('coverage') is None:
        warnings.append('no "coverage": the report will not say what was read and what was sampled')
    if not check_only:
        counts = {SEVERITY[s].lower(): sum(1 for f in findings if f.get('severity') == s) for s in SEVERITY}
        review['severity_counts'] = counts
    return errors, warnings, mismatches


def normalize_fences(text):
    """Make code fences inside a text field well formed. A fence written mid-line moves to its own
    line; text after a closing fence moves to the next line; an unclosed block is closed. Otherwise
    one malformed fence turns the rest of the report into a code block or a code span."""
    text = re.sub(r'(?<=\S)[ \t]*(```)', r'\n\1', text)        # a fence after other text on its line
    out, fence = [], None
    for line in text.split('\n'):
        m = re.match(r'^(\s*)(```+|~~~+)(.*)$', line)
        if m and fence is None:
            fence = m.group(2)
            out.append(line)
        elif m and m.group(2).startswith(fence[0]) and len(m.group(2)) >= len(fence):
            fence = None
            out.append(m.group(1) + m.group(2))
            if m.group(3).strip():
                out += ['', m.group(3).strip()]
        else:
            out.append(line)
    if fence:
        out.append(fence)
    return '\n'.join(out)


def labeled(label, text):
    """A bold label followed by text. Text containing a fenced code block starts on its own line,
    because a fence only opens a code block at the start of a line; inline, it would turn the rest
    of the report into one long code span."""
    text = text.strip()
    if '```' in text or re.search(r'^\s*~~~', text, re.M):
        return f'**{label}**\n\n{normalize_fences(text)}\n'
    return f'**{label}** {text}\n'


def cell(x):
    return str(x).replace('|', '\\|').replace('\n', ' ')


def render(r):
    out = []
    pkg = r.get('package', 'Package')
    out.append(f'# {pkg} — package review\n')
    executed = r.get('executed')
    ex = 'yes' if executed else 'no'
    if r.get('execution_note'):
        ex += f" ({r['execution_note']})"
    out.append(f"**Snapshot:** {r.get('snapshot', 'unspecified')} · **Executed:** {ex}  ")
    passes = r.get('passes', {}) or {}
    done = '; '.join(f"{k.capitalize()} {', '.join(v) if v else 'none'}" for k, v in passes.items() if k != 'skipped' and isinstance(v, list))
    out.append(f'**Passes completed:** {done or "unspecified"}  ')
    skipped = passes.get('skipped', r.get('skipped'))
    if isinstance(skipped, dict):
        sk = '; '.join(f'{k} ({v})' for k, v in skipped.items())
    elif isinstance(skipped, list):
        sk = '; '.join(map(str, skipped))
    else:
        sk = str(skipped) if skipped else 'none'
    out.append(f'**Skipped:** {sk}\n')
    c = r.get('severity_counts', {})
    if c:
        out.append('**Findings:** ' + ' · '.join(f'{v} {k}' for k, v in c.items()) + '\n')
    out.append('## Summary\n')
    out.append(r.get('summary', '').strip() + '\n')
    out.append('## Findings\n')
    order = {c: i for i, c in enumerate(CERTAINTY)}
    findings = sorted(r.get('findings', []), key=lambda f: (f.get('severity', 9), order.get(f.get('certainty'), 9)))
    for sev, name in SEVERITY.items():
        group = [f for f in findings if f.get('severity') == sev]
        if not group:
            continue
        out.append(f'### {name}\n')
        for f in group:
            out.append(f"#### {f['id']}. {f['title']}\n")
            cert = f['certainty'] + (f" ({f['certainty_note']})" if f.get('certainty_note') else '')
            out.append(f"**Severity:** {name} · **Certainty:** {cert} · **Kind:** {f.get('kind', '')}\n")
            out.append(labeled('What happens.', f['what_happens']))
            out.append(labeled('Why it matters.', f['why_it_matters']))
            out.append(labeled('Confirm / fix.', f['confirm_or_fix']))
            if f.get('repro'):
                out.append(fence(f['repro'].rstrip()) + '\n')
            evs = f.get('evidence', [])
            where = ', '.join(loc(e) + (f" — {e['note']}" if e.get('note') else '') for e in evs)
            out.append(f'**Where:** {where}\n')
            for e in evs:
                label = quoted_loc(e)
                if len(evs) > 1 or label != loc(e):
                    out.append(label + '\n')
                out.append(fence(e['excerpt']) + '\n')
            if f.get('also_at'):
                out.append('**Also at:** ' + '; '.join(also_loc(x) for x in f['also_at']) + '\n')
    sweep = r.get('boundary_sweep') or []
    if sweep:
        out.append('## Boundary sweep\n')
        out.append('Central functions traced through degenerate inputs. `ok` means traced and handled.\n')
        out.append('| Function | Case | Outcome | Note |')
        out.append('|---|---|---|---|')
        for row in sweep:
            outcome = row.get('outcome', '')
            if outcome == 'finding':
                outcome = f"see {row.get('finding')}"
            out.append(f"| `{cell(row.get('function', ''))}` | {cell(row.get('case', ''))} | {cell(outcome)} | {cell(row.get('note', ''))} |")
        out.append('')
    strengths = r.get('strengths', [])
    if strengths:
        out.append('## Strengths worth preserving\n')
        for s in strengths:
            if isinstance(s, str):
                out.append(f'- {s}')
                continue
            locs = ', '.join(loc(e) for e in s.get('evidence', []))
            note = f" — {s['note']}" if s.get('note') else ''
            out.append(f"- **{s.get('title', '')}**{note}" + (f' ({locs})' if locs else ''))
        out.append('')
    if r.get('style_notes'):
        out.append('## Style-guide notes\n')
        out.extend(f'- {x}' if isinstance(x, str) else f"- {also_loc(x)}" for x in r['style_notes'])
        out.append('')
    lim = r.get('limitations', [])
    if lim:
        out.append('## Limitations\n')
        out.extend(f'- {x}' for x in (lim if isinstance(lim, list) else [lim]))
        out.append('')
    if r.get('next_steps'):
        out.append('## Suggested next steps\n')
        out.extend(f'{i}. {x}' for i, x in enumerate(r['next_steps'], 1))
        out.append('')
    tc = r.get('test_coverage')
    if tc:
        out.append('## Test coverage\n')
        out.append(f"**Tests:** {tc['running']} running, {tc['skipped']} skipped · **Total:** {tc['total_time']} · **Slowest:** {tc['slowest_test']}\n")
        out.append('One row per exported function. **Running tests:** tests that run and use it. **Asserts on result:** at least one '
                   'of them checks its result. **Options tested:** a test would fail if the option were ignored.\n')
        out.append('| Function | Running tests | Asserts on result | Options tested | Options not tested | Finding | Note |')
        out.append('|---|---|---|---|---|---|---|')
        names = lambda xs: ', '.join(f'`{cell(x)}`' for x in xs) or 'none'
        for t in tc['functions']:
            see = ', '.join(f'see {x}' for x in finding_ids(t))
            note = t.get('note', '')
            if t.get('options_exempt'):
                note = (note + ' ' if note else '') + 'Exempt: ' + ', '.join(t['options_exempt']) + '.'
            out.append(f"| `{cell(t['function'])}` | {t['running_tests']} | {t['asserts_on_result']} | {names(t['options_tested'])} | "
                       f"{names(t['options_not_tested'])} | {cell(see)} | {cell(note)} |")
        out.append('')
    audit = r.get('doc_audit') or []
    if audit:
        out.append('## Documentation audit\n')
        out.append('One table per exported function. **Documented:** the item is listed in the docs. **Described:** someone '
                   'wrote at least a line for it. **Limits:** its range or limits are stated. **Correct:** the description '
                   'matches the code.\n')
        for t in audit:
            out.append(f"### `{t['function']}`\n")
            ex = str(t.get('examples', 0))
            if t.get('canned_examples'):
                ex += f" ({t['canned_examples']} canned)"
            if t.get('examples'):
                ex += f", correct: {t.get('examples_correct')}"
            names = ', '.join(f'`{x}`' for x in t.get('see_also_missing', [])) or 'none'
            refs = finding_ids(t)
            out.append(f'**Examples:** {ex} · **See also missing:** {names}' + (f" · **See:** {', '.join(refs)}" if refs else '') + '\n')
            out.append('| Item | Kind | Documented | Described | Limits | Correct | Finding | Note |')
            out.append('|---|---|---|---|---|---|---|---|')
            for row in t['items']:
                kind = row['kind'] + (f", {row['type']}" if row.get('type') else '')
                see = ', '.join(f'see {x}' for x in finding_ids(row))
                out.append(f"| `{cell(row['item'])}` | {cell(kind)} | {row['documented']} | {row['described']} | {row['limits']} | "
                           f"{row['correct']} | {cell(see)} | {cell(row.get('note', ''))} |")
            out.append('')
    cov = r.get('coverage', [])
    if cov:
        out.append('## Review coverage\n')
        out.extend(f'- {x}' for x in (cov if isinstance(cov, list) else [cov]))
        out.append('')
    return '\n'.join(out).rstrip() + '\n'


def main():
    global MAX_LINES
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('json')
    ap.add_argument('--root', required=True)
    ap.add_argument('--out')
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--max-lines', type=int, default=MAX_LINES, help=f'max quoted lines per finding citation (default {MAX_LINES})')
    a = ap.parse_args()
    MAX_LINES = a.max_lines
    with open(a.json, encoding='utf-8') as f:
        review = json.load(f)
    src = Sources(os.path.abspath(a.root), review.get('package', ''))
    errors, warnings, mismatches = process(review, src, a.check)
    for w in warnings:
        print('warning:', w, file=sys.stderr)
    if errors:
        print(f'{len(errors)} error(s); nothing written:', file=sys.stderr)
        for e in errors:
            print('  ', e, file=sys.stderr)
        sys.exit(1)
    if a.check:
        if mismatches:
            print(f'{len(mismatches)} excerpt(s) differ from the source:', file=sys.stderr)
            for m in mismatches:
                print('  ', m, file=sys.stderr)
            sys.exit(1)
        print('all excerpts match the source')
        return
    out = a.out or os.path.splitext(a.json)[0] + '.md'
    # Render completely in memory first, then replace both files atomically, so a failure
    # leaves the previous JSON and report untouched.
    try:
        md = render(review)
        js = json.dumps(review, indent=1, ensure_ascii=False) + '\n'
    except Exception as e:  # a shape check_types did not anticipate
        print(f'rendering failed ({type(e).__name__}: {e}); nothing written', file=sys.stderr)
        sys.exit(1)
    # Stage both outputs next to their destinations, then swap them in. If staging fails, nothing is
    # replaced; if the second swap fails, the first file is restored, so the pair never mixes versions.
    staged = []
    try:
        for path, text in ((a.json, js), (out, md)):
            tmp = f'{path}.tmp-{os.getpid()}'
            with open(tmp, 'w', encoding='utf-8') as f:
                f.write(text)
            staged.append((tmp, path))
    except OSError as e:
        for tmp, _ in staged:
            os.remove(tmp)
        print(f'could not write output ({e}); nothing replaced', file=sys.stderr)
        sys.exit(1)
    previous_json = open(a.json, encoding='utf-8').read() if os.path.exists(a.json) else None
    os.replace(*staged[0])
    try:
        os.replace(*staged[1])
    except OSError as e:
        if previous_json is not None:
            with open(a.json, 'w', encoding='utf-8') as f:
                f.write(previous_json)
        os.remove(staged[1][0])
        print(f'could not replace {out} ({e}); restored {a.json}', file=sys.stderr)
        sys.exit(1)
    n = len(review.get('findings', []))
    print(f'wrote {out} and updated {a.json}: {n} findings, ' + ', '.join(f'{v} {k}' for k, v in review['severity_counts'].items()))


if __name__ == '__main__':
    main()
