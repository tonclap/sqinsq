# results — the audit trail

One JSON file per entry, grouped by the month the value was produced. These are
not a log of what was run: they are the claim itself, in a form that can be
checked without asking anyone.

    results/2026-08/s238.json    # 32 flagged entries
    results/2026-09/s152.json    # 5 entries carrying an exact closed form

The dates are part of the claim. Each record says what was true of the registry
in that month, and the registry has moved since: of the 32 entries in the first
set only **n = 238** became an improvement in the registry. The other 31 had
already been beaten independently, in June 2026, by Tej Stead — their records
still describe admissible packings, but those packings no longer beat the
published values. The files are kept unedited anyway: an audit trail that gets
tidied up once the outcome is known is not an audit trail.

## What is in a record

| Field | What it answers |
| --- | --- |
| `side` | the value being claimed, to 34 digits |
| `verification.admissible` | does the packing survive an exact check at **zero** overlap tolerance |
| `verification.max_overlap` / `max_outside` | by how much it fails, if it does |
| `verification.foreign_verifiers` | verdicts of independent implementations by other authors, by name |
| `tightness.tight_side` / `slack` | the smallest axis-aligned square that really contains the packing, and the room left over |
| `structure.*` | tilted squares, distinct tilt angles, contacts, degrees of freedom |
| `provenance.sha256_lf` | the hash of the exact file this was computed from |

### The foreign verdicts

Our verifier and our polisher were written by the same head, so their agreement
is not evidence. Every record therefore carries the verdicts of implementations
written by other people, keyed by author:

* `schadt` — `check.py` by Thomas Schadt: `Decimal` at 300 digits, epsilon
  `1e-100`, its own separating-axis test;
* `ellsworth` — `check_packing.py` by David Ellsworth, who keeps the registry
  itself; published 2026-09-12, added here on 2026-09-14. Its epsilon comes from
  the file, so for these 34-digit coordinates it checks at `1e-31`.

Both are fetched from pinned commits by `sqinsq fetch-external` and run by
`sqinsq crosscheck`; a verifier that was never run on a file is **absent** from
the record rather than `null`, because "we did not ask" and "it had nothing to
say" are different statements.

**Every run starts with a packing the verifier must reject** — the same file
with one square moved exactly on top of another. A verifier that answers "valid"
to everything (wrong path, unparsed file, changed output wording) would confirm
37 records out of 37 exactly as convincingly as a working one, so its agreement
is only recorded once it has demonstrated that it can disagree.

Records are re-written when a new verdict is added to them. `provenance.recorded`
stays the date the record was first written and `provenance.updated` is the last
such change; both refer to the same bytes, and `sha256_lf` proves it.

## Why `structure` is here

Because "the numbers improved" is not an explanation. The gains here live in the
11th to 13th significant digit, and the packings stay visually indistinguishable
from the published ones without heavy zoom — so a picture settles nothing, and a
side length on its own says that something moved without saying what.

The contact graph answers that in numbers. How many squares are tilted, how many
distinct angles they use, how many contacts hold the arrangement, how that
compares to the degrees of freedom — that is what kind of configuration it is,
and it is the same data whether you trust us or not.

One caveat that must be read with it: `contacts_*` are counted at
`contact_tolerance`, and published coordinates are numerical, so most real
contacts sit around 1e-6 rather than at that threshold. A small contact count
means "this file is not exact", not "this packing is loose". `sqinsq
contact-tolerance` unrolls the same graph across tolerances and shows the
difference.

## Reproducing a record

```bash
sqinsq verify <coordinate file>            # the verdict, in one line
sqinsq results <coordinate file> --out /tmp/check
diff /tmp/check/s238.json results/2026-08/s238.json
```

Two fields will differ and should: the dates in `provenance`, and
`verification.foreign_verifiers`, which stays empty unless you pass
`--crosscheck` (it needs the third-party verifiers, which `sqinsq fetch-external`
downloads).

## What these records are not

They are not a proof of optimality. Nothing here claims the values cannot be
improved further; the claim is narrower and checkable — that each packing is
admissible in exact arithmetic and that its side is what is stated. The
limitations of the method are in [../KNOWN_ISSUES.md](../KNOWN_ISSUES.md).

They are also not regenerated. Polishing is not deterministic in outcome, so
re-running it would produce the same file names with different numbers; these
records are built from the frozen files the values were taken from, and
`provenance.sha256_lf` is the hash of each of those files.
