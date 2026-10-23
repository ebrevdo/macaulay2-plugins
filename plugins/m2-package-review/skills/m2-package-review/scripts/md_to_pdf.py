#!/usr/bin/env python3
"""Convert review reports (Markdown) to formatted, clickable PDFs.

Usage:
    python3 -I md_to_pdf.py review.md [more.md ...]     # writes review.pdf next to each input
    python3 -I md_to_pdf.py review.md -o out.pdf        # one input, explicit output
    python3 -I md_to_pdf.py review.md --html            # write the styled HTML instead
    python3 -I md_to_pdf.py review.md --page "Letter"    # portrait; the default is Letter landscape
    python3 -I md_to_pdf.py review.md --source-url https://github.com/Macaulay2/M2/blob/<commit>/M2/Macaulay2/packages/

What it adds to plain Markdown, when the document has the matching parts:
  - a clickable contents list at the top, and a PDF bookmark outline (Chrome 128 and later);
  - finding cards (#### F01. ...) with a border colored by severity, and severity, certainty and kind pills;
  - links from finding ids in the text ("see F23") and from the severity counts to their sections;
  - with --source-url, every `path.m2:12-34` citation links to those lines (GitHub-style #L12-L34 anchors);
  - colored outcomes in boundary-sweep and verdict tables.

Markdown -> HTML uses pandoc if installed, otherwise the Python `markdown` package.
HTML -> PDF uses a headless Chrome/Chromium/Edge if one is found, otherwise WeasyPrint, otherwise
wkhtmltopdf. If no PDF engine is available, the styled HTML is written instead (open it in a browser
and print to PDF) and the script exits with status 2.
"""
import argparse
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CSS = """
@page { size: __PAGE__; margin: __MARGIN__; }
:root { --ink: #1d2433; --muted: #5b6475; --accent: #1f4e8c; --rule: #d5dbe5; --soft: #f5f7fb;
        --crit: #b42318; --crit-bg: #fef3f2; --major: #c4320a; --major-bg: #fff4ed;
        --mod: #a15c07; --mod-bg: #fffaeb; --minor: #475467; --minor-bg: #f2f4f7;
        --ok: #067647; --ok-bg: #ecfdf3; }
* { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-family: "DejaVu Sans", "Helvetica Neue", Arial, sans-serif; font-size: 10.3pt; line-height: 1.45;
       color: var(--ink); margin: 0; }
h1 { font-size: 21pt; color: var(--accent); margin: 0 0 0.35em; padding-bottom: 0.25em;
     border-bottom: 4px solid var(--accent); }
h2 { font-size: 15pt; color: var(--accent); margin-top: 1.5em; padding-bottom: 0.15em;
     border-bottom: 1.5px solid var(--rule); break-after: avoid; }
h3 { font-size: 12.5pt; margin-top: 1.3em; break-after: avoid; }
h3.sev-1 { color: var(--crit); } h3.sev-2 { color: var(--major); } h3.sev-3 { color: var(--mod); } h3.sev-4 { color: var(--minor); }
h4 { font-size: 11pt; margin: 0 0 0.35em; break-after: avoid; }
a { color: var(--accent); text-decoration: none; border-bottom: 1px dotted #9db3d3; }
a.xref { font-weight: 600; }
a.src { border-bottom: none; } a.src code { border-bottom: 1px dotted #9db3d3; }
code { font-family: "DejaVu Sans Mono", Menlo, Consolas, monospace; font-size: 8.8pt; background: #eef1f6;
       padding: 0 3px; border-radius: 3px; }
pre { background: var(--soft); border: 1px solid var(--rule); border-left: 4px solid #8a9bb8; border-radius: 4px;
      padding: 6px 9px; white-space: pre-wrap; overflow-wrap: anywhere; break-inside: avoid; }
pre code { background: none; padding: 0; font-size: 8.4pt; }
table { border-collapse: separate; border-spacing: 0; width: 100%; font-size: 8.9pt; margin: 0.7em 0;
        border: 1px solid var(--rule); border-radius: 5px; overflow: hidden; }
th, td { padding: 4px 7px; vertical-align: top; border-bottom: 1px solid var(--rule); border-right: 1px solid var(--rule);
         overflow-wrap: break-word; word-break: normal; hyphens: manual; }
th:last-child, td:last-child { border-right: none; }
tr:last-child td { border-bottom: none; }
th { background: #e8eef7; color: #23395d; text-align: left; font-weight: 600; }
tbody tr:nth-child(even) td { background: #f8fafc; }
td code { overflow-wrap: anywhere; }
tr { break-inside: avoid; }
td.out-ok { color: var(--ok); background: var(--ok-bg) !important; font-weight: 600; }
td.out-finding { background: var(--crit-bg) !important; font-weight: 600; }
td.out-unclear { color: var(--mod); background: var(--mod-bg) !important; font-weight: 600; }
td.out-na { color: var(--muted); }
td.v-good { color: var(--ok); font-weight: 600; } td.v-part { color: var(--mod); font-weight: 600; }
td.v-bad { color: var(--crit); font-weight: 600; }
.finding { border: 1px solid var(--rule); border-left: 6px solid var(--minor); border-radius: 6px;
           padding: 8px 12px 4px; margin: 0.9em 0; background: #fff; }
.finding.sev-1 { border-left-color: var(--crit); } .finding.sev-2 { border-left-color: var(--major); }
.finding.sev-3 { border-left-color: var(--mod); } .finding.sev-4 { border-left-color: var(--minor); }
.finding.sev-1 h4 { color: var(--crit); } .finding.sev-2 h4 { color: var(--major); }
.finding.sev-3 h4 { color: var(--mod); } .finding.sev-4 h4 { color: #344054; }
.pill { display: inline-block; padding: 0 7px; border-radius: 9px; font-size: 8.6pt; font-weight: 600;
        line-height: 1.55; border: 1px solid transparent; }
.pill.sev-1 { color: #fff; background: var(--crit); } .pill.sev-2 { color: #fff; background: var(--major); }
.pill.sev-3 { color: #fff; background: var(--mod); } .pill.sev-4 { color: #fff; background: var(--minor); }
.pill.cert-definite { color: var(--ok); background: var(--ok-bg); border-color: #abefc6; }
.pill.cert-probable { color: var(--mod); background: var(--mod-bg); border-color: #fedf89; }
.pill.cert-speculative { color: var(--muted); background: var(--minor-bg); border-color: #d0d5dd; }
.pill.kind { color: var(--accent); background: #eaf1fb; border-color: #c7d7f0; }
a.chip { display: inline-block; padding: 1px 9px; margin: 0 2px; border-radius: 10px; font-weight: 600; border: none; }
a.chip.sev-1 { color: #fff; background: var(--crit); } a.chip.sev-2 { color: #fff; background: var(--major); }
a.chip.sev-3 { color: #fff; background: var(--mod); } a.chip.sev-4 { color: #fff; background: var(--minor); }
nav.toc { border: 1px solid var(--rule); border-radius: 6px; background: var(--soft); padding: 6px 12px 8px;
          margin: 0.6em 0 1em; font-size: 8.9pt; }
nav.toc .toc-title { font-weight: 700; color: var(--accent); margin-bottom: 3px; }
nav.toc ul { margin: 0; padding-left: 1.1em; } nav.toc li { margin: 1px 0; }
nav.toc ul.findings { columns: __COLS__; column-gap: 1.6em; list-style: none; padding-left: 0.4em; }
nav.toc ul.findings li { break-inside: avoid; }
nav.toc a { border-bottom: none; }
.dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 5px; vertical-align: 1px; }
.dot.sev-1 { background: var(--crit); } .dot.sev-2 { background: var(--major); }
.dot.sev-3 { background: var(--mod); } .dot.sev-4 { background: var(--minor); }
"""

BROWSERS = ['google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser', 'microsoft-edge', 'msedge',
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            '/Applications/Chromium.app/Contents/MacOS/Chromium',
            '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge']
DEFAULT_PAGE = 'Letter landscape'   # about 125 characters per line of text; 'Letter' is about 95
SEV_WORDS = {'critical': '1', 'major': '2', 'moderate': '3', 'minor': '4'}
FINDING_ID = r'[A-Z]{1,2}\d{2,3}'


def md_to_body(text):
    if shutil.which('pandoc'):
        r = subprocess.run(['pandoc', '-f', 'gfm', '-t', 'html5'], input=text, capture_output=True, text=True)
        if r.returncode == 0:
            return r.stdout
    try:
        import markdown
    except ImportError:
        sys.exit('md_to_pdf: needs pandoc or the Python "markdown" package to convert Markdown')
    return markdown.markdown(text, extensions=['tables', 'fenced_code', 'sane_lists', 'toc'])


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', re.sub(r'<[^>]+>', '', s).lower()).strip('-') or 'section'


def enhance(body, source_url=None, toc=True):
    """Add anchors, finding cards, pills, cross-reference links, and source links to converted HTML."""
    used = set()

    def heading(m):
        level, attrs, inner = m.group(1), m.group(2), m.group(3)
        plain = html.unescape(re.sub(r'<[^>]+>', '', inner)).strip()
        fid = re.match(rf'({FINDING_ID})\.\s', plain)
        hid = fid.group(1).lower() if fid else (re.search(r'id="([^"]+)"', attrs).group(1)
                                                if 'id="' in attrs else slug(plain))
        while hid in used:
            hid += '-x'
        used.add(hid)
        attrs = re.sub(r'\s*id="[^"]*"', '', attrs)
        cls = ''
        if level == '3' and plain.lower() in SEV_WORDS:
            cls = f' class="sev-{SEV_WORDS[plain.lower()]}"'
        return f'<h{level} id="{hid}"{cls}{attrs}>{inner}</h{level}>'
    body = re.sub(r'<h([1-6])([^>]*)>(.*?)</h\1>', heading, body, flags=re.S)

    findings = {}   # id -> (title, severity)
    for m in re.finditer(rf'<h4 id="([a-z]{{1,2}}\d{{2,3}})"[^>]*>(.*?)</h4>', body, re.S):
        findings[m.group(1)] = [html.unescape(re.sub(r'<[^>]+>', '', m.group(2))).strip(), None]

    # Wrap each finding (an h4 up to the next h2/h3/h4) in a card colored by its severity.
    starts = [m.start() for m in re.finditer(r'<h[2-4][ >]', body)]
    out, pos = [], 0
    for i, s in enumerate(starts):
        if not body.startswith('<h4', s):
            continue
        e = starts[i + 1] if i + 1 < len(starts) else len(body)
        chunk = body[s:e]
        sev = re.search(r'Severity:</strong>\s*([1-4])', chunk)
        fid = re.match(r'<h4 id="([^"]+)"', chunk).group(1)
        if fid in findings and sev:
            findings[fid][1] = sev.group(1)
        out.append(body[pos:s])
        out.append(f'<div class="finding sev-{sev.group(1) if sev else 0}">' + chunk.rstrip() + '</div>\n')
        pos = e
    out.append(body[pos:])
    body = ''.join(out)

    # Pills for severity, certainty and kind; chips for the severity counts.
    body = re.sub(r'(<strong>Severity:</strong>)\s*([1-4]) (Critical|Major|Moderate|Minor)',
                  r'\1 <span class="pill sev-\2">\2 \3</span>', body)
    body = re.sub(r'(<strong>Certainty:</strong>)\s*(definite|probable|speculative)',
                  r'\1 <span class="pill cert-\2">\2</span>', body)
    body = re.sub(r'(<strong>Kind:</strong>)\s*([a-z][a-z-]+)', r'\1 <span class="pill kind">\2</span>', body)
    sev_ids = set(re.findall(r'<h3 id="([^"]+)" class="sev-', body))

    def chip(m):
        n, word = m.group(1), m.group(2)
        target = word if word in sev_ids else None
        label = f'{n} {word}'
        return (f'<a class="chip sev-{SEV_WORDS[word]}" href="#{target}">{label}</a>' if target
                else f'<span class="pill sev-{SEV_WORDS[word]}">{label}</span>')
    body = re.sub(r'(<strong>Findings:</strong>)(.*?)</p>',
                  lambda m: m.group(1) + ' ' + re.sub(r'\s*·\s*', ' ',
                                                      re.sub(r'(\d+)\s+(critical|major|moderate|minor)', chip, m.group(2)))
                  + '</p>', body, flags=re.S)

    # Source links for `path.m2:12-34` citations.
    if source_url:
        base = source_url if source_url.endswith('/') else source_url + '/'

        def src(m):
            path, a, b = m.group(1), m.group(2), m.group(3) or m.group(2)
            return f'<a class="src" href="{html.escape(base + path)}#L{a}-L{b}"><code>{m.group(0)[6:-7]}</code></a>'
        body = re.sub(r'<code>([\w./+-]+\.m2):(\d+)(?:-(\d+))?</code>', src, body)

    # Cross-reference links from finding ids in running text (not in code, links, or headings).
    if findings:
        tokens = re.split(r'(<[^>]+>)', body)
        depth, out = 0, []
        for t in tokens:
            if t.startswith('<'):
                m = re.match(r'<(/?)(code|pre|a|h[1-6])\b', t)
                if m:
                    depth += -1 if m.group(1) else 1
                out.append(t)
            elif depth == 0 and t:
                out.append(re.sub(rf'\b({FINDING_ID})\b',
                                  lambda m: (f'<a class="xref" href="#{m.group(1).lower()}">{m.group(1)}</a>'
                                             if m.group(1).lower() in findings else m.group(1)), t))
            else:
                out.append(t)
        body = ''.join(out)

    # Color boundary-sweep outcomes and verdict cells.
    body = re.sub(r'<td>(ok|unclear)</td>', r'<td class="out-\1">\1</td>', body)
    body = re.sub(r'<td>n/a</td>', '<td class="out-na">n/a</td>', body)
    body = re.sub(r'<td>(see <a class="xref")', r'<td class="out-finding">\1', body)
    body = re.sub(r'<td>(Confirmed)</td>', r'<td class="v-good">\1</td>', body)
    body = re.sub(r'<td>(Partly confirmed|Partially correct|Unclear)</td>', r'<td class="v-part">\1</td>', body)
    body = re.sub(r'<td>(Refuted|Retracted)</td>', r'<td class="v-bad">\1</td>', body)
    body = re.sub(r'<td><strong>(Retracted\.?)</strong>', r'<td class="v-bad"><strong>\1</strong>', body)

    # A compact contents list after the first h1 (sections, then findings in two columns).
    if toc:
        secs = re.findall(r'<h2 id="([^"]+)"[^>]*>(.*?)</h2>', body, re.S)
        if len(secs) + len(findings) >= 6:
            items = ''.join(f'<li><a href="#{i}">{re.sub(r"<[^>]+>", "", t).strip()}</a></li>' for i, t in secs)
            def short(t, n=60):
                fid, _, rest = t.partition('. ')
                rest = rest if len(rest) <= n else rest[:n].rsplit(' ', 1)[0] + '…'
                return f'<b>{html.escape(fid)}</b> {html.escape(rest)}'
            fl = ''.join(f'<li><span class="dot sev-{s or 4}"></span><a href="#{i}">{short(t)}</a></li>'
                         for i, (t, s) in findings.items())
            nav = ('<nav class="toc"><div class="toc-title">Contents</div><ul>' + items + '</ul>'
                   + (f'<div class="toc-title" style="margin-top:5px">Findings</div><ul class="findings">{fl}</ul>' if fl else '')
                   + '</nav>')
            m = re.search(r'<h2[ >]', body) or re.search(r'</h1>', body)   # after the header block
            at = (m.start() if m.group(0).startswith('<h2') else m.end()) if m else 0
            body = body[:at] + nav + body[at:]
    return body


def page_css(page):
    landscape = 'landscape' in page.lower()
    return (CSS.replace('__PAGE__', page).replace('__MARGIN__', '0.5in 0.55in' if landscape else '0.7in 0.65in')
            .replace('__COLS__', '3' if landscape else '2'))


def page_html(text, title, source_url=None, toc=True, page=DEFAULT_PAGE):
    body = enhance(md_to_body(text), source_url, toc)
    return (f'<!doctype html>\n<html><head><meta charset="utf-8"><title>{html.escape(title)}</title>'
            f'<style>{page_css(page)}</style></head><body>\n{body}\n</body></html>\n')


def find_browser():
    for b in BROWSERS:
        p = shutil.which(b) or (b if os.path.isabs(b) and os.access(b, os.X_OK) else None)
        if p:
            return p
    return None


def html_to_pdf(html_path, pdf_path):
    """Write pdf_path from html_path; return the engine used, or None if no engine is available."""
    browser = find_browser()
    if browser:
        with tempfile.TemporaryDirectory() as profile:  # throwaway profile: never touch the user's
            for headless in ('--headless=new', '--headless'):
                cmd = [browser, headless, '--disable-gpu', '--no-pdf-header-footer', '--print-to-pdf-no-header',
                       '--generate-pdf-document-outline', f'--user-data-dir={profile}',
                       f'--print-to-pdf={pdf_path}', Path(html_path).as_uri()]
                try:
                    subprocess.run(cmd, capture_output=True, timeout=180)
                except subprocess.TimeoutExpired:
                    continue
                if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                    return 'chrome'
    try:
        import weasyprint
        weasyprint.HTML(filename=html_path).write_pdf(pdf_path)
        return 'weasyprint'
    except ImportError:
        pass
    for tool, args in (('weasyprint', [html_path, pdf_path]),
                       ('wkhtmltopdf', ['--quiet', '--encoding', 'utf-8', html_path, pdf_path])):
        if shutil.which(tool):
            subprocess.run([tool, *args], check=True, capture_output=True)
            return tool
    return None


def convert(md_path, out_path, html_only, source_url=None, toc=True, page=DEFAULT_PAGE):
    text = Path(md_path).read_text(encoding='utf-8')
    title = next((l[2:].strip() for l in text.splitlines() if l.startswith('# ')), Path(md_path).stem)
    doc = page_html(text, title, source_url, toc, page)
    if html_only:
        Path(out_path).write_text(doc, encoding='utf-8')
        return 'html'
    with tempfile.TemporaryDirectory() as work:
        hp, pp = os.path.join(work, 'report.html'), os.path.join(work, 'report.pdf')
        Path(hp).write_text(doc, encoding='utf-8')
        engine = html_to_pdf(hp, pp)
        if engine is None:
            fallback = str(Path(out_path).with_suffix('.html'))
            shutil.copyfile(hp, fallback)
            print(f'md_to_pdf: no PDF engine found (Chrome/Chromium/Edge, WeasyPrint, or wkhtmltopdf); '
                  f'wrote {fallback} instead -- open it in a browser and print to PDF', file=sys.stderr)
            return None
        shutil.move(pp, out_path)
        return engine


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('inputs', nargs='+', help='Markdown files')
    ap.add_argument('-o', '--output', help='output path (only with a single input)')
    ap.add_argument('--html', action='store_true', help='write styled HTML instead of PDF')
    ap.add_argument('--source-url', help='base URL for linking path.m2:line citations, e.g. a GitHub blob URL of the packages directory')
    ap.add_argument('--no-toc', action='store_true', help='omit the contents list')
    ap.add_argument('--page', default=DEFAULT_PAGE, help=f'CSS page size (default "{DEFAULT_PAGE}"; e.g. "Letter", "A4 landscape")')
    a = ap.parse_args()
    if a.output and len(a.inputs) > 1:
        ap.error('-o/--output takes a single input')
    status = 0
    for md in a.inputs:
        out = a.output or str(Path(md).with_suffix('.html' if a.html else '.pdf'))
        engine = convert(md, out, a.html, a.source_url, not a.no_toc, a.page)
        if engine is None:
            status = 2
        else:
            print(f'wrote {out} ({engine})')
    sys.exit(status)


if __name__ == '__main__':
    main()
