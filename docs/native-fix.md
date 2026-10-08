# Label-offset repair

Use for authorized repair of warning-level label collisions. Run on the source diagram, not an annotated report. Requirements and renderer flags match [native checking](native-check.md). For a label hidden by an opaque shape, consider the independent [stacking fixer](native-stack-fix.md) first; neither fixer invokes the other.

```bash
# Verified dry-run
python3 "$SKILL_DIR/scripts/drawio_arch.py" native-fix design.drawio
# Apply to a new file; optionally restrict/protect labels
python3 "$SKILL_DIR/scripts/drawio_arch.py" native-fix design.drawio --output fixed.drawio --only request --keep response
```

`--only` selects exact label IDs, including child labels; `--keep` protects labels, edges or ancestors. Both repeat. IDs apply across selected pages; `--page 0` selects the first. Unknown IDs are errors.

| Budget | Default | Maximum |
|---|---|---|
| `--max-move` | 32 pixels total displacement per label | 128 |
| `--max-attempts` | 160 candidates per page | 2000 |
| `--max-passes` | 3 | 10 |

Do not automatically increase movement limits when repair fails; inspect intent and spacing first.

## Preservation and limits

Only `x`/`y` of a label's `mxGeometry/mxPoint[@as='offset']` may change; the point is added if needed. Text, styles, geometry elsewhere, routes, ports, terminals, parents, cell order and metadata are preserved. All pages remain. XML serialization/compression may change; the parsed document is compared against exactly the declared edits and the saved file is independently rendered again.

The bounded deterministic search can move pairs of labels together. Each accepted step reduces warnings without new collision pairs or severity increases. Labels retain their connection segment, established side and containment; guards reject new shape overlaps, connector crossings or ambiguous association with another connection. Displacement is measured from the input, not accumulated per pass.

- Advisory/info findings are not targets. Native `locked=1`, `movable=0`, `labelMovable=0` and `autofix=0` on labels/edges/ancestors are honored.
- Node labels, structural children and labels with descendants never move. Direct zero-size child text labels are supported.
- Rotated/directional text, noncentral label positions, image/SVG/math labels and unsupported geometry are skipped. Pages with unmeasured labels or unsupported curved/rounded/custom routes remain unchanged.
- Rectangle guards can reject visually feasible placements. This is a local search, not a global layout solver or proof of semantic correctness; visually review label association.

## Results

JSON includes hashes, options, search/skipped results, `before`/`after` native reports, preservation/recheck status and `changes` with page, label, edge and old/new absolute offsets. In dry-run mode, `after` describes the verified temporary candidate.

- **0**: no warnings or unmeasured labels remain; advisories/info may remain.
- **1**: unresolved warnings or incomplete measurements; verified partial changes are still written with `--output`.
- **2**: invalid input, renderer/verification failure or output conflict; no output published.

The source is untouched; publication is atomic, refuses existing output paths and aborts if the source changes during repair. Transfer accepted `after` offsets into the authoritative generator's `label_offset` or child-label `offset` as **replacements, not deltas**, then regenerate and check. The fixer does not rewrite Python.
