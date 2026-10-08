"""Conservative native label repair. Only mxGeometry/mxPoint[@as='offset'] x/y may change."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from drawio_arch import Diagram, _number
from drawio_native import native_check
from drawio_repair import findings_severity as _findings, publish_repair, repair_paths


def _offset(page, ident):
    cell = page.cell(ident)
    geo = cell.find('mxGeometry')
    if geo is None or geo.get('relative') != '1':
        raise ValueError('Unsupported label geometry: ' + ident)
    if cell.get('edge') != '1':
        parent = page.cells().get(cell.get('parent'))
        if (parent is None or parent.get('edge') != '1' or
                float(geo.get('width', 0)) or float(geo.get('height', 0))):
            raise ValueError('Only edge text labels can move: ' + ident)
    points = geo.findall("mxPoint[@as='offset']")
    if len(points) > 1:
        raise ValueError('Ambiguous label offset: ' + ident)
    point = points[0] if points else None
    offset = [float(point.get(k, 0)) if point is not None else 0.0 for k in ('x', 'y')]
    if not all(math.isfinite(v) for v in offset):
        raise ValueError('Nonfinite label offset: ' + ident)
    return geo, point, offset


def apply_offsets(doc, changes, max_move):
    """Allowlisted edit; preserve all other geometry attributes and child elements."""
    seen = set()
    for change in changes:
        target = (change['page'], change['id'])
        if target in seen:
            raise ValueError('Duplicate label repair')
        seen.add(target)
        geo, point, old = _offset(doc.pages[change['page']], change['id'])
        new = change['after']
        if old != change['before'] or len(new) != 2 or not all(math.isfinite(v) for v in new):
            raise ValueError('Label repair does not match source geometry')
        if math.hypot(*(a-b for a, b in zip(new, old))) > max_move + .001:
            raise ValueError('Label repair exceeds displacement limit')
        if point is None:
            point = ET.SubElement(geo, 'mxPoint', {'as': 'offset'})
        for key, value in zip(('x', 'y'), new):
            point.set(key, _number(value))


def verify_preservation(before, after, changes, max_move):
    expected = copy.deepcopy(before)
    apply_offsets(expected, changes, max_move)
    if ET.tostring(expected.xml) != ET.tostring(after.xml):
        raise RuntimeError('Preservation failed: a change beyond the declared label offsets was found')


def verify_render(before, after, changes):
    """Fresh serialized-file render must reproduce proposals and preserve unrelated geometry."""
    if [p['index'] for p in before['pages']] != [p['index'] for p in after['pages']]:
        raise RuntimeError('Verification page mismatch')
    moved = {(c['page'], c['id']): c for c in changes}
    for old, new in zip(before['pages'], after['pages']):
        index = old['index']
        if new['routes'] != old['routes'] or new['obstacles'] != old['obstacles']:
            raise RuntimeError('Rendered routes or shapes changed')
        # An incomplete page is left entirely untouched; it remains explicitly unresolved.
        if new['unmeasured_labels'] != old['unmeasured_labels']:
            raise RuntimeError('Label measurement changed during verification')
        known = _findings(old)
        if any(k not in known or rank > known[k] for k, rank in _findings(new).items()):
            raise RuntimeError('Fresh render introduced or worsened a collision')
        labels = {label['id']: label for label in new['labels']}
        if set(labels) != {label['id'] for label in old['labels']}:
            raise RuntimeError('Visible labels changed during verification')
        for label in old['labels']:
            checked = labels[label['id']]
            if (checked['text'], checked['edge']) != (label['text'], label['edge']):
                raise RuntimeError('Label content or ownership changed')
            change = moved.get((index, label['id']))
            dx, dy = (tuple(b-a for a, b in zip(change['before'], change['after'])) if change else (0, 0))
            expected = dict(label['bounds'], x=label['bounds']['x']+dx, y=label['bounds']['y']+dy)
            if any(abs(checked['bounds'][key]-value) > .15 for key, value in expected.items()):
                raise RuntimeError('Native label movement did not match the proposed offset')
        if any(page == index for page, _ in moved) and new['summary']['warning'] >= old['summary']['warning']:
            raise RuntimeError('A repaired page did not reduce warnings')


def native_fix(source, *, output=None, only=(), keep=(), max_move=32, max_attempts=160,
               max_passes=3, **renderer):
    """Dry-run by default; output publishes a new, verified file without replacing source."""
    if not math.isfinite(max_move) or not 0 < max_move <= 128:
        raise ValueError('max_move must be finite and in (0, 128] pixels')
    if not isinstance(max_attempts, int) or not 1 <= max_attempts <= 2000:
        raise ValueError('max_attempts must be an integer in [1, 2000] per page')
    if not isinstance(max_passes, int) or not 1 <= max_passes <= 10:
        raise ValueError('max_passes must be an integer in [1, 10]')
    if '_fix' in renderer:
        raise ValueError('Internal renderer options cannot be overridden')
    source, destination, raw = repair_paths(source, output)
    options = {'only': list(only), 'keep': list(keep), 'max_move': max_move,
               'max_attempts': max_attempts, 'max_passes': max_passes}
    with tempfile.TemporaryDirectory(prefix='drawio-label-fix-') as directory:
        temporary = Path(directory)
        snapshot = temporary / 'source.drawio'
        snapshot.write_bytes(raw)
        original = Diagram.load(snapshot)
        selected = [p for i, p in enumerate(original.pages) if renderer.get('page') in (None, i)]
        available = {ident for p in selected for ident in p.cells()}
        missing = (set(only) | set(keep)) - available
        if missing:
            raise ValueError('Unknown selected-page cell IDs: ' + ', '.join(sorted(missing)))
        proposed = native_check(snapshot, _fix=options, **renderer)
        before = {k: v for k, v in proposed.items() if k != 'pages'}
        before['pages'] = [p['fix']['before'] for p in proposed['pages']]
        before['source'] = str(source)
        changes = [dict(c, page=p['index']) for p in proposed['pages'] for c in p['fix']['changes']]
        candidate = copy.deepcopy(original)
        apply_offsets(candidate, changes, max_move)
        staged = temporary / 'candidate.drawio'
        if changes:
            candidate.save(staged, pretty=False)
        else:
            staged.write_bytes(raw)
        # This compares the entire parsed XML, including metadata, style strings and cell order.
        verify_preservation(original, Diagram.load(staged), changes, max_move)
        after = native_check(staged, **renderer)
        verify_render(before, after, changes)
        # Repeatable bounds/classification in a fresh browser must agree with the accepted search.
        for searched, verified in zip(proposed['pages'], after['pages']):
            if _findings(searched) != _findings(verified):
                raise RuntimeError('Fresh render disagrees with candidate verification')
        data = staged.read_bytes()
    after['source'] = str(destination if destination is not None else source)
    status = ('partial' if any(p['summary']['warning'] or p['unmeasured_labels'] for p in after['pages'])
              else 'warnings-cleared')
    result = {'mode': 'apply' if destination else 'dry-run', 'status': status,
              'source': str(source), 'source_sha256': hashlib.sha256(raw).hexdigest(),
              'output': str(destination) if destination else None,
              'options': options, 'changes': changes,
              'pages': [{'index': p['index'], 'attempts': p['fix']['attempts'],
                         'passes': p['fix'].get('passes', 0),
                         'stop_reason': p['fix']['stop_reason'], 'skipped': p['fix']['skipped']}
                        for p in proposed['pages']],
              'preservation': 'passed', 'native_recheck': 'passed', 'before': before, 'after': after}
    digest = publish_repair(source, raw, destination, data)
    if digest is not None:
        result['output_sha256'] = digest
    return result


def add_arguments(parser):
    # Match native-check renderer options without exposing report-export flags for a repair command.
    parser.add_argument('source')
    parser.add_argument('--output', help='Apply to a new file; omit for a fully verified dry-run')
    parser.add_argument('--page', type=int)
    parser.add_argument('--browser')
    assets = parser.add_mutually_exclusive_group()
    assets.add_argument('--drawio-webapp', dest='webapp')
    assets.add_argument('--drawio-asar', dest='asar')
    parser.add_argument('--padding', type=float, default=2)
    parser.add_argument('--timeout', type=float, default=60)
    parser.add_argument('--no-sandbox', action='store_true')
    parser.add_argument('--only', action='append', default=[], help='Only consider this label ID (repeatable)')
    parser.add_argument('--keep', action='append', default=[], help='Freeze this label/edge ID (repeatable)')
    parser.add_argument('--max-move', type=float, default=32, help='Maximum total movement in pixels (default 32, ceiling 128)')
    parser.add_argument('--max-attempts', type=int, default=160, help='Maximum candidate renders per page')
    parser.add_argument('--max-passes', type=int, default=3)
    return parser


def run(args):
    options = vars(args).copy()
    options.pop('command', None)
    try:
        result = native_fix(**options)
    except (ValueError, RuntimeError, OSError, KeyError, ET.ParseError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if result['status'] == 'partial' else 0


if __name__ == '__main__':
    raise SystemExit(run(add_arguments(argparse.ArgumentParser(description=__doc__)).parse_args()))
