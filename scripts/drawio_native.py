"""Optional offline Draw.io renderer checks. Python standard library; Chromium required."""
import argparse
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import xml.etree.ElementTree as ET


def _webapp_from_asar(archive, destination):
    """Extract installed Draw.io assets, never vendor or download them."""
    with Path(archive).open('rb') as stream:
        raw = stream.read(16)
        if len(raw) != 16:
            raise RuntimeError('Invalid Draw.io ASAR header')
        _, header_size, _, json_size = struct.unpack('<4I', raw)
        if not 0 < json_size < 64 * 1024 * 1024 or header_size < json_size + 8:
            raise RuntimeError('Invalid Draw.io ASAR header sizes')
        tree = json.loads(stream.read(json_size))
        for name in ('drawio', 'src', 'main', 'webapp'):
            tree = tree['files'][name]
        base = 8 + header_size

        def extract(node, target):
            for name, entry in node.get('files', {}).items():
                if name in ('.', '..') or '/' in name or '\\' in name:
                    raise RuntimeError('Unsafe path in Draw.io archive')
                path = target / name
                if 'files' in entry:
                    extract(entry, path)
                elif 'offset' in entry:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    stream.seek(base + int(entry['offset']))
                    remaining = int(entry['size'])
                    with path.open('wb') as output:
                        while remaining:
                            block = stream.read(min(remaining, 1024 * 1024))
                            if not block:
                                raise RuntimeError('Truncated Draw.io archive')
                            output.write(block)
                            remaining -= len(block)
        extract(tree, destination)
    return destination


def _asar_candidates():
    candidates = [Path('/opt/drawio/resources/app.asar'),
                  Path('/snap/drawio/current/app/resources/app.asar'),
                  Path('/Applications/draw.io.app/Contents/Resources/app.asar')]
    candidates.extend(sorted(Path('/snap/drawio').glob('*/app/resources/app.asar'), reverse=True))
    if os.environ.get('LOCALAPPDATA'):
        candidates.append(Path(os.environ['LOCALAPPDATA']) / 'Programs/draw.io/resources/app.asar')
    executable = shutil.which('drawio')
    if executable:
        candidates.insert(0, Path(executable).resolve().parent / 'resources/app.asar')
    return list(dict.fromkeys(candidates))


def _find_asar(archive=None):
    candidates = [Path(archive).expanduser()] if archive is not None else _asar_candidates()
    found = next((p for p in candidates if p.is_file()), None)
    if found is None:
        tried = ', '.join(str(p) for p in candidates)
        if archive is None:
            tried += ', /snap/drawio/*/app/resources/app.asar'
        raise RuntimeError(f'Draw.io ASAR not found. Tried: {tried}. '
                           'Install Draw.io Desktop or pass --drawio-asar /path/to/app.asar '
                           '(or --drawio-webapp /path/to/src/main/webapp). '
                           'On Linux, locate it with: find /snap /opt /usr -name app.asar 2>/dev/null; '
                           'Snap normally uses /snap/drawio/current/app/resources/app.asar.')
    return found


class _ResultParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == 'pre' and dict(attrs).get('id') == 'native-check-result':
            self.inside = True

    def handle_endtag(self, tag):
        if tag == 'pre':
            self.inside = False

    def handle_data(self, data):
        if self.inside:
            self.parts.append(data)


def native_check(source, *, page=None, browser=None, webapp=None, asar=None,
                 padding=2, timeout=60, no_sandbox=False, _fix=None):
    """Return measured overlaps; source is never changed. page=None checks all pages."""
    from drawio_arch import Diagram
    if not math.isfinite(padding) or padding < 0 or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('Padding must be finite and nonnegative; timeout must be positive')
    doc = Diagram.load(source)
    errors = doc.validate()
    if errors:
        raise ValueError('\n'.join(errors))
    if page is not None and not 0 <= page < len(doc.pages):
        raise ValueError('Page index out of range')
    if webapp and asar:
        raise ValueError('Choose webapp or asar, not both')
    browser = browser or next((shutil.which(n) for n in
                              ('chromium', 'chromium-browser', 'google-chrome', 'chrome')
                              if shutil.which(n)), None)
    if not browser or not shutil.which(str(browser)):
        raise RuntimeError('Native checking requires Chromium/Chrome; use --browser /path/to/browser')
    if not webapp:
        asar = _find_asar(asar)
    with tempfile.TemporaryDirectory(prefix='drawio-native-check-') as directory:
        temporary = Path(directory)
        if webapp:
            assets = Path(webapp).resolve()
        else:
            try:
                assets = _webapp_from_asar(asar, temporary / 'webapp')
            except (OSError, RuntimeError, ValueError, KeyError) as exc:
                raise RuntimeError(f'Cannot extract Draw.io renderer assets from {asar}: {exc}. '
                                   'Use --drawio-asar with a readable Draw.io app.asar '
                                   'or --drawio-webapp with an extracted src/main/webapp directory.') from exc
        for name in ('js/app.min.js', 'js/export-init.js', 'js/stencils.min.js', 'js/shapes-14-6-5.min.js'):
            if not (assets / name).is_file():
                raise RuntimeError('Draw.io renderer asset missing: ' + name)
        pages = [{'index': i, 'name': p.diagram.get('name'),
                  'xml': ET.tostring(p.model, encoding='unicode')}
                 for i, p in enumerate(doc.pages) if page is None or i == page]
        payload = {'pages': pages, 'padding': padding, 'fix': _fix}
        (temporary / 'input.js').write_text('const nativeCheckInput = ' + json.dumps(payload) + ';\n', encoding='utf-8')
        # Only local/data resources are available. This does not control a user's browser profile.
        html = '''<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src file: 'unsafe-eval'; style-src file: 'unsafe-inline'; img-src file: data:; font-src file: data:; connect-src 'none'">
'''
        html += '<link rel="stylesheet" href="' + (assets / 'mxgraph/css/common.css').as_uri() + '">\n'
        for name in ('js/export-init.js', 'js/app.min.js', 'js/stencils.min.js', 'js/shapes-14-6-5.min.js'):
            html += '<script src="' + (assets / name).as_uri() + '"></script>\n'
        html += '</head><body><script src="input.js"></script>'
        if _fix:
            html += '<script src="' + Path(__file__).with_name('native_fix.js').resolve().as_uri() + '"></script>'
        html += '<script src="' + Path(__file__).with_name('native_check.js').resolve().as_uri() + '"></script></body></html>'
        harness = temporary / 'check.html'
        harness.write_text(html, encoding='utf-8')
        cmd = [str(browser), '--headless', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
               '--disable-background-networking', '--allow-file-access-from-files',
               '--user-data-dir=' + str(temporary / 'profile'), '--dump-dom', '--virtual-time-budget=8000']
        if no_sandbox:
            cmd.append('--no-sandbox')
        cmd.append(harness.as_uri())
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError('Native renderer timed out; no verification result') from exc
        parser = _ResultParser()
        parser.feed(result.stdout)
        if result.returncode or not parser.parts:
            raise RuntimeError('Native renderer failed; no verification result. ' + result.stderr[-1500:])
        report = json.loads(''.join(parser.parts))
        if report.get('error'):
            raise RuntimeError('Native renderer failed: ' + report['error'])
        report['source'] = str(Path(source).resolve())
        report['assets'] = str(Path(webapp or asar).resolve())
        return report


def add_arguments(parser):
    parser.add_argument('source')
    parser.add_argument('--page', type=int, help='Zero-based page index; default checks all pages')
    parser.add_argument('--browser', help='Chromium/Chrome executable')
    assets = parser.add_mutually_exclusive_group()
    assets.add_argument('--drawio-webapp', dest='webapp', help='Local Draw.io src/main/webapp directory')
    assets.add_argument('--drawio-asar', dest='asar', help='Installed Draw.io resources/app.asar')
    parser.add_argument('--padding', type=float, default=2, help='Required clearance in pixels (default 2)')
    parser.add_argument('--timeout', type=float, default=60)
    parser.add_argument('--no-sandbox', action='store_true', help='Only where Chromium sandbox cannot run')
    parser.add_argument('--fail-on', choices=('warning', 'advisory'), default='warning',
                        help='Findings that cause exit 1 (default warning; advisory includes warnings)')
    parser.add_argument('--report-dir', help='Create a new directory with JSON, annotated Draw.io and page PNGs')
    parser.add_argument('--highlight', default='all', help='Visual filter: all or comma-separated warning,advisory,info')
    parser.add_argument('--export-executable', default='drawio', help='Draw.io Desktop executable for report PNGs')
    parser.add_argument('--headless', action='store_true', help='Use Xvfb for report PNG export')
    return parser


def run(args):
    options = vars(args).copy()
    options.pop('command', None)
    fail_on = options.pop('fail_on', 'warning')
    report_dir = options.pop('report_dir', None)
    highlight = options.pop('highlight', 'all')
    executable = options.pop('export_executable', 'drawio')
    headless = options.pop('headless', False)
    try:
        from drawio_report import highlight_severities, write_visual_report
        highlight_severities(highlight)
        if report_dir and Path(report_dir).exists():
            raise ValueError('Report directory already exists; choose a new directory: ' + str(report_dir))
        report = native_check(**options)
        if report_dir:
            report = write_visual_report(options['source'], report, report_dir, highlight=highlight,
                                         executable=executable, headless=headless,
                                         no_sandbox=options.get('no_sandbox', False),
                                         timeout=options.get('timeout', 60))
    except (ValueError, RuntimeError, OSError, KeyError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=False))
    severities = {'warning', 'advisory'} if fail_on == 'advisory' else {'warning'}
    return 1 if any(p['unmeasured_labels'] or any(c['severity'] in severities for c in p['collisions'])
                    for p in report['pages']) else 0


def main():
    return run(add_arguments(argparse.ArgumentParser(description=__doc__)).parse_args())


if __name__ == '__main__':
    raise SystemExit(main())
