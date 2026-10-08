---
name: drawio-python-arch
description: Generate and edit editable Draw.io diagrams with a bundled Python standard-library API. Use for SoC hardware architecture, microarchitecture, flowcharts, schemas, swimlanes, networks and native-shape illustrations. Includes deterministic connections, records, structural checks and optional native PNG export.
---

# Draw.io with Python

Use `scripts/drawio_arch.py`; no pip install is needed. Deliver native editable cells and text. `save()` writes indented, multiline XML and validates it before replacing a file.

Requires Python 3.9+ and a local filesystem. Generation and editing need no third-party Python packages or network access. Optional PNG export requires Draw.io Desktop; headless Linux export also requires Xvfb.

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
- Existing diagrams, stencils or advanced options: read the relevant section of [API reference](references/api.md).

These are patterns, not required layouts. Read only the relevant example. For a new diagram, the starting point above usually needs no library-source inspection.

## Place and connect

Ordinary geometry is in pixels relative to the parent's top-left. Ports use fractions in `[0,1]`. `p.bounds(id)` and `p.point(id, 'E')` compute positions across nested parents. Put connections spanning containers on a common ancestor layer; express all corners in that edge parent's coordinates.

`p.connect()` binds endpoints, chooses a simple orthogonal dogleg, and preserves the explicit polyline. Use `lane=...` for an outside return lane, or `via=[(x,y), ...]` for **every** turn on a longer path. It checks orthogonality and that the route approaches the chosen sides from outside. It does not avoid obstacles automatically. Use different attachment fractions/lane coordinates for different signals. On a long connector, `label_segment=...` selects a leg for its label; `label_offset=(dx,dy)` leaves space from the line.

Reserve corridors before wiring dense SoC diagrams. Keep data/control/clock paths distinguishable; label only specified widths/protocols. Represent misses as a result of lookup, include both victim data and replacement control, and show refill completion when requested. A connected picture still needs a check against the prompt's actual semantics. For BPMN-style requests, preserve specified shapes even when they differ from strict BPMN. For ER cardinality, use native `ERone`/`ERmany` markers; a label `1:M` on an ordinary arrow is insufficient.

## Check and finish

```bash
python3 "$SKILL_DIR/scripts/drawio_arch.py" inspect /absolute/user/workspace/design.drawio
python3 "$SKILL_DIR/scripts/drawio_arch.py" export /absolute/user/workspace/design.drawio /absolute/user/workspace/design.png --headless
```

`save()` already checks structure. `inspect` reports connections by ID and conservative bounds/manual-route warnings and estimated edge-label overlaps. For specified topology, use `p.assert_connections([(source_id, target_id, label), ...])`; child edge labels are included. These helpers avoid writing a new XML/SVG checker for each diagram.

PNG export uses optional Draw.io Desktop. `--headless` also needs Xvfb; omit it with a working display. Use `--no-sandbox` only when the execution environment requires Electron's flag. Library `--page 0` means the first page. PNGs crop to content on the tested Desktop version.

If image viewing is available, inspect one native render, fix concrete defects, and re-render affected pages. If the model/tool cannot view images, use the bundled checks and report that visual inspection was unavailable. Do not repeatedly retry an unsupported image tool or build a bespoke SVG parser to claim visual verification. Bounds checks do not measure text or reproduce native autorouting. Once required topology and available checks pass and observed defects are fixed, deliver the files at the requested path.

## Preserve edits

Use `Diagram.load(path)`, then `set_label`, `set_style`, or `move` on intended IDs. Preserve unrelated pages, cells and metadata; save to a new path unless overwrite is requested. The API exposes raw ElementTree/native styles for other capabilities. Read [editing details](references/api.md#preserving-edits) before deleting/reparenting content. Formatting is not byte-preserved; mixed XML content and `xml:space` subtrees are retained.

[Session analysis and revised examples](references/session-analysis.md) records why these helpers exist; [verification](references/verification.md) records supported features and limits.
