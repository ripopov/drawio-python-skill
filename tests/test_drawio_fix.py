"""Offset allowlist, no-clobber delivery, and optional native repair regressions."""
import ast
import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from drawio_arch import Diagram, EDGE, style
from drawio_fix import apply_offsets, native_fix, verify_preservation, verify_render


def fixture():
    doc = Diagram()
    page = doc.page('Links')
    a = page.node('CPU', 20, 80, 100, 60, id='cpu', metadata={'custom': 'retain'})
    b = page.node('Memory', 400, 80, 100, 60, id='memory')
    page.edge(a, b, 'Request', id='request', style=style(EDGE, fontColor='#c01d42', dashed=1))
    page.edge(a, b, 'Response', id='response')
    return doc, page


class FixInvariantTests(unittest.TestCase):
    def test_only_declared_offsets_may_change(self):
        doc, page = fixture()
        geo = page.cell('request').find('mxGeometry')
        ET.SubElement(geo, 'mxPoint', {'as': 'offset', 'x': '2', 'y': '3', 'custom': 'keep'})
        changes = [dict(page=0, id='request', before=[2, 3], after=[2, -15])]
        fixed = copy.deepcopy(doc)
        apply_offsets(fixed, changes, 32)
        verify_preservation(doc, fixed, changes, 32)
        self.assertEqual(fixed.pages[0].cell('request').find("mxGeometry/mxPoint").get('custom'), 'keep')
        for mutation in ('label', 'style', 'terminal', 'waypoint', 'position', 'metadata'):
            broken = copy.deepcopy(fixed)
            p = broken.pages[0]
            if mutation == 'label': p.set_label('request', 'WRONG')
            if mutation == 'style': p.set_style('request', fontColor='#000000')
            if mutation == 'terminal': p.cell('request').set('target', 'cpu')
            if mutation == 'waypoint': ET.SubElement(p.cell('request').find('mxGeometry'), 'Array', {'as': 'points'})
            if mutation == 'position': p.cell('request').find('mxGeometry').set('x', '.5')
            if mutation == 'metadata': p.root.find('object').set('custom', 'changed')
            with self.subTest(mutation=mutation), self.assertRaisesRegex(RuntimeError, 'Preservation failed'):
                verify_preservation(doc, broken, changes, 32)
        with self.assertRaisesRegex(ValueError, 'displacement'):
            apply_offsets(copy.deepcopy(doc), changes, 5)
        with self.assertRaisesRegex(ValueError, 'match source'):
            apply_offsets(copy.deepcopy(doc), [dict(changes[0], before=[0, 0])], 32)

    def test_render_rejects_new_collisions_and_hidden_changes(self):
        page = dict(index=0, summary={'warning': 0}, collisions=[], routes=[], obstacles=[],
                    unmeasured_labels=[], labels=[dict(id='label', edge='edge', text='Text',
                                                      bounds=dict(x=10, y=10, width=40, height=14))])
        before = {'pages': [page]}
        for field, value in [('routes', [{'id': 'changed'}]), ('obstacles', [{'id': 'changed'}]),
                             ('unmeasured_labels', [{'id': 'label'}]), ('collisions', [dict(
                                 type='label-shape', a='label', b='shape', severity='advisory')])]:
            after = copy.deepcopy(before)
            after['pages'][0][field] = value
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                verify_render(before, after, [])
        after = copy.deepcopy(before)
        after['pages'][0]['labels'][0]['bounds']['x'] = 11
        with self.assertRaisesRegex(RuntimeError, 'movement'):
            verify_render(before, after, [])

    def test_invalid_options_and_existing_output_fail_without_renderer(self):
        with tempfile.TemporaryDirectory() as directory:
            doc, _ = fixture()
            path = doc.save(Path(directory) / 'input.drawio')
            before = path.read_bytes()
            for options in (dict(output=path), dict(max_move=0), dict(max_move=float('nan')),
                            dict(max_attempts=0), dict(max_passes=0), dict(only=['typo'])):
                with self.subTest(options=options), self.assertRaises(ValueError):
                    native_fix(path, **options)
            destination = Path(directory) / 'new.drawio'
            with self.assertRaisesRegex(RuntimeError, 'requires Chromium'):
                native_fix(path, output=destination, browser='/no-such-browser')
            self.assertFalse(destination.exists())
            self.assertEqual(before, path.read_bytes())
        ast.parse((Path(__file__).resolve().parents[1] / 'scripts/drawio_fix.py').read_text(),
                  feature_version=(3, 9))

    def test_source_change_aborts_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            doc, _ = fixture()
            path = doc.save(Path(directory) / 'input.drawio')
            destination = Path(directory) / 'new.drawio'
            page = dict(index=0, labels=[], routes=[], obstacles=[], collisions=[],
                        summary={'warning': 0}, unmeasured_labels=[])
            planned = dict(page, fix=dict(before=page, changes=[], attempts=0, stop_reason='warnings-cleared', skipped=[]))
            def renderer(source, **options):
                if options.get('_fix'):
                    return {'pages': [planned]}
                path.write_bytes(path.read_bytes() + b'\n')
                return {'pages': [page]}
            with patch('drawio_fix.native_check', side_effect=renderer):
                with self.assertRaisesRegex(RuntimeError, 'Source changed'):
                    native_fix(path, output=destination)
            self.assertFalse(destination.exists())


@unittest.skipUnless(os.environ.get('DRAWIO_NATIVE_TEST_BROWSER'), 'Configure native renderer for repair tests')
class NativeFixTests(unittest.TestCase):
    def options(self):
        result = dict(browser=os.environ['DRAWIO_NATIVE_TEST_BROWSER'],
                      no_sandbox=os.environ.get('DRAWIO_NATIVE_TEST_NO_SANDBOX') == '1')
        for key in ('asar', 'webapp'):
            if os.environ.get('DRAWIO_NATIVE_TEST_' + key.upper()):
                result[key] = os.environ['DRAWIO_NATIVE_TEST_' + key.upper()]
        return result

    def test_html_dry_run_apply_and_idempotence(self):
        with tempfile.TemporaryDirectory() as directory:
            doc, page = fixture()
            page.set_label('request', '<b>Request</b>')
            page.set_style('request', html=1)
            doc.page('Untouched').node('Other page', -100, -100)
            source = doc.save(Path(directory) / 'input.drawio')
            original = source.read_bytes()
            dry = native_fix(source, **self.options())
            self.assertEqual(dry['status'], 'warnings-cleared')
            self.assertTrue(dry['changes'])
            self.assertEqual(source.read_bytes(), original)
            output = Path(directory) / 'fixed.drawio'
            applied = native_fix(source, output=output, **self.options())
            self.assertEqual(dry['changes'], applied['changes'])
            verify_preservation(Diagram.load(source), Diagram.load(output), applied['changes'], 32)
            again = native_fix(output, **self.options())
            self.assertEqual(again['changes'], [])
            self.assertEqual(again['status'], 'warnings-cleared')
            self.assertEqual(source.read_bytes(), original)

    def test_coupled_small_moves_preserve_routes(self):
        with tempfile.TemporaryDirectory() as directory:
            doc, _ = fixture()
            source = doc.save(Path(directory) / 'input.drawio')
            result = native_fix(source, max_move=8, **self.options())
            self.assertEqual(result['status'], 'warnings-cleared', result['pages'])
            self.assertEqual(len(result['changes']), 2)
            self.assertTrue(all(c['displacement'] <= 8 for c in result['changes']))
            self.assertEqual(result['before']['pages'][0]['routes'], result['after']['pages'][0]['routes'])

    def test_locked_labels_child_labels_and_page_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            doc, page = fixture()
            page.set_style('request', locked=1)
            page.set_label('response', '')
            page.edge_label('response', 'Extra label', id='child')
            source = doc.save(Path(directory) / 'input.drawio')
            result = native_fix(source, only=['child'], **self.options())
            self.assertEqual([c['id'] for c in result['changes']], ['child'])
            frozen = native_fix(source, keep=['response'], **self.options())
            self.assertEqual(frozen['changes'], [])
            self.assertEqual(frozen['status'], 'partial')
            doc.page('Clean').node('Other', 10, 10)
            doc.save(source)
            selected = native_fix(source, page=1, **self.options())
            self.assertEqual(selected['changes'], [])
            self.assertEqual([p['index'] for p in selected['after']['pages']], [1])

    def test_does_not_cross_nearby_connectors_or_change_styles(self):
        with tempfile.TemporaryDirectory() as directory:
            doc, page = fixture()
            for y in (96, 124):
                page.edge(label='', source_point=(0, y), target_point=(600, y), routing='manual')
            source = doc.save(Path(directory) / 'input.drawio')
            result = native_fix(source, **self.options())
            self.assertEqual(result['changes'], [])
            self.assertEqual(result['status'], 'partial')

    def test_unsupported_routes_and_advisories_are_not_repaired(self):
        with tempfile.TemporaryDirectory() as directory:
            doc, page = fixture()
            page.set_style('response', curved=1)
            source = doc.save(Path(directory) / 'input.drawio')
            result = native_fix(source, **self.options())
            self.assertEqual(result['changes'], [])
            self.assertEqual(result['pages'][0]['stop_reason'], 'unsupported-route-on-page')
            doc, page = fixture()
            apply_offsets(doc, [dict(page=0, id='request', before=[0, 0], after=[0, -7.5]),
                                dict(page=0, id='response', before=[0, 0], after=[0, 7.5])], 32)
            doc.save(source)
            result = native_fix(source, **self.options())
            self.assertEqual(result['before']['pages'][0]['summary']['advisory'], 1)
            self.assertEqual(result['changes'], [])

    def test_budget_and_failed_recheck_do_not_publish_unsafe_output(self):
        with tempfile.TemporaryDirectory() as directory:
            doc, _ = fixture()
            source = doc.save(Path(directory) / 'input.drawio')
            result = native_fix(source, max_attempts=1, **self.options())
            self.assertLessEqual(result['pages'][0]['attempts'], 1)
            from drawio_native import native_check
            def renderer(path, **options):
                report = native_check(path, **options)
                if not options.get('_fix'):
                    report['pages'][0]['routes'][0]['points'][0]['x'] += 1
                return report
            output = Path(directory) / 'fixed.drawio'
            with patch('drawio_fix.native_check', side_effect=renderer):
                with self.assertRaisesRegex(RuntimeError, 'routes or shapes'):
                    native_fix(source, output=output, **self.options())
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
