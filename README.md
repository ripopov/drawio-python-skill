# Draw.io Python Skill

A self-contained [Agent Skills](https://agentskills.io/specification) package for generating and editing native, editable Draw.io diagrams with Python. It focuses on SoC architecture and microarchitecture and also supports flowcharts, schemas, swimlanes, networks, and illustrations built from native shapes.

The bundled API uses only the Python standard library. It provides shapes, ports, containers, layers, multiple pages, deterministic connectors, tables, metadata, structural validation, and targeted edits to existing diagrams.

## Install and use

The skill lives at [`.agents/skills/drawio-python-arch`](.agents/skills/drawio-python-arch/SKILL.md). Use this repository as a workspace with an agent that discovers `.agents/skills/`, or copy the entire `drawio-python-arch` directory into your agent's supported skills directory. Keep its scripts, references, and examples together.

Ask your agent to use `drawio-python-arch`, for example:

> Use drawio-python-arch to create an editable CPU and memory diagram with an AXI4 interconnect. Save it as design.drawio.

Requirements:

- Python 3.9 or later for generation, editing, and structural checks. No pip installation is needed.
- Draw.io Desktop for optional PNG export.
- Xvfb for optional headless PNG export on Linux.

The output `.drawio` files can be opened and edited in Draw.io Desktop or diagrams.net. Connector routing is explicit; the library does not automatically avoid obstacles or measure text.

## Package contents

```text
.agents/skills/drawio-python-arch/
├── SKILL.md       # Agent instructions and standard YAML metadata
├── scripts/       # Self-contained Python API and CLI
├── references/    # API documentation and verification notes
├── examples/      # Generators, prompts, editable diagrams, and previews
└── tests/         # Standard-library unittest suite
```

Read [SKILL.md](.agents/skills/drawio-python-arch/SKILL.md) for the agent workflow and the [API reference](.agents/skills/drawio-python-arch/references/api.md) for direct Python use.

## Run examples and checks

From the repository root:

```bash
python3 .agents/skills/drawio-python-arch/examples/generate.py --output-dir /tmp/drawio-demo
python3 .agents/skills/drawio-python-arch/scripts/drawio_arch.py inspect /tmp/drawio-demo/axi_test_system.drawio
python3 -m unittest discover -s .agents/skills/drawio-python-arch/tests -v
```

For optional native rendering:

```bash
python3 .agents/skills/drawio-python-arch/scripts/drawio_arch.py export /tmp/drawio-demo/axi_test_system.drawio /tmp/drawio-demo/axi_test_system.png --headless
```

Omit `--headless` when a display is available. Structural checks do not replace visual inspection; see the [verification notes](.agents/skills/drawio-python-arch/references/verification.md) for supported features and limits.
