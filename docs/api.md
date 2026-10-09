# Python API

Optional rendered collision verification is available through `from drawio_native import native_check` or the `native-check` CLI command. See [native checking and fixes](native-check.md) for its dependencies, report schema and usage. Ordinary generation/editing remains independent of the browser.

Import `Diagram`, `style`, `BLOCK`, `EDGE`, `TEXT`, `export_png`, `export_svg` from `drawio_arch` by putting this skill's `scripts` directory on `PYTHONPATH`. All parameters after `*` are keyword-only. IDs are strings scoped to one page. Returned IDs are the handles for later operations. No third-party Python modules are imported.

## Document and page

```python
doc = Diagram()
p = doc.page('Overview', width=1100, height=850, id='overview')
detail = doc.page('Detail', id='detail')
doc.save('/tmp/design.drawio')
doc = Diagram.load('/tmp/existing.drawio')
errors = doc.validate()  # list of messages, empty means structural pass
```

`page(name='Page-1', *, width=1100, height=850, id=None, **attrs)` accepts native mxGraphModel attributes such as `grid='0'`, `background='#ffffff'`. `doc.pages` is an ordered list. `save(path, *, validate=True, pretty=True)` returns a Path; it validates before writing and replaces atomically. Output is indented multiline XML by default; `pretty=False` writes compact XML. Formatting operates on a copy and retains mixed text content and `xml:space="preserve"` subtrees. `validate=False` is an escape hatch for unsupported valid native patterns, not a routine solution for dangling references.

`doc.xml`, `p.diagram`, `p.model`, `p.root` expose ElementTree elements. Unknown XML content and attributes are kept during imports. Any native capability not wrapped below can be added through these elements, then validated and rendered. XML source is not a complete editor automation API.

## Shapes, editable text, styles

```python
box = p.node('FIFO\n16 entries', 40, 80, 180, 70, id='fifo',
             style=style(BLOCK, fillColor='#fff2cc', rounded=1),
             metadata={'protocol': 'AXI-Stream', 'width': '24'})
p.text('Capture pipeline', 40, 10, 700, 40,
       style=style(TEXT, fontSize=24, fontStyle=1))
p.node('Decision', 260, 80, 100, 80, style=style(BLOCK, shape='rhombus'))
```

- `node(label, x, y, width=120, height=60, *, id=None, parent='1', style=BLOCK, metadata=None, **attrs)` creates a native vertex. `**attrs` are native mxCell attributes (`visible`, `connectable`, etc.). Pass a native shape name through style, e.g. `shape=ellipse`, `shape=hexagon`, or a supported `mxgraph.*` name. Library names depend on the installed editor; test unfamiliar ones by rendering.
- `text(label, x, y, width=120, height=30, *, style=TEXT, **kwargs)` is a shape with no fill or outline and editable text.
- `style(base=None, **values)` merges a semicolon style string or a dict; named styles and unknown keys survive. Boolean values become `1`/`0`. Use exact native camelCase names: `fontSize`, `fontColor`, `fillColor`, `strokeWidth`, `dashed`, `endArrow`. `exit`, `entry`, `waypoints`, `source_point`, `target_point`, `routing`, `label_position` and `label_offset` are API arguments, not style keys, and are rejected by `style()` when passed as keyword arguments. Arbitrary other native style keys remain accepted. A `None` value means a named style token with no equals sign; it does not remove the key.
- `BLOCK`, `EDGE`, `TEXT` are default native style strings. Text defaults to `html=0`; labels accept literal Unicode, `&`, `<`, newlines without pre-escaping. For intentional rich text use `html=1` and supply an HTML label; XML escaping remains automatic.
- `metadata={...}` adds a native `object` wrapper. Values are converted to strings. `id` and `label` are managed by the module; do not use them as metadata keys. Use `link='https://...'` or `link='data:page/id,detail'` for hyperlinks/page links. Metadata appears in Draw.io Edit Data.

## Groups, containers, layers

```python
layer = p.layer('Datapath', id='datapath')
group = p.group(40, 80, 300, 180, parent=layer)
a = p.node('Register', 20, 30, 120, 60, parent=group)
cluster = p.container('CPU', 400, 80, 500, 300, parent=layer)
p.node('Rename', 25, 55, parent=cluster)
p.layer('Notes', visible=False, locked=True)
```

`layer(name, *, id=None, visible=True, locked=False)` creates a child of root `0`. The built-in layer `1` remains available. `group(x, y, width, height, *, parent='1', id=None)` creates an invisible group vertex. `container(label, x, y, width, height, *, style=None, **kwargs)` merges supplied styles into a non-collapsible swimlane with a 30-pixel header and top-aligned title; leave child space below its header. All child positions are relative to the full parent's geometry origin. Groups/containers do not automatically resize or fit their children. Set explicit dimensions.

## Ports and bound connectors

```python
out = p.port(a, 'out', 1, .5, size=8)
inp = p.port(b, 'in', 0, .5)
p.edge(out, inp, '32-bit AXI4', id='data')
p.edge(a, b, 'feedback', exit=(.5, 0), entry=(.5, 0),
       waypoints=[(100, 50), (500, 50)], style=style(EDGE, dashed=1))
p.edge(a, b, style=style(EDGE, startArrow='block', endArrow='block'))
p.edge(source_point=(10, 20), target_point=(80, 20),
       style=style(EDGE, edgeStyle='none', endArrow='none'))
```

- `port(parent, name, x, y, *, size=8, id=None, style=None)` creates a relative child vertex with a centered offset. Fractions `(0,.5)`, `(1,.5)`, `(.5,0)`, `(.5,1)` mean W/E/N/S. Bind an edge to the **port ID**. To hide an anchor while retaining it as an endpoint, use an empty name and `style='ellipse;opacity=0;fillColor=none;strokeColor=none;'`; do not set `visible=0` on it.
- `edge(source=None, target=None, label='', *, id=None, parent='1', style=EDGE, waypoints=(), source_point=None, target_point=None, exit=None, entry=None, metadata=None, routing='auto', label_position=0, label_offset=(0,0), **attrs)` creates a bound edge; omitted endpoints require explicit point coordinates. Geometry is relative for edge labels, but waypoints and loose endpoints are in the edge parent's coordinates. Endpoints can be shapes, groups, containers or ports. Keep edges spanning nested containers under their common ancestor layer. `routing='auto'` uses the native router, which may simplify waypoints. `routing='manual'` sets `noEdgeStyle=1` and retains the explicit polyline; the caller is responsible for every corner. `label_position` ranges from -1 (source) to 1 (target), and `label_offset` is pixels. Bad coordinates/anchors fail before adding a cell.
- `exit`/`entry` are `(x_fraction,y_fraction)` with perimeter projection disabled. They constrain attachments to exact locations on the terminal vertex. With visible ports, default perimeter attachment stops at the port circle's outline.
- The default connector is orthogonal with one arrowhead. Use `edgeStyle='none'` for straight or manually segmented paths, `curved=1` for native curved edges, `endArrow='none'` for undirected connections. `jumpStyle='arc', jumpSize=8` shows crossings without implying junctions. Draw explicit junction vertices when links join.
- `edge_label(edge, label, *, position=0, offset=(0,0), id=None, style=TEXT)` adds an editable relative child label. `position` ranges from -1 (source) to +1 (target); offset is pixels. To style the edge's main label use `labelBackgroundColor`, `fontColor`, or raw mxGeometry offsets.

## Deterministic connections and label placement

```python
p.connect(a, b, '32-bit', source_side='E', target_side='W',
          lane=300, label_offset=(0, -12))
p.connect(b, a, 'retry', source_side='N', target_side='N', lane=30)
p.connect(a, b, 'control', source_side='S', target_side='N',
          via=[(100, 300), (500, 300)], label_segment=1,
          label_offset=(0, -12))
p.connect(a, b, source_fraction=.25, target_fraction=.75)
```

`connect(source, target, label='', *, source_side='E', target_side='W', via=None, lane=None, source_fraction=.5, target_fraction=.5, label_segment=None, parent='1', style=EDGE, **kwargs)` is a convenience wrapper around `edge()` with explicit manual geometry and bound endpoints. It accepts edge options such as `id`, `metadata`, `label_offset` and `label_position`.

Sides are `N/E/S/W`; fractions locate the attachment along that side. With no `via`, two horizontal sides get an x lane, two vertical sides get a y lane, and mixed sides get one corner. Same-side connections default to a lane 30 pixels outside both endpoints. Opposite sides use the midpoint. `lane` overrides that coordinate. This is simple geometric composition, **not obstacle avoidance**: plan a route around unrelated blocks yourself. Invalid inward approaches fail with a message to supply outside corners.

`via` supplies **every** orthogonal corner in the edge parent's coordinates. It cannot be combined with `lane`. `connect()` rejects diagonal segments and coincident endpoints. Manual routes remain bound and editable; moving a node keeps the endpoints attached, but you may need to adjust fixed corners after a large move.

`label_segment` is the zero-based index of a leg after duplicate consecutive points are removed, including legs from/to the terminals. It places the main label at that leg's midpoint by setting the native relative arclength position. It cannot be combined with `label_position`. Use pixel `label_offset` to keep text away from the line and other shapes. Segment indexing does not guarantee the text fits the available space; native text layout still needs inspection.

`bounds(id, *, relative_to='1')` returns `(x,y,width,height)` for unrotated vertices, including nested groups and relative ports. `point(id, side='E', *, fraction=.5, relative_to='1')` returns a side point in the requested parent's coordinates. They are geometric rectangle helpers, not stencil perimeter calculations. Rotated cells and edge labels are unsupported. For a rotated/custom perimeter use `edge()` with native perimeter handling rather than these helpers.

## Generic editable records/tables

```python
record = p.table('Control register', [('0x00', 'STATUS'), ('0x04', 'ENABLE')],
                 40, 100, width=280, key_width=70, id='registers')
entity = p.table('Policy', [('PK', 'ID'), ('FK', 'Owner_ID'), ('', 'Active')],
                 400, 100, id='policy')
p.connect(entity, record, style=style(EDGE, startArrow='ERone', endArrow='ERmany'))
```

`table(title, rows, x, y, *, width=280, row_height=26, header_height=32, key_width=44, id=None, parent='1', style=None, header_style=None, text_style=None)` returns the ID of a native group containing a blank rounded body, one header and editable row text in separate key/value columns. Rows are strings or `(key, text)` pairs. Height is calculated as `header_height + row_height * len(rows) + 4`; field names are not squeezed into the key column. All components move with the group. Children have stable IDs `<group>:body`, `<group>:header`, `<group>:key:0` and `<group>:row:0` (zero-based rows); edit a title/field directly with `set_label()` on that ID. A title appears once, in the header; the group's own label is empty. `style`, `header_style`, and `text_style` merge native styles into their respective defaults. The body/header/text children use `connectable=0`; bind relationships to the returned group ID.

There is no automatic PK/FK inference or cardinality assumption in the library. Supply those from the prompt, as the records example does. Native `ERone` and `ERmany` markers display one/many at the source/target respectively; preserve arrow direction relative to the entity IDs. For long field names, increase width or row height; the helper does not measure fonts. The same helper works for register maps, interface lists and software records.

## Topology and conservative geometry checks

`label(id)` reads bare or wrapped cell labels. `connections(*, include_loose=False)` returns dictionaries with `id`, `source`, `target`, and whitespace-normalized `label`, combining the main label and child edge labels. Completely loose edges used for symbol strokes are omitted by default; set `include_loose=True` to include them. Connection IDs and endpoints remain unchanged; it does not collapse ports to parent blocks.

`assert_connections(expected, *, exact=True)` compares `(source_id, target_id, label)` triples, including duplicate counts. It raises ValueError with missing/unexpected triples. Use `exact=False` to assert a required subset. Keep source IDs in your node/connection data; do not search for nodes by wrapped display labels or count root/edge-label cells as blocks.

`layout_warnings()` returns conservative diagnostics for:

- Positive-area overlaps between sibling connectable shapes/groups.
- Ordinary child vertices extending outside a parent; relative boundary ports are allowed.
- Axis-aligned segments of manual edges passing through unrelated connectable shapes/groups. Container ancestors and source/target descendants are excluded; loose component strokes inside an icon are allowed.

Intentional decorative overlays can use `connectable=0`. No warning does **not** certify text fit, rotated geometry, diagonals/curves, stencil perimeters, autorouter output, or arbitrary shape silhouettes. Rectangle checks can over-report when an irregular outline has empty regions. Inspect native renders when available; use warnings as leads, not a visual pass/fail oracle.

`label_warnings()` estimates overlaps between plain-text labels on manually routed edges, including child labels. It uses approximate character widths and line heights; it does not measure fonts, HTML, or text wrapping and does not certify text fitting. Use warnings to choose a different segment or offset.

CLI: `python3 scripts/drawio_arch.py inspect file.drawio` validates structure, prints topology, layout warnings and separate estimated label warnings, and states its coverage. It returns nonzero for structural errors; layout warnings are advisory. `python3 scripts/drawio_arch.py validate file.drawio` remains available for structure only.

## Custom stencils

```python
stencil = '''<shape w="100" h="60" aspect="variable" strokewidth="inherit">
<connections><constraint x="0" y="0.5" perimeter="1" name="in"/>
<constraint x="1" y="0.5" perimeter="1" name="out"/></connections>
<background><rect x="0" y="0" w="100" h="60"/></background>
<foreground><fillstroke/></foreground></shape>'''
p.stencil('Unit', stencil, 40, 80, 160, 70,
          style=style(BLOCK, fillColor='#d5e8d4'))
```

`stencil(label, stencil_xml, x, y, width, height, **kwargs)` embeds a native shape through Draw.io's compressed `shape=stencil(...)` style. It accepts node options. Supply native mxStencil `<shape>` XML: paths, rects, ellipses, curves, text and connection constraints are available in the native syntax. The module checks the root tag, not the full drawing grammar. The network example contains working curved paths. Embedded stencils need no external registration or image. This method does not import arbitrary `.mxlibrary` JSON assets; native installed shape names and raw XML remain available.

## Preserving edits

```python
doc = Diagram.load('/tmp/input.drawio')
p = doc.pages[0]
p.set_label('fifo', 'FIFO\n32 entries')
p.set_style('fifo', fillColor='#d5e8d4')
p.move('fifo', 80, 100, width=200)  # omitted dimensions remain unchanged
doc.save('/tmp/edited.drawio')
```

`p.cells()` maps effective IDs to mxCell elements, including `object` and `UserObject` wrappers. `p.cell(id)` retrieves one. `set_label` edits a wrapper label when present; `set_style` merges native styles. `move(id,x,y,width=None,height=None)` changes geometry fields while retaining offsets, waypoint arrays, alternate bounds and unknown children.

Keep a copy of the input. Inspect IDs, labels and parents to locate the target. Do not regenerate an existing diagram just to relabel a block. Compressed pages are decoded to native XML and saved uncompressed; comments and unknown attributes/elements inside the XML are retained, but whitespace, attribute formatting, and compression are not byte-preserved. Import is for XML `.drawio`/`.xml`, not PNG/PDF files with embedded diagrams.

For advanced edits use ElementTree on the loaded elements. Deleting a container requires handling its descendants and incident edges; deleting a metadata vertex requires removing its wrapper. Reparenting requires converting geometry/waypoints into the new parent's coordinates; do not merely change `parent`. There is no high-level delete, clone, or reparent helper. Compare unaffected elements before/after and render each affected page. Never strip unknown styles or reconstruct wrappers as bare mxCells.

## Structural validation

`doc.validate()` checks page/cell IDs, root `0`, parent existence/cycles, common misplaced edge arguments in styles, finite geometry, nonnegative sizes, vertex/edge geometry, bound terminal existence/type, and explicit loose endpoints. IDs must be unique within their page; edge terminals cannot cross pages. The CLI returns nonzero on errors; `save()` raises ValueError and leaves an existing output untouched.

Validation is deliberately structural. It does not verify stencil grammar, style names, text fitting, port label placement, routing collisions, page bounds, clock semantics or topology specified in natural language. Check those in the script and native render.

## Native PNG export

```python
export_png('/tmp/design.drawio', '/tmp/design.png', page=0,
           scale=1.5, border=10, headless=True)
```

`export_png(source, output, *, page=0, scale=1, border=10, executable='drawio', headless=False, timeout=60, extra_args=())` invokes Draw.io Desktop via an argument list, returns `(width,height)`, verifies a PNG signature/dimensions, and atomically installs the output. Renderer errors/timeouts do not replace an existing PNG. Page selection is **zero-based in this library**, translated to the native CLI's one-based index. A missing binary or headless display helper produces an explicit error. On macOS/Windows pass the installed executable path and keep `headless=False`. Headless Linux needs Xvfb as well as Desktop. Do not install packages unless the task authorizes installation.

CLI equivalent:

```bash
python3 "$SKILL_DIR/scripts/drawio_arch.py" export input.drawio output.png --page 1 --scale 1.5 --headless
```

`extra_args` can pass supported native exporter options such as `--embed-diagram` or `--transparent`. Check the installed Desktop's `--help`; capabilities differ between versions. PNGs can crop to diagram bounds; page width/height in XML remain the editable canvas size. Multi-page files require a separate PNG export per page. Never describe a cropped PNG as exact page-sized output.

## Native SVG export

```python
export_svg('/tmp/design.drawio', '/tmp/design.svg', page=0,
           scale=1.5, border=10, headless=True)
```

`export_svg(source, output, *, page=0, scale=1, border=10, theme='light', executable='drawio', headless=False, timeout=60, extra_args=())` shares the PNG export prerequisites, page indexing, Snap path restrictions and atomic replacement behavior. It returns `(width, height)` in pixels, which can be fractional. It verifies SVG XML, positive finite dimensions, and an adaptive root color scheme when `theme='auto'`. Invalid output, renderer errors, color-conversion failures and timeouts leave an existing destination untouched. Adaptive export requires Draw.io Desktop 26+; an older renderer that emits fixed colors causes an explicit error.

CLI equivalents:

```bash
python3 "$SKILL_DIR/scripts/drawio_arch.py" export input.drawio output.svg --headless
python3 "$SKILL_DIR/scripts/drawio_arch.py" export input.drawio adaptive.svg --theme auto --headless
```

The CLI selects SVG for a `.svg` output (including `.drawio.svg`), otherwise PNG. `--format svg` or `--format png` overrides selection. `--theme auto|light|dark` applies only to SVG and defaults to `light`. The wrapper uses Desktop's compatible `--svg-theme` flag, including on releases before the shared native `--theme` flag was introduced.

The default `theme='light'` resolves every native CSS `light-dark()` pair to its light value, removes `color-scheme` declarations, and paints a white rectangle covering the SVG viewBox. The background is part of the SVG artwork, so it stays white in image previews and renderers that do not support CSS backgrounds. Fixed colors apply to shapes, connectors, gradients, and SVG/HTML labels; ordinary styling, geometry and embedded diagram data are retained. Export never changes the `.drawio` source. This removes unused dark palettes and makes appearance independent of the viewer's theme. `theme='dark'` similarly resolves the dark palette and keeps a transparent background.

Optional `theme='auto'` keeps the background transparent and preserves Draw.io's native `light-dark()` pairs and `color-scheme: light dark`. Hardcoded source hex colors can still receive dark variants unless adaptive colors are disabled on the source page; custom source pairs remain authoritative. [Draw.io's adaptive SVG documentation](https://jgraph.github.io/drawio-github/DARK-MODE.html) describes how the containing page or image supplies the color scheme. VS Code's built-in image preview on Linux follows the system preference independently of the editor theme, so adaptive export does not guarantee switching with the editor theme. SVG background behavior is selected by `theme`; passing `--transparent` via `extra_args` does not remove the default light export's white rectangle.

Native SVG may contain HTML labels (`foreignObject`), so viewers need support for those labels; only adaptive export needs modern CSS color functions. Use `extra_args=['--embed-diagram']` to include editable diagram data; SVG export does not embed it by default. Multi-page sources require one export per page.
