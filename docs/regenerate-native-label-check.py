#!/usr/bin/env python3
"""Regenerate the documented before/after example using native checks and both fixers.

Replaces only native-label-check.png, native-label-check-fixed.png and
native-label-check-fixed.drawio in the output directory after all renders succeed.
The checked-in native-label-check.drawio source is never modified.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

DOCS = Path(__file__).resolve().parent
sys.path.insert(0, str(DOCS.parent / 'scripts'))
from drawio_native import native_check
from drawio_fix import native_fix
from drawio_stack import native_stack_fix
from drawio_report import write_visual_report


def regenerate(args):
    source = DOCS / 'native-label-check.drawio'
    destination = args.output_dir.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    renderer = dict(browser=args.browser, asar=args.drawio_asar, webapp=args.drawio_webapp,
                    no_sandbox=args.no_sandbox, timeout=args.timeout)
    exporter = dict(executable=args.export_executable, headless=args.headless,
                    no_sandbox=args.no_sandbox, timeout=args.timeout)
    with tempfile.TemporaryDirectory(prefix='.native-label-example-', dir=destination) as directory:
        work = Path(directory)
        print('Checking and rendering the original diagram…', flush=True)
        before = native_check(source, **renderer)
        write_visual_report(source, before, work / 'before', **exporter)
        print('Applying stacking repairs, then label-offset repairs…', flush=True)
        stacked = work / 'stacked.drawio'
        stacking = native_stack_fix(source, output=stacked, **renderer)
        fixed = work / 'native-label-check-fixed.drawio'
        offsets = native_fix(stacked, output=fixed, **renderer)
        # Partial repairs are valid artifacts. Independently report anything remaining.
        print('Checking and rendering the fixed diagram…', flush=True)
        after = native_check(fixed, **renderer)
        write_visual_report(fixed, after, work / 'after', **exporter)
        for report, name in (('before', 'native-label-check.png'),
                             ('after', 'native-label-check-fixed.png')):
            shutil.copyfile(work / report / 'page-1.png', work / name)
        names = ('native-label-check.png', 'native-label-check-fixed.png',
                 'native-label-check-fixed.drawio')
        # Render failures leave existing documentation artifacts untouched.
        for name in names:
            os.replace(work / name, destination / name)
    print(json.dumps({'before': before['pages'][0]['summary'],
                      'after': after['pages'][0]['summary'],
                      'stacking_changes': stacking['changes'],
                      'offset_changes': offsets['changes'],
                      'artifacts': [str(destination / name) for name in names]}, indent=2))
    return 1 if any(p['summary']['warning'] or p['unmeasured_labels'] for p in after['pages']) else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=DOCS,
                        help='Replace the three generated artifacts here (default: docs)')
    parser.add_argument('--browser', help='Chromium/Chrome executable')
    assets = parser.add_mutually_exclusive_group()
    assets.add_argument('--drawio-asar')
    assets.add_argument('--drawio-webapp')
    parser.add_argument('--export-executable', default='drawio')
    parser.add_argument('--headless', action='store_true', help='Use Xvfb for Desktop PNG export')
    parser.add_argument('--no-sandbox', action='store_true', help='Only where Chromium sandbox cannot run')
    parser.add_argument('--timeout', type=float, default=60, help='Timeout per renderer invocation')
    try:
        return regenerate(parser.parse_args())
    except (ValueError, RuntimeError, OSError, KeyError, ET.ParseError, subprocess.TimeoutExpired) as exc:
        print('Example generation failed: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
