"""Report preservation, filtering, multipage output, and failure behavior."""
import ast
import copy
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from drawio_arch import Diagram
from drawio_native import add_arguments, native_check, run
from drawio_report import highlight_severities, write_visual_report


class VisualReportTests(unittest.TestCase):
    def fixture(self, directory):
        doc = Diagram()
        doc.page('Untouched').node('Original', 0, 0)
        page = doc.page('Findings')
        a = page.node('A', -200, -100, id='c2')
        b = page.node('B', 200, -100)
        page.edge(a, b, 'Request', id='request')
        page.edge(a, b, 'Response', id='response')
        source = doc.save(Path(directory) / 'source.drawio')
        bounds = {'x': -30, 'y': -80, 'width': 60, 'height': 18}
        collisions = [dict(type='label-label', a='request', b='response', overlap=bounds,
                           severity=s, reason='overlapping-label-bounds')
                      for s in ('warning', 'advisory', 'info')]
        report = {'pages': [{'index': 1, 'name': 'Findings',
                            'bounds': {'x': -200, 'y': -100, 'width': 520, 'height': 60},
                            'labels': [dict(id=s, bounds=bounds) for s in ('request', 'response')],
                            'summary': dict(warning=1, advisory=1, info=1),
                            'collisions': collisions, 'unmeasured_labels': []}]}
        return source, doc, report

    def fake_export(self, source, output, **kwargs):
        Path(output).write_bytes(b'test image')
        return 800, 600

    def test_filtered_bundle_preserves_source_and_original_cells(self):
        with tempfile.TemporaryDirectory() as directory:
            source, original, report = self.fixture(directory)
            before = source.read_bytes()
            original_report = copy.deepcopy(report)
            destination = Path(directory) / 'report'
            with patch('drawio_report.export_png', side_effect=self.fake_export) as export:
                result = write_visual_report(source, report, destination, highlight='warning,info')
            self.assertEqual(before, source.read_bytes())
            self.assertEqual(report, original_report)
            self.assertEqual(result, json.loads((destination / 'report.json').read_text()))
            self.assertEqual(export.call_args.kwargs['page'], 1)
            self.assertTrue((destination / 'page-2.png').exists())
            self.assertFalse((destination / 'page-1.png').exists())
            annotated = Diagram.load(destination / 'annotated.drawio')
            self.assertEqual(annotated.validate(), [])
            for old_page, new_page in zip(original.pages, annotated.pages):
                for ident, cell in old_page.cells().items():
                    self.assertEqual(ET.canonicalize(ET.tostring(cell), strip_text=True),
                                     ET.canonicalize(ET.tostring(new_page.cell(ident)), strip_text=True))
            self.assertEqual(len(original.pages[0].cells()), len(annotated.pages[0].cells()))
            findings = result['pages'][0]['collisions']
            self.assertEqual([f['number'] for f in findings], [1, 2, 3])
            self.assertEqual([f['highlighted'] for f in findings], [True, False, True])
            page = annotated.pages[1]
            layer = result['pages'][0]['findings_layer']
            for finding in (findings[0], findings[2]):
                oval = page.cell(finding['annotation_cells'][0])
                self.assertEqual(oval.get('parent'), layer)
                geometry = oval.find('mxGeometry')
                self.assertLess(float(geometry.get('x')), -30)
                self.assertGreater(float(geometry.get('width')), 60)

    def test_clean_and_unmeasured_pages_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            source, _, report = self.fixture(directory)
            clean = copy.deepcopy(report['pages'][0])
            clean.update(index=0, name='Untouched', collisions=[], summary=dict(warning=0, advisory=0, info=0),
                         unmeasured_labels=[{'id': 'missing', 'text': 'Unknown'}])
            report['pages'].insert(0, clean)
            with patch('drawio_report.export_png', side_effect=self.fake_export) as export:
                result = write_visual_report(source, report, Path(directory) / 'report')
            self.assertEqual(export.call_count, 2)
            self.assertEqual([x['page'] for x in result['visual_report']['images']], [0, 1])
            doc = Diagram.load(Path(directory) / 'report/annotated.drawio')
            text = '\n'.join(doc.pages[0].label(i) for i in doc.pages[0].cells())
            self.assertIn('INCOMPLETE', text)
            self.assertIn('missing', text)
            self.assertIn('No label collisions detected', text)

    def test_failure_and_existing_destination_preserve_files(self):
        with tempfile.TemporaryDirectory() as directory:
            source, _, report = self.fixture(directory)
            before = source.read_bytes()
            destination = Path(directory) / 'report'
            with patch('drawio_report.export_png', side_effect=RuntimeError('renderer unavailable')):
                with self.assertRaisesRegex(RuntimeError, 'renderer unavailable'):
                    write_visual_report(source, report, destination)
            self.assertFalse(destination.exists())
            self.assertEqual(source.read_bytes(), before)
            with self.assertRaisesRegex(ValueError, 'already exists'):
                write_visual_report(source, report, source)
            destination.mkdir()
            sentinel = destination / 'keep.txt'
            sentinel.write_text('keep')
            with self.assertRaisesRegex(ValueError, 'already exists'):
                write_visual_report(source, report, destination)
            self.assertEqual(sentinel.read_text(), 'keep')

    def test_filter_does_not_hide_failures_and_errors_return_two(self):
        import argparse
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as directory:
            source, _, report = self.fixture(directory)
            parser = add_arguments(argparse.ArgumentParser())
            args = parser.parse_args([str(source), '--report-dir', str(Path(directory) / 'report'),
                                      '--highlight', 'info'])
            with patch('drawio_native.native_check', return_value=report), \
                    patch('drawio_report.export_png', side_effect=self.fake_export), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(run(args), 1)
            self.assertEqual(json.loads(output.getvalue())['visual_report']['highlight'], ['info'])
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(run(args), 2)
            self.assertIn('already exists', json.loads(output.getvalue())['error'])
        with self.assertRaises(ValueError):
            highlight_severities('warn')
        ast.parse((Path(__file__).resolve().parents[1] / 'scripts/drawio_report.py').read_text(),
                  feature_version=(3, 9))

    @unittest.skipUnless(os.environ.get('DRAWIO_NATIVE_TEST_BROWSER') and shutil.which('drawio')
                         and (not sys.platform.startswith('linux') or os.environ.get('DISPLAY')
                              or shutil.which('xvfb-run')),
                         'Native report integration needs configured browser and Desktop export support')
    def test_native_selected_page_report(self):
        with tempfile.TemporaryDirectory() as directory:
            source, _, _ = self.fixture(directory)
            before = source.read_bytes()
            options = {'browser': os.environ['DRAWIO_NATIVE_TEST_BROWSER'],
                       'no_sandbox': os.environ.get('DRAWIO_NATIVE_TEST_NO_SANDBOX') == '1'}
            for key in ('asar', 'webapp'):
                value = os.environ.get('DRAWIO_NATIVE_TEST_' + key.upper())
                if value:
                    options[key] = value
            report = native_check(source, page=1, **options)
            destination = Path(directory) / 'report'
            result = write_visual_report(source, report, destination, highlight='warning',
                                         no_sandbox=options['no_sandbox'],
                                         headless=sys.platform.startswith('linux') and not os.environ.get('DISPLAY'))
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(len(result['pages'][0]['collisions']), 1)
            self.assertTrue(result['pages'][0]['collisions'][0]['highlighted'])
            self.assertTrue((destination / 'page-2.png').read_bytes().startswith(b'\x89PNG\r\n\x1a\n'))
            self.assertFalse((destination / 'page-1.png').exists())
            self.assertEqual(len(Diagram.load(destination / 'annotated.drawio').pages), 2)


if __name__ == '__main__':
    unittest.main()
