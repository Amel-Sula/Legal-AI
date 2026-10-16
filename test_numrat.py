#!/usr/bin/env python3
"""Albanian numbers, parsed the way Albania writes them.

This test exists because of a bug that sat in the corpus from the first
fixture: parse_qty("85.000 lekë") returned 85.0. Albanian separates thousands
with a dot, float() reads a dot as a decimal point, and so a salary of
eighty-five thousand lekë was compared as eighty-five. kontrata_test_01 states
exactly that figure, which means the arithmetic gate had been comparing the
wrong number for as long as the gate existed, and nothing in the output said
so: the citation verified, the clause really did contain "85.000", and the
report looked ordinary.

The second half is the decimal comma: "4,8 orë" parsed as 4, because the comma
was stripped along with the brackets.

Both are the same shape of failure as the OCR digit problem, which is how they
were found -- a number that is wrong but confident is the one error this
product cannot survive, so the parser gets its own test.

    python3 test_numrat.py
"""
from verify import parse_qty, vlerat

RASTET = [
    # Albanian thousands: the dot is a separator, never a decimal point
    ("85.000 leke", 85000.0, "leke"),
    ("50.000 leke", 50000.0, "leke"),
    ("1.234.567 leke", 1234567.0, "leke"),
    ("100 000 leke", 100000.0, "leke"),
    # OCR splits the group; the value must survive
    ("85. 000 leke", 85000.0, "leke"),
    # the American form folds into the same rule
    ("100,000 leke", 100000.0, "leke"),
    # Albanian decimals: the comma IS a decimal point
    ("4,8 ore", 4.8, "ore"),
    ("2,5 per qind", 2.5, "perqind"),
    # and none of that may disturb what already worked
    ("40 ore", 40.0, "ore"),
    ("22 dite", 22.0, "dite"),
    ("6 (gjashte) muaj", 6.0, "muaj"),
    ("tridhjete vjet", 30.0, "vit"),
    ("25 per qind", 25.0, "perqind"),
    ("jo me shume se 40 ore", 40.0, "ore"),
    # a real decimal must not be eaten by the thousands rule
    ("4.8 ore", 4.8, "ore"),
]

ok = n = 0
for s, pritet_v, pritet_nj in RASTET:
    n += 1
    g = parse_qty(s)
    mire = bool(g) and abs(g[0] - pritet_v) < 1e-9 and g[1] == pritet_nj
    ok += mire
    print(f"  [{'PASS' if mire else 'FAIL'}] {s!r:26} -> {g}"
          f"{'' if mire else f'   pritej ({pritet_v}, {pritet_nj!r})'}")

# and the clause extractor must surface the figure in its written form, so the
# report quotes the contract rather than a rounded reconstruction of it
KLAUZOLA = ("Paga bruto mujore eshte 85.000 (tetedhjete e pese mije) leke, "
            "koha javore 40 ore ne jave, pushim 22 dite.")
v = vlerat(KLAUZOLA)
n += 1
mire = any("85.000" in x for x in v) and any("40 ore" in x for x in v)
ok += mire
print(f"\n  [{'PASS' if mire else 'FAIL'}] vlerat() i nxjerr fjale per fjale: {v}")

print(f"\n{ok}/{n}")
raise SystemExit(0 if ok == n else 1)
