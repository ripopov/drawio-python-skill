---
name: drawio-python-arch
description: Generate and edit editable Draw.io diagrams with a bundled Python standard-library API. Use for SoC hardware architecture, microarchitecture, flowcharts, schemas, swimlanes, networks and native-shape illustrations. Includes deterministic connections, records, structural checks, optional PNG and SVG export, native label collision verification and conservative label repair.
---

# Draw.io with Python

Use `scripts/drawio_arch.py`; no pip install is needed. Deliver native editable cells and text. `save()` writes indented, multiline XML and validates it before replacing a file.

Requires Python 3.9+ and a local filesystem. Generation and editing need no third-party Python packages or network access. Optional PNG/SVG export requires Draw.io Desktop (26+ for adaptive SVG); headless Linux export also requires Xvfb.

Optional native label collision checking requires local Draw.io assets and Chromium/Chrome. It uses browser-measured text bounds and needs no extra Python packages.

## Generate

Resolve `SKILL_DIR` from this `SKILL.md`. Resolve the **user's output path against their workspace directory**, before changing directories. The skill directory supplies the module/examples; ordinary deliverables belong in the user's destination. Write a temporary generator outside the skill. Run it with:

```bash
PYTHONPATH="$SKILL_DIR/scripts${PYTHONPATH:+:$PYTHONPATH}" python3 /tmp/make_diagram.py --output /absolute/user/workspace/design.drawio
```

Copy and adapt this complete starting point:

```python
from argparse import ArgumentParser
from pathlib import Path
from drawio_arch import Diagram, style, BLOCK, EDGE

parser = ArgumentParser()
parser.add_argument('--output', required=True)
out = Path(parser.parse_args().output).resolve()
doc = Diagram()
p = doc.page('Datapath', width=900, height=450)
a = p.node('CPU', 40, 100, 160, 70, id='cpu')
b = p.node('Interconnect', 340, 100, 180, 70, id='bus')
p.connect(a, b, 'AXI4', source_side='E', target_side='W',
          label_offset=(0, -12), style=style(EDGE, labelBackgroundColor='#ffffff'))
doc.save(out)
```

Creation methods return string IDs. Use descriptive IDs for meaningful blocks. Define repeated nodes/connections as data or loops; keep one generator authoritative and revise its coordinates directly.

**Arguments:** `exit`, `entry`, `waypoints`, `routing`, `label_position`, `label_offset` belong in `p.edge(...)`. Native colors/fonts/arrows belong in `style(...)`. The library rejects the common mistake `style(exit=(...), waypoints=[...])` instead of silently drawing a different route.

## Choose the relevant pattern

- SoC datapaths, caches, buses: [cache.py](examples/cache.py), [mesh/CPU/AXI examples](examples/generate.py).
- Decisions and outside return loops: [manufacturing.py](examples/manufacturing.py).
- Register maps, interfaces, ER records: use `p.table(title, rows, x, y)`; see [records.py](examples/records.py).
- Pools and composite symbols: [pools.py](examples/pools.py).
- Existing diagrams, stencils or advanced options: read the relevant section of [API reference](docs/api.md).

These are patterns, not required layouts. Read only the relevant example. For a new diagram, the starting point above usually needs no library-source inspection.

## Place and connect

Ordinary geometry is in pixels relative to the parent's top-left. Ports use fractions in `[0,1]`. `p.bounds(id)` and `p.point(id, 'E')` compute positions across nested parents. Put connections spanning containers on a common ancestor layer; express all corners in that edge parent's coordinates.

`p.connect()` binds endpoints, chooses a simple orthogonal dogleg, and preserves the explicit polyline. Use `lane=...` for an outside return lane, or `via=[(x,y), ...]` for **every** turn on a longer path. It checks orthogonality and that the route approaches the chosen sides from outside. It does not avoid obstacles automatically. Use different attachment fractions/lane coordinates for different signals. On a long connector, `label_segment=...` selects a leg for its label; `label_offset=(dx,dy)` leaves space from the line.

Reserve corridors before wiring dense SoC diagrams. Keep data/control/clock paths distinguishable; label only specified widths/protocols. Represent misses as a result of lookup, include both victim data and replacement control, and show refill completion when requested. A connected picture still needs a check against the prompt's actual semantics. For BPMN-style requests, preserve specified shapes even when they differ from strict BPMN. For ER cardinality, use native `ERone`/`ERmany` markers; a label `1:M` on an ordinary arrow is insufficient.

## Check and finish

```bash
python3 "$SKILL_DIR/scripts/drawio_arch.py" inspect /absolute/user/workspace/design.drawio
python3 "$SKILL_DIR/scripts/drawio_arch.py" export /absolute/user/workspace/design.drawio /absolute/user/workspace/design.png --headless
python3 "$SKILL_DIR/scripts/drawio_arch.py" export /absolute/user/workspace/design.drawio /absolute/user/workspace/design.svg --headless
```

`save()` already checks structure. `inspect` reports connections by ID and conservative bounds/manual-route warnings and estimated edge-label overlaps. For specified topology, use `p.assert_connections([(source_id, target_id, label), ...])`; child edge labels are included. These helpers avoid writing a new XML/SVG checker for each diagram.

For dense diagrams, suspected label collisions, or requested in-depth verification, read [native checking and fixes](docs/native-check.md). Run `python3 "$SKILL_DIR/scripts/drawio_arch.py" native-check /absolute/user/workspace/design.drawio` when its optional prerequisites are available. It reports measured overlaps by cell ID with severity and reasons, considering sampled paint order, fill opacity and label backgrounds. Review warnings, revise `label_offset`, label position/segment, or route spacing for unintended conflicts, and re-check affected pages. Do not automatically move readable labels for advisory/informational shape overlaps. Exit 0 can still include advisories; a failed renderer or unmeasured label is not a clean verification result. This check is read-only and does not replace visual inspection.

For a visual findings report, add `--report-dir /absolute/user/workspace/design-report` (a new directory). This scripts the entire check, JSON report, editable findings layer, and PNGs with numbered ovals colored by severity; do not write a custom annotation script. PNGs additionally require Draw.io Desktop, with `--headless` for Xvfb on headless Linux. Optional `--highlight warning,advisory` filters visual annotations while JSON and exit status still include all findings. Inspect or fix the source diagram, not the annotated report copy.

For requested overlap fixes, use `native-fix design.drawio` for a verified dry-run or add `--output design-fixed.drawio` to produce a new file. Read [conservative automatic repair](docs/native-fix.md) first. It adjusts only connection-label offsets, preserves text/styles/routes/topology, and rechecks the serialized output. Use `--keep ID` for intentionally placed labels or `--only ID` to narrow repairs. Its bounded search can leave warnings unresolved; do not automatically increase movement limits. Transfer accepted `changes` into the authoritative generator's `label_offset` (or child label `offset`) so regeneration retains the repairs. Visual review still checks meaning and label association.

For `possible-label-occlusion` warnings, consider the separate `native-stack-fix design.drawio` first; the warning includes this suggestion. Read [stacking-only repair](docs/native-stack-fix.md). It keeps label positions/styles fixed and tests a minimal reorder of the owning edge above a sibling shape. Use `--output design-stacked.drawio` to apply to a new file. Reordering also raises the line, so the fixer rejects unsafe crossings/obscuration and cross-layer cases. Neither fixer invokes the other.

Image export selects SVG for a `.svg` output, otherwise PNG; `--format svg` or `--format png` overrides this. SVG defaults to a fixed light palette on an opaque white background, with embedded theme CSS resolved to plain colors so the diagram looks the same in light and dark system themes. Python callers can use `export_svg(...)` or `export_svg(..., theme='light')`.

Use `--theme auto` (Python: `theme='auto'`) only when adaptive SVG is requested; this keeps the background transparent and preserves Draw.io's light/dark color pairs. Hardcoded hex colors on shapes and labels still receive dark-mode variants in adaptive SVG export unless the source diagram explicitly disables adaptive colors. Adaptive SVG follows the viewer's CSS color scheme; VS Code's built-in preview on Linux follows the system preference rather than the selected editor theme. `--theme dark` exports fixed dark colors on a transparent background. Export does not change source page settings.

PNG/SVG export uses optional Draw.io Desktop. `--headless` also needs Xvfb; omit it with a working display. Use `--no-sandbox` only when the execution environment requires Electron's flag. Library `--page 0` means the first page. Images can crop to content. Both exporters validate the native output before atomically replacing the destination; failed exports preserve existing files.

If image viewing is available, inspect one native render, fix concrete defects, and re-render affected pages. If the model/tool cannot view images, use the bundled checks and report that visual inspection was unavailable. Do not repeatedly retry an unsupported image tool or build a bespoke SVG parser to claim visual verification. Bounds checks do not measure text or reproduce native autorouting. Once required topology and available checks pass and observed defects are fixed, deliver the files at the requested path.

## Preserve edits

Use `Diagram.load(path)`, then `set_label`, `set_style`, or `move` on intended IDs. Preserve unrelated pages, cells and metadata; save to a new path unless overwrite is requested. The API exposes raw ElementTree/native styles for other capabilities. Read [editing details](docs/api.md#preserving-edits) before deleting/reparenting content. Formatting is not byte-preserved; mixed XML content and `xml:space` subtrees are retained.

See [verification scope](docs/verification.md) for check coverage and development commands.
