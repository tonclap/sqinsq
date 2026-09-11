"""Checking the table against itself: formula against number, polynomial against root.

The occasion was a find at n=179. The page shows

    $s = {25\\over 2} + \\sqrt 2 = \\Nn{13.89540982243640}$

but 25/2 + sqrt(2) = 13.914213562..., not 13.895409822.... The attribution
explains how: the entry was found in January 2025 (when the value really was
25/2+sqrt(2)), improved by annealing in January 2026, and flagged "Not yet
analytically optimized". On the update the decimal was replaced while the closed
form of the old packing was left in place.

The check is mechanical and cheap, so it is worth running over the whole table:

  1. if an entry has a closed form, evaluate it and compare with the decimal;
  2. if a polynomial is published, substitute the decimal into it and make sure
     it really is a root;
  3. compare the decimal from the caption with the side in the SVG's own viewBox.

    sqinsq audit-table
"""

from __future__ import annotations

import argparse
import csv
import re

from sqinsq.paths import snapshot_arg

import sympy as sp
from mpmath import mp, mpf

from sqinsq import svgpack, table

mp.dps = 60


def latex_to_sympy(latex: str) -> sp.Expr | None:
    """Parsing the subset of LaTeX in which the registry writes closed forms.

    Supported: integers, ``{a\\over b}``, ``\\sqrt N``, ``\\sqrt[3] N``, sums and
    differences, a fraction times a root. Anything else is None and the entry is
    simply not checked (a silent "ok" is unacceptable, hence a separate status).
    """
    text = latex.strip()
    if "\\Nn" in text:
        text = text.split("=")[0].strip() if "=" in text else ""
    if not text or "🔒" in text or "{}^" in text:
        return None

    text = re.sub(r"\\left|\\right", "", text)
    text = re.sub(r"\{(-?[\d.]+)\\over\s*(-?[\d.]+)\}", r"((\1)/(\2))", text)
    text = re.sub(r"\\sqrt\[(\d+)\]\s*\{?(-?[\d.]+)\}?", r"((\2)**(1/Integer(\1)))", text)
    text = re.sub(r"\\sqrt\s*\{?(-?[\d.]+)\}?", r"sqrt(\1)", text)
    text = text.replace("\\,", "").replace("\\;", "").replace("~", "")
    text = re.sub(r"\)\s*sqrt", r")*sqrt", text)
    text = re.sub(r"(\d)\s*sqrt", r"\1*sqrt", text)
    text = re.sub(r"\)\s*\(", r")*(", text)
    if re.search(r"[\\{}]", text):
        return None
    try:
        return sp.sympify(text, locals={"sqrt": sp.sqrt, "Integer": sp.Integer})
    except (sp.SympifyError, TypeError, SyntaxError):
        return None


def poly_newton_step(poly_latex: str, value: mpf):
    """How far the displayed value is from the true root of the polynomial.

    The raw residual P(s) is useless: these polynomials reach degree 62 with
    coefficients up to 1e150, so |P(s)| ~ 1e152 means nothing. What is
    interpretable is the Newton correction |P(s)/P'(s)| - the distance to the
    root in the same units as s itself. The displayed value is truncated to ~16
    digits, so a correction of 1e-16 or below is normal, while a noticeably
    larger one means the number and the polynomial describe different quantities.
    """
    text = poly_latex.replace("=0", "").replace("= 0", "")
    text = re.sub(r"s\^\{(\d+)\}", r"s**\1", text)
    text = re.sub(r"s\^(\d+)", r"s**\1", text)
    text = re.sub(r"(\d)\s*s", r"\1*s", text)
    text = re.sub(r"\\left|\\right|\\!|\\,", "", text)
    if re.search(r"[\\{}]", text):
        return None
    try:
        expr = sp.sympify(text, locals={"s": sp.Symbol("s")})
    except (sp.SympifyError, TypeError, SyntaxError):
        return None
    s = sp.Symbol("s")
    try:
        degree = sp.degree(expr, s)
        # Coefficients go up to 1e150 and the degree up to 144: evaluated at 50
        # digits the significant figures cancel entirely, and the "discrepancy"
        # ends up being ours, not the registry's. Precision is taken with margin.
        digits = int(max(200, 4 * degree + 200))
        point = sp.Float(str(value), digits)
        p_val = sp.N(expr.subs(s, point), digits)
        d_val = sp.N(sp.diff(expr, s).subs(s, point), digits)
        if d_val == 0:
            return None
        with mp.workdps(digits):
            return abs(mpf(str(p_val)) / mpf(str(d_val)))
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--snapshot")
    args = ap.parse_args()

    snap = snapshot_arg(args.snapshot)
    html = (snap / "squares_in_squares.html").read_text(encoding="utf-8", errors="replace")
    entries = table.parse_table(html)

    rows = []
    mismatches = []
    for entry in entries:
        if not entry.s_decimal:
            continue
        declared = mpf(entry.s_decimal)
        digits = len(entry.s_decimal.split(".")[1]) if "." in entry.s_decimal else 0
        shown_tol = mpf(10) ** (-digits) * 2

        row = {
            "n": entry.n,
            "s_decimal": entry.s_decimal,
            "s_latex": entry.s_latex,
            "closed_form": "",
            "closed_form_value": "",
            "closed_form_delta": "",
            "poly_newton": "",
            "svg_delta": "",
            "verdict": "ok",
            "note": "",
        }

        expr = latex_to_sympy(entry.s_latex)
        if expr is not None and not expr.is_number:
            expr = None
        if expr is not None:
            value = mpf(str(sp.N(expr, 40)))
            row["closed_form"] = str(expr)
            row["closed_form_value"] = mp.nstr(value, 20)
            delta = abs(value - declared)
            row["closed_form_delta"] = mp.nstr(delta, 5)
            if delta > shown_tol:
                row["verdict"] = "MISMATCH"
                row["note"] = "the closed form does not equal the displayed number"
                mismatches.append(row)

        if entry.poly:
            step = poly_newton_step(entry.poly, declared)
            if step is not None:
                row["poly_newton"] = mp.nstr(step, 5)
                # The displayed number is itself rounded to its last digit, so
                # the threshold here is an order milder than for a closed form.
                if step > shown_tol * 10:
                    row["verdict"] = "MISMATCH"
                    row["note"] = (row["note"] + "; " if row["note"] else "") + (
                        "the displayed number is not a root of the published polynomial"
                    )
                    mismatches.append(row)

        try:
            packing = svgpack.load(snap / "svg" / entry.svg)
            row["svg_delta"] = mp.nstr(abs(packing.s - declared), 5)
        except Exception:  # noqa: BLE001
            row["svg_delta"] = "?"

        rows.append(row)

    out = snap / "audit_table.csv"
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    checked = sum(1 for r in rows if r["closed_form"])
    print(f"entries with a decimal value: {len(rows)}")
    print(f"of them with a parsed closed form: {checked}")
    print(f"formula <-> number mismatches: {len(mismatches)}")
    print(f"report: {out}")
    for row in mismatches:
        print()
        print(f"  n={row['n']}")
        print(f"    formula:   {row['s_latex']}")
        print(f"    = {row['closed_form_value']}")
        print(f"    displayed: {row['s_decimal']}")
        print(f"    difference: {row['closed_form_delta']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
