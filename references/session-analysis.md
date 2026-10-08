# Lessons from the supplied sessions

Analyzed the transcripts, final generators, `.drawio` structures and PNGs in `examples/manufacturing`, `examples/l1-cache`, `examples/insurance` and `examples/BPMN`. Source sessions were retained unchanged. Transcript spans include discussion and path corrections, so they are not isolated model-speed benchmarks. Counts below use top-level `## Assistant` and `**Tool:` entries, excluding numbered echoed source lines.

| Session | Recorded span / tool calls | Evidence in the result and transcript | Change driven by that evidence |
|---|---|---|---|
| Manufacturing | 23m 55s / 68 | Image read failed. Turns 10–42 constructed/debugged geometry and SVG parsers: wrong Cartesian-product nesting, regex ownership mistakes, coordinate-origin mismatches, and label/edge ownership confusion. Subsequent topology checks repeatedly failed on label normalization and root/label cell counts. The otherwise readable result was saved under the skill's internal examples, then relocated after user correction. | A bundled topology/geometry inspector, IDs instead of display-label lookup, explicit manual lanes and label placement, honest no-vision fallback, destination resolved against workspace; no new per-task SVG parser. |
| L1 cache | 14m 31s / 29 | Headers initially landed in the wrong place; `waypoints`, `exit`, and `entry` were placed in `style(...)` and silently ignored. Regex patches failed on tuples and multiline calls before a rewrite. Repeated renders fixed routes and labels. The final stored generator still contains `style(..., exit=..., entry=...)`; native XML retains those ineffective keys. The result still shows crowded address/selector geometry, and misses originate from CPU rather than lookup. No MSHR→CPU completion connection is present. | Reject misplaced edge arguments, merge container header defaults, named-side connections and coordinate helpers, editable generator data instead of regex repair, leg-based labels, reserved lanes, explicit miss and refill completion paths in the SoC example. |
| Insurance | 1m 25s / 11 | Fast completion did not imply accuracy: fields run outside fixed-height table bodies, titles appear twice, FK text is squeezed into a narrow column, and `openThin` arrows plus `1:M` are used instead of crow's feet. Output was initially placed in `/tmp/opencode` and needed user-directed relocation. | A generic two-column record/table helper with derived height, blank body and one header; explicit PK/FK column; actual native ERone/ERmany markers; destination passed as an output argument. |
| BPMN-style | 3m 43s / 12 | Good first native render, reusable component symbols, little rework. However pools/activity region are flat background shapes: enclosed tasks are still page children, so moving the region does not move its contents. Agent loaded unrelated verification/detail resources and reconstructed reusable event symbols. | Keep the composition approach; package a relevant pool/symbol recipe with real containment, separate feedback attachment fractions and explicit routed connectors. Avoid reading unrelated recipes or library source before generating. |

The one-line XML came directly from the previous serializer, not from any of these agents. `save()` now formats a copy with two-space indentation and a final newline. It retains literal labels, metadata, comments, mixed XML text and `xml:space="preserve"` content. `pretty=False` remains available when compact output is useful.

## Revised reusable support

The core remains domain-neutral: arbitrary native styles/shapes/XML, editable text, ports, stencils, groups, layers and pages. New helpers are geometric or compositional rather than hard-coded architecture templates:

- `connect()` produces bound manual polylines with named sides, fractions, explicit lanes/corners and labels selected by segment. It rejects inward/diagonal routes early; it does not claim obstacle autorouting.
- `bounds()` / `point()` eliminate repeated nested-coordinate arithmetic.
- `table()` works for hardware register maps/interface inventories as well as ER schemas. PK/FK semantics remain supplied by the caller.
- `connections()` / `assert_connections()` handle IDs, metadata wrappers and child labels without counting root or edge-label vertices as blocks.
- `layout_warnings()` detects supported geometric problems; `label_warnings()` estimates manual-edge label overlaps. Neither replaces a native render or a domain review.

The entrypoint now contains a runnable minimal generator, preserves workspace output paths, routes to only the relevant example, and distinguishes render success from visual inspection. If an image tool is unavailable, agents use existing checks and disclose that limit rather than implementing and debugging a renderer-specific parser. Save already validates structure, so repeated identical validate calls add no confidence.

## Exercised revised examples

| Case | Generator | Editable output / inspected native render | Verified outcome |
|---|---|---|---|
| Manufacturing | [manufacturing.py](../examples/manufacturing.py) | [XML](../examples/output/manufacturing.drawio) / [PNG](../examples/output/manufacturing.png) | 16 semantic nodes, all 18 requested directed connections, six Yes/No branch labels, three outside return loops; indented XML and bound deterministic connectors. |
| L1 cache / SoC | [cache.py](../examples/cache.py) | [XML](../examples/output/l1-cache.drawio) / [PNG](../examples/output/l1-cache.png) | 64-set/8-way/64-B geometry and correct address fields; eight tag ways, comparators and data ways; lookup-originated miss, store-hit update, replacement/victim data, refill and pending-request completion paths. Dense labels were revised using segment placement and an estimator warning, then inspected natively. |
| Insurance | [records.py](../examples/records.py) | [XML](../examples/output/insurance-schema.drawio) / [PNG](../examples/output/insurance-schema.png) | Six tables, all 39 fields in their requested order, separate PK/FK labels, five correctly directed native crow's-foot relations, no Vehicle entity, children within auto-sized groups. |
| BPMN-style | [pools.py](../examples/pools.py) | [XML](../examples/output/bpmn.drawio) / [PNG](../examples/output/bpmn.png) | Native composite timer/message symbols; genuine pool/activity containment; specified rounded Available? task, associations, return label and end events. Distinct bottom anchors keep the scheduling return separate from the outgoing document connection. |

The old saved generators contain 118/153/152/164 lines for manufacturing/cache/insurance/BPMN respectively. Revised corresponding recipes contain 56/72/38/67 lines at the time of this audit. This demonstrates reduced per-diagram mechanics, not a measured speedup across LLMs: no external model benchmark was run. SoC hardware remains the first detailed recipe and the primary guidance; the other cases test generic composition.

## Verification scope

Thirteen standard-library unit tests pass. New regressions cover pretty serialization and unchanged in-memory XML, preserved mixed/xml:space content, fast rejection of misplaced arguments, no partial edge on invalid geometry, nested/relative-port coordinates, manual routes and attachment fractions, label-segment arclength, topology mismatches, real overlaps/route collisions/child overflow, estimated label collisions, complete records, native ER marker styles, and all four revised examples. Existing compression, metadata, stencils, pages, meshes, atomic writes and export checks remain covered.

Generation/tests ran on Python 3.14 with Python 3.9 syntax checks. PNGs were rendered with installed Draw.io Desktop 30.0.4 and inspected. Generated files are standard editable XML; Desktop/Xvfb are optional external rendering tools. Geometry diagnostics intentionally cover rectangles and explicit paths; text measurement, font layout, stencil silhouettes, arbitrary imported geometry and native autorouting remain limited. The cache is a conceptual microarchitecture diagram, not an executable cache implementation or cycle-accurate specification.

To reproduce a revised case without writing any custom parser:

```bash
PYTHONPATH="$SKILL_DIR/scripts" python3 "$SKILL_DIR/examples/manufacturing.py" --output /tmp/manufacturing.drawio
python3 "$SKILL_DIR/scripts/drawio_arch.py" inspect /tmp/manufacturing.drawio
python3 "$SKILL_DIR/scripts/drawio_arch.py" export /tmp/manufacturing.drawio /tmp/manufacturing.png --headless
```

Use the analogous `cache.py`, `records.py`, or `pools.py` script. For ordinary tasks choose the user's requested destination rather than the skill's output gallery.
