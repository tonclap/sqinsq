"""One entry point for everything runnable: ``sqinsq <command> [options]``.

Before this existed the tool was twenty loose scripts, and using it meant first
knowing which of the twenty to run. The commands themselves did not change: each
one still lives in its own module under :mod:`sqinsq.commands`, with its own
``--help``, and this file only routes to them.

    sqinsq                       # the list below
    sqinsq verify packing.svg    # is this packing admissible
    sqinsq verify-registry       # positive control: the whole registry
    sqinsq polish 238 --refine 30

Two implementation notes worth knowing before editing.

**Dispatch is lazy.** The module of a command is imported only when that command
is called, so ``sqinsq --help`` does not pull in scipy and sympy, and a missing
optional dependency breaks one command rather than the whole tool.

**Arguments are not re-declared here.** Each command parses its own; this file
hands the remaining argv over untouched. Declaring them twice would mean a flag
that exists in one place and not the other, and the divergence would show up as
a confusing error rather than as a missing feature.
"""

from __future__ import annotations

import importlib
import sys

# command -> (module under sqinsq.commands, one-line description)
# The groups mirror the order of the README, because a reader who has just read
# it should find the same shape here.
COMMANDS: dict[str, tuple[str, str]] = {
    # Working on packings
    "verify": ("verify", "verify packings given as .svg or .txt files"),
    "polish": ("polish", "tighten a published packing at fixed topology"),
    "refine": ("refine_polished", "refine an existing result in exact arithmetic"),
    "pick-best": ("pick_best", "select the smallest side per n across runs"),
    "make-svg": ("make_svg", "emit a registry-style SVG and read it back"),
    "results": ("results", "write an audit record per packing: verdicts, structure, hashes"),
    # The registry
    "snapshot": ("snapshot", "take a dated snapshot of the registry"),
    "verify-registry": ("verify_registry", "positive control: verify the whole registry"),
    "audit-table": ("audit_table", "check the table against itself: formula, decimal, polynomial"),
    "triage": ("triage_symbolic", "structure of each entry: tilted squares, distinct angles"),
    "contact-tolerance": ("contact_tolerance", "how precise the published coordinates are"),
    "report-unflagged": ("report_unflagged", "pass over entries without the flag: a control by scale"),
    # Independent verification
    "fetch-external": ("fetch_external", "download the pinned third-party verifier"),
    "crosscheck": ("crosscheck_external", "re-verify results with the foreign verifier"),
    "verify-external": ("verify_external", "verify coordinates that never passed our SVG parser"),
    "verify-interval": ("verify_interval", "prove gaps are positive, in interval arithmetic"),
    "verify-dump": ("verify_dump", "dump verdicts over every packing: the refactoring baseline"),
    "agreement": ("check_schadt_agreement", "our reading of the coordinate format against theirs"),
    "agreement-ellsworth": ("agreement_ellsworth", "our SVG reading against the author's own parser"),
    "check-gradients": ("check_gradients", "analytic derivatives against finite differences"),
}

GROUPS = [
    ("Working on packings", ["verify", "polish", "refine", "pick-best", "make-svg", "results"]),
    (
        "The registry",
        ["snapshot", "verify-registry", "audit-table", "triage", "contact-tolerance",
         "report-unflagged"],
    ),
    (
        "Independent verification",
        ["fetch-external", "crosscheck", "verify-external", "verify-interval", "verify-dump",
         "agreement", "agreement-ellsworth", "check-gradients"],
    ),
]


def usage() -> str:
    lines = [
        "usage: sqinsq <command> [options]",
        "",
        "Packings of unit squares in a square: parse, verify, tighten.",
        "Every command takes --help of its own.",
    ]
    for title, names in GROUPS:
        lines.append("")
        lines.append(f"{title}:")
        for name in names:
            lines.append(f"  {name:<18} {COMMANDS[name][1]}")
    lines += [
        "",
        "Data (snapshots, downloaded third-party files, results) is looked for in",
        "$SQINSQ_DATA, then ./data, then the source checkout.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv or argv[0] in ("-h", "--help", "help"):
        print(usage())
        return 0

    name = argv[0]
    if name not in COMMANDS:
        print(f"unknown command: {name}\n", file=sys.stderr)
        print(usage(), file=sys.stderr)
        return 2

    module_name, _ = COMMANDS[name]
    module = importlib.import_module(f"sqinsq.commands.{module_name}")

    # The command parses the rest itself. argv[0] is rewritten so that its own
    # --help prints "sqinsq verify" rather than the module path.
    sys.argv = [f"sqinsq {name}", *argv[1:]]
    return module.main()


if __name__ == "__main__":
    sys.exit(main())
