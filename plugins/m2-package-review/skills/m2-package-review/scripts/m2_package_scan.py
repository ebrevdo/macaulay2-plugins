#!/usr/bin/env python3
"""Static triage scan of a Macaulay2 package.

Maps what the package actually loads, then lists *candidate* locations for defect
patterns that recur in real package reviews. Every hit is a lead to verify by reading
the surrounding code, callers, and tests -- never a finding by itself.

Usage:
    python3 -I m2_package_scan.py <Package.m2 | package directory> [--json] [--max N]

The path may be the entry file Foo.m2, or a directory that contains Foo.m2 (and
optionally the auxiliary directory Foo/). Only the Python standard library is used.
"""
import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

END_RE = re.compile(r'^\s*end(\b|-|;|\s*$)')
LOAD_RE = re.compile(r'^\s*(?:load|needs)\b.*?"([^"]+\.m2)"')
TEST_OPEN_RE = re.compile(r'\bTEST\s*///')
UNREGISTERED_TEST_RE = re.compile(r'///\s*TEST\b')
STATEMENT_START = r'(?:^|;|\bthen\b|\belse\b|\bdo\b)'


class Line:
    __slots__ = ('file', 'no', 'raw', 'code', 'region', 'test_id')

    def __init__(self, file, no, raw, code, region, test_id=None):
        self.file, self.no, self.raw, self.code = file, no, raw, code
        self.region, self.test_id = region, test_id

    def loc(self):
        return f'{self.file}:{self.no}'


def strip_comment(s):
    """Remove a trailing -- comment that is outside a double-quoted string."""
    out, i, inq = [], 0, False
    while i < len(s):
        c = s[i]
        if inq:
            out.append(c)
            if c == '\\' and i + 1 < len(s):
                out.append(s[i + 1]); i += 2; continue
            if c == '"':
                inq = False
        else:
            if s.startswith('--', i):
                break
            if c == '"':
                inq = True
            out.append(c)
        i += 1
    return ''.join(out)


def resolve_entry(path):
    path = os.path.abspath(path)
    if os.path.isfile(path):
        return path
    base = os.path.basename(path.rstrip('/'))
    cand = os.path.join(path, base + '.m2')
    if os.path.isfile(cand):
        return cand
    m2s = [f for f in os.listdir(path) if f.endswith('.m2')]
    for f in m2s:
        if 'newPackage' in open(os.path.join(path, f), encoding='utf-8', errors='replace').read():
            return os.path.join(path, f)
    sys.exit(f'no package entry file found under {path}')


def segments(s, in_block=False, in_triple=False, in_dq=False):
    """Lex one line into (context, text) pieces, carrying block-comment and ///-string state across lines.

    Contexts: 'code', 'dq' (a "..." string, which may span lines), 'triple' (inside a /// string), 'block' (-* ... *-),
    'comment' (-- to end of line), and the markers 'open' / 'close' for /// delimiters. Comment and
    string delimiters only count in the context where Macaulay2 recognizes them, so "a-*b" is text.
    """
    segs, cur, i = [], [], 0
    ctx = 'block' if in_block else ('triple' if in_triple else ('dq' if in_dq else 'code'))

    def flush():
        if cur:
            segs.append((ctx, ''.join(cur)))
            cur.clear()
    while i < len(s):
        if ctx == 'block':
            if s.startswith('*-', i):
                cur.append('*-'); flush(); ctx = 'code'; i += 2
            else:
                cur.append(s[i]); i += 1
        elif ctx == 'triple':
            if s.startswith('///', i):
                flush(); segs.append(('close', '///')); ctx = 'code'; i += 3
            else:
                cur.append(s[i]); i += 1
        elif ctx == 'dq':
            cur.append(s[i])
            if s[i] == '\\' and i + 1 < len(s):
                cur.append(s[i + 1]); i += 2; continue
            if s[i] == '"':
                flush(); ctx = 'code'
            i += 1
        elif s.startswith('--', i):
            flush(); segs.append(('comment', s[i:])); i = len(s)
        elif s.startswith('-*', i):
            flush(); ctx = 'block'; cur.append('-*'); i += 2
        elif s.startswith('///', i):
            flush(); segs.append(('open', '///')); ctx = 'triple'; i += 3
        elif s[i] == '"':
            flush(); ctx = 'dq'; cur.append('"'); i += 1
        else:
            cur.append(s[i]); i += 1
    flush()
    return segs, ctx == 'block', ctx == 'triple', ctx == 'dq'


def code_of(segs):
    """Code text of a lexed line: code and "..." strings kept, /// delimiters kept as markers,
    comments and the contents of /// strings dropped."""
    return ''.join(t for c, t in segs if c in ('code', 'dq', 'open', 'close'))


def no_strings(code):
    """Code with the contents of "..." literals removed, for counting identifiers such as assert."""
    return re.sub(r'"(?:[^"\\]|\\.)*"', '""', code)


def load_package(entry):
    """Follow the files Macaulay2 loads when the package loads.

    A `load` or `needs` is followed only at top level or inside non-function brackets (such as an
    `if ... then ( ... )` block). One inside a function body runs only if the function is called, so
    it is recorded as deferred instead. A top-level `end` stops the file.
    """
    root = os.path.dirname(entry)
    lines, loaded, post_end, missing, deferred = [], [], [], [], []
    seen = set()

    def visit(path):
        if path in seen:
            return
        seen.add(path)
        rel = os.path.relpath(path, root)
        loaded.append(rel)
        raw = open(path, encoding='utf-8', errors='replace').read().split('\n')
        in_block = in_triple = in_dq = False
        frames, tail = [], ''   # frames: True for brackets opening a function body
        for i, ln in enumerate(raw):
            at_code = not (in_block or in_triple or in_dq)
            segs, in_block, in_triple, in_dq = segments(ln, in_block, in_triple, in_dq)
            code = code_of(segs) if at_code else ''
            if at_code and not frames and END_RE.match(code):
                rest = raw[i + 1:]
                txt = '\n'.join(rest)
                post_end.append(dict(file=rel, line=i + 1, lines_after=len(rest),
                                     has_TEST=bool(re.search(r'\bTEST\b', txt)),
                                     has_doc=bool(re.search(r'\bdoc\s*///|\bdocument\s*\{|\bKey\b', txt))))
                break
            lines.append((rel, i + 1, ln))
            in_function = any(frames) or bool(re.search(r'->\s*$', tail))
            m = LOAD_RE.match(code) if at_code else None
            if m and '///' not in code[:m.start(1)]:
                target = m.group(1)
                if in_function:
                    deferred.append(f'{rel}:{i + 1} -> {target}')
                else:
                    for base in (os.path.dirname(path), root):
                        p = os.path.normpath(os.path.join(base, target))
                        if os.path.isfile(p):
                            visit(p)
                            break
                    else:
                        missing.append(f'{rel}:{i + 1} -> {target}')
            for c, t in segs:   # only executable code moves brackets; strings and comments don't
                if c != 'code':
                    if c in ('dq', 'open', 'close'):
                        tail += ' x '
                    continue
                for ch in t:
                    if ch in '([{':
                        frames.append(bool(re.search(r'->\s*$', tail)))
                    elif ch in ')]}' and frames:
                        frames.pop()
                    tail = (tail + ch)[-200:]
            if len(frames) > 200:
                frames = []

    visit(entry)
    return root, lines, loaded, post_end, missing, deferred


def classify(raw_lines):
    """Assign regions (impl/doc/test) and comment-stripped code to each loaded line.

    TEST bodies are /// strings, so their contents are lexed a second time as code (with their own
    block-comment state) to see what the test actually executes.
    """
    out, after_doc, ntests = [], False, 0
    in_block = in_triple = in_dq = False
    test_id, test_block, test_dq, test_pending, cur_file = None, False, False, False, None
    for f, no, ln in raw_lines:
        if f != cur_file:  # each loaded file is parsed on its own
            in_block = in_triple = in_dq = False
            test_id, test_block, test_dq, test_pending, cur_file = None, False, False, False, f
        segs, in_block, in_triple, in_dq = segments(ln, in_block, in_triple, in_dq)
        outer, test_code, in_test_line = [], [], test_id is not None
        line_test = test_id
        for c, t in segs:
            if c == 'open':
                if test_pending:
                    ntests += 1
                    test_id, test_block, test_dq, line_test, in_test_line = ntests, False, False, ntests, True
                    test_pending = False
                outer.append(t)
            elif c == 'close':
                if test_id is not None:
                    test_id = None
                outer.append(t)
            elif c == 'triple':
                if test_id is not None:
                    tsegs, test_block, _, test_dq = segments(t, test_block, False, test_dq)
                    test_code.append(''.join(x for k, x in tsegs if k in ('code', 'dq')))
            elif c in ('code', 'dq'):
                outer.append(t)
                if c == 'code' and t.strip():
                    test_pending = bool(re.search(r'\bTEST\s*$', t))
        code = ''.join(outer)
        if in_test_line:
            out.append(Line(f, no, ln, ''.join(test_code), 'test', line_test))
            continue
        if 'beginDocumentation' in code:
            after_doc = True
        out.append(Line(f, no, ln, code, 'doc' if after_doc else 'impl'))
    return out


def paren_frames(lines):
    """For each line, the text that precedes each enclosing open paren/bracket at line start
    (innermost last), so callers can ask whether a line sits inside e.g. `if Verbose then (`."""
    frames, out, cur_file = [], [], None
    for l in lines:
        if l.file != cur_file:
            frames, cur_file = [], l.file
        out.append(list(frames))
        s, i, inq = l.code, 0, False
        while i < len(s):
            c = s[i]
            if inq:
                if c == '\\':
                    i += 1
                elif c == '"':
                    inq = False
            elif c == '"':
                inq = True
            elif c in '([{':
                frames.append(s[max(0, i - 120):i])
            elif c in ')]}' and frames:
                frames.pop()
            i += 1
        if len(frames) > 200:  # unbalanced text; resynchronize
            frames = []
    return out


def statements(lines):
    """Group lines into top-level statements (newline-terminated once parens balance)."""
    stmt, depth = [], 0
    for l in lines:
        stmt.append(l)
        s, i, inq = l.code, 0, False
        while i < len(s):
            c = s[i]
            if inq:
                if c == '\\':
                    i += 1
                elif c == '"':
                    inq = False
            elif c == '"':
                inq = True
            elif c in '([{':
                depth += 1
            elif c in ')]}':
                depth -= 1
            i += 1
        if depth <= 0 and not re.search(r'(==|=|,|\band|\bor|\||\+|-|\*)\s*$', l.code.rstrip()):
            yield stmt
            stmt, depth = [], 0
    if stmt:
        yield stmt


DOC_SECTIONS = {'Key', 'Headline', 'Usage', 'Inputs', 'Outputs', 'Consequences', 'Description', 'Caveat',
                'SeeAlso', 'Subnodes', 'Contributors', 'References', 'Acknowledgement', 'Citation',
                'ExampleFiles', 'SourceCode', 'Example', 'CannedExample', 'Text', 'Code', 'Pre', 'Tree', 'Node'}


def parse_doc_nodes(doc):
    """Split documentation into nodes. SimpleDoc nodes (a `Key` section) yield keys, Outputs types
    and whether an example is present; old-style document{} nodes yield keys and example presence."""
    nodes, cur = [], None

    def close():
        if cur:
            nodes.append(cur)
    for l in doc:
        s, ind = l.raw.strip(), len(l.raw) - len(l.raw.lstrip())
        if s == 'Key' or re.search(r'\bdocument\s*\{', l.raw):
            close()
            cur = dict(line=l, keys=[], outputs=[], example=False, section=None, sec_ind=ind, item_ind=None, simple=(s == 'Key'))
            if not cur['simple']:
                m = re.search(r'Key\s*=>\s*(\{[^}]*\}|[^,\n]+)', l.raw)
                if m:
                    cur['keys'].append(m.group(1).strip('{} '))
                cur['section'] = 'old'
            else:
                cur['section'] = 'Key'
            continue
        if cur is None:
            continue
        if '///' in l.raw and cur['simple']:
            close(); cur = None; continue
        if 'EXAMPLE' in l.raw or s in ('Example', 'CannedExample'):
            cur['example'] = True
        if not cur['simple']:
            if cur['keys'] == [] and 'Key' in l.raw:
                m = re.search(r'Key\s*=>\s*(\{[^}]*\}|[^,\n]+)', l.raw)
                if m:
                    cur['keys'].append(m.group(1).strip('{} '))
            continue
        if s in DOC_SECTIONS and ind <= cur['sec_ind'] + 1:
            cur['section'], cur['sec_ind'], cur['item_ind'] = s, ind, None
            continue
        if not s or ind <= cur['sec_ind']:
            continue
        if cur['section'] == 'Key':
            cur['keys'].append(s)
        elif cur['section'] == 'Outputs':
            if cur['item_ind'] is None:
                cur['item_ind'] = ind
            if ind == cur['item_ind']:
                m = re.match(r"[\w']*\s*:\s*([A-Za-z][\w']*)", s)
                if m:
                    cur['outputs'].append(m.group(1))
    close()
    for n in nodes:
        parsed = []
        for k in n['keys']:
            k = k.strip().rstrip(',')
            m = re.match(r'\(\s*([A-Za-z][\w\']*)\s*,\s*(.*)\)$', k)
            if m:
                parsed.append(('method', m.group(1), re.sub(r'\s', '', m.group(2))))
            elif re.match(r'\[', k):
                parsed.append(('option', k, None))
            elif re.match(r'[A-Za-z][\w\']*$', k):
                parsed.append(('name', k, None))
            else:
                parsed.append(('other', k, None))
        n['parsed'] = parsed
    return nodes


def balanced_args(s, start):
    """Return the text inside balanced parentheses starting at s[start] == '('."""
    depth = 0
    for j in range(start, len(s)):
        if s[j] == '(':
            depth += 1
        elif s[j] == ')':
            depth -= 1
            if depth == 0:
                return s[start + 1:j]
    return s[start + 1:]


def scan(entry):
    root, raw_lines, loaded, post_end, missing, deferred_loads = load_package(entry)
    L = classify(raw_lines)
    impl = [l for l in L if l.region == 'impl']
    doc = [l for l in L if l.region == 'doc']
    tst = [l for l in L if l.region == 'test']
    impl_text = '\n'.join(l.code for l in impl)
    all_code = '\n'.join(l.code for l in L)
    hits = defaultdict(list)

    def hit(check, line, note=''):
        snippet = line.raw.strip()
        hits[check].append(dict(loc=line.loc(), code=snippet[:160], note=note))

    def ncl(ls):
        return sum(1 for l in ls if l.code.strip())

    # ---------- exports and documentation keys
    exports = set()
    for m in re.finditer(r'\bexport(?:Mutable)?\s*\{(.*?)\}', impl_text, re.S):
        exports |= {a or b for a, b in re.findall(r'"([^"]+)"|\b([A-Za-z][A-Za-z0-9\']*)\b', m.group(1))}
    exports.discard('symbol')
    doc_text = '\n'.join(l.raw for l in doc)
    keys = set()
    in_key, key_ind = False, 0
    for l in doc:
        s = l.raw.strip()
        if not s:
            continue
        ind = len(l.raw) - len(l.raw.lstrip())
        if s in ('Key', 'Node'):
            in_key, key_ind = s == 'Key', ind; continue
        if in_key:
            if ind > key_ind:
                keys |= set(re.findall(r"[A-Za-z][A-Za-z0-9']*", s))
            else:
                in_key = False
    for m in re.finditer(r'Key\s*=>\s*(\{.*?\}|[^,\n]+)', doc_text, re.S):
        keys |= set(re.findall(r"[A-Za-z][A-Za-z0-9']*", m.group(1)))
    undocumented = sorted(e for e in exports if e not in keys)
    examples = len(re.findall(r'^\s*Example\s*$', doc_text, re.M)) + len(re.findall(r'\bEXAMPLE\b', doc_text))

    # ---------- tests
    blocks = defaultdict(list)
    for l in tst:
        blocks[l.test_id].append(l)
    test_summary, test_files = [], []

    helper_code = []

    def test_loaded_asserts(ls):
        """Asserts in files a TEST body loads. They run as part of that test, not at package load, so
        they are parsed with the same end-aware loader (following their own nested loads)."""
        n = 0
        for l in ls:
            m = LOAD_RE.match(l.code)
            if not m:
                continue
            for base in (os.path.dirname(os.path.join(root, l.file)), root):
                p = os.path.normpath(os.path.join(base, m.group(1)))
                if os.path.isfile(p):
                    try:
                        _, hl, hfiles, _, _, _ = load_package(p)
                    except Exception:
                        break
                    base_dir = os.path.dirname(p)
                    for hf in hfiles:
                        rel = os.path.relpath(os.path.normpath(os.path.join(base_dir, hf)), root)
                        if rel not in test_files:
                            test_files.append(rel)
                    code = '\n'.join(x.code for x in classify(hl))
                    helper_code.append(code)
                    n += len(re.findall(r'\bassert\b', no_strings(code)))
                    break
        return n
    for tid, ls in blocks.items():
        code = '\n'.join(l.code for l in ls)
        n_assert = len(re.findall(r'\bassert\b', no_strings(code))) + test_loaded_asserts(ls)
        test_summary.append(dict(loc=ls[0].loc(), lines=len(ls), asserts=n_assert))
        if n_assert == 0 and not re.search(r'\berror\b', no_strings(code)):
            hit('T1 TEST block with no assert', ls[0], f'{len(ls)} lines')
        for st in statements(ls):
            text = ' '.join(x.code.strip() for x in st).strip()
            m_time = re.match(r'(time|elapsedTime|timing|elapsedTiming)\b\s*', text)
            if m_time:
                text = text[m_time.end():]
                if text and not re.match(r'(assert|\w+\s*:?=[^=])', text):
                    hit('T5 timed computation whose result is never checked', st[0])
            head = re.split(r'(===|==|=!=|!=)', text)[0]
            if (re.search(r'[^=!<>:]\s*(===|==)\s*[^=]', text)
                    and not re.match(r'(assert|if|while|for|scan|apply|return|try|print|<<|error)\b', text)
                    and not re.search(r'(:=|[^=!<>:]=[^=]|->)', head)):
                hit('T2 bare comparison in TEST (result not asserted)', st[0])
        for l in ls:
            c = l.code
            if re.search(r'\btry\b.*\bfalse\s*\)\s*else\s*true', c) or re.search(r'\btry\b.*\bthen\s+false\s+else\s+true', c):
                hit('T3 catch-all negative test (any error passes)', l)
    for l in L:
        if UNREGISTERED_TEST_RE.search(l.raw) and not l.raw.lstrip().startswith('--'):
            hit('T4 "///TEST" opens a string, not a registered TEST', l)

    # ---------- statement-level comparison whose value is discarded (often a mistyped assignment)
    for l in impl:
        for m in re.finditer(STATEMENT_START + r'\s*([A-Za-z_][\w.#"\']*)\s*(===|==)\s*([^;]*?);', l.code):
            rhs = m.group(3)
            if not re.search(r'\b(then|do|and|or|else|if)\b|=>|->', rhs):
                hit('C1 comparison used as a statement (assignment intended?)', l)

    # ---------- collection operation whose result is discarded
    prev = ''
    for l in impl:
        c = l.code.strip()
        if c:
            arg_context = (re.search(r'(=|:=|\||,|=>)\s*$', prev)
                           or (prev.endswith('(') and not re.search(r'(\bthen|\belse|\bdo|->|;)\s*\($', prev)))
            if (re.search(r'\bdo\s+(append|prepend|insert|join|delete|drop)\s*\(', c)
                    or (re.match(r'(append|prepend|insert|delete|drop)\s*\(', c) and c.endswith(';') and not arg_context)):
                hit('C2 immutable-collection result discarded', l)
            prev = c

    # ---------- methods with options: overload handlers and option forwarding
    opt_methods = {}
    for m in re.finditer(r'\b([A-Za-z]\w*)\s*=\s*method\s*\(', impl_text):
        args = balanced_args(impl_text, m.end() - 1)
        om_ = re.search(r'\bOptions\s*=>\s*(?!true\b)(.*)', args, re.S)
        if om_:
            opt_methods[m.group(1)] = re.findall(r'\b([A-Z]\w*)\s*=>', om_.group(1))
    install_re = re.compile(r'^\s*([A-Za-z]\w*)(?:\s*(\([^)]*\))|\s+([A-Z]\w*))\s*:=\s*(?:[A-Z]\w*\s*=>\s*)?(.*)$')
    sigs = Counter()
    sig_lines = defaultdict(list)
    for idx, l in enumerate(impl):
        m = install_re.match(l.code)
        if not m:
            continue
        name, sig, rhs = m.group(1), re.sub(r'\s', '', m.group(2) or m.group(3)).strip('()'), m.group(4).strip()
        sigs[(name, sig)] += 1
        sig_lines[(name, sig)].append(l)
        if name in opt_methods and rhs:
            om = re.match(r'([A-Za-z]\w*)\s*->', rhs)
            if rhs.startswith('(') or re.match(r'[a-z]\w*\s*->', rhs) and not om:
                if not om:
                    hit('C3 overload of an option-taking method has no options handler', l, f'{name} declares options')
                continue
            if not om:
                continue
            ov = om.group(1)
            body = [l]
            for nxt in impl[idx + 1:]:
                if install_re.match(nxt.code) or (nxt.raw[:1].strip() and not nxt.raw.startswith(')')):
                    break
                body.append(nxt)
            for b in body:
                for cm in re.finditer(r'\b' + re.escape(name) + r'\s*\(', b.code):
                    if b is l and cm.start() < l.code.index(':='):
                        continue
                    args = balanced_args(b.code, cm.end() - 1)
                    if not re.search(r'\b' + re.escape(ov) + r'\b', args):
                        hit('C4 delegating call does not forward the options table', b, f'{name}(...) inside an overload with {ov}')
                    elif re.search(r'\b' + re.escape(ov) + r'\.\w', args) and not re.search(r'\b' + re.escape(ov) + r'\b(?!\.)', args):
                        hit('C4 delegating call forwards only some options', b, f'{name}(...) inside an overload with {ov}')
    for (name, sig), n in sigs.items():
        if n > 1:
            for l in sig_lines[(name, sig)]:
                hit('C5 same dispatch signature installed more than once (later one wins)', l, f'{name}({sig}) x{n}')
    for name, opts in opt_methods.items():
        for o in opts:
            if len(re.findall(r'\b' + re.escape(o) + r'\b', all_code)) <= 1:
                hit('C6 declared option never referenced elsewhere', next(l for l in impl if re.search(r'\b' + re.escape(name) + r'\s*=\s*method', l.code)), f'{name}: {o}')

    # ---------- string keys read but never written; option strings used in tests/docs but unknown to the implementation
    builtin_keys = {'source directory', 'version', 'auxiliary files', 'package prefix', 'pkgname', 'title',
                    'Headline', 'exported symbols', 'private dictionary', 'test inputs', 'example results',
                    'raw documentation', 'source file', 'baseFilename', 'test number', 'VERSION',
                    'compile node name', 'operating system', 'machine'}
    reads = defaultdict(list)
    for l in impl:
        if re.search(r'\b(PackageDictionary|version|Core#|loadedFiles)\b', l.code):
            continue
        for k in re.findall(r'#\??\s*"([^"]+)"', l.code):
            reads[k].append(l)
    written = set(re.findall(r'"([^"]+)"\s*=>', all_code)) | set(re.findall(r'#\s*"([^"]+)"\s*(?:=|:=)(?!=)', all_code))
    for k, ls in reads.items():
        if k not in written and k not in builtin_keys:
            hit('C7 string key read but never written in this package', ls[0], f'"{k}" (read {len(ls)}x; external producer?)')
    compared_opts = set(re.findall(r'\.(\w+)\s*(?:===|==|=!=|!=)\s*"', impl_text)) | set(re.findall(r'#"?(\w+)"?\s*(?:===|==|=!=|!=)\s*"', impl_text))
    impl_strings = set(re.findall(r'"([^"\n]*)"', impl_text))
    for l in tst + doc:
        if re.search(r'\btry\b', l.raw):  # deliberate invalid-value tests
            continue
        for name, val in re.findall(r'\b([A-Z]\w*)\s*=>\s*"([^"]+)"', l.raw):
            if name in compared_opts and val not in impl_strings:
                hit('C8 option value used in tests/docs is never recognized by the implementation', l, f'{name} => "{val}"')

    # ---------- side effects and state
    frames = paren_frames(impl)
    aliases = set(re.findall(r'\b(\w+)\s*:?=\s*[\w.#"]*\b(?:Verbose|debugLevel)\b', impl_text))
    gate = r'(Verbose|debugLevel|verbose|VERBOSE' + ''.join('|\\b' + re.escape(a) + r'\b' for a in aliases) + ')'
    guard_rx = re.compile(gate + r'[^;]*\b(then|do)\s*$|\bif\b[^;]*' + gate)
    for idx, l in enumerate(impl):
        c = l.code
        if re.search(STATEMENT_START + r'\s*use\s+[\w(#]', c) or re.match(r'\s*use\s', c):
            hit('S1 `use` in package code changes the active ring/user bindings', l)
        prev = next((x.code.strip() for x in reversed(impl[max(0, idx - 4):idx]) if x.code.strip()), ';')
        starts_output = (re.search(r'\bprint\s*[("\w]|\b(stdio|stdout)\s*<<', c)
                         or (re.match(r'\s*<<', c) and re.search(r'(;|\(|\bthen|\belse|\bdo)$', prev)))
        if starts_output:
            same_line = re.search(gate, c.split('print')[0].split('<<')[0])
            enclosing = any(guard_rx.search(f) for f in frames[idx])
            printer = re.search(r'AfterPrint|AfterNoPrint|BeforePrint', ' '.join(frames[idx]) + ' '.join(x.code for x in impl[max(0, idx - 6):idx]))
            if not (same_line or enclosing or printer or re.search(gate + r'[^;]*\b(then|do)\s*$', prev)):
                hit('S2 output not gated by Verbose/debugLevel', l)
        if re.search(r'\blookup\s*\(\s*\w+\s*,\s*[A-Z]', c) and re.search(r'=\s*lookup', c):
            hit('S3 saves an existing method before overriding it (global behavior change?)', l)
        if re.search(r'^\s*\w+\s+(Type|Thing)\s*:=|^\s*\w+\s*\(\s*(Type|Thing)\s*\)\s*:=', c):
            hit('S3 method installed on Type/Thing (affects every object)', l)
        if re.search(r'needsPackage\s*\(.*Configuration', c) or re.search(r'\bsetRandomSeed\b', c):
            hit('S4 load-time or call-time change to shared configuration/random state', l)
        if re.search(r'\b(debugLevel|errorDepth|gbTrace|printWidth|printingPrecision)\s*=[^=]', c):
            hit('S4 assigns a session-wide variable', l)
        if re.search(r'\bclass\s*\(?\s*\w+\s*\)?\s*===\s*[A-Z]', c):
            hit('S5 `class x === T` disables inheritance (use instance)', l)
        if re.search(r':=\s*local\s+\w', c):
            hit('S6 ring variables from `local` symbols are inaccessible to users if returned', l)

    # ---------- external tools and files
    ext = Counter()
    for l in impl:
        c = l.code
        for k, rx in [('run', r'\brun\s*[("]|\brun\s+\w'), ('runProgram', r'\brunProgram\b'), ('findProgram', r'\bfindProgram\b'),
                      ('shell get "!"', r'\bget\s*"!'), ('temporaryFileName', r'\btemporaryFileName\b'), ('openOut', r'\bopenOut\b'),
                      ('removeFile', r'\bremoveFile\b|\bremoveDirectory\b'), ('value', r'\bvalue\b')]:
            if re.search(rx, c):
                ext[k] += 1
        if re.search(r'\brun\s*\(?\s*("[^"]*"\s*\||\w+\s*\|)', c) or re.search(r'\bget\s*\(?\s*"!"\s*\|', c):
            hit('X1 shell command assembled by string concatenation (quoting, exit status?)', l)
        else:
            mv = re.search(r'\b(?:run|runProgram)\s*\(?\s*([A-Za-z]\w*)\s*\)?\s*(;|$)', c)
            if mv:
                i0 = impl.index(l)
                ctx = '\n'.join(x.code for x in impl[max(0, i0 - 6):i0 + 1])
                if re.search(r'\b' + re.escape(mv.group(1)) + r'\s*:?=\s*[^;]*"\s*\|', ctx):
                    hit('X1 shell command assembled by string concatenation (quoting, exit status?)', l)
    if (ext['temporaryFileName'] or ext['openOut']) and not ext['removeFile']:
        first = next(l for l in impl if re.search(r'temporaryFileName|openOut', l.code))
        hit('X2 temporary/output files created but nothing is ever removed', first)
    if ext['value'] and re.search(r'\b(get|lines\s+get|openIn)\b', impl_text):
        for idx, l in enumerate(impl):
            if re.search(r'\bvalue\b', l.code):
                ctx = ' '.join(x.code for x in impl[max(0, idx - 3):idx + 1])
                if re.search(r'\b(get|lines|separate\w*|read|substring|replace|openIn)\b', ctx):
                    hit('X3 `value` evaluates text as code (check whether it comes from files)', l)

    # ---------- performance patterns
    for l in impl:
        c = l.code
        if re.search(r'\b(\w+)\s*=\s*(?:append|prepend)\s*\(\s*\1\b|\b(\w+)\s*=\s*\2\s*\|\s*\{|\b(\w+)\s*=\s*join\s*\(\s*\3\b|\b(\w+)\s*=\s*(?:drop|delete)\s*\([^)]*\b\4\b', c):
            hit('P1 growing/shrinking an immutable list by reassignment (quadratic in loops)', l)
        if re.search(r'\b(subsets|permutations|partitions|compositions)\s*\(', c):
            hit('P2 full combinatorial enumeration (check sizes and whether all are needed)', l)

    # ---------- documentation contracts and coverage maps
    declared, typical, installed_names = {}, {}, set()
    ret_re = re.compile(r"^\s*([A-Za-z][\w']*)(?:\s*\(([^)]*)\)|\s+([A-Z][\w']*))\s*:=\s*(?:([A-Z][\w']*)\s*=>)?")
    for l in impl:
        m = ret_re.match(l.code)
        if m:
            name, sig = m.group(1), re.sub(r'\s', '', m.group(2) or m.group(3) or '').strip('()')
            installed_names.add(name)
            if m.group(4):
                declared[(name, sig)] = m.group(4)
    for m in re.finditer(r"\b([A-Za-z][\w']*)\s*=\s*method\s*\(", impl_text):
        installed_names.add(m.group(1))
        tv = re.search(r"\bTypicalValue\s*=>\s*([A-Z][\w']*)", balanced_args(impl_text, m.end() - 1))
        if tv:
            typical[m.group(1)] = tv.group(1)
    for m in re.finditer(r"(?m)^\s*([A-Za-z][\w']*)\s*=\s*(?:\([^)]*\)|[A-Za-z][\w']*)\s*->", impl_text):
        installed_names.add(m.group(1))
    nodes = parse_doc_nodes(doc)
    generic = {'Thing', 'Type', 'Nothing', 'Expression', 'Net', 'BasicList', 'VisibleList', 'Function'}
    for n in nodes:
        outs = [o for o in n['outputs'] if o not in generic]
        if not outs:
            continue
        decl = []
        for kind, name, sig in n['parsed']:
            if kind == 'method':
                d = declared.get((name, sig)) or typical.get(name)
            elif kind == 'name':
                exp_types = {t for (nm, _), t in declared.items() if nm == name}
                d = next(iter(exp_types)) if len(exp_types) == 1 else typical.get(name)
            else:
                continue
            if d and d not in generic:
                decl.append((f'{name}({sig})' if sig else name, d))
        if not decl:
            continue
        # A node documenting several overloads usually lists one output per overload, so it is
        # flagged only when its Outputs mention none of the declared types. A single-method node
        # with several outputs is documenting a sequence.
        if len(decl) == 1 and len(outs) > 1 and decl[0][1] != 'Sequence':
            hit('D1 documented outputs disagree with the declared return type', n['line'],
                f'{decl[0][0]}: docs list {len(outs)} outputs (a sequence); code declares {decl[0][1]}')
        elif not any(d in outs for _, d in decl):
            hit('D1 documented outputs disagree with the declared return type', n['line'],
                f"{', '.join(k for k, _ in decl[:3])}: docs say {'/'.join(outs)}; code declares {'/'.join(sorted({d for _, d in decl}))}")
    no_example = [n for n in nodes if not n['example'] and not all(k == 'option' for k, _, _ in n['parsed'])]
    for n in no_example:
        label = ', '.join(nm for _, nm, _ in n['parsed'][:2]) or '?'
        hit('D2 documentation node without an example', n['line'], label[:80])
    test_text = no_strings('\n'.join([l.code for l in tst] + helper_code))
    funcs = sorted(e for e in exports if e in installed_names)
    untested = [f for f in funcs if not re.search(r'(?<![\w\'])' + re.escape(f) + r'(?![\w\'])', test_text)]

    # ---------- per-export validation: exported functions with no error() on any path they reach
    defs = defaultdict(list)          # name -> body texts of every definition/overload
    arity = defaultdict(int)
    def_re = re.compile(r"^([A-Za-z][\w']*)(?:\s*\(([^)]*)\)|\s+([A-Z][\w']*))?\s*:?=\s*")
    for idx, l in enumerate(impl):
        if not l.raw[:1].strip():
            continue
        m = def_re.match(l.code)
        if not m or m.group(1) not in installed_names:
            continue
        body = [l.code]
        for nxt in impl[idx + 1:]:
            if nxt.raw[:1].strip() and not nxt.raw.startswith(')'):
                break
            body.append(nxt.code)
        defs[m.group(1)].append('\n'.join(body))
        sig = m.group(2) if m.group(2) is not None else m.group(3)
        if sig:
            arity[m.group(1)] = max(arity[m.group(1)], len([t for t in sig.split(',') if t.strip()]))
    known = set(defs)
    calls = {n: {c for c in re.findall(r"[A-Za-z][\w']*", '\n'.join(b)) if c in known and c != n} for n, b in defs.items()}
    raises = {n for n, b in defs.items() if re.search(r'\berror\s*[("]', '\n'.join(b))}

    def reaches_error(n, depth=3, seen=None):
        seen = seen or set()
        if n in raises:
            return True
        if depth == 0 or n in seen:
            return False
        seen.add(n)
        return any(reaches_error(c, depth - 1, seen) for c in calls.get(n, ()))
    unvalidated = [f for f in funcs if f in defs and not reaches_error(f)]
    for f in unvalidated:
        if f in opt_methods or arity.get(f, 0) >= 2:
            first_def = next((l for l in impl if l.raw[:1].strip() and def_re.match(l.code) and def_re.match(l.code).group(1) == f), None)
            if first_def is not None:
                hit('V1 exported function with no error() on any path it reaches (does it validate its input?)', first_def,
                    f'{f}: ' + ('takes options' if f in opt_methods else f'{arity[f]} arguments'))

    # ---------- silent boundary traps
    # A -1 "not found" sentinel used as an index silently selects the LAST element (negative indices
    # count from the end), e.g. L#(findIndex x) when findIndex returns -1.
    sentinel_funcs = set()
    cur_fn = None
    for l in impl:
        m = re.match(r"^\s*([A-Za-z][\w']*)\s*(?:\([^)]*\)|\s[A-Z][\w']*)?\s*:?=\s*(?:method\b|.*->)", l.code)
        if m and not l.raw[:1].isspace():
            cur_fn = m.group(1)
        if cur_fn and re.search(r'\breturn\s*\(?\s*-1\b|\bthen\s+-1\b|\belse\s+-1\b', l.code):
            sentinel_funcs.add(cur_fn)
    for idx, l in enumerate(impl):
        c = l.code
        for fn in sentinel_funcs:
            if re.search(r'[#_]\s*\(?\s*' + re.escape(fn) + r'\b', c):
                hit('C9 a function that can return -1 is used as an index (negative indices wrap to the end)', l, f'{fn} returns -1')
        mv = re.search(r"\b([A-Za-z][\w']*)\s*:?=\s*-1\s*;", c)
        if mv:
            v = mv.group(1)
            for nxt in impl[idx + 1:idx + 40]:
                if re.search(r'[#_]\s*\(?\s*' + re.escape(v) + r'\b(?!\s*[+*/-])', nxt.code) and not re.search(r'\b' + re.escape(v) + r'\s*(>=?|<=?|==|!=|=!=|===)\s*', nxt.code):
                    hit('C9 a -1 sentinel may reach an index (negative indices wrap to the end)', nxt, f'{v} initialized to -1 at line {l.no}')
                    break
    pkg_funcs = sorted(f for f in set(installed_names) | exports if len(f) > 2)
    own_call = (r'|'.join(re.escape(f) for f in pkg_funcs) + r')\b') if pkg_funcs else r'(?!x)x)'
    c10 = re.compile(r'\bcomplex\s*\(?\s*(for\b|apply\s*\(|select\s*\()'
                     r'|\b(ideal|sum|product)\s*\(?\s*(select\s*\(|(' + own_call + r')')
    for l in impl:
        m = c10.search(l.code)
        if m:
            hit('C10 object built from a list that may be empty (ideal {} is over ZZ, sum {} is 0, complex {} fails)', l, m.group(0)[:40])
    # ---------- mutation of objects that also carry cached derived results
    if re.search(r'\bcacheValue\b|\.cache\s*#|\.cache\.\w+\s*=|\bCacheTable\b', impl_text):
        inst = re.compile(r"^([A-Za-z][\w']*)(?:\s*\([^)]*\)|\s+[A-Z][\w']*)\s*:=\s*(?:[A-Z][\w']*\s*=>\s*)?(?:[a-z]\w*\s*->\s*)?(\([^)]*\)|[A-Za-z]\w*)\s*->")
        for idx, l in enumerate(impl):
            m = inst.match(l.code)
            # Lazy memoization (X#"dim" = ...) is the caching mechanism itself; deliberate mutators are what can leave
            # caches stale, and they are conventionally named for what they change.
            if not m or not re.match(r'(set|add|remove|delete|insert|update|change|replace|clear|reset|append|merge|force)[A-Z_]', m.group(1)):
                continue
            params = re.findall(r'[A-Za-z]\w*', m.group(2))
            body = [l]
            for nxt in impl[idx + 1:]:
                if nxt.raw[:1].strip() and not nxt.raw.startswith(')'):
                    break
                body.append(nxt)
            for b in body:
                mm = re.search(r'\b(' + '|'.join(map(re.escape, params)) + r')\s*(?:\.\s*(\w+)|#\s*"?([\w ]+)"?)\s*=(?![=!])', b.code) if params else None
                if mm and (mm.group(2) or mm.group(3) or '').strip() not in ('cache',) and not re.search(r'\.cache\b', b.code):
                    hit('S8 mutates an argument object in a package that caches derived results (are dependent caches invalidated?)', b,
                        f'{m.group(1)} sets {mm.group(1)}.{(mm.group(2) or mm.group(3)).strip()}')
                    break

    # A package with an explicit cache-invalidation routine should clear every key that depends on the
    # data its mutators change; keys written elsewhere but never cleared are candidates for stale results.
    def cache_keys(text):
        ks = re.findall(r'\.cache\s*#\??\s*(\(\s*symbol\s+\w+\s*\)|"[^"]+"|[A-Za-z]\w*)', text)
        ks += re.findall(r'\.cache\s*\.\s*\??\s*([A-Za-z]\w*)', text)
        ks += [k for k in re.findall(r'remove\s*\(\s*\w+\s*\.\s*cache\s*,\s*(\(?\s*symbol\s+\w+\s*\)?|"[^"]+"|[A-Za-z]\w*)', text)]
        return {re.sub(r'^\(?\s*symbol\s+|\s*\)$|"', '', k).strip() for k in ks}
    inval_bodies = []
    for idx, l in enumerate(impl):
        m = re.match(r"^((?:invalidate|clear|reset)\w*)\b", l.code)
        if m and ':=' in l.code or (m and re.search(r'=\s*(method|\(|[A-Za-z]\w*\s*->)', l.code)):
            body = [l]
            for nxt in impl[idx + 1:]:
                if nxt.raw[:1].strip() and not nxt.raw.startswith(')'):
                    break
                body.append(nxt)
            inval_bodies.append((m.group(1), body))
    if inval_bodies:
        cleared = set().union(*(cache_keys('\n'.join(b.code for b in body)) for _, body in inval_bodies))
        names = sorted({n for n, _ in inval_bodies})
        writes = {}
        for l in impl:
            for k in re.findall(r'\.cache\s*#\s*(\(\s*symbol\s+\w+\s*\)|"[^"]+"|[A-Za-z]\w*)\s*=(?![=!])', l.code) + re.findall(r'\.cache\s*\.\s*([A-Za-z]\w*)\s*=(?![=!])', l.code):
                writes.setdefault(re.sub(r'^\(?\s*symbol\s+|\s*\)$|"', '', k).strip(), l)
        for k, l in writes.items():
            if k not in cleared and not any(l in body for _, body in inval_bodies):
                hit('S9 cache key never cleared by the package\'s own invalidation routine (stale after mutation?)', l,
                    f'"{k}" not handled by {", ".join(names)}')

    # ---------- dependency seams: methods installed on functions and types the package does not own
    own_types = set(re.findall(r"(?m)^\s*([A-Z][\w']*)\s*=\s*new\s+(?:Type|HeaderType|SelfInitializingType|WrapperType)\s+of\b", impl_text))
    deps = []
    hdr = re.search(r'newPackage\s*\((.*?)\n\s*\)', impl_text, re.S)
    if hdr:
        for key in ('PackageImports', 'PackageExports'):
            mm = re.search(key + r'\s*=>\s*\{([^}]*)\}', hdr.group(1))
            if mm:
                deps += re.findall(r'"([^"]+)"', mm.group(1))
    dep_installs, dep_checked = {}, []
    for dep in sorted(set(deps)):
        for f in (os.path.join(root, dep + '.m2'), os.path.join(os.path.dirname(root), dep + '.m2'),
                  os.path.join(os.path.dirname(root), dep, dep + '.m2')):
            if os.path.isfile(f) and os.path.abspath(f) != os.path.abspath(entry):
                try:
                    _, dl, _, _, _, _ = load_package(f)
                except Exception:
                    break
                dep_checked.append(dep)
                for (df, dno, dln) in dl:
                    mi = ret_re.match(strip_comment(dln))
                    if mi:
                        sig = re.sub(r'\s', '', mi.group(2) or mi.group(3) or '').strip('()')
                        dep_installs.setdefault((mi.group(1), sig), f'{dep}/{df}:{dno}')
                break
    foreign = []
    for l in impl:
        m = ret_re.match(l.code)
        if not m:
            continue
        name, sig = m.group(1), re.sub(r'\s', '', m.group(2) or m.group(3) or '').strip('()')
        types = [t for t in sig.split(',') if t]
        if name in exports or re.search(r'\b' + re.escape(name) + r'\s*=\s*method\b', impl_text):
            continue
        if not types or any(t in own_types for t in types) or not all(re.match(r"[A-Z][\w']*$", t) for t in types):
            continue
        where = dep_installs.get((name, sig))
        if where:
            hit('S7 reinstalls a method that an imported package already defines (changes it for everyone)', l, f'{name}({sig}) also at {where}')
        else:
            foreign.append(f'{name}({sig}) at {l.loc()}')

    # ---------- summary
    impl_kloc = max(ncl(impl), 1) / 1000
    errors = len(re.findall(r'\berror\s*[("]', impl_text))
    summary = dict(
        package=os.path.basename(entry)[:-3], entry=os.path.relpath(entry, root),
        loaded_files=loaded, unresolved_loads=missing,
        not_loaded_after_end=post_end,
        impl_lines=ncl(impl), doc_lines=sum(1 for l in doc if l.raw.strip() and not l.raw.strip().startswith('--')), test_lines=ncl(tst),
        exports=len(exports), undocumented_exports=undocumented,
        doc_example_blocks=examples,
        tests=len(test_summary), asserts=sum(t['asserts'] for t in test_summary),
        tests_without_assert=sum(1 for t in test_summary if t['asserts'] == 0),
        doc_nodes=len(nodes), doc_nodes_without_example=len(no_example),
        exported_functions=len(funcs), exported_functions_never_in_tests=untested,
        files_loaded_by_tests=test_files, deferred_loads=deferred_loads,
        exported_functions_without_error_path=unvalidated,
        imports=sorted(set(deps)), imports_checked_for_overrides=dep_checked,
        foreign_installs=foreign,
        error_calls=errors, error_calls_per_kloc=round(errors / impl_kloc, 1),
        options_methods=sorted(opt_methods),
        external=dict(ext),
        todo_fixme=len(re.findall(r'\b(TODO|FIXME|XXX|HACK)\b', '\n'.join(l.raw for l in impl))),
        commented_code_lines=sum(1 for l in impl if l.raw.strip().startswith('--') and re.search(r'(:=|->|\);|\bif\b.*\bthen\b|\bfor\b.*\bdo\b)', l.raw)),
    )
    unloaded = []
    for dp, _, fns in os.walk(root):
        for fn in fns:
            rel = os.path.relpath(os.path.join(dp, fn), root)
            if fn.endswith('.m2') and rel not in loaded and rel not in test_files and rel.startswith(summary['package'] + os.sep):
                unloaded.append(rel)
    summary['m2_files_not_loaded'] = sorted(unloaded)
    return summary, dict(hits)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('path')
    ap.add_argument('--json', action='store_true', help='machine-readable output')
    ap.add_argument('--max', type=int, default=12, help='max hits shown per check (text mode)')
    a = ap.parse_args()
    summary, hits = scan(resolve_entry(a.path))
    if a.json:
        json.dump(dict(summary=summary, candidates=hits), sys.stdout, indent=1)
        return
    s = summary
    print(f"# Static triage: {s['package']}\n")
    print(f"Loaded files ({len(s['loaded_files'])}): " + ', '.join(s['loaded_files'][:30]) + (' ...' if len(s['loaded_files']) > 30 else ''))
    if s['unresolved_loads']:
        print('Unresolved loads: ' + '; '.join(s['unresolved_loads']))
    for p in s['not_loaded_after_end']:
        if p['lines_after'] > 3:
            print(f"After `end` in {p['file']}:{p['line']}: {p['lines_after']} lines NOT loaded"
                  + (' (contains TEST -- not registered)' if p['has_TEST'] else '') + (' (contains docs -- not installed)' if p['has_doc'] else ''))
    if s['deferred_loads']:
        print(f"Loads inside function bodies (run only when called, not at package load): {len(s['deferred_loads'])} -> " + '; '.join(s['deferred_loads'][:6]) + (' ...' if len(s['deferred_loads']) > 6 else ''))
    if s['files_loaded_by_tests']:
        print(f"Files loaded only from inside TEST blocks ({len(s['files_loaded_by_tests'])}; their asserts count toward those tests): "
              + ', '.join(s['files_loaded_by_tests'][:10]) + (' ...' if len(s['files_loaded_by_tests']) > 10 else ''))
    if s['m2_files_not_loaded']:
        print(f"Package .m2 files never loaded ({len(s['m2_files_not_loaded'])}): " + ', '.join(s['m2_files_not_loaded'][:15]) + (' ...' if len(s['m2_files_not_loaded']) > 15 else ''))
    print(f"\nSize: {s['impl_lines']} implementation, {s['doc_lines']} documentation, {s['test_lines']} test lines (non-blank, non-comment)")
    print(f"Exports: {s['exports']}; without a documentation Key: {len(s['undocumented_exports'])}" + (f" -> {', '.join(s['undocumented_exports'][:20])}" if s['undocumented_exports'] else ''))
    print(f"Doc nodes: {s['doc_nodes']} ({s['doc_nodes_without_example']} without an example); doc example blocks: {s['doc_example_blocks']}")
    print(f"TEST blocks: {s['tests']} ({s['asserts']} asserts, {s['tests_without_assert']} blocks without assert)")
    nt = s['exported_functions_never_in_tests']
    print(f"Exported functions never mentioned in any TEST: {len(nt)} of {s['exported_functions']}" + (f" -> {', '.join(nt[:25])}" + (' ...' if len(nt) > 25 else '') if nt else ''))
    print(f"error() calls in implementation: {s['error_calls']} ({s['error_calls_per_kloc']}/kLOC; "
          "in the 24-package calibration study, curated top packages had a median of 32 and the rest 8)")
    uv = s['exported_functions_without_error_path']
    print(f"Exported functions with no error() on any path they reach: {len(uv)} of {s['exported_functions']}"
          + (f" -> {', '.join(uv[:20])}" + (' ...' if len(uv) > 20 else '') if uv else ''))
    print(f"Methods with options: {', '.join(s['options_methods']) or 'none'}")
    if s['imports']:
        unchecked = [d for d in s['imports'] if d not in s['imports_checked_for_overrides']]
        print(f"Imports: {', '.join(s['imports'])}" + (f" (sources not found, so not checked for overridden methods: {', '.join(unchecked)})" if unchecked else ' (all checked for overridden methods)'))
    if s['foreign_installs']:
        fi = s['foreign_installs']
        print(f"Methods installed on functions and types the package doesn't own: {len(fi)} -> " + ', '.join(fi[:8]) + (' ...' if len(fi) > 8 else '')
              + ". Check whether Core or an import already defines each; collisions found in available imports are listed under S7.")
    if s['external']:
        print('External/file operations: ' + ', '.join(f'{k}={v}' for k, v in sorted(s['external'].items())))
    print(f"TODO/FIXME: {s['todo_fixme']}; commented-out code lines: {s['commented_code_lines']}")
    print('\n## Candidates (heuristic leads -- verify each before reporting)\n')
    if not hits:
        print('none')
    for check in sorted(hits):
        hs = hits[check]
        print(f'### {check} ({len(hs)})')
        for h in hs[:a.max]:
            print(f"- {h['loc']}: `{h['code']}`" + (f"  [{h['note']}]" if h['note'] else ''))
        if len(hs) > a.max:
            print(f'- ... {len(hs) - a.max} more (use --max or --json)')
        print()


if __name__ == '__main__':
    main()
