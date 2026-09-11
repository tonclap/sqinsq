# sqinsq

Tools for the registry of best known packings of unit squares in a square
(<https://kingbird.myphotos.cc/packing/squares_in_squares.html>): extracting the
geometry out of the published SVGs, verifying packings in exact arithmetic, and
numerically polishing published configurations that are not yet analytically
optimised.

The result this code produced is in the registry: **s(238) = 15.93965520031394**,
attributed to Grigoriy Dyachkov, August 2026. Improvements for
n = 152, 236, 268, 1453 and 2043 were produced the same way and are in
[results/](results/README.md).

## What the method actually does

It does not search for packings. It takes a configuration that is already
published and squeezes the container around it, keeping the topology fixed.

1. **Read the published configuration.** The registry SVGs are the only place
   the coordinates exist. Precision lives in DTD entities, squares are placed by
   nested transforms, and adjacent squares are frequently merged into a single
   path — so `sqinsq/svgpack.py` reconstructs the unit squares rather than
   parsing shapes one by one.
2. **Linearise the contacts.** For every pair of squares that can touch, the
   separating axis and the gap along it are computed, and the same is done for
   square-to-wall contacts. Each contact becomes a linear constraint in the
   displacements (dx, dy, dθ) of the two squares and the change of the container
   side ds.
3. **Solve a trust-region LP.** Minimise `ds` subject to those constraints
   inside a trust region, apply the step, rebuild the active set, adapt the
   region. This is sequential linear programming, and it converges to a locally
   rigid configuration — the same configuration, pressed tighter.
4. **Refine in exact arithmetic.** float64 stalls at a trust region of ~1e-14,
   because a coordinate of magnitude 10 carries only ~1e-16. Above that,
   `sqinsq/refine.py` switches to iterative refinement: derivatives stay in
   float64 (they only set a direction), while the right-hand sides — gaps and
   wall distances — are computed in mpmath and converted to float *as
   differences*. A difference of 1e-14 survives the conversion with relative
   error 1e-16, so each iteration adds roughly 15 digits instead of stopping at
   1e-16.
5. **Accept a step only if exact geometry allows it.** The LP is a model; the
   verdict belongs to `sqinsq/verify.py` running at 300 digits with a **zero**
   overlap budget. A step that shrinks the side but produces an overlap of
   1e-40 is rejected.

Two consequences worth stating plainly. The improvements are typically in the
11th to 13th significant digit and are invisible without heavy zoom — they are
relaxations of the published configuration, not new arrangements. And the
declared side is a *tight* one: it is measured from the geometry that was
verified (`verify.tight_side`), not read off the LP variable.

Where the process stops is honest and known: it stops when the trust region
collapses, which is convergence of the region and not a proof of optimality.
Re-running on already-polished files still yields about 3e-11 — two orders of
magnitude below the last significant digit of anything claimed, which is why
it is accepted rather than chased.

## Why you can believe the numbers

Four independent controls, all of which have to pass. Each of them is weak on
its own, and one of them has already caught a real error.

| Control | What it establishes |
| --- | --- |
| **Positive** — `sqinsq verify-registry` | our parser and verifier accept all 174 registry entries. If they reject one, the bug is ours |
| **Negative** — `sqinsq polish --n 11 29 50 55 71 123` | on entries with a known exact optimum the polisher must gain nothing (it returns -2.5e-11 ... -1.0e-10, i.e. zero plus the export margin). A positive gain there would mean the polisher invents improvements |
| **Foreign code** — `sqinsq crosscheck` | every result is re-verified by Thomas Schadt's independent `check.py` at 300 digits with epsilon 1e-100. This is the one that caught 7 false results out of 32 that our own verifier had passed |
| **Round trip** — `sqinsq make-svg` | the emitted SVG is read back by our own parser and compared; agreement is ~1e-33 |

A third verifier, `sqinsq verify-interval`, works in interval arithmetic: it
does not measure a gap, it *proves* the gap is positive.

Validity is binary here. There is no tolerance budget for overlap "because it is
orders of magnitude smaller than the gain" — that reasoning is exactly how seven
of the results above passed an internal check and failed an external one.

And the results themselves do not have to be taken on trust either:
[results/](results/README.md) holds one JSON record per claimed entry — the
value, the verdict of an exact check at zero tolerance, the verdict of the
foreign verifier where it was run, the tight side, the contact structure, and
the sha256 of the file each number came from.

What this code does not claim, and where it is known to be awkward, is in
[KNOWN_ISSUES.md](KNOWN_ISSUES.md).

## Installation

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows
source .venv/bin/activate     # Linux / macOS
pip install -r requirements.txt
```

Python 3.10 or newer. Two files describe dependencies and they answer different
questions: [pyproject.toml](pyproject.toml) says what the library needs to work
(ranges, `pip install -e .`), while [requirements.txt](requirements.txt) pins
the exact versions every published number was produced with. Reproducing a
claim means using the pins; using the library does not.

`pip install -r requirements-dev.txt` (or `pip install -e ".[dev]"`) adds pytest.

Installing gives one entry point, `sqinsq`, with a subcommand per job; run it
with no arguments for the list. Without installing, the same commands work as
`python -m sqinsq.cli <command>`.

## Reproducing a result

```bash
sqinsq snapshot                   # dated snapshot of the registry
sqinsq verify-registry            # positive control: 174/174
sqinsq polish --n 238 --refine 30 # polish one entry
sqinsq make-svg --n 238           # emit registry-style SVG + coordinates
sqinsq fetch-external             # get the third-party verifier
sqinsq crosscheck                 # re-verify with foreign code
```

Polishing is **not deterministic in outcome**: different LP formulations reach
different local optima, and a re-run can be worse than a previous one for some n
and better for others. Runs therefore do not replace each other — each writes
its own branch, and `sqinsq pick-best` selects the smaller side per n and
records the provenance.

The full pass over all flagged entries takes around half an hour.

## Layout

* `sqinsq/` — the library: `fetch` (snapshots), `table` (parsing the registry
  captions), `svgpack` (SVG → coordinates), `verify` (SAT check in exact
  arithmetic), `contacts` (contact graph), `polish` (float64 optimiser),
  `refine` (mpmath refinement), `schadt` (coordinate format), `svgemit`
  (packing → SVG).
* `sqinsq/commands/` — the runnable half of the tool, one module per command,
  indexed below. Each starts with a docstring saying why it exists.
  `sqinsq/paths.py` answers the one question they share: where `data/` is.
* `results/` — the audit trail: one JSON record per entry whose value this code
  produced, with the verdicts, the contact structure and the hash of the file
  each number came from. See [results/README.md](results/README.md).
* `tests/` — `python -m pytest tests/ -q`. Self-contained: no registry snapshot
  and no third-party file required.
* `data/` — **empty on a fresh clone, and that is deliberate.** Registry
  snapshots are downloaded, not committed (174 SVGs per snapshot), and
  third-party files are fetched from a pinned upstream rather than vendored.
  The only thing stored here is the note explaining the latter:
  [data/external/EXTERNAL.md](data/external/EXTERNAL.md).

### The commands

Everything runnable is one command with subcommands; `sqinsq` on its own prints
the list, and every subcommand takes `--help` of its own. Five of them are the
path from a registry page to a verified improvement, and the rest exist to
disprove it — which is the more important half.

**Snapshot, and auditing the registry**

| Command | What it does |
| --- | --- |
| `snapshot` | dated snapshot of the registry: page, all SVGs, `table.csv`, sha256 |
| `verify-registry` | positive control: parse and verify the entire registry (174/174) |
| `verify-external` | verifier against coordinates that never passed our SVG parser |
| `verify-interval` | third verifier, in interval arithmetic: proves the gap is positive rather than measuring it |
| `verify-dump` | dump of verdicts over 206 packings — the regression baseline for refactoring |
| `audit-table` | the table against itself: closed form ↔ decimal ↔ polynomial ↔ SVG |
| `agreement` | our reading of the coordinate format against the foreign loader, at the level of geometry |
| `triage` | structure of each entry: tilted squares, distinct angles — what is tractable symbolically |
| `contact-tolerance` | contacts unrolled by tolerance: how precise the published coordinates are |
| `report-unflagged` | pass over entries *without* the flag — a control by scale, not a search |
| `check-gradients` | the polisher's analytic derivatives against finite differences |

**Improving and packaging a result**

| Command | What it does |
| --- | --- |
| `polish` | the polisher: minimise the side at fixed topology (`--refine` adds the mpmath stage) |
| `refine` | refinement on top of an existing file, without re-polishing in float |
| `pick-best` | select the smallest side per n across runs, recording provenance |
| `make-svg` | emit a registry-style SVG and read it back with our own parser |
| `fetch-external` | download the pinned third-party verifier and check its sha256 |
| `crosscheck` | run every result through that foreign verifier |

## How this repository is maintained

It is assembled from a larger private working tree — the research journal, the
task and risk registers and the correspondence with the registry curator stay
there, because they are notes about people and priorities rather than anything a
reader of the code needs. The composition is an explicit allowlist in a builder
script, not a denylist, so nothing reaches this side by accident.

The practical consequence for you: issues are the reliable way to reach the
author, and a pull request is welcome but will be applied on the private side
and reappear here in the next rebuild rather than being merged directly. Say so
in the PR and you will be credited for it.

## Licence

MIT, see [LICENSE](LICENSE). This covers the code in this repository. It does
not cover material by other people: the third-party verifier is fetched rather
than vendored (MIT, Copyright (c) 2025 Thomas Schadt), and the registry pages
and their SVGs belong to the registry.
