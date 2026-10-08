# Native label checks

Use for dense wiring, suspected collisions, HTML/wrapped labels or requested in-depth verification. Requires Chromium/Chrome and local Draw.io Desktop assets or a built `src/main/webapp` directory. No Python/Node packages, network access or Xvfb are needed for JSON-only checking.

```bash
python3 "$SKILL_DIR/scripts/drawio_arch.py" native-check design.drawio > report.json
python3 "$SKILL_DIR/scripts/drawio_arch.py" native-check design.drawio --report-dir design-report --headless
```

The source stays untouched. Use `--browser` and `--drawio-asar` or `--drawio-webapp` when autodetection fails. Snap assets are at `/snap/drawio/current/resources/app.asar`.

| Option | Meaning |
|---|---|
| `--page 0` | First page; default checks all pages |
| `--padding 2` | Default clearance in pixels; `0` checks strict intersections |
| `--timeout 60` | Default seconds per check/export |
| `--fail-on advisory` | Make advisories also cause exit 1 |
| `--no-sandbox` | Only where the environment requires it |

Exit **0**: no findings at the selected threshold and no unmeasured visible labels. Exit **1**: findings or incomplete measurement need review. Exit **2**: invalid input, missing prerequisite or failed verification. Exit 0 may include advisories/info.

## Findings

Each page contains `labels` (IDs, owning edges, text, pixel bounds), `shapes`, rendered `bounds`, `collisions`, severity `summary`, and `unmeasured_labels`. Collisions include `type` (`label-label` or `label-shape`), IDs `a`/`b`, overlap rectangle, `severity` and `reason`. At least one label belongs to an edge; node-label pairs are not checked.

| Severity | Meaning | Action |
|---|---|---|
| Warning | Label bounds intersect, or an opaque shape is painted above a label | Review and repair unintended conflicts |
| Advisory | Insufficient clearance, unprotected label above a shape, translucent foreground or uncertain paint order | Inspect readability before changing anything |
| Info | Label is above the shape with an opaque background | Usually retain |

Label-shape findings include `paint_order`, `shape_fill_alpha` and `label_background_alpha`. Browser hit testing samples paint order, including HTML labels; fully transparent fills and containing ancestors are excluded. `possible-label-occlusion` includes a message and `suggested_fix` pointing to [stacking repair](native-stack-fix.md). Other warning overlaps may suit [offset repair](native-fix.md). A suggestion does not guarantee a safe repair exists.

## Visual reports

`--report-dir` must name a **new directory**. Reports additionally require Draw.io Desktop (`--export-executable` for its path) and Xvfb with `--headless` on Linux. Omit `--headless` with a working display. Match exporter assets/fonts to the checker.

- `report.json`: all findings, stable numbers, explanations, `highlighted`/`highlight_color` and an artifact manifest.
- `annotated.drawio`: all pages/cells plus an editable **Native check findings** layer; hide it to remove annotations.
- `page-N.png`: each checked page, numbered from 1 (`--page 1` produces `page-2.png`).

Ovals circle affected labels with matching numbers and legend entries: **red warning, amber advisory, blue info**. Unmeasured labels are marked **INCOMPLETE**. `--highlight all` is the default; `--highlight warning,advisory` filters only illustrations, never JSON, numbering or exit status.

A warning result still publishes the complete report. Failed exports publish no partial bundle or overwrite. Check and fix the source, not the annotated copy: annotations are themselves diagram content.

## Manual repair and limits

Adjust `label_offset=(dx,dy)` on `edge()`/`connect()`, or `offset` on `edge_label()`; negative `dy` moves up. Use `label_position` along an edge or `connect(..., label_segment=...)` for another leg. Revise lanes/attachment fractions if routing needs space, preserving topology. Update the authoritative generator, recheck affected pages, and inspect a PNG when available. Avoid unbounded offset retries; unresolved cases need layout review.

Native text bounds are not pixel-perfect glyph/shape intersections. Rotated text and nonrectangular shapes can over-report. Hidden cells/collapsed descendants are excluded. Remote fonts/images, math, complex HTML backgrounds, gradients and blending are not verified. The checker does not detect line-label intersections, shape overlap, text fitting, clipping or semantic errors; retain structural checks and visual review.
