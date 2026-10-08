# Draw.io Python Skill

A self-contained [Agent Skills](https://agentskills.io/specification) package for generating and editing native, editable Draw.io diagrams with Python. It focuses on SoC architecture and microarchitecture and also supports flowcharts, schemas, swimlanes, networks, and illustrations built from native shapes.

The bundled API uses only the Python standard library. It provides shapes, ports, containers, layers, multiple pages, deterministic connectors, tables, metadata, structural validation, and targeted edits to existing diagrams.

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

The optional checker runs Draw.io's local JavaScript renderer in headless Chromium and returns JSON containing label IDs, measured bounds, and potential collisions with severity and reasons. Shape overlaps consider sampled paint order, fill transparency, and native label backgrounds. Warnings affect the default exit code; advisories remain available for review (`--fail-on advisory` enables a stricter threshold). It needs no Xvfb or third-party Python packages. See [native checking and fixes](references/native-check.md) for dependency paths, exit codes, limitations, and the fix-and-recheck workflow.
