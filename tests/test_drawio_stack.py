"""Stacking-only repair: persistent ordering, protected content, and unsafe-crossing rejection."""
import ast
import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from drawio_arch import Diagram, EDGE, TEXT, style
from drawio_stack import (apply_stack, native_stack_fix, verify_stack_preservation,
                          verify_stack_render, _paths_touch)


def fixture(*, child=False, through=False, node_text='', crossing=False, layers=False):
    doc = Diagram()
    page = doc.page('Stacking')
    a = page.node('A', 20, 170, 100, 60, id='a')
    b = page.node('B', 400, 170, 100, 60, id='b')
    page.edge(a, b, '' if child else 'Signal', id='signal', metadata={'custom': 'preserved'},
              label_offset=(0, 0 if through or child else -80), style=style(EDGE, fontColor='#950000'))
    if child:
        page.edge_label('signal', 'Signal', id='child', offset=(0, -80), style=TEXT)
    if crossing:
        page.edge(source_point=(260, 150), target_point=(260, 250), id='crossing', routing='manual')
    parent = page.layer('Overlay', id='overlay') if layers else '1'
    page.node(node_text, 220, 185 if through else 100, 80, 40, id='cover', parent=parent)
    return doc, page


class StackInvariantTests(unittest.TestCase):
    def test_only_order_changes_and_wrappers_survive(self):
        doc, _ = fixture()
        change = dict(page=0, edge='signal', after='cover')
        fixed = copy.deepcopy(doc)
        apply_stack(fixed, change)
        verify_stack_preservation(doc, fixed, [change])
        self.assertEqual(list(fixed.pages[0].cells())[-1], 'signal')
        self.assertEqual(fixed.pages[0].root[-1].get('custom'), 'preserved')
        for mutation in ('label', 'style', 'offset', 'terminal', 'parent'):
            modified = copy.deepcopy(fixed)
            p = modified.pages[0]
            if mutation == 'label': p.set_label('signal', 'Wrong')
            if mutation == 'style': p.set_style('signal', fontColor='#000000')
            if mutation == 'offset': p.cell('signal').find('mxGeometry/mxPoint').set('y', '0')
            if mutation == 'terminal': p.cell('signal').set('target', 'a')
            if mutation == 'parent': p.cell('signal').set('parent', 'cover')
            with self.subTest(mutation=mutation), self.assertRaisesRegex(RuntimeError, 'preservation'):
                verify_stack_preservation(doc, modified, [change])
        with self.assertRaises(ValueError):
            apply_stack(fixed, change)

    def test_geometry_comparison_ignores_enumeration_order_only(self):
        page = dict(index=0, labels=[dict(id='a', text='A'), dict(id='b', text='B')],
                    routes=[], obstacles=[], unmeasured_labels=[], collisions=[])
        before = {'pages': [page]}
        after = copy.deepcopy(before)
        after['pages'][0]['labels'].reverse()
        verify_stack_render(before, after)
        after['pages'][0]['labels'][0]['text'] = 'Changed'
        with self.assertRaisesRegex(RuntimeError, 'labels'):
            verify_stack_render(before, after)

    def test_crossing_guard_includes_collinear_and_diagonal_paths(self):
        def route(points): return {'points': [dict(x=x, y=y) for x, y in points]}
        self.assertTrue(_paths_touch(route([(0, 0), (10, 10)]), route([(0, 10), (10, 0)])))
        self.assertTrue(_paths_touch(route([(0, 0), (10, 0)]), route([(5, 0), (20, 0)])))
        self.assertFalse(_paths_touch(route([(0, 0), (10, 0)]), route([(0, 10), (10, 10)])))
        first = dict(route([(0, 0), (10, 0)]), bounds=dict(x=-2, y=-8, width=14, height=16))
        second = dict(route([(0, 10), (10, 10)]), bounds=dict(x=-2, y=2, width=14, height=16))
        self.assertTrue(_paths_touch(first, second))

    def test_existing_destination_and_invalid_options_fail_early(self):
        with tempfile.TemporaryDirectory() as directory:
            doc, _ = fixture()
            source = doc.save(Path(directory) / 'input.drawio')
            raw = source.read_bytes()
            for kwargs in (dict(output=source), dict(max_attempts=0), dict(only=['unknown'])):
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    native_stack_fix(source, **kwargs)
            self.assertEqual(source.read_bytes(), raw)
        for name in ('drawio_stack.py', 'drawio_repair.py'):
            ast.parse((Path(__file__).resolve().parents[1] / 'scripts' / name).read_text(),
                      feature_version=(3, 9))


@unittest.skipUnless(os.environ.get('DRAWIO_NATIVE_TEST_BROWSER'), 'Configure native renderer for stacking tests')
class NativeStackTests(unittest.TestCase):
    def options(self):
        options = dict(browser=os.environ['DRAWIO_NATIVE_TEST_BROWSER'],
                       no_sandbox=os.environ.get('DRAWIO_NATIVE_TEST_NO_SANDBOX') == '1')
        for key in ('asar', 'webapp'):
            value = os.environ.get('DRAWIO_NATIVE_TEST_' + key.upper())
            if value: options[key] = value
        return options

    def test_persistent_fix_dry_run_apply_hint_and_idempotence(self):
        with tempfile.TemporaryDirectory() as directory:
            doc, _ = fixture()
            source = doc.save(Path(directory) / 'input.drawio')
            original = source.read_bytes()
            dry = native_stack_fix(source, **self.options())
            self.assertEqual(dry['remaining_occlusions'], 0, dry['skipped'])
            self.assertEqual(len(dry['changes']), 1)
            warning = dry['before']['pages'][0]['collisions'][0]
            self.assertEqual(warning['suggested_fix']['command'], 'native-stack-fix')
            self.assertIn('native-stack-fix', warning['message'])
            output = Path(directory) / 'fixed.drawio'
            result = native_stack_fix(source, output=output, **self.options())
            self.assertEqual(result['changes'], dry['changes'])
            self.assertEqual(source.read_bytes(), original)
            verify_stack_preservation(Diagram.load(source), Diagram.load(output), result['changes'])
            self.assertEqual(result['after']['pages'][0]['collisions'][0]['paint_order'], 'label-above-shape')
            self.assertEqual(native_stack_fix(output, **self.options())['changes'], [])

    def test_rejects_line_exposure_label_covering_and_crossing_order(self):
        with tempfile.TemporaryDirectory() as directory:
            for options, reason in [(dict(through=True), 'would-expose-line-through-shape'),
                                    (dict(node_text='Title'), 'would-cover-other-label'),
                                    (dict(crossing=True), 'would-change-line-crossing-order'),
                                    (dict(layers=True), 'different-parent-or-layer')]:
                doc, _ = fixture(**options)
                source = doc.save(Path(directory) / 'input.drawio')
                with self.subTest(options=options):
                    result = native_stack_fix(source, **self.options())
                    self.assertEqual(result['changes'], [])
                    self.assertEqual(result['status'], 'partial')
                    self.assertIn(reason, [s['reason'] for s in result['skipped']])

    def test_child_label_locked_cells_and_other_pages_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            doc, page = fixture(child=True)
            doc.page('Other').node('Untouched', 0, 0)
            source = doc.save(Path(directory) / 'input.drawio')
            result = native_stack_fix(source, only=['child'], **self.options())
            self.assertEqual(result['status'], 'occlusions-cleared', result['skipped'])
            self.assertEqual(result['changes'][0]['edge'], 'signal')
            self.assertEqual(result['changes'][0]['label'], 'child')
            selected = native_stack_fix(source, page=1, **self.options())
            self.assertEqual(selected['changes'], [])
            frozen = native_stack_fix(source, keep=['signal'], **self.options())
            self.assertEqual(frozen['changes'], [])
            self.assertEqual(frozen['skipped'][0]['reason'], 'locked')
            page.set_style('signal', locked=1)
            doc.save(source)
            self.assertEqual(native_stack_fix(source, **self.options())['changes'], [])


if __name__ == '__main__':
    unittest.main()
