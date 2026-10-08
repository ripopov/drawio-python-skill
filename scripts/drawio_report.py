"""Scripted visual reports for native checks; source diagrams remain untouched."""
import copy
import json
import os
from pathlib import Path
import tempfile
import textwrap

from drawio_arch import Diagram, TEXT, export_png, style


SEVERITIES = ('warning', 'advisory', 'info')
REASONS = {
    'overlapping-label-bounds': 'Label bounds overlap',
    'insufficient-clearance': 'Less than the requested clearance',
    'possible-label-occlusion': 'Opaque shape painted above label',
    'translucent-shape-above-label': 'Translucent shape painted above label',
    'label-visible-above-shape': 'Label above shape without an opaque background',
    'label-background-protects-text': 'Label above shape with a protective background',
    'shape-overlap-needs-review': 'Shape overlap with uncertain paint order',
}


def highlight_severities(value):
    """Parse an exact severity selection, independent of the failure threshold."""
    if value == 'all':
        return SEVERITIES
    selected = set(value.split(','))
    if not selected or not selected <= set(SEVERITIES):
        raise ValueError('Highlight must be all or comma-separated warning,advisory,info')
    return tuple(s for s in SEVERITIES if s in selected)


def _union(boxes):
    left = min(b['x'] for b in boxes)
    top = min(b['y'] for b in boxes)
    right = max(b['x'] + b['width'] for b in boxes)
    bottom = max(b['y'] + b['height'] for b in boxes)
    return left, top, right, bottom


def annotate(doc, report, severities):
    """Add editable findings layers; number all findings even when filtered out."""
    number = 0
    for result in report['pages']:
        page = doc.pages[result['index']]
        layer = page.layer('Native check findings')
        result['findings_layer'] = layer
        labels = {label['id']: label for label in result['labels']}
        extents = [result['bounds']] + [label['bounds'] for label in result['labels']]
        notes = []
        for finding in result['collisions']:
            number += 1
            finding['number'] = number
            finding['explanation'] = REASONS.get(finding['reason'], finding['reason'])
            finding['highlighted'] = finding['severity'] in severities
            if not finding['highlighted']:
                continue
            boxes = [labels[finding['a']]['bounds']]
            if finding['type'] == 'label-label':
                boxes.append(labels[finding['b']]['bounds'])
            left, top, right, bottom = _union(boxes)
            # Extra space keeps corners of the measured rectangles inside the oval.
            padx = max(9, (right - left) * .22)
            pady = max(9, (bottom - top) * .22)
            x, y = left - padx, top - pady
            width, height = right - left + 2 * padx, bottom - top + 2 * pady
            oval = page.node('', x, y, width, height, parent=layer,
                             style=style(shape='ellipse', fillColor='none',
                                         strokeColor='#dc2626', strokeWidth=3))
            badge = page.text(str(number), x + width, y - 12, 48, 26, parent=layer,
                              style=style(TEXT, fontSize=16, fontStyle=1,
                                          fontColor='#dc2626', labelBackgroundColor='#ffffff'))
            finding['annotation_cells'] = [oval, badge]
            extents.append({'x': x, 'y': y - 12, 'width': width + 48, 'height': height + 12})
            notes.append('{} [{}] {} / {}\n{}'.format(
                number, finding['severity'].upper(), finding['a'], finding['b'],
                finding['explanation']))
            if finding.get('suggested_fix'):
                notes[-1] += '\nSuggested: ' + finding['suggested_fix']['command'] + ' (dry-run)'

        left, _, right, bottom = _union(extents)
        width = max(600, min(1000, right - left))
        y = bottom + 40

        def note(text, size=14, bold=False):
            nonlocal y
            # Use explicit wrapping and generous line height for a readable native legend.
            columns = max(20, int((width - 24) / size))
            lines = []
            for line in text.split('\n'):
                lines.extend(textwrap.wrap(line, width=columns, replace_whitespace=False) or [''])
            height = len(lines) * (size * 1.5) + 12
            page.text('\n'.join(lines), left, y, width, height, parent=layer,
                      style=style(TEXT, fontSize=size, fontStyle=int(bold), align='left',
                                  verticalAlign='top', whiteSpace='nowrap',
                                  fontColor='#0f172a', fillColor='#ffffff', spacing=6))
            y += height + 6

        note('Native label check: ' + (result.get('name') or 'Untitled page'), 20, True)
        summary = result['summary']
        note('{} warnings | {} advisories | {} informational findings'.format(
            *(summary[s] for s in SEVERITIES)))
        note('Highlighted: {}. Red ovals mark potential issues, not confirmed defects.'.format(
            ', '.join(severities)))
        if not notes:
            note('No findings match the highlight filter.' if result['collisions']
                 else 'No label collisions detected within the native checker scope.')
        for entry in notes:
            note(entry)
        if result['unmeasured_labels']:
            note('INCOMPLETE: visible labels could not be measured: ' +
                 ', '.join(label['id'] for label in result['unmeasured_labels']), bold=True)
        note('Bounds and sampled paint order only. Line crossings, text fitting and semantics '
             'are outside this check. Hide the findings layer to view the original diagram.', 12)


def write_visual_report(source, report, destination, *, highlight='all', executable='drawio',
                        headless=False, no_sandbox=False, scale=1.5, timeout=60):
    """Publish a complete bundle to a new directory, or leave no bundle on failure."""
    severities = highlight_severities(highlight)
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError('Report directory already exists; choose a new directory: ' + str(destination))
    doc = Diagram.load(source)
    result = copy.deepcopy(report)
    annotate(doc, result, severities)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.drawio-report-', dir=destination.parent) as temporary:
        stage = Path(temporary) / 'bundle'
        stage.mkdir()
        annotated = doc.save(stage / 'annotated.drawio')
        images = []
        for page in result['pages']:
            name = 'page-{}.png'.format(page['index'] + 1)
            width, height = export_png(annotated, stage / name, page=page['index'], scale=scale,
                                       executable=executable, headless=headless, timeout=timeout,
                                       extra_args=['--no-sandbox'] if no_sandbox else ())
            images.append({'page': page['index'], 'path': name, 'width': width, 'height': height})
        result['visual_report'] = {
            'directory': str(destination), 'json': 'report.json', 'diagram': 'annotated.drawio',
            'images': images, 'highlight': list(severities),
        }
        (stage / 'report.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n',
                                         encoding='utf-8')
        # A failed page export never publishes a partial report or touches the source.
        if destination.exists():
            raise ValueError('Report directory appeared during generation: ' + str(destination))
        os.rename(stage, destination)
    return result
