# Features, research and verification

## Design decision

Research performed 2026-10-08 using primary sources:

- [Drawpyo](https://github.com/MerrimanInd/drawpyo) provides a broad object/style API and generated diagram types. Its [contribution guide](https://github.com/MerrimanInd/drawpyo/blob/main/CONTRIBUTING.md) describes its TOML compatibility dependency before newer Python versions.
- [N2G DrawIO plugin](https://github.com/dmulyalin/N2G/blob/master/docs/source/diagram_plugins/DrawIo%20Module.rst) provides nodes, links, metadata and imports; its layout option relies on igraph.

A small original module was built rather than vendoring either library: the requested Python 3.9 baseline, zero third-party dependencies, arbitrary parent geometry and conservative XML edits are explicit design goals. No third-party library code is bundled. Familiar node/edge concepts are retained, with native styles and ElementTree access as escape hatches.

Native behavior references: [mxGeometry coordinates and relative geometry](https://jgraph.github.io/mxgraph/docs/js-api/files/model/mxGeometry-js.html), [Draw.io XML source editing](https://www.drawio.com/docs/manual/advanced/diagram-source-edit/), [custom shape XML](https://www.drawio.com/docs/manual/shapes/shape-complex-create-edit/), [Desktop implementation](https://github.com/jgraph/drawio-desktop). Installed Desktop `drawio --help` was also inspected: version 30.0.4 uses one-based `--page-index`, translated from this module's zero-based API.

## Supported features and boundaries

| Feature | Support | Boundary |
|---|---|---|
| Shapes and geometry | Native vertices, arbitrary native shape/style names, explicit pixel dimensions | Simple deterministic doglegs/lane composition via connect(), no obstacle autorouting or shape-name catalog; editor must support a named shape |
| Styles and text | Raw string/dict styles, merge edits, Unicode/newlines, optional HTML, native editable labels | No text measurement; HTML must be intentional |
| Ports | Relative child vertices, visible or transparent anchors | They are native graph vertices, not domain-specific electrical pin objects |
| Connectors | Bound source/target, exact entry/exit anchors, bidirectional/undirected/curved styles | Explicit manual routes, named sides/fractions and segment labels; no automatic congestion avoidance or protocol semantics |
| Waypoints and labels | Native point arrays, loose endpoints, extra relative edge labels | Coordinate conversion across parents is the caller's responsibility |
| Groups and containers | Native group/swimlane parents, nesting, component illustrations | Auto-sized record/table groups available; no general auto-fit, clone, high-level reparent or cascading deletion |
| Layers and pages | Native layers, visibility/lock styles, multiple pages, page hyperlinks | Cross-page bound edges are not supported; render pages individually |
| Custom stencils | Self-contained compressed mxStencil shape styles with curves and constraints | No `.mxlibrary` asset importer; stencil grammar is checked by native rendering |
| Metadata | Native object wrappers, arbitrary string data, link metadata; imported UserObject preserved | Reserved wrapper `id`/`label` managed by module |
| Existing diagrams | Compressed/uncompressed XML import, raw models, targeted edits, comments and unknown content | Output formatting/compression changes; no embedded PNG/PDF import |
| Structural validation | IDs, parents/cycles, finite geometry, terminal references, loose endpoints | Separate conservative bounds/manual-route and estimated-label checks; does not certify visual quality, full native schema, or prompt semantics |
| PNG | Native Desktop export, scale/border/page selection, headless Xvfb option, atomic output | Requires optional external Desktop, and Xvfb on headless Linux; tested exports crop to content |
| Advanced native features | Raw ElementTree and arbitrary cell/model attributes preserve and expose native features | Not every native editor operation has a convenience method |

All generation/editing code and the tests use only Python standard-library imports. Compatibility was checked with Python 3.9's syntax grammar; execution used Python 3.14 in this environment. A Python 3.9 interpreter was not available for a runtime test.

## Executed verification

The original creation checks below are a historical baseline. The current revision adds formatted XML, generic composition helpers and four session-driven regression examples; see [session analysis](session-analysis.md) for current tests and inspected outputs.

The original seven `unittest` tests remain covered in the current thirteen-test suite. They cover full construction and save/load, custom-stencil decoding, metadata wrappers and extra edge labels, compressed imports, conservative edits retaining unknown content/comments/alternate bounds/unaffected pages, invalid geometry and graph references, atomic-save protection, mesh topology across 1×1/4×4/8×8/2×5, example structure, native-export page-number translation and failure preservation, and Python 3.9 syntax parsing. The skill-creator frontmatter validator also passes; it is a development check and is not bundled as a dependency.

Additionally, all 13 supplied `.drawio` files in the repository's original examples loaded and passed structural validation. Saving/reloading each in a temporary directory retained its complete normalized mxGraphModel XML. Original input files were not modified.

The examples use five supplied prompts (copies in [examples/prompts](../examples/prompts/)). The outputs are complete editable XML generated directly with this skill, not an intermediate model/compiler format. These examples were authored and executed with the library; no claim is made that specific inexpensive models were benchmarked. The short copyable workflow, small API and deterministic helper aim to reduce the work those models must perform.

Native PNGs were exported with Draw.io Desktop 30.0.4 and visually inspected:

| Prompt / case | Editable output | Native preview | Evidence and revisions |
|---|---|---|---|
| 03-mesh, 4×4 | [mesh.drawio](../examples/output/mesh.drawio) | [mesh.png](../examples/output/mesh.png) | 16 routers, 24 unique neighbor edges, N/E/S/W ports, bidirectional 128-bit links; regular spacing and readable labels |
| Scaled mesh, 8×8 | [mesh-8x8.drawio](../examples/output/mesh-8x8.drawio) | [mesh-8x8.png](../examples/output/mesh-8x8.png) | 64 routers, 112 neighbor edges, no wraparound or diagonals; repeated layout remains readable |
| 06-cpu-hier, microarchitecture | [cpu.drawio](../examples/output/cpu.drawio) | [cpu.png](../examples/output/cpu.png) | Nested CPU/Front-end/Back-end, staggered BPU/IFU/IQ path, five uop links and dashed ROB feedback; no extra units or inferred widths |
| 08-axi-inter, irregular fanout | [axi_test_system.drawio](../examples/output/axi_test_system.drawio) | [axi_test_system.png](../examples/output/axi_test_system.png) | Bridge stack, four Full destinations, three Lite destinations, unused port3; revised MM2M Full lane to avoid crossing bridge blocks; native jump arcs at unconnected crossings |
| 10-home-network, illustration | [network.drawio](../examples/output/network.drawio) | [network.png](../examples/output/network.png) | Editable 450×680 canvas, six equipment groups, curved globe/router stencils, editable 32px labels, two downward arrows and three undirected device branches; no external images. Main arrows bind to section labels to avoid passing through text |
| 04-hierarchy, capture detail | [detail.drawio](../examples/output/detail.drawio) | [detail-page2.png](../examples/output/detail-page2.png) | Two pages, separate data/clock layers, native page link, 16-bit datapath/mask, custom AND stencil and shared clk_sample fanout; revised clock route to avoid its label |

The content-cropped PNG dimensions are 702×612 (4×4 mesh), 1382×1212 (8×8), 1064×464 (CPU), 964×689 (AXI), 322×627 (network) and 864×514 (capture detail). The `.drawio` page dimensions remain those specified by the generator.

## Reproduce

### Optional native collision checker

The package also includes `native-check`, which uses the installed Draw.io JavaScript renderer in headless Chromium. See [native checking and fixes](native-check.md) for its dependencies and limits. The original thirteen library tests still pass, alongside two browser-independent helper tests and four optional end-to-end native tests. Native tests were executed against the installed Draw.io assets and Chrome: an auto-routed HTML/plain/child-label collision was detected, native offsets cleared it, page selection and hidden-label exclusion passed, an obstacle collision was detected, and source bytes remained unchanged by checking. Additional fixtures verify foreground/background shape ordering, transparent/translucent fills, protected label backgrounds, clearance-only advisories and configurable CLI exit thresholds. These measurements do not constitute visual inspection or certify remote fonts, math typesetting, or diagram semantics.

### Scripted visual reports

`native-check --report-dir <new-directory>` adds numbered findings layers, a JSON artifact manifest and native page PNGs. Report regressions cover source/cell preservation, negative coordinates, severity filtering independent of exit status, selected-page filenames, clean/incomplete results and failure cleanup. With the native-test browser configured and Draw.io Desktop export available, an additional integration test checks a filtered second-page report. The eight-shape, 24-connection experiment was also rendered through the CLI and visually inspected: five warnings, two advisories and one informational finding were correctly numbered and highlighted.

### Conservative native repair

The suite now has 34 tests, all executed successfully with the optional native renderer enabled. New repair tests cover exact offset-only XML preservation (rejecting text, style, terminal, waypoint, position and metadata changes), bounded coupled moves, HTML/child labels, locked labels and selected pages, deterministic dry-run/apply behavior and idempotence, connector barriers, unsupported routes, advisory-only input, candidate budgets, source changes, and failed fresh-render verification. The eight-shape experiment reduced five warnings to one using four label-offset changes; its two advisories and informational overlap were retained. The remaining hidden label could not be safely moved within the default 32-pixel limit. The corrected native PNG and automated findings report were visually inspected. These are specific regression results, not a claim of global optimality or semantic certification. See [repair scope and research](native-fix.md).

### Independent stacking repair

The suite now has 41 tests, all passing with the optional native renderer enabled. Stacking tests cover exact sibling-order-only XML preservation, metadata wrappers, immutable label/shape/route measurements, persistent dry-run/apply behavior, idempotence, warning suggestions, direct child labels, locks, selected pages, and refusal of line exposure, covering other text, crossing-order changes and cross-layer reordering. Geometry guards also cover collinear paths and overlapping stroke/marker bounds.

Applied after offset repair in the eight-shape experiment, `native-stack-fix` raised the edge owning `CG-covered` above shape `C` without changing coordinates, text or styles. Native rechecking confirmed the label is now above the shape, leaving zero warnings, two advisories and two informational findings. The resulting PNG was visually inspected. These bounded checks do not certify diagram semantics or pixel-perfect appearance. See [stacking repair scope](native-stack-fix.md).

### Original examples

From the skill directory:

```bash
python3 -m unittest discover -s tests -v
python3 examples/generate.py --output-dir /tmp/drawio-demo
python3 examples/generate.py --rows 8 --cols 8 --output-dir /tmp/drawio-large
python3 examples/detail.py /tmp/drawio-demo/detail.drawio
python3 scripts/drawio_arch.py validate /tmp/drawio-demo/axi_test_system.drawio
python3 scripts/drawio_arch.py export /tmp/drawio-demo/axi_test_system.drawio /tmp/drawio-demo/axi_test_system.png --headless
python3 scripts/drawio_arch.py export /tmp/drawio-demo/detail.drawio /tmp/drawio-demo/detail-page2.png --page 1 --headless
```

Drop `--headless` when a display is available. In an environment requiring Electron's `--no-sandbox` flag, add it to these export commands. Generation, editing and tests work without Desktop or Xvfb.
