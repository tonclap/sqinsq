# Third-party files used for cross-checking

This directory holds work by other people. **None of it is stored in this
repository** — `.gitignore` keeps it out, and `sqinsq.commands.fetch_external`
downloads it on demand from a pinned upstream commit, verifying a recorded
SHA-256 before anything is written.

Why fetch instead of vendor, when the upstream licence would allow a copy: a
cached copy silently becomes a *fork* the moment upstream changes, and then the
independent verifier that vouches for our numbers is no longer the verifier
anybody else can run. A pinned download keeps the two identical by
construction, and makes the version we relied on explicit rather than implicit.

## `schadt_check.py` and `schadt_s29_squares.txt`

| | |
| --- | --- |
| Author | Thomas Schadt (GitHub: [BalthasarStrauss](https://github.com/BalthasarStrauss)) |
| Upstream | <https://github.com/BalthasarStrauss/Squares-packing_S-29-_New-Record> |
| Pinned commit | `71ea2ee9166fb7ffcefb6f9bea6124fab6ad95c3` (2025-12-08) |
| Licence | MIT, Copyright (c) 2025 Thomas Schadt |
| Upstream names | `check.py`, `squares.txt` |

`check.py` is an independent verifier: its own Taylor series for sine and
cosine, its own separating-axis test, `Decimal` arithmetic at 300 significant
digits, epsilon `1e-100`. Every packing this project claims is run through it,
not a sample — "32 out of 32 improved" is exactly the shape a systematic error
takes, and picking convenient cases would be the worst possible response to it.

`squares.txt` is Schadt's record packing for n = 29, used as a positive control:
a configuration we did not produce, which the pipeline must read and confirm.

## `ellsworth_check.py`

| | |
| --- | --- |
| Author | David Ellsworth (GitHub: [Davidebyzero](https://github.com/Davidebyzero)) |
| Upstream | <https://github.com/Davidebyzero/packing_squares_in_squares__tools> |
| Pinned commit | `79f8a378d52e757d70f7cfb2c2f7a24a53da0204` (2026-09-12) |
| Licence | **none stated** — no licence file in the repository |
| Upstream names | `check_packing.py` |

The author of the registry this project submits to published his own tools on
2026-09-12. `check_packing.py` is a second independent verifier: `Decimal`,
its own Taylor series, its own separating-axis test, and an epsilon taken from
the digit count of the file it is given (`1e-31` for our 34-digit coordinates)
unless one is passed on the command line. It reads the same text format as
Schadt's, which is why it cost a wrapper rather than a converter.

**The missing licence is the reason this file must never be vendored.** With
Schadt's MIT file, fetching instead of copying is a choice about drift; here a
copy in this repository would be redistribution of work whose author has granted
no permission for it. Fetch-on-demand from a pinned commit is the only form in
which it may be used — in this tree and in any tree built from it.

### Line endings

The pinned hashes are taken over **LF-normalised** content. Upstream ships CRLF;
this tree is LF by `.gitattributes`. A hash over raw bytes would disagree with
itself depending on which side of a clone it was computed on, which makes such a
hash worse than none: it fails for a reason that has nothing to do with the file.

### Verifying without downloading

    sqinsq fetch-external --check

Exit code 1 means a local copy is missing or no longer matches the pin. Until
that is resolved, no cross-check result from this directory should be trusted.
