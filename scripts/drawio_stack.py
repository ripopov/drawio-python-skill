"""Independent stacking-only repair for labels hidden by opaque shapes."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from drawio_arch import Diagram, _styles
from drawio_native import native_check
from drawio_repair import findings_severity as _findings, publish_repair, repair_paths


def occlusions(page):
    return [c for c in page['collisions'] if c['reason'] == 'possible-label-occlusion']


def _elements(page):
    result = {}
    for element in page.root:
        cell = element if element.tag == 'mxCell' else element.find('mxCell')
        if cell is not None:
            result[element.get('id', cell.get('id'))] = element
    return result


def apply_stack(doc, change):
    """Move exactly one whole XML cell/wrapper after a later sibling; edit no attributes."""
    page = doc.pages[change['page']]
    cells, elements = page.cells(), _elements(page)
    edge, obstacle = cells[change['edge']], cells[change['after']]
    if edge.get('edge') != '1' or edge.get('parent') != obstacle.get('parent'):
        raise ValueError('Stack repair requires an edge and a sibling occluder')
    children = list(page.root)
    source, target = elements[change['edge']], elements[change['after']]
    if children.index(source) >= children.index(target):
        raise ValueError('Stack repair must raise an edge past a later sibling')
    page.root.remove(source)
    page.root.insert(list(page.root).index(target) + 1, source)


def verify_stack_preservation(before, after, changes):
    expected = copy.deepcopy(before)
    for change in changes:
        apply_stack(expected, change)
    if ET.tostring(expected.xml) != ET.tostring(after.xml):
        raise RuntimeError('Stack preservation failed: changes beyond the declared cell order')


def verify_stack_render(before, after):
    if [p['index'] for p in before['pages']] != [p['index'] for p in after['pages']]:
        raise RuntimeError('Stack verification page mismatch')
    for old, new in zip(before['pages'], after['pages']):
        # Ordering may change enumeration but no measured content or geometry may change.
        for field in ('routes', 'obstacles', 'labels', 'unmeasured_labels'):
            if {x['id']: x for x in old[field]} != {x['id']: x for x in new[field]}:
                raise RuntimeError('Stack repair changed native ' + field)
        known = _findings(old)
        if any(key not in known or rank > known[key] for key, rank in _findings(new).items()):
            raise RuntimeError('Stack repair introduced or worsened a collision')


def _overlap(a, b):
    return (a['x'] < b['x'] + b['width'] and b['x'] < a['x'] + a['width'] and
            a['y'] < b['y'] + b['height'] and b['y'] < a['y'] + a['height'])


def _inside(a, b, margin=2):
    return (a['x'] >= b['x'] + margin and a['y'] >= b['y'] + margin and
            a['x'] + a['width'] <= b['x'] + b['width'] - margin and
            a['y'] + a['height'] <= b['y'] + b['height'] - margin)


def _segment_box(a, b, box, inset=0):
    lo, hi = 0.0, 1.0
    for axis, size in (('x', 'width'), ('y', 'height')):
        low, high = box[axis] + inset, box[axis] + box[size] - inset
        if high < low:
            return False
        v, delta = a[axis], b[axis] - a[axis]
        if abs(delta) < 1e-9:
            if v < low or v > high:
                return False
        else:
            t1, t2 = (low-v)/delta, (high-v)/delta
            lo, hi = max(lo, min(t1, t2)), min(hi, max(t1, t2))
            if lo > hi:
                return False
    return True


def _path_box(route, box, inset=0):
    return any(_segment_box(a, b, box, inset) for a, b in zip(route['points'], route['points'][1:]))


def _paths_touch(first, second):
    # Native visual bounds include stroke/marker extents. Reject ambiguous footprint
    # overlap even when the centerlines miss (e.g. thick parallel strokes or arrowheads).
    if first.get('bounds') and second.get('bounds') and _overlap(first['bounds'], second['bounds']):
        return True
    def cross(a, b, c):
        return (b['x']-a['x'])*(c['y']-a['y']) - (b['y']-a['y'])*(c['x']-a['x'])
    for a, b in zip(first['points'], first['points'][1:]):
        for c, d in zip(second['points'], second['points'][1:]):
            if any(max(min(a[k], b[k]), min(c[k], d[k])) > min(max(a[k], b[k]), max(c[k], d[k])) + 1
                   for k in ('x', 'y')):
                continue
            if cross(a, b, c)*cross(a, b, d) <= 1e-6 and cross(c, d, a)*cross(c, d, b) <= 1e-6:
                return True
    return False


def _locked(cells, ident, keep):
    while ident in cells:
        if ident in keep:
            return True
        cell = cells[ident]
        styles = _styles(cell.get('style', ''))
        if any(styles.get(k) == v for k, v in (('locked', '1'), ('movable', '0'),
                                              ('labelMovable', '0'), ('autofix', '0'))):
            return True
        ident = cell.get('parent')
    return False


def stack_candidate(doc, report, finding, only, keep):
    """Restrict reorder to siblings with disjoint linework and no other obscured text."""
    page = doc.pages[report['index']]
    cells, elements = page.cells(), _elements(page)
    labels = {l['id']: l for l in report['labels']}
    label = labels.get(finding['a'])
    if not label or not label['edge']:
        return None, 'not-an-edge-label'
    if only and label['id'] not in only:
        return None, 'not-selected'
    owner, target = label['edge'], finding['b']
    if _locked(cells, label['id'], keep) or _locked(cells, owner, keep):
        return None, 'locked'
    if report['unmeasured_labels']:
        return None, 'incomplete-measurement'
    if cells[owner].get('parent') != cells[target].get('parent'):
        return None, 'different-parent-or-layer'
    siblings = [ident for ident in elements if cells[ident].get('parent') == cells[owner].get('parent')]
    start, end = siblings.index(owner), siblings.index(target)
    if start >= end:
        return None, 'unsupported-paint-order'
    crossed = siblings[start+1:end+1]
    routes = {r['id']: r for r in report['routes']}
    shapes = {s['id']: s['bounds'] for s in report['obstacles']}
    own = routes.get(owner)
    if not own or not own['supported']:
        return None, 'unsupported-route'
    children = [ident for ident, cell in cells.items() if cell.get('parent') == owner]
    if any(ident not in labels or labels[ident]['edge'] != owner or _locked(cells, ident, keep) for ident in children):
        return None, 'protected-or-structural-edge-child'
    for ident in children:
        geo = cells[ident].find('mxGeometry')
        styles = _styles(cells[ident].get('style', ''))
        if (geo is None or geo.get('relative') != '1' or float(geo.get('width', 0)) or
                float(geo.get('height', 0)) or 'text' not in styles or styles.get('shape', 'text') != 'text'):
            return None, 'protected-or-structural-edge-child'
    if any(cell.get('parent') in children for cell in cells.values()):
        return None, 'nested-edge-children'
    own_labels = [l for l in report['labels'] if l['edge'] == owner]
    allowed = {(c['a'], c['b']) for c in occlusions(report)}
    if _styles(cells[owner].get('style', '')).get('jumpStyle', 'none') != 'none':
        return None, 'unsupported-jump-style'
    for ident in crossed:
        if _locked(cells, ident, keep):
            return None, 'crosses-protected-cell'
        if any(c.get('parent') == ident for c in cells.values()):
            return None, 'crosses-composite-cell'
        other_labels = [l for l in report['labels'] if l['id'] == ident or l['edge'] == ident]
        if any(_overlap(a['bounds'], b['bounds']) for a in own_labels for b in other_labels):
            return None, 'would-cover-other-label'
        if any(_path_box(own, l['bounds'], -2) or _overlap(own['bounds'], l['bounds']) for l in other_labels):
            return None, 'would-draw-line-over-text'
        if ident in routes:
            route = routes[ident]
            if not route['supported'] or _styles(cells[ident].get('style', '')).get('jumpStyle', 'none') != 'none':
                return None, 'unsupported-crossed-route'
            if _paths_touch(own, route):
                return None, 'would-change-line-crossing-order'
            if any(_path_box(route, l['bounds'], -2) or _overlap(route['bounds'], l['bounds']) for l in own_labels):
                return None, 'would-cover-other-connection'
        elif ident in shapes:
            bounds = shapes[ident]
            styles = _styles(cells[ident].get('style', ''))
            if (styles.get('shape', 'rectangle') != 'rectangle' or styles.get('rounded', '0') != '0' or
                    styles.get('rotation', '0') != '0'):
                return None, 'unsupported-crossed-shape'
            if _path_box(own, bounds, 1):
                return None, 'would-expose-line-through-shape'
            for own_label in own_labels:
                if _overlap(own_label['bounds'], bounds):
                    if (own_label['id'], ident) not in allowed or not _inside(own_label['bounds'], bounds):
                        return None, 'would-cover-shape-outline-or-content'
        else:
            return None, 'unmeasured-crossed-cell'
    return {'page': report['index'], 'edge': owner, 'label': label['id'], 'after': target,
            'parent': cells[owner].get('parent'), 'crossed': crossed}, None


def native_stack_fix(source, *, output=None, only=(), keep=(), max_attempts=32, **renderer):
    if not isinstance(max_attempts, int) or not 1 <= max_attempts <= 128:
        raise ValueError('max_attempts must be an integer in [1, 128]')
    if '_fix' in renderer:
        raise ValueError('Internal renderer options cannot be overridden')
    source, destination, raw = repair_paths(source, output)
    changes, skipped, attempts = [], [], 0
    with tempfile.TemporaryDirectory(prefix='drawio-stack-fix-') as directory:
        snapshot, staged = Path(directory) / 'source.drawio', Path(directory) / 'candidate.drawio'
        snapshot.write_bytes(raw)
        original = Diagram.load(snapshot)
        available = {ident for i, p in enumerate(original.pages) if renderer.get('page') in (None, i) for ident in p.cells()}
        if (set(only) | set(keep)) - available:
            raise ValueError('Unknown selected-page cell IDs')
        before = native_check(snapshot, **renderer)
        current, doc = before, copy.deepcopy(original)
        targets = [(p['index'], f['a'], f['b']) for p in before['pages'] for f in occlusions(p)]
        for index, label, shape in targets:
            page = next(p for p in current['pages'] if p['index'] == index)
            finding = next((c for c in occlusions(page) if c['a'] == label and c['b'] == shape), None)
            if finding is None:
                continue
            change, reason = stack_candidate(doc, page, finding, only, keep)
            if not reason and attempts >= max_attempts:
                reason = 'attempt-budget'
            if reason:
                skipped.append(dict(page=index, label=label, shape=shape, reason=reason))
                continue
            candidate = copy.deepcopy(doc)
            apply_stack(candidate, change)
            candidate.save(staged, pretty=False)
            verify_stack_preservation(original, Diagram.load(staged), changes + [change])
            attempts += 1
            checked = native_check(staged, **renderer)
            try:
                verify_stack_render(current, checked)
                new_page = next(p for p in checked['pages'] if p['index'] == index)
                resolved = next((c for c in new_page['collisions'] if c['type'] == 'label-shape' and
                                 c['a'] == label and c['b'] == shape), None)
                if resolved is None or resolved.get('paint_order') != 'label-above-shape':
                    raise RuntimeError('Native renderer did not confirm the label is in front')
                if len(occlusions(new_page)) >= len(occlusions(page)):
                    raise RuntimeError('Occlusion count did not improve')
            except RuntimeError as exc:
                skipped.append(dict(page=index, label=label, shape=shape, reason=str(exc)))
                continue
            doc, current = candidate, checked
            changes.append(change)
        if changes:
            doc.save(staged, pretty=False)
        else:
            staged.write_bytes(raw)
        verify_stack_preservation(original, Diagram.load(staged), changes)
        after = native_check(staged, **renderer)
        verify_stack_render(before, after)
        for expected, actual in zip(current['pages'], after['pages']):
            if _findings(expected) != _findings(actual):
                raise RuntimeError('Final native render disagrees with stacking verification')
        data = staged.read_bytes()
    before['source'] = str(source)
    after['source'] = str(destination if destination else source)
    remaining = sum(len(occlusions(p)) for p in after['pages'])
    result = {'mode': 'apply' if destination else 'dry-run',
              'status': 'partial' if remaining or any(p['unmeasured_labels'] for p in after['pages']) else 'occlusions-cleared',
              'source': str(source), 'output': str(destination) if destination else None,
              'source_sha256': hashlib.sha256(raw).hexdigest(),
              'changes': changes, 'skipped': skipped, 'attempts': attempts, 'max_attempts': max_attempts,
              'remaining_occlusions': remaining, 'remaining_warnings': sum(p['summary']['warning'] for p in after['pages']),
              'preservation': 'passed', 'native_recheck': 'passed', 'before': before, 'after': after}
    digest = publish_repair(source, raw, destination, data)
    if digest is not None:
        result['output_sha256'] = digest
    return result


def add_arguments(parser):
    parser.add_argument('source')
    parser.add_argument('--output', help='New output file; omit for a verified dry-run')
    parser.add_argument('--page', type=int)
    parser.add_argument('--browser')
    assets = parser.add_mutually_exclusive_group()
    assets.add_argument('--drawio-webapp', dest='webapp')
    assets.add_argument('--drawio-asar', dest='asar')
    parser.add_argument('--padding', type=float, default=2)
    parser.add_argument('--timeout', type=float, default=60)
    parser.add_argument('--no-sandbox', action='store_true')
    parser.add_argument('--only', action='append', default=[], help='Only this label ID (repeatable)')
    parser.add_argument('--keep', action='append', default=[], help='Protect this cell/ancestor ID (repeatable)')
    parser.add_argument('--max-attempts', type=int, default=32)
    return parser


def run(args):
    options = vars(args).copy()
    options.pop('command', None)
    try:
        result = native_stack_fix(**options)
    except (ValueError, RuntimeError, OSError, KeyError, ET.ParseError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if result['status'] == 'partial' else 0


if __name__ == '__main__':
    raise SystemExit(run(add_arguments(argparse.ArgumentParser(description=__doc__)).parse_args()))
