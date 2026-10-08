"""Optional end-to-end renderer tests; normal tests need no browser installation."""
import ast
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from drawio_arch import Diagram, EDGE, BLOCK, style
from drawio_native import native_check


class NativeCheckTests(unittest.TestCase):
    def test_missing_browser_is_explicit_and_source_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'diagram.drawio'
            doc = Diagram()
            doc.page().node('CPU', 20, 20)
            doc.save(path)
            before = path.read_bytes()
            with self.assertRaisesRegex(RuntimeError, 'requires Chromium/Chrome'):
                native_check(path, browser=str(Path(directory) / 'missing-browser'))
            self.assertEqual(before, path.read_bytes())

    def test_optional_python_helper_supports_python39_syntax(self):
        path = Path(__file__).resolve().parents[1] / 'scripts/drawio_native.py'
        ast.parse(path.read_text(), feature_version=(3, 9))


@unittest.skipUnless(os.environ.get('DRAWIO_NATIVE_TEST_BROWSER'),
                     'Set DRAWIO_NATIVE_TEST_BROWSER to run installed-renderer checks')
class NativeRenderTests(unittest.TestCase):
    def options(self):
        options = {'browser': os.environ['DRAWIO_NATIVE_TEST_BROWSER'],
                   'no_sandbox': os.environ.get('DRAWIO_NATIVE_TEST_NO_SANDBOX') == '1'}
        if os.environ.get('DRAWIO_NATIVE_TEST_ASAR'):
            options['asar'] = os.environ['DRAWIO_NATIVE_TEST_ASAR']
        if os.environ.get('DRAWIO_NATIVE_TEST_WEBAPP'):
            options['webapp'] = os.environ['DRAWIO_NATIVE_TEST_WEBAPP']
        return options

    def test_auto_routed_html_plain_and_child_labels_detect_then_fix(self):
        with tempfile.TemporaryDirectory() as directory:
            doc = Diagram()
            page = doc.page('Links')
            a = page.node('CPU', 20, 80, 100, 60, id='cpu')
            b = page.node('Memory', 400, 80, 100, 60, id='memory')
            request = page.edge(a, b, '<b>Request</b>', id='request', style=style(EDGE, html=1))
            response = page.edge(a, b, 'Response', id='response')
            page.edge_label(response, 'Ack', id='ack')
            hidden = page.layer('Hidden', visible=False)
            page.edge(a, b, 'Not rendered', id='hidden', parent=hidden)
            page.node('Invisible label', 600, 80, id='no-label', style=style(noLabel=1))
            doc.page('Other').node('Second page', 20, 20)
            path = doc.save(Path(directory) / 'links.drawio')
            before = path.read_bytes()
            report = native_check(path, **self.options())
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(len(report['pages']), 2)
            first = report['pages'][0]
            self.assertTrue(any({c['a'], c['b']} == {'request', 'response'}
                                for c in first['collisions']))
            self.assertIn('ack', {label['id'] for label in first['labels']})
            self.assertNotIn('hidden', {label['id'] for label in first['labels']})
            self.assertEqual(first['unmeasured_labels'], [])
            # Apply a real edit to native geometry, preserving routing and endpoints.
            import xml.etree.ElementTree as ET
            for ident, y in [('request', -30), ('response', 0), ('ack', 30)]:
                geo = page.cell(ident).find('mxGeometry')
                for old in geo.findall("mxPoint[@as='offset']"):
                    geo.remove(old)
                ET.SubElement(geo, 'mxPoint', {'x': '0', 'y': str(y), 'as': 'offset'})
            doc.save(path)
            fixed = native_check(path, **self.options())
            self.assertEqual(fixed['pages'][0]['collisions'], [])
            selected = native_check(path, page=1, **self.options())
            self.assertEqual([p['index'] for p in selected['pages']], [1])
            self.assertEqual(selected['pages'][0]['collisions'], [])

    def test_label_shape_collision_and_nested_container_exclusion(self):
        with tempfile.TemporaryDirectory() as directory:
            doc = Diagram()
            page = doc.page()
            group = page.container('System', 0, 0, 600, 240, id='system')
            a = page.node('A', 20, 80, 80, 60, parent=group)
            b = page.node('B', 480, 80, 80, 60, parent=group)
            page.edge(a, b, 'Signal', id='signal', parent=group)
            page.node('Obstacle', 260, 80, 80, 60, id='obstacle', parent=group)
            path = doc.save(Path(directory) / 'obstacle.drawio')
            report = native_check(path, **self.options())
            collisions = report['pages'][0]['collisions']
            self.assertTrue(any(c['type'] == 'label-shape' and c['a'] == 'signal'
                                and c['b'] == 'obstacle' for c in collisions))
            self.assertFalse(any(c['b'] == 'system' for c in collisions))

    def test_shape_paint_order_transparency_and_label_background(self):
        with tempfile.TemporaryDirectory() as directory:
            doc = Diagram()
            cases = [('covered', True, 100, 'none'), ('visible', False, 100, 'none'),
                     ('protected', False, 100, '#ffffff'), ('translucent', True, 30, 'none'),
                     ('transparent', True, 0, 'none')]
            for name, after, alpha, background in cases:
                page = doc.page(name)
                a = page.node('A', 20, 80, 100, 60)
                b = page.node('B', 400, 80, 100, 60)
                def obstacle():
                    page.node('', 220, 85, 80, 50, id='obstacle',
                              style=style(BLOCK, fillOpacity=alpha))
                if not after:
                    obstacle()
                page.edge(a, b, 'Signal', id='signal',
                          style=style(EDGE, labelBackgroundColor=background))
                if after:
                    obstacle()
            path = doc.save(Path(directory) / 'order.drawio')
            report = native_check(path, **self.options())
            findings = {p['name']: p['collisions'] for p in report['pages']}
            self.assertEqual(findings['covered'][0]['severity'], 'warning')
            self.assertEqual(findings['covered'][0]['reason'], 'possible-label-occlusion')
            self.assertEqual(findings['visible'][0]['severity'], 'advisory')
            self.assertEqual(findings['visible'][0]['paint_order'], 'label-above-shape')
            self.assertEqual(findings['protected'][0]['severity'], 'info')
            self.assertEqual(findings['translucent'][0]['severity'], 'advisory')
            self.assertEqual(findings['transparent'], [])

    def test_clearance_advisory_does_not_fail_default_cli(self):
        import json
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            doc = Diagram()
            page = doc.page()
            a = page.node('A', 20, 80, 100, 60)
            b = page.node('B', 400, 80, 100, 60)
            page.edge(a, b, 'Signal', id='signal1', label_offset=(0, -7.5))
            page.edge(a, b, 'Signal', id='signal2', label_offset=(0, 7.5))
            path = doc.save(Path(directory) / 'clearance.drawio')
            script = Path(__file__).resolve().parents[1] / 'scripts/drawio_arch.py'
            command = [sys.executable, str(script), 'native-check', str(path)]
            names = {'browser': '--browser', 'asar': '--drawio-asar', 'webapp': '--drawio-webapp'}
            for key, value in self.options().items():
                if key == 'no_sandbox':
                    if value:
                        command.append('--no-sandbox')
                else:
                    command.extend([names[key], value])
            default = subprocess.run(command, capture_output=True, text=True, timeout=60)
            report = json.loads(default.stdout)
            self.assertEqual(default.returncode, 0, default.stdout + default.stderr)
            self.assertEqual(report['pages'][0]['collisions'][0]['reason'], 'insufficient-clearance')
            strict = subprocess.run(command + ['--fail-on', 'advisory'], capture_output=True, text=True, timeout=60)
            self.assertEqual(strict.returncode, 1, strict.stdout + strict.stderr)


if __name__ == '__main__':
    unittest.main()
