# Native label collision checks

Use this optional check for dense wiring, suspected label collisions, HTML/wrapped text, native autorouting, or in-depth verification requested by the user. It complements structural validation and visual inspection.

## Requirements

- Chromium or Google Chrome, running headless; no Python or Node packages are needed.
- Installed Draw.io Desktop assets, or a local Draw.io `src/main/webapp` directory containing its built JavaScript bundles.

The helper discovers Chromium/Chrome on `PATH` and Draw.io `resources/app.asar` in common installation paths. Otherwise provide `--browser`, and either `--drawio-asar` or `--drawio-webapp`. macOS users can specify `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome` as the browser. All assets are local; the checker does not download dependencies or connect to a user's editor/browser session. It extracts installed ASAR assets into a temporary directory and launches a temporary browser profile. No Xvfb is needed.

```bash
python3 "$SKILL_DIR/scripts/drawio_arch.py" native-check /absolute/path/design.drawio > /tmp/design-native-report.json
```

Explicit paths, when autodetection is unavailable:

```bash
python3 "$SKILL_DIR/scripts/drawio_arch.py" native-check /absolute/path/design.drawio \
  --browser /path/to/chromium \
  --drawio-asar /path/to/drawio/resources/app.asar
```

`--page 0` checks the first page; omitting it checks all pages. `--padding 2` requests two pixels of clearance between bounding rectangles; use `--padding 0` to detect strict intersections. The default wall-clock timeout is 60 seconds. Use `--no-sandbox` only when the execution environment requires that Chromium flag.

Exit codes: **0** means no warnings or unmeasured visible labels at the selected threshold; **1** means warnings or incomplete label measurement need review; **2** means verification failed or a prerequisite is unavailable. Advisories and informational findings remain in the JSON even when the exit code is 0. Add `--fail-on advisory` to make advisories also cause exit 1. The JSON error on failure must not be treated as a successful check. The source file is never modified.

## Read the report and fix

Each page reports:

- `labels`: cell IDs, owning edge IDs, text, and measured bounds in diagram pixels at scale 1. Child labels keep their own cell IDs.
- `shapes`: vertex IDs and rectangular geometry bounds.
- `collisions`: `label-label` or `label-shape`, the two IDs `a` and `b`, the intersection rectangle including requested clearance, plus `severity` and `reason`. At least one label belongs to an edge. Node-to-node label overlaps are outside this check's scope.
- `summary`: counts of `warning`, `advisory`, and `info` findings per page.
- `unmeasured_labels`: visible labels for which the renderer did not supply usable bounds. These prevent a clean result.

Findings are classified conservatively:

| Severity | Cases | Agent action |
|---|---|---|
| `warning` | Actual label bounding boxes intersect; or sampled browser hit testing finds an opaque shape painted above a label | Review, then fix an unintended conflict |
| `advisory` | Clearance-only proximity; label above a shape without an opaque background; translucent foreground shape; uncertain paint order | Inspect readability/context before considering a change |
| `info` | Label is above the shape and has an opaque native label background | Usually retain the placement |

Label-shape findings also provide `paint_order`, `shape_fill_alpha`, and `label_background_alpha`. Paint order is sampled using browser hit testing, including separate HTML label panes; it is not inferred from XML cell order. Fully transparent fills are excluded. A background protects a label only when it is painted above the overlapping shape.

Do not automatically move labels for advisory or informational shape overlaps. Do not treat a warning as proof that an intentional overlap is wrong. Locate the reported IDs in the generator or diagram and review the finding before changing it. Prefer revising the authoritative generator:

```python
p.connect(a, b, 'Request', id='request', label_offset=(0, -18))
p.connect(a, b, 'Response', id='response', label_offset=(0, 18))
```

Move text with `label_offset=(dx,dy)` on `edge()`/`connect()`, or `offset=(dx,dy)` on `edge_label()`. Negative `dy` moves up. Use `label_position` to shift along the edge, or `label_segment` with `connect()` to select a longer leg. If the route itself needs room, revise its attachment fractions or lanes. Do not change topology to resolve a label collision.

For an existing diagram, the native label offset can be changed through the exposed XML API without altering its route:

```python
import xml.etree.ElementTree as ET
from drawio_arch import Diagram

doc = Diagram.load(source)
geo = doc.pages[0].cell('request').find('mxGeometry')
point = geo.find("mxPoint[@as='offset']")
if point is None:
    point = ET.SubElement(geo, 'mxPoint', {'as': 'offset'})
point.set('x', '0')
point.set('y', '-18')
doc.save(destination)
```

Save to a new destination unless overwrite is requested. Re-run native checking on affected pages after a concrete fix; inspect a PNG when available. Avoid an unbounded search over offsets: if two targeted revisions do not resolve the findings, inspect the rendering and reconsider spacing or label placement. Report any intentional or unresolved overlaps and any unavailable verification.

## Limits

This uses Draw.io's `Graph` renderer and its `state.text.boundingBox`, not estimated font widths. It measures plain text, HTML labels, extra edge labels and native routed connections. Labels are tested against other labels and filled vertex rectangles; containing ancestors are excluded to avoid treating an edge's pool/group as an obstacle.

Rectangle intersections and sampled paint order flag potential issues, not pixel-level proof: rotated text and nonrectangular shapes can produce false positives, and unfilled shapes are excluded. Missing/contradictory hit-test evidence remains advisory rather than being promoted to an occlusion warning. Opacity checks use native fill/label background colors and style alpha; complex HTML backgrounds, gradients, images, masks and blending are not certified. Only visible cells are checked; hidden layers and collapsed descendants are excluded. Fonts come from the local browser/system and available local resources, so unavailable remote fonts can fall back. Remote images/fonts and math typesetting are not verified. This does not check line-to-label intersections, shape overlap, clipping, text fitting, or semantic correctness. The optional checker does not replace the existing structural/layout checks or visual review.

Renderer sources: [mxCellState label bounds](https://jgraph.github.io/mxgraph/docs/js-api/files/view/mxCellState-js.html), [Draw.io native export page](https://github.com/jgraph/drawio/blob/dev/src/main/webapp/export3.html). Draw.io's own `mxEdgeLabelLayout` handles label-to-vertex avoidance; our checker also compares edge-label rectangles with one another.

## Development verification

Normal tests require no browser. To run the end-to-end checks against installed assets:

```bash
DRAWIO_NATIVE_TEST_BROWSER=/path/to/chromium \
  python3 -m unittest discover -s "$SKILL_DIR/tests" -v
```

Optional environment variables: `DRAWIO_NATIVE_TEST_ASAR`, `DRAWIO_NATIVE_TEST_WEBAPP`, and `DRAWIO_NATIVE_TEST_NO_SANDBOX=1` where needed. The tests reproduce a collision on auto-routed HTML/plain/child labels, fix it via native offsets, verify multipage selection and hidden-label exclusion, detect a label over an obstacle, and verify source preservation. They also verify paint-order/transparency/background classifications and that clearance-only advisories leave the default CLI exit code at 0 while `--fail-on advisory` returns 1.
