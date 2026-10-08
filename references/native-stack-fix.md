# Independent stacking-only repair

Use for `possible-label-occlusion`: native hit testing found an opaque shape painted above an edge label. The checker adds a `message` and `suggested_fix` pointing here. Stacking repair is separate from `native-fix` (offset repair); neither calls the other. Advisory/info overlaps and label-label collisions are not stacking targets.

```bash
# Verified dry-run; no diagram output
python3 "$SKILL_DIR/scripts/drawio_arch.py" native-stack-fix design.drawio

# Apply to a NEW file, optionally limited to a specific label
python3 "$SKILL_DIR/scripts/drawio_arch.py" native-stack-fix design.drawio \
  --only signal --output design-stacked.drawio
```

Requires the same local Draw.io assets and Chromium/Chrome as `native-check`. Renderer flags (`--browser`, `--drawio-asar` / `--drawio-webapp`, `--padding`, `--timeout`, `--no-sandbox` where required) are unchanged. No Desktop/Xvfb dependency unless exporting a preview. `--page 0` restricts checking to the first page. `--only ID` selects a label; `--keep ID` protects a label, owning edge, crossed cell or ancestor. Both repeat. Native lock/movement/autofix flags are honored. The candidate-render budget is 32 per run (`--max-attempts`, range 1–128).

## What changes

Draw.io's main edge label belongs to the edge cell. Raising that cell raises its line as well. This fixer moves the **owning edge** just after the covering sibling shape in the native model order. It retains the same parent/layer and never moves groups/layers, detaches labels, creates copies, changes text, changes styles/backgrounds, or adjusts coordinates/offsets/routes. Direct zero-size text children can be raised with their owning edge; structural or protected children block the repair.

The whole parsed XML is compared against the source with exactly the reported reorder operations applied, including wrappers, metadata and child order. Serialization/compression can change. Only native sibling stacking order may differ. After saving and reopening, native checking must confirm unchanged routes, shape bounds, labels and label bounds, no new/worsened collision, and the target label painted above its covering shape.

## When a reorder is refused

The safety checks cover every sibling the edge would pass, not just the reported covering shape:

- Different parents/layers, protected cells, composite crossed cells or unsupported geometry are skipped.
- The raised line must not pass through a crossed shape's interior or another label's bounds.
- Crossed connection paths must be supported and disjoint, so their crossing/overlap order is not changed. Overlapping native visual bounds are also refused conservatively to account for stroke and arrowhead extents. Jump styles are excluded.
- Raised label bounds must not overlap other text or crossed connections. A label over a crossed shape must be one of the known occlusion findings and fit inside a supported rectangular shape with a margin from its outline.
- Unmeasured labels, curved/rounded/custom affected routes, and nonrectangular/rotated crossed shapes are conservative exclusions.

These rectangle/polyline guards and native hit tests are not a pixel-perfect proof of appearance. A refusal leaves the diagram intact and records a reason; it does not fall back to moving text or altering styles. Review intentional overlap and rendered label association as usual.

## Receipt and exit status

JSON contains `changes` (page, edge, label, parent, covering shape and crossed sibling IDs), skipped reasons, attempted native renders, source/output hashes, before/after reports and preservation/recheck results. The source stays untouched. `--output` publishes a new file only after final verification; existing paths are never overwritten, and a changed source aborts publication.

- **0**: opaque-label occlusion targets are cleared and measurement is complete on checked pages. Other warnings may remain: see `remaining_warnings` and run the ordinary checker.
- **1**: occlusions or unmeasured labels remain. Verified partial stacking improvements are still written if an output was requested.
- **2**: invalid input, unavailable/failed renderer, preservation/final verification failure or output conflict. No candidate is published.

Candidate rechecks that reveal unsafe visual changes are rejected and recorded while preserving the last accepted candidate. The final saved artifact receives another native check before publication.

For a generated diagram, preserve the accepted order in the authoritative generator: after creating all cells, move the whole edge XML element (or its metadata wrapper) immediately after the reported sibling. Keep its `parent` unchanged. The fixer does not rewrite Python. Verify the regenerated diagram before delivery.

To combine the independent fixers explicitly, use distinct files:

```bash
python3 "$SKILL_DIR/scripts/drawio_arch.py" native-stack-fix design.drawio --output stacked.drawio
python3 "$SKILL_DIR/scripts/drawio_arch.py" native-fix stacked.drawio --output fixed.drawio
python3 "$SKILL_DIR/scripts/drawio_arch.py" native-check fixed.drawio --report-dir fixed-report --headless
```

Inspect each command's JSON/exit status. A partial result may still be useful input to the next stage, while a failed invocation produces no output.
