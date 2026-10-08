# Verification scope

| Check | Covers | Does not establish |
|---|---|---|
| `save()` / `validate` | IDs, parents, finite geometry, terminals and loose endpoints | Visual quality or full native schema validity |
| `assert_connections()` | Expected endpoint/label triples, including duplicates | Domain correctness beyond supplied expectations |
| `inspect` | Topology, rectangle/manual-route diagnostics and estimated text overlap | Actual fonts, curved routes or stencil silhouettes |
| [Native check](native-check.md) | Rendered label bounds and sampled label/shape paint order | Text fitting, line crossings, clipping or semantics |
| PNG inspection | Visible layout and label association | Correctness of unspecified domain assumptions |

Check meaning against the user's requirements. Review intentional overlaps instead of treating every finding as a defect. If rendering or image viewing is unavailable, state the missing verification; do not report a visual pass.

## Development checks

From the repository root:

```bash
python3 -m unittest discover -s tests -v
DRAWIO_NATIVE_TEST_BROWSER=/path/to/chromium python3 -m unittest discover -s tests -v
```

Native tests are optional. Set `DRAWIO_NATIVE_TEST_ASAR` or `DRAWIO_NATIVE_TEST_WEBAPP` for explicit assets, and `DRAWIO_NATIVE_TEST_NO_SANDBOX=1` only where required. PNG report tests additionally need Draw.io Desktop and, on headless Linux, Xvfb. For a before/after example, use [the documentation script](regenerate-native-label-check.py).
