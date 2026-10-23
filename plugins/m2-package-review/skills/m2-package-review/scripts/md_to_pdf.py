#!/usr/bin/env python3
"""Convert review reports (Markdown) to nicely formatted PDFs.

Usage:
    python3 -I md_to_pdf.py review.md [more.md ...]     # writes review.pdf next to each input
    python3 -I md_to_pdf.py review.md -o out.pdf        # one input, explicit output
    python3 -I md_to_pdf.py review.md --html            # write the styled HTML instead

Markdown -> HTML uses pandoc if installed, otherwise the Python `markdown` package.
HTML -> PDF uses a headless Chrome/Chromium/Edge if one is found, otherwise WeasyPrint, otherwise
wkhtmltopdf. If no PDF engine is available, the styled HTML is written instead (open it in a browser
and print to PDF) and the script exits with status 2.
"""
import argparse
import html
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CSS = """
@page { size: Letter; margin: 0.75in 0.7in; }
body { font-family: "DejaVu Sans", "Helvetica Neue", Arial, sans-serif; font-size: 10.5pt; line-height: 1.45;
       color: #1a1a1a; margin: 0; }
h1 { font-size: 20pt; margin: 0 0 0.4em; }
h2 { font-size: 15pt; margin-top: 1.4em; border-bottom: 1px solid #ccc; padding-bottom: 0.15em; }
h3 { font-size: 12.5pt; margin-top: 1.2em; }
h4 { font-size: 11pt; margin-top: 1.1em; break-after: avoid; }
code { font-family: "DejaVu Sans Mono", Menlo, Consolas, monospace; font-size: 9pt; background: #f3f3f3;
       padding: 0 2px; border-radius: 2px; }
pre { background: #f6f6f6; border: 1px solid #e2e2e2; padding: 6px 8px; white-space: pre-wrap;
      overflow-wrap: anywhere; break-inside: avoid; }
pre code { background: none; padding: 0; font-size: 8.5pt; }
table { border-collapse: collapse; width: 100%; font-size: 9pt; margin: 0.6em 0; }
th, td { border: 1px solid #cfcfcf; padding: 3px 6px; vertical-align: top; overflow-wrap: break-word;
         word-break: normal; hyphens: manual; }
td code { overflow-wrap: anywhere; }
th { background: #efefef; }
tr { break-inside: avoid; }
a { color: #1a4fa0; text-decoration: none; }
"""

BROWSERS = ['google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser', 'microsoft-edge', 'msedge',
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            '/Applications/Chromium.app/Contents/MacOS/Chromium',
            '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge']


def md_to_html(text, title):
    body = None
    if shutil.which('pandoc'):
        r = subprocess.run(['pandoc', '-f', 'gfm', '-t', 'html5'], input=text, capture_output=True, text=True)
        if r.returncode == 0:
            body = r.stdout
    if body is None:
        try:
            import markdown
        except ImportError:
            sys.exit('md_to_pdf: needs pandoc or the Python "markdown" package to convert Markdown')
        body = markdown.markdown(text, extensions=['tables', 'fenced_code', 'sane_lists'])
    return (f'<!doctype html>\n<html><head><meta charset="utf-8"><title>{html.escape(title)}</title>'
            f'<style>{CSS}</style></head><body>\n{body}\n</body></html>\n')


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
                       f'--user-data-dir={profile}', f'--print-to-pdf={pdf_path}', Path(html_path).as_uri()]
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


def convert(md_path, out_path, html_only):
    text = Path(md_path).read_text(encoding='utf-8')
    title = next((l[2:].strip() for l in text.splitlines() if l.startswith('# ')), Path(md_path).stem)
    page = md_to_html(text, title)
    if html_only:
        Path(out_path).write_text(page, encoding='utf-8')
        return 'html'
    with tempfile.TemporaryDirectory() as work:
        hp, pp = os.path.join(work, 'report.html'), os.path.join(work, 'report.pdf')
        Path(hp).write_text(page, encoding='utf-8')
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
    a = ap.parse_args()
    if a.output and len(a.inputs) > 1:
        ap.error('-o/--output takes a single input')
    status = 0
    for md in a.inputs:
        out = a.output or str(Path(md).with_suffix('.html' if a.html else '.pdf'))
        engine = convert(md, out, a.html)
        if engine is None:
            status = 2
        else:
            print(f'wrote {out} ({engine})')
    sys.exit(status)


if __name__ == '__main__':
    main()
