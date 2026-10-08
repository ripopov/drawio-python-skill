# Conservative automatic label repair

Use when overlap repair is requested, or to finish an authorized diagram-generation task with unintended label collisions. Run it on the original diagram, not an annotated report copy. Requirements match `native-check`: local Draw.io assets plus Chromium/Chrome, with no third-party Python packages. Draw.io Desktop export and Xvfb are only needed for optional preview PNGs.

For a label hidden by an opaque shape, first consider the independent [stacking-only fixer](native-stack-fix.md), which preserves the label position. This offset fixer never changes stacking order and never invokes the stacking fixer automatically.

## Commands and outputs

```bash
# Fully verified dry-run; source remains unchanged
python3 "$SKILL_DIR/scripts/drawio_arch.py" native-fix design.drawio > repair.json

# Apply to a NEW destination; never overwrite input or an existing output
python3 "$SKILL_DIR/scripts/drawio_arch.py" native-fix design.drawio \
  --output design-fixed.drawio > repair.json

# Restrict repair to one connection label, protecting another intentional placement
python3 "$SKILL_DIR/scripts/drawio_arch.py" native-fix design.drawio \
  --only request --keep response --output design-fixed.drawio
```

`--only` selects exact label cell IDs (including child labels); `--keep` freezes a label, or all labels of an edge. Both are repeatable. IDs apply across selected pages; `--page 0` narrows to the first page. Unknown IDs are errors. Renderer options are `--browser`, `--drawio-asar` / `--drawio-webapp`, `--padding`, `--timeout`, and `--no-sandbox` only where required.

Defaults: total displacement at most **32 px per label**, **160 candidate renders per page**, **3 passes**. Options are `--max-move` (ceiling 128), `--max-attempts` (ceiling 2000), and `--max-passes` (ceiling 10). These are budgets, not quality guarantees. Do not automatically raise movement limits when a local fix fails; inspect spacing and intent first. Timeout applies separately to candidate search and final verification.

JSON contains source/output paths and SHA-256 hashes, `mode`, `status`, options, page search budgets/results, skipped-label reasons, `before`/`after` native reports, and `changes` with page index, label ID, owning edge ID, old/new absolute offsets and total displacement. A successful verification records `preservation: passed` and `native_recheck: passed`. In a dry-run, `after` describes the verified temporary candidate; the source is unchanged.

Exit codes:

- **0**: no warnings or unmeasured labels remain on checked pages. Advisories/info may remain; this is not certification of semantics or appearance.
- **1**: unresolved warnings or incomplete measurements remain. Safe partial improvements are still published when `--output` is supplied.
- **2**: invalid input/options, unavailable renderer, preservation/recheck failure, or output conflict. No candidate is published.

Output is staged and atomically published without replacing an existing path. A source-content change during repair aborts publication. A no-change result can write a byte-identical copy to a new destination.

## Preservation and selection rules

The only permitted edit is `x`/`y` on `mxGeometry/mxPoint[@as='offset']` for an eligible edge text label. An offset point is added only when needed. Label text, native style strings, arrows, fonts, colors, backgrounds, node bounds, label position along the connection, parent/group/layer membership, ports, terminals, routing points, cell order and metadata remain unchanged. All pages are retained. XML serialization/compression can change; the entire parsed document is compared against the source with exactly the declared offsets applied. Unknown XML and metadata remain part of that comparison.

Only warning-level conflicts trigger movement. Advisory/informational findings are not repair targets. Native `locked=1`, `movable=0`, `labelMovable=0`, or `autofix=0` on a label/edge/ancestor prevents movement. Use `--keep` for protected placements without modifying the file.

Candidates use measured native bounds, clearance-derived displacements and short axis/perpendicular offsets. They are deterministic; scoring prefers fewer warnings, then fewer remaining findings, then smaller displacement. A bounded coupled search can move both conflicting labels when neither can succeed alone. Every accepted step strictly reduces warnings; paired moves are accepted together. Movement budgets are measured from the original input, so repeated passes cannot accumulate unbounded drift.

Each candidate must retain the same carrier segment and established side of its connection, remain near that segment, stay inside previously containing ancestors, introduce no new shape overlap or connector crossing, and avoid becoming closer to another connection when that association was previously clear. Native routes, visible-label identity, and measured sizes must remain stable. New collision pairs and severity increases are rejected; an existing warning can become a lower-severity finding. The resulting file is independently reloaded and rendered in a fresh browser before delivery.

## Conservative limits

- Node labels and structural edge children/ports never move. Direct, zero-size child text labels are supported. Labels with descendants are frozen because their movement may affect other content.
- Rotated/directional text, noncentral label positions, image/SVG/math labels and unsupported geometry are skipped. A page with unmeasured visible labels or unsupported curved/rounded/custom connector paths is left unchanged: its obstacles cannot be assessed reliably by the polyline guard.
- Shapes use conservative rectangles. Nonrectangular symbols or intentional overlays can prevent a fix even when a human sees available space.
- The search is local and bounded, not a globally optimal layout solver. A safe partial result is preferable to changing routes, shrinking fonts, rewriting text or moving boxes.
- Preserving XML semantics cannot prove that a human will read every label correctly. The distance/side/carrier guards reduce association risk; visual inspection and the native checker's font/HTML/paint-order limitations still apply.

For a generated diagram, apply each receipt's `after` offset to its authoritative generator (`label_offset=(dx, dy)` on `edge`/`connect`, or `offset=(dx, dy)` on `edge_label`), then regenerate and check. Offsets are absolute replacements, not deltas. The fixer does not rewrite Python code.

Inspect the repaired output, optionally producing the existing automated visual report:

```bash
python3 "$SKILL_DIR/scripts/drawio_arch.py" native-check design-fixed.drawio \
  --report-dir design-fixed-report --headless
```

## Implementation research

Reviewed public implementations on 2026-10-09. Our implementation is original and uses the existing native browser checker; no third-party repair code is bundled.

- [product-swimlane-drawio label planner](https://github.com/zz-zed/product-swimlane-drawio/blob/main/skills/product-swimlane-drawio/scripts/swimlane_core/labels.py) uses finite label candidates, frozen placements, conflict checks and bounded pair reconsideration. Its [repair module](https://github.com/zz-zed/product-swimlane-drawio/blob/main/skills/product-swimlane-drawio/scripts/swimlane_core/review_repair.py) verifies a protected document projection. These motivated coupled search, explicit bounds and whole-document preservation checks here. Its managed swimlane schema and geometry model are not dependencies.
- [Agents365 edgeports.py](https://github.com/Agents365-ai/drawio-skill/blob/main/skills/drawio-skill/scripts/edgeports.py) offers deterministic endpoint spreading and preserves pinned ports. Endpoint reassignment was deliberately excluded here because the requested repair must preserve routes and diagram intent.
- [BTP autofix.py](https://github.com/marianfoo/btp-drawio-skill/blob/main/plugins/sap-architecture/skills/sap-architecture/scripts/autofix.py) offers dry-run mechanical cleanup. Its style normalization/grid snapping was excluded: existing styles and geometry are protected in this fixer.
