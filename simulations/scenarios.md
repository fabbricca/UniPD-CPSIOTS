# Scenario catalogue

All `.csc` files are generated from `templates/` by `scripts/gen_scenario.py`.
Do not hand-edit generated files; edit the template or the generator.

Naming: `<phase>-<nodes>-<attack>-<attackers>-s<seed>-<mode>.csc`

| Field | Values |
|---|---|
| phase | `dev` (10 nodes, 5 min) or `final` (30 min) |
| nodes | 10, 20, 30, 40 (grid, 20/30/40 m spacing, 1 root) |
| attack | `baseline`, `neighbor`, `dis` |
| attackers | count (1, or 20% / 30% of nodes rounded) |
| seed | Cooja random seed; also selects attacker positions |
| mode | `paper` (fixed 5 min window) or `sliding` (60 s / 10 s) |

Ground truth: attacker mote IDs are written into the scenario file and into
`results/<name>.truth.csv`; the analysis never infers them from IDS output.
