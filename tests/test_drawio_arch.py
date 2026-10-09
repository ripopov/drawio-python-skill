import ast
import base64
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import struct
import subprocess
import urllib.parse
import xml.etree.ElementTree as ET
import zlib
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'examples'))
from drawio_arch import Diagram, style, export_png, export_svg, _is_snap_executable, main
import generate
import detail
import manufacturing
import records
import pools
import cache


class ExportTests(unittest.TestCase):
    def render(self, cmd, **kwargs):
        temporary = Path(cmd[cmd.index('--output') + 1])
        source = Path(cmd[-1])
        self.assertFalse(any(part.startswith('.') for part in temporary.relative_to(source.parent).parts))
        temporary.write_bytes(b'\x89PNG\r\n\x1a\n' + b'\0' * 8 + struct.pack('>II', 100, 200))
        return subprocess.CompletedProcess(cmd, 0, '', '')

    def test_snap_launcher_and_resolved_binary_detection(self):
        self.assertTrue(_is_snap_executable('/snap/bin/drawio'))
        self.assertTrue(_is_snap_executable('/snap/drawio/305/app/drawio'))
        self.assertFalse(_is_snap_executable('/opt/drawio/drawio'))
        with tempfile.TemporaryDirectory() as directory:
            launcher = Path(directory) / 'drawio'
            launcher.symlink_to('/usr/bin/snap')
            self.assertTrue(_is_snap_executable(launcher))
            launcher.unlink()
            launcher.symlink_to('/snap/drawio/305/app/drawio')
            self.assertTrue(_is_snap_executable(launcher))

    def test_snap_blocks_outside_hidden_and_symlink_paths_before_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / 'home'
            home.mkdir()
            source = Diagram()
            source.page().node('CPU', 0, 0)
            allowed = source.save(home / 'source.drawio')
            outside = source.save(root / 'source.drawio')
            hidden = source.save(home / '.hidden/source.drawio')
            link = home / 'linked.drawio'
            link.symlink_to(outside)
            escape = home / 'escape'
            escape.symlink_to(root, target_is_directory=True)
            cases = ((outside, home / 'out.png'), (allowed, root / 'out.png'),
                     (allowed, root / 'home-other/out.png'), (hidden, home / 'out.png'),
                     (allowed, home / '.out.png'), (link, home / 'out.png'),
                     (allowed, escape / 'out.png'))
            with patch('drawio_arch.Path.home', return_value=home), \
                    patch('drawio_arch.shutil.which', return_value='/snap/bin/drawio'), \
                    patch('drawio_arch.subprocess.run') as run:
                for src, output in cases:
                    with self.subTest(source=src, output=output):
                        with self.assertRaisesRegex(RuntimeError, 'Snap Draw.io.*\\$HOME'):
                            export_png(src, output, headless=True)
                        self.assertFalse(output.exists())
                run.assert_not_called()

    def test_snap_visible_home_export_uses_accessible_temporary_output(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            doc = Diagram()
            doc.page().node('CPU', 0, 0)
            source = doc.save(home / 'source.drawio')
            with patch('drawio_arch.Path.home', return_value=home), \
                    patch('drawio_arch.shutil.which', return_value='/snap/bin/drawio'), \
                    patch('drawio_arch.subprocess.run', side_effect=self.render) as run:
                self.assertEqual(export_png(source, home / 'out.png', headless=True), (100, 200))
            self.assertEqual(run.call_args.args[0][:2], ['xvfb-run', '-a'])
            self.assertEqual(sorted(p.name for p in home.iterdir()), ['out.png', 'source.drawio'])

    def test_export_surfaces_early_error_before_gpu_noise(self):
        noise = '[ERROR:gl_display.cc:100] EGL Driver message: eglInitialize failed\n' * 100
        cases = (('Error: input file/directory not found\n', noise, 'input file/directory not found'),
                 ('', 'Error: permission denied\n' + noise, 'permission denied'),
                 ('', 'Error: invalid rectangle\n' + noise, 'invalid rectangle'),
                 ('', noise, 'No actionable renderer output'))
        with tempfile.TemporaryDirectory() as directory:
            doc = Diagram()
            doc.page().node('CPU', 0, 0)
            source = doc.save(Path(directory) / 'source.drawio')
            output = Path(directory) / 'out.png'
            output.write_bytes(b'previous PNG')
            for stdout, stderr, expected in cases:
                with self.subTest(expected=expected), \
                        patch('drawio_arch.shutil.which', return_value='/opt/drawio/drawio'), \
                        patch('drawio_arch.subprocess.run',
                              return_value=subprocess.CompletedProcess([], 1, stdout, stderr)):
                    with self.assertRaisesRegex(RuntimeError, expected) as failure:
                        export_png(source, output)
                    self.assertNotIn('EGL Driver', str(failure.exception))
                    self.assertEqual(output.read_bytes(), b'previous PNG')

    def test_export_accepts_native_asset_flags_for_compatibility(self):
        for flag in ('--drawio-asar', '--drawio-webapp'):
            with self.subTest(flag=flag), \
                    patch('sys.argv', ['drawio_arch.py', 'export', 'source.drawio', 'out.png',
                                       flag, '/unused/assets', '--executable', '/custom/drawio']), \
                    patch('drawio_arch.export_png', return_value=(100, 200)) as export, \
                    patch('builtins.print'):
                self.assertEqual(main(), 0)
                self.assertEqual(export.call_args.kwargs['executable'], '/custom/drawio')


class SvgExportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        doc = Diagram()
        doc.page('First').node('CPU', 0, 0)
        doc.page('Second').node('Memory', 0, 0)
        self.source = doc.save(self.root / 'source.drawio')
        self.before = self.source.read_bytes()
        self.output = self.root / 'out.svg'
        self.output.write_bytes(b'previous SVG')
        self.which = patch('drawio_arch.shutil.which', return_value='/opt/drawio/drawio')
        self.which.start()
        self.addCleanup(self.which.stop)

    def svg(self, scheme='light dark'):
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="100.5px" height="200px" '
                f'style="background: transparent; color-scheme: {scheme};" content="&lt;mxfile/&gt;">'
                '<rect width="100" height="200" fill="#ffffff" '
                'style="fill: light-dark(#ffffff, #222222);"/></svg>').encode()

    def renderer(self, data):
        def render(cmd, **kwargs):
            Path(cmd[cmd.index('--output') + 1]).write_bytes(data)
            return subprocess.CompletedProcess(cmd, 0, '', '')
        return render

    def assert_unchanged(self):
        self.assertEqual(self.source.read_bytes(), self.before)
        self.assertEqual(self.output.read_bytes(), b'previous SVG')
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['out.svg', 'source.drawio'])

    def test_adaptive_default_preserves_native_svg_and_selects_page(self):
        data = self.svg()
        with patch('drawio_arch.subprocess.run', side_effect=self.renderer(data)) as run:
            self.assertEqual(export_svg(self.source, self.output, page=1, scale=1.5,
                                        headless=True, extra_args=['--embed-diagram']), (100.5, 200))
        self.assertEqual(self.output.read_bytes(), data)
        self.assertEqual(self.source.read_bytes(), self.before)
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[:2], ['xvfb-run', '-a'])
        for option, expected in (('--format', 'svg'), ('--svg-theme', 'auto'),
                                 ('--page-index', '2'), ('--scale', '1.5')):
            self.assertEqual(cmd[cmd.index(option) + 1], expected)
        self.assertIn('--embed-diagram', cmd)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['out.svg', 'source.drawio'])

    def test_fixed_themes(self):
        for theme in ('light', 'dark'):
            data = self.svg(theme).replace(b'100.5px', b'100.5')
            with self.subTest(theme=theme), \
                    patch('drawio_arch.subprocess.run', side_effect=self.renderer(data)) as run:
                self.assertEqual(export_svg(self.source, self.output, theme=theme), (100.5, 200))
                cmd = run.call_args.args[0]
                self.assertEqual(cmd[cmd.index('--svg-theme') + 1], theme)
                self.assertEqual(self.output.read_bytes(), data)

    def test_invalid_or_nonadaptive_output_preserves_previous_file(self):
        cases = (b'not XML', b'<svg', b'<html/>', b'<svg width="100" height="200"/>',
                 self.svg().replace(b'100.5px', b'0px'),
                 self.svg().replace(b'200px', b'nan'),
                 self.svg().replace(b'200px', b'inf'),
                 self.svg().replace(b'200px', b'10%'),
                 self.svg('light'), self.svg('dark'))
        for data in cases:
            with self.subTest(data=data), patch('drawio_arch.subprocess.run', side_effect=self.renderer(data)):
                with self.assertRaises(RuntimeError):
                    export_svg(self.source, self.output)
                self.assert_unchanged()

    def test_renderer_failure_missing_output_and_timeout_preserve_previous_file(self):
        cases = (subprocess.CompletedProcess([], 1, '', 'export failed'),
                 subprocess.CompletedProcess([], 0, '', ''),
                 subprocess.TimeoutExpired('drawio', 60))
        for result in cases:
            effect = {'side_effect': result} if isinstance(result, Exception) else {'return_value': result}
            with self.subTest(result=result), patch('drawio_arch.subprocess.run', **effect):
                with self.assertRaises((RuntimeError, subprocess.TimeoutExpired)):
                    export_svg(self.source, self.output)
                self.assert_unchanged()

    def test_invalid_options_do_not_launch_renderer(self):
        with patch('drawio_arch.subprocess.run') as run:
            for options in ({'theme': 'invalid'}, {'page': -1}, {'page': 2}, {'scale': 0}, {'border': -1}):
                with self.subTest(options=options), self.assertRaises(ValueError):
                    export_svg(self.source, self.output, **options)
            with self.assertRaisesRegex(ValueError, 'overwrite source'):
                export_svg(self.source, self.source)
            run.assert_not_called()
        self.assert_unchanged()

    def test_cli_infers_svg_and_supports_explicit_format_and_theme(self):
        for arguments, theme in ((['out.svg'], 'auto'), (['out.drawio.SVG'], 'auto'),
                                 (['out.svg', '--theme', 'dark'], 'dark'),
                                 (['out.image', '--format', 'svg', '--theme', 'light'], 'light')):
            with self.subTest(arguments=arguments), \
                    patch('sys.argv', ['drawio_arch.py', 'export', 'source.drawio'] + arguments), \
                    patch('drawio_arch.export_svg', return_value=(100, 200)) as export, \
                    patch('drawio_arch.export_png') as png, patch('builtins.print'):
                self.assertEqual(main(), 0)
                self.assertEqual(export.call_args.kwargs['theme'], theme)
                png.assert_not_called()

    def test_cli_rejects_svg_theme_for_png(self):
        with patch('sys.argv', ['drawio_arch.py', 'export', 'source.drawio', 'out.png', '--theme', 'auto']), \
                patch('drawio_arch.export_png') as png, patch('sys.stderr'):
            with self.assertRaises(SystemExit) as exit:
                main()
            self.assertEqual(exit.exception.code, 2)
            png.assert_not_called()


class DiagramTests(unittest.TestCase):
    def test_full_composition_roundtrip(self):
        doc = Diagram()
        p = doc.page('A & B', id='a')
        layer = p.layer('Data', id='data')
        group = p.group(20,30,500,300,parent=layer)
        box = p.container('CPU',10,10,450,250,parent=group)
        node = p.node('<register> & "data"',20,40,parent=box,metadata={'role':'register','link':'https://example.org'})
        port = p.port(node,'out',1,.5)
        target = p.node('Memory',250,40,parent=box)
        edge = p.edge(port,target,'32-bit',parent=box,waypoints=[(200,70),(200,100)],exit=(1,.5),entry=(0,.5),metadata={'bus':'AXI'})
        p.edge_label(edge,'control',offset=(0,-15))
        p.edge(source_point=(0,0),target_point=(10,20))
        p.stencil('',generate.GLOBE,10,10,72,72)
        doc.page('Detail',id='b')
        with tempfile.TemporaryDirectory() as td:
            path = doc.save(Path(td)/'diagram.drawio')
            loaded = Diagram.load(path)
            self.assertEqual(loaded.validate(), [])
            self.assertEqual(len(loaded.pages), 2)
            self.assertEqual(loaded.pages[0].cell(port).get('parent'),node)
            self.assertEqual(loaded.pages[0].cell(edge).get('source'),port)
            self.assertEqual(len(loaded.pages[0].cell(edge).findall('mxGeometry/Array/mxPoint')),2)
            self.assertIn('&amp;',path.read_text())
            st = next(c.get('style') for c in loaded.pages[0].cells().values() if 'stencil(' in c.get('style',''))
            payload = st.split('stencil(')[1].split(')')[0]
            self.assertEqual(urllib.parse.unquote(zlib.decompress(base64.b64decode(payload),-15).decode()),generate.GLOBE)

    def test_preservation_compressed_and_wrapped(self):
        # Unknown attributes, elements, comments, wrappers and unaffected pages survive.
        source = '<mxfile custom="keep"><diagram id="a" name="A"><mxGraphModel custom="yes"><root><mxCell id="0"/><mxCell id="1" parent="0"/><!--keep--><UserObject id="reg" label="Before" custom="x"><mxCell parent="1" vertex="1" style="named;unknown=keep;"><mxGeometry x="5" y="6" width="100" height="50" as="geometry"><mxRectangle x="9" y="8" width="7" height="6" as="alternateBounds"/></mxGeometry></mxCell><extra foo="bar"/></UserObject></root></mxGraphModel></diagram><diagram id="b" name="B" /></mxfile>'
        model = '<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/></root></mxGraphModel>'
        root = ET.fromstring(source, parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True)))
        compressed = zlib.compress(urllib.parse.quote(model).encode())[2:-4]
        root[1].text = base64.b64encode(compressed).decode()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'input.drawio'
            ET.ElementTree(root).write(path)
            doc = Diagram.load(path)
            before = ET.canonicalize(ET.tostring(doc.pages[1].diagram), strip_text=True)
            p = doc.pages[0]
            old_geometry = ET.canonicalize(ET.tostring(p.cell('reg').find('mxGeometry')), strip_text=True)
            p.set_label('reg','After & editable')
            p.set_style('reg',fillColor='#ffffff')
            out = doc.save(Path(td)/'edited.drawio')
            loaded = Diagram.load(out)
            self.assertEqual(loaded.xml.get('custom'),'keep')
            self.assertEqual(ET.canonicalize(ET.tostring(loaded.pages[1].diagram), strip_text=True),before)
            self.assertEqual(ET.canonicalize(ET.tostring(loaded.pages[0].cell('reg').find('mxGeometry')), strip_text=True),old_geometry)
            self.assertEqual(loaded.pages[0].root.find('UserObject').get('custom'),'x')
            self.assertIsNotNone(loaded.pages[0].root.find('UserObject/extra'))
            self.assertIn('unknown=keep;',loaded.pages[0].cell('reg').get('style'))
            self.assertIn('<!--keep-->',out.read_text())

    def test_validation_and_atomic_save(self):
        doc = Diagram(); p = doc.page()
        a = p.node('A',0,0,id='a'); b = p.node('B',200,0,id='b')
        e = p.edge(a,b)
        with self.assertRaises(ValueError): p.node('duplicate',0,0,id='a')
        with self.assertRaises(ValueError): p.node('nan',float('nan'),0)
        with tempfile.TemporaryDirectory() as td:
            path = doc.save(Path(td)/'ok.drawio'); before = path.read_bytes()
            p.cell(e).set('target','missing')
            self.assertTrue(any('dangling' in s for s in doc.validate()))
            with self.assertRaises(ValueError): doc.save(path)
            self.assertEqual(path.read_bytes(),before)
        p.cell(a).set('parent','b'); p.cell(b).set('parent','a')
        self.assertTrue(any('cycle' in s for s in doc.validate()))
        p.cell(a).find('mxGeometry').set('width','-10')
        self.assertTrue(any('invalid width' in s for s in doc.validate()))

    def test_mesh_topology(self):
        for rows,cols in [(1,1),(4,4),(8,8),(2,5)]:
            doc = generate.mesh(rows,cols)
            self.assertEqual(doc.validate(),[])
            cells = doc.pages[0].cells()
            routers = {i:c for i,c in cells.items() if i.startswith('r')}
            self.assertEqual(len(routers),rows*cols)
            edges = [c for c in cells.values() if c.get('edge')=='1']
            self.assertEqual(len(edges),rows*(cols-1)+cols*(rows-1))
            pairs = set()
            for e in edges:
                a = cells[e.get('source')].get('parent'); b = cells[e.get('target')].get('parent')
                ar,ac = map(int,a[1:].split('_')); br,bc = map(int,b[1:].split('_'))
                self.assertEqual(abs(ar-br)+abs(ac-bc),1)
                pair = tuple(sorted((a,b))); self.assertNotIn(pair,pairs); pairs.add(pair)
                self.assertIn('startArrow=block;',e.get('style'))
                self.assertIn('endArrow=block;',e.get('style'))

    def test_examples(self):
        for builder in [generate.cpu,generate.axi,generate.network,detail.build]:
            doc = builder(); self.assertEqual(doc.validate(),[])
        network = generate.network()
        p = network.pages[0]
        self.assertEqual(p.model.get('pageWidth'),'450')
        self.assertEqual(p.model.get('pageHeight'),'680')
        self.assertEqual(sum(c.get('style')=='group;' for c in p.cells().values()),6)
        self.assertEqual(sum(c.get('edge')=='1' for c in p.cells().values()),5)
        self.assertFalse(any('image=' in c.get('style','') for c in p.cells().values()))

    def test_export_page_and_failure_preserves_output(self):
        doc = Diagram(); doc.page('First'); doc.page('Second')
        with tempfile.TemporaryDirectory() as td:
            source = doc.save(Path(td)/'source.drawio')
            output = Path(td)/'output.png'
            output.write_bytes(b'previous PNG')
            def renderer(cmd, **kwargs):
                self.assertEqual(cmd[cmd.index('--page-index')+1],'2')
                Path(cmd[cmd.index('--output')+1]).write_bytes(b'\x89PNG\r\n\x1a\n' + b'\0'*8 + struct.pack('>II',100,200))
                return subprocess.CompletedProcess(cmd,0,'','')
            with patch('drawio_arch.shutil.which',return_value='/usr/bin/drawio'):
                with patch('drawio_arch.subprocess.run',side_effect=renderer):
                    self.assertEqual(export_png(source,output,page=1),(100,200))
                before = output.read_bytes()
                with patch('drawio_arch.subprocess.run',return_value=subprocess.CompletedProcess([],1,'','failure')):
                    with self.assertRaises(RuntimeError): export_png(source,output)
                self.assertEqual(output.read_bytes(),before)
                with self.assertRaises(ValueError): export_png(source,output,page=2)

    def test_pretty_xml_preserves_content_and_in_memory_tree(self):
        doc=Diagram(); p=doc.page()
        p.node('A & B\neditable',0,0,id='a')
        mixed=ET.SubElement(p.root,'extension'); mixed.text=' prefix '
        ET.SubElement(mixed,'span').tail=' suffix '
        protected=ET.SubElement(p.root,'extension',{'{http://www.w3.org/XML/1998/namespace}space':'preserve'})
        protected.text='   '; ET.SubElement(protected,'raw').tail='  '
        before=ET.tostring(doc.xml)
        with tempfile.TemporaryDirectory() as td:
            path=doc.save(Path(td)/'pretty.drawio')
            data=path.read_text()
            self.assertIn('\n  <diagram',data)
            self.assertIn('\n        <mxCell',data)
            self.assertGreater(len(data.splitlines()),10)
            self.assertEqual(ET.tostring(doc.xml),before)
            loaded=Diagram.load(path)
            self.assertEqual(loaded.pages[0].label('a'),'A & B\neditable')
            self.assertEqual(ET.tostring(loaded.pages[0].root.find('extension')).strip(),ET.tostring(mixed).strip())
            self.assertEqual(loaded.pages[0].root.findall('extension')[1].text,'   ')
            compact=doc.save(Path(td)/'compact.drawio',pretty=False)
            self.assertEqual(len(compact.read_text().splitlines()),2)

    def test_edge_arguments_fail_fast_without_mutation(self):
        for key,value in [('exit',(1,.5)),('entry',(0,.5)),('waypoints',[(20,30)]),('routing','manual')]:
            with self.assertRaisesRegex(ValueError,'p.edge'):
                style('strokeColor=red;',**{key:value})
        doc=Diagram(); p=doc.page(); a=p.node('A',0,0); b=p.node('B',200,0)
        before=ET.tostring(p.root)
        with self.assertRaises(ValueError): p.edge(a,b,waypoints=[(float('nan'),0)])
        self.assertEqual(ET.tostring(p.root),before)
        with self.assertRaises(ValueError): p.edge(a,b,exit=(2,.5))
        p.cell(a).set('style','unknown=preserved;exit=(1, 0.5);')
        self.assertTrue(any('belongs in p.edge' in msg for msg in doc.validate()))

    def test_bounds_ports_routes_and_labels(self):
        doc=Diagram(); p=doc.page()
        g=p.group(100,50,500,500)
        a=p.node('A',20,30,100,60,parent=g,id='a')
        b=p.node('B',300,180,100,60,parent=g,id='b')
        port=p.port(a,'',1,.5,size=8)
        self.assertEqual(p.bounds(a),(120,80,100,60))
        self.assertEqual(p.bounds(port),(216,106,8,8))
        self.assertEqual(p.point(a,'E',relative_to=g),(120,60))
        edge=p.connect(a,b,'bus',parent=g,lane=200,label_segment=1,label_offset=(20,0))
        cell=p.cell(edge); self.assertIn('noEdgeStyle=1;',cell.get('style'))
        points=cell.findall("mxGeometry/Array/mxPoint")
        self.assertEqual([(pt.get('x'),pt.get('y')) for pt in points],[('200','60'),('200','210')])
        # Label uses midpoint of the selected leg, not midpoint of the entire path.
        self.assertAlmostEqual(float(cell.find('mxGeometry').get('x')),-2/33)
        e2=p.connect(a,b,'offset',parent=g,source_fraction=.2,target_fraction=.8,lane=240)
        self.assertIn('exitY=0.2;',p.cell(e2).get('style'))
        with self.assertRaisesRegex(ValueError,'Diagonal'):
            p.connect(a,b,via=[(250,170)])
        with self.assertRaisesRegex(ValueError,'outward'):
            p.connect(b,a,parent=g)
        self.assertEqual(p.layout_warnings(),[])

    def test_layout_checks_and_topology_labels(self):
        doc=Diagram(); p=doc.page()
        a=p.node('A',0,0,100,60,id='a'); b=p.node('B',400,0,100,60,id='b')
        obstacle=p.node('obstacle',200,0,100,60,id='obstacle')
        edge=p.connect(a,b)
        p.edge_label(edge,'Yes\nbranch')
        p.assert_connections([('a','b','Yes branch')])
        with self.assertRaises(ValueError): p.assert_connections([('b','a','Yes branch')])
        self.assertTrue(any('manual route crosses obstacle' in m for m in p.layout_warnings()))
        p.node('overlap',20,20,100,50,id='overlap')
        self.assertTrue(any('overlaps sibling' in m for m in p.layout_warnings()))
        child=p.node('outside',450,0,100,60,parent=a)
        self.assertTrue(any('child extends' in m for m in p.layout_warnings()))
        p.edge(source_point=(10,100),target_point=(20,100))
        self.assertEqual(len(p.connections()),1)
        self.assertEqual(len(p.connections(include_loose=True)),2)

    def test_estimated_label_collisions(self):
        doc=Diagram(); p=doc.page()
        a=p.node('A',0,0,id='a'); b=p.node('B',400,0,id='b')
        p.connect(a,b,'First long label')
        second=p.connect(a,b,'Second long label')
        self.assertTrue(p.label_warnings())
        offset=ET.SubElement(p.cell(second).find('mxGeometry'),'mxPoint',{'x':'0','y':'50','as':'offset'})
        self.assertEqual(p.label_warnings(),[])

    def test_generic_records_and_session_regressions(self):
        insurance=records.build(); p=insurance.pages[0]
        self.assertEqual(len(p.connections()),5)
        p.assert_connections([('Policy','PolicyEditLog',''),('Policy','Bill',''),
            ('Policy','Policy_Coverage',''),('Coverage','Policy_Coverage',''),
            ('Coverage','Vehicle_Coverage','')])
        self.assertEqual(p.label('Coverage'),'')  # no duplicate centered body label
        for table,fields in records.TABLES.items():
            x,y,w,h=p.bounds(table)
            self.assertEqual(h,32+26*len(fields)+4)
            labels=[p.label(k) for k,c in p.cells().items() if c.get('parent')==table]
            self.assertEqual(labels.count(table),1)
            self.assertEqual(p.label(table+':header'),table)
            self.assertEqual(p.label(table+':row:0'),'ID')
            self.assertEqual(p.label(table+':key:0'),'PK')
            self.assertEqual([label for label in labels if label in fields],fields)
            for field in fields:
                self.assertIn(field,labels)
        for connection in p.connections():
            st=p.cell(connection['id']).get('style')
            self.assertIn('startArrow=ERone;',st); self.assertIn('endArrow=ERmany;',st)
        flow=manufacturing.build().pages[0]
        self.assertEqual(len(flow.connections()),18)
        flow.assert_connections([('start','raw',''),('raw','inspect',''),('inspect','materials_ok',''),
            ('materials_ok','reject','No'),('reject','raw',''),('materials_ok','begin','Yes'),
            ('begin','assemble',''),('assemble','initial',''),('initial','initial_ok',''),
            ('initial_ok','rework','No'),('rework','assemble',''),('initial_ok','qc','Yes'),
            ('qc','qc_ok',''),('qc_ok','package','Yes'),('qc_ok','scrap','No'),('scrap','begin',''),
            ('package','ship',''),('ship','end','')])
        self.assertEqual(sum(c['label'] in ('Yes','No') for c in flow.connections()),6)
        for builder in [manufacturing.build,records.build,pools.build,cache.build]:
            doc=builder(); self.assertEqual(doc.validate(),[])
            self.assertEqual(doc.pages[0].layout_warnings(),[])
            self.assertEqual(doc.pages[0].label_warnings(),[])
        cache_page=cache.build().pages[0]
        self.assertEqual(cache_page.label('tag'),'Tag [47:12]')
        self.assertEqual(cache_page.label('index'),'Set index [11:6]')
        self.assertEqual(cache_page.label('offset'),'Byte offset [5:0]')
        pool_page=pools.build().pages[0]
        self.assertEqual(pool_page.cell('compose').get('parent'),'region')
        self.assertEqual(pool_page.cell('region').get('parent'),'factory')
        self.assertEqual(pool_page.cell('create').get('parent'),'scheduling')
        self.assertEqual(sum(k.startswith('cmp') for k in cache_page.cells()),8)
        self.assertEqual(sum(k.startswith('tw') for k in cache_page.cells()),8)
        self.assertEqual(sum(k.startswith('dw') for k in cache_page.cells()),8)
        cache_page.assert_connections([('compare','mshr','no way hits → allocate / merge'),
            ('mshr','done','complete pending requests'),('l2','mshr','refill → resolve MSHRs'),
            ('data','writeback','victim line data')],exact=False)

    def test_python39_syntax(self):
        for path in Path(__file__).resolve().parents[1].rglob('*.py'):
            ast.parse(path.read_text(),feature_version=(3,9))


if __name__ == '__main__':
    unittest.main()
