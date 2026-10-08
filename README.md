# Draw.io Python Skill

A self-contained [Agent Skills](https://agentskills.io/specification) package for generating and editing native, editable Draw.io diagrams with Python. It focuses on SoC architecture and microarchitecture and also supports flowcharts, schemas, swimlanes, networks, and illustrations built from native shapes.

The bundled API uses only the Python standard library. It provides shapes, ports, containers, layers, multiple pages, deterministic connectors, tables, metadata, structural validation, and targeted edits to existing diagrams.

![Draw.io diagram with eight shapes and 24 labeled connections, with native checker findings highlighted in numbered red ovals](docs/native-label-check.png)

Native verification example: red ovals mark five warnings, two advisories, and one informational overlap. The diagram intentionally contains defects to illustrate what the checker detects.

## Install and use

The repository root is the complete skill package. Install it directly into your agent's skills directory, using `drawio-python-arch` as the local directory name to match the skill metadata:

```bash
mkdir -p "$HOME/.agents/skills"
git clone https://github.com/ripopov/drawio-python-skill.git \
  "$HOME/.agents/skills/drawio-python-arch"
```

For other agents, use their supported skills directory. Keep the whole repository together so scripts, references, and examples remain available.

Update an installed clone with:

```bash
git -C "$HOME/.agents/skills/drawio-python-arch" pull --ff-only
```

Run that command before starting your agent, or schedule it on each machine for automatic updates.

Ask your agent to use `drawio-python-arch`, for example:

> Use drawio-python-arch to create an editable CPU and memory diagram with an AXI4 interconnect. Save it as design.drawio.

Requirements:

- Python 3.9 or later for generation, editing, and structural checks. No pip installation is needed.
- Draw.io Desktop for optional PNG export.
- Xvfb for optional headless PNG export on Linux.
- Chromium/Chrome plus local Draw.io assets for optional native label collision checking.

The output `.drawio` files can be opened and edited in Draw.io Desktop or diagrams.net. Connector routing is explicit; the library does not automatically avoid obstacles or measure text.

## Package contents

```text
drawio-python-arch/
├── SKILL.md       # Agent instructions and standard YAML metadata
├── scripts/       # Self-contained Python API and CLI
├── references/    # API documentation and verification notes
├── examples/      # Generators, prompts, editable diagrams, and previews
├── docs/          # README illustrations
└── tests/         # Standard-library unittest suite
```

Read [SKILL.md](SKILL.md) for the agent workflow and the [API reference](references/api.md) for direct Python use.

## Run examples and checks

From the repository root:

```bash
python3 examples/generate.py --output-dir /tmp/drawio-demo
python3 scripts/drawio_arch.py inspect /tmp/drawio-demo/axi_test_system.drawio
python3 -m unittest discover -s tests -v
```

For optional native rendering:

```bash
python3 scripts/drawio_arch.py export /tmp/drawio-demo/axi_test_system.drawio /tmp/drawio-demo/axi_test_system.png --headless
```

Omit `--headless` when a display is available. Structural checks do not replace visual inspection; see the [verification notes](references/verification.md) for supported features and limits.

For deeper verification, check actual rendered label bounds without modifying the diagram:

```bash
python3 scripts/drawio_arch.py native-check /tmp/drawio-demo/axi_test_system.drawio
```

Generate a complete visual report in one command (also requires Draw.io Desktop, and Xvfb with `--headless`):

```bash
python3 scripts/drawio_arch.py native-check /tmp/drawio-demo/axi_test_system.drawio \
  --report-dir /tmp/axi-visual-report --headless
```

Use a new output directory. It contains `report.json`, `annotated.drawio` with a separate editable findings layer, and `page-1.png` (one PNG per checked page). Numbered red ovals match the severity, affected cell IDs, and explanation in the legend and JSON. All severities are highlighted by default; `--highlight warning` or `--highlight warning,advisory` filters the illustrations without hiding findings from the JSON or changing the failure threshold. Generation is fully scripted; deciding whether a finding needs a fix still requires review. The source diagram stays unchanged.

The optional checker runs Draw.io's local JavaScript renderer in headless Chromium and returns JSON containing label IDs, measured bounds, and potential collisions with severity and reasons. Shape overlaps consider sampled paint order, fill transparency, and native label backgrounds. Warnings affect the default exit code; advisories remain available for review (`--fail-on advisory` enables a stricter threshold). It needs no Xvfb or third-party Python packages. See [native checking and fixes](references/native-check.md) for dependency paths, exit codes, limitations, and the fix-and-recheck workflow.

For conservative automatic label fixes:

```bash
# Verified dry-run: JSON proposals, no diagram written
python3 scripts/drawio_arch.py native-fix design.drawio

# Apply to a new file and independently verify its native rendering
python3 scripts/drawio_arch.py native-fix design.drawio --output design-fixed.drawio
```

The fixer changes only connection-label offsets. Text, styles, shapes, ports, routes, topology, and metadata are preserved and checked against the source. It uses bounded native-rendered candidates, including coupled label moves, and retains unresolved cases when a safe local move cannot be found. `--keep ID` freezes intentional placements; `--only ID` limits repairs. See [automatic repair](references/native-fix.md) for limits, receipts, and generator updates.

For a label hidden behind an opaque shape, there is a **separate stacking-only fixer**:

```bash
python3 scripts/drawio_arch.py native-stack-fix design.drawio
python3 scripts/drawio_arch.py native-stack-fix design.drawio --output design-stacked.drawio
```

Occlusion warnings suggest this command. It preserves every coordinate and style, changing only the owning edge's order relative to sibling cells. Native verification confirms the label is in front; conservative checks reject raising its line through shapes or over other text and overlapping connections. See [stacking repair](references/native-stack-fix.md) for supported cases and exit codes. Offset and stacking repairs are independent.
