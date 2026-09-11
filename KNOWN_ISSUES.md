# Known limitations

Things that work, with a caveat. Format: problem - when it applies - what to do
about it. Written for someone using this code, not for its author; the internal
register with the project's own history lives outside this repository.

## About the results

**Refinement stops when the trust region collapses, not at a proven optimum.**
Re-running `refine` on already selected files still squeezes out
about 3e-11 of side. Applies to: every file in `polished/`. What to do: run the
refinement again before relying on a value - though this is two orders below the
last significant digit of anything claimed, so it changes no claim.

**The improvements are not proved optimal - they are relaxations of somebody
else's configuration.** No square was moved to a different place in any packing:
the flag "not yet analytically optimized" means the author considers the entry
unfinished, and what this code contributes is numerical tightening in the 11th
to 13th significant digit.

**No closed form is found here.** The registry prefers exact values; this code
produces decimal approximations to 34 digits. For the flagged entries that is
expected: they have 32 to 109 distinct tilt angles, whereas every analytically
solved entry has at most 6.

## About the tools

**Polishing is not deterministic in outcome.** The same entry reaches different
local optima under different LP formulations (spread up to 8e-5), so a new run
does not replace an old one. Applies to: any re-run of `polish`. What to do:
keep branches in separate directories and select with `pick-best`, which also
records the provenance in `pick.csv`.

**The parser is built for the registry's current markup.** DTD entities, nested
transforms, merged outlines, several lattices in one outline, a viewBox that does
not start at the origin - all of it is decoded the way the page looks now.
Applies to: the registry changing its generator. What to do: nothing in advance -
the positive control `verify-registry` will drop below 174/174 loudly and at
once, so the failure cannot be silent.

**The registry snapshot (174 SVGs) is not stored in git**, only `table.csv`,
`meta.json` with sha256 hashes, and derived data. Applies to: a fresh clone.
What to do: `sqinsq snapshot` downloads it again; the hashes in
`meta.json` allow comparison with an earlier snapshot.

**The registry answers 429 without a browser-like User-Agent.** Applies to: any
request without that header. What to do: `sqinsq/fetch.py` sets it and keeps
pauses between requests; do not fetch pages by hand with `curl` and no `-A`.

**A full pass over all 32 flagged entries takes around half an hour.** Applies
to: `polish --all-flagged --refine 30`. What to do: run it in the background;
the report stays in `polish.csv`.

## About the checks

**A fresh snapshot leads scripts away from their own data.** `snapshot`
creates a new directory containing nothing but SVGs, and "the newest snapshot"
stops being the one holding derived data that very second. Applies to: any new
snapshot. What to do: nothing - scripts working with derived data select their
snapshot through `sqinsq.paths.work_snapshot(<needed directory>)`, by the presence of
data rather than by date. The danger was never the crash; it was that a check
could report "0 problems" having examined nothing.

**A verifier dump goes stale when the data under it is rebuilt.** A dump taken
by `verify-dump` describes the files as they were; rebuilding them
(`make-svg`, `pick-best`, `refine`) shifts the declared side,
and the comparison starts failing on entries no code change ever touched.
Applies to: any rebuild of derived files. What to do: separate the causes - take
your own dump BEFORE editing code, and compare against that. A difference
already there means the data was rebuilt, not that the code broke.

**The SVG output is checked by parsing, not by comparing images.** Applies to:
changes in the SVG generator. What to do: `make-svg` reads back what it wrote
with the project's own registry parser and verifies the geometry; there is no
pixel reference, and none is planned.
