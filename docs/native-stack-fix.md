# Stacking-only repair

Targets only `possible-label-occlusion`: an opaque shape painted above an edge label. These warnings suggest `native-stack-fix`. Requirements and renderer flags match [native checking](native-check.md); this command is independent of [offset repair](native-fix.md).

```bash
# Verified dry-run; add --output to save a new file
python3 "$SKILL_DIR/scripts/drawio_arch.py" native-stack-fix design.drawio
python3 "$SKILL_DIR/scripts/drawio_arch.py" native-stack-fix design.drawio --only signal --output stacked.drawio
```

`--only ID` selects labels; `--keep ID` protects labels, owning edges, crossed cells or ancestors. Both repeat; native locks are honored. `--page 0` selects the first page. `--max-attempts` defaults to 32 candidate renders per run, maximum 128.

## Preservation and refusals

The label belongs to its edge: raising it also raises the line. The fixer moves the whole edge cell/wrapper just after the covering sibling shape, retaining its parent/layer. It changes no text, styles, offsets, coordinates, routes or metadata. Direct zero-size text children can move with the edge; structural/protected/nested children block repair.

Every sibling crossed must pass these guards:

- No protected/composite cells, different layers/parents, unsupported routes, unmeasured labels or nonrectangular/rotated/rounded shapes.
- The raised line cannot pass through shape interiors or other label bounds. Crossed connections must have disjoint paths and visual bounds (including strokes/markers); jump styles are excluded.
- Raised labels cannot cover other text or connections. Overlap with a shape must be a known occlusion, with the label inside its rectangular outline by a margin.

The parsed XML must match exactly the declared reorder operations; serialization/compression can change. Fresh native rendering must confirm unchanged label/shape/route measurements, no new/worsened collisions, and the target label in front. Unsafe candidates are discarded. These conservative checks do not prove pixel-perfect appearance or semantic correctness.

## Results and follow-up

JSON records `changes` (page, edge, label, parent, covering shape and crossed IDs), skipped reasons, attempts, hashes, before/after reports, verification status and remaining occlusions/warnings.

- **0**: opaque-label occlusions cleared and measurements complete on checked pages. **Other warnings may remain.**
- **1**: occlusions or unmeasured labels remain; verified partial changes are written with `--output`.
- **2**: invalid input, renderer/final verification failure or output conflict; no output published.

The source remains untouched. Output is published atomically after final verification, refuses existing paths, and aborts if the source changes. In a generator, move the whole edge XML element/wrapper after the reported sibling, leaving `parent` unchanged; regenerate and verify. The fixer does not rewrite Python.

To combine repairs, run stacking repair to a new file, pass that file to `native-fix --output` with another destination, then run `native-check`. Inspect each exit status: partial results can be useful; failures produce no output.
