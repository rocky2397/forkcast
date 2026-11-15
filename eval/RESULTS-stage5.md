# Stage 5: reading nutrition labels

**Question:** you photograph the nutrition table on a pack. Does Forkcast
read the right calories, protein, carbs and fat per 100 g?

**Short answer:** all four right for about **two in three** products
(estimated 67%, plausibly 59 to 78%). The single most important number,
calories, is wrong in roughly one product in five. The mistakes are
systematic: the kilojoule number taken for kcal, "1,2 g" read as 12, and
values taken from the neighbouring row (saturated fat as fat, salt or fibre
as protein). A simple sum check (calories should be about 9 × fat +
4 × (carbs + protein)) catches most of them.

## What was tested

- **Products:** 150 of the most-scanned products sold in Germany in
  [Open Food Facts](https://world.openfoodfacts.org) with complete
  nutrition facts and a photo of the nutrition table, frozen in
  [`data/labels_off150.json`](data/labels_off150.json) (data © Open Food
  Facts contributors, [ODbL](https://opendatacommons.org/licenses/odbl/1-0/)). Products without
  energy (water) were left out. The photos are contributors' phone photos
  (CC BY-SA, not committed); many show labels in other languages or several
  at once, because the same product is sold across Europe.
- **System under test:** the app's label reader exactly as shipped
  (`backend/app/vision.py` `extract_product`: Claude Haiku 4.5, its prompt
  and schema).
- **Reference:** the values in the Open Food Facts database. A reading
  counts as right within rounding: kcal within 1 kcal or 2%, grams within
  0.2 g or 3%; a "< 0.5 g" entry accepts anything up to it.

Scripts: [`scripts/sample_labels.py`](scripts/sample_labels.py),
[`scripts/run_labels.py`](scripts/run_labels.py),
[`scripts/score_labels.py`](scripts/score_labels.py). Every reading is in
`labeling/labels/haiku-4-5_off150.jsonl`.

## Results against the database

| Value | Read right |
|---|---|
| kcal | 71% (64 to 78) |
| protein | 69% (62 to 76) |
| carbs | 76% (69 to 82) |
| fat | 77% (69 to 83) |
| **all four** | **49%** (41 to 57) |

Of the 76 products with a disagreement, the scorer recognises 10 as
kilojoules read as kcal and 2 where nothing was read.

## Who is wrong? 20 disagreements checked by eye

The database is typed in by volunteers, and a product's recipe changes over
time, so a disagreement is not automatically the reader's fault. 20 of the
76 were picked at random (fixed seed) and checked against the photo
([`labeling/labels/audit_20.jsonl`](labeling/labels/audit_20.jsonl)):

| Verdict | Products |
|---|---|
| **Reader wrong** | **13** |
| … value from the wrong row (saturated fat as fat, salt or fibre as protein, rows swapped) | 8 |
| … kilojoules taken for kcal | 3 |
| … decimal comma lost ("3,7 g" read as 37) | 1 |
| … per-portion column instead of per 100 g | 1 |
| **Reader right**, database wrong or a different version of the product | **7** |

So about two thirds of disagreements are the reader's. Applied to all 76,
the reader gets all four values right for an estimated **67%** of products
(the uncertainty of a 20-product check puts it between about 59 and 78%).

Misaligned tables (values printed a line below their label, as on a curved
pack) cause most of the wrong-row mistakes. Labels in several languages at
once and tiny print make it worse.

## A cheap safety net

Calories follow from the macros: about 9 kcal per gram of fat and 4 per gram
of carbs or protein. When the reading breaks that sum by more than about
20%, something was misread:

| Flag when calories and 9 × fat + 4 × (carbs + protein) differ by more than 20% | |
|---|---|
| audited reader mistakes caught | 8 of 13 |
| fully right readings flagged (false alarm) | 1 of 74 |
| readings that were right where the database was wrong, flagged | 0 of 7 |

It catches every kJ and decimal mistake and most row swaps; swaps between
two values of similar size slip through. The threshold was chosen on this
same data, so these numbers are a first estimate, not a held-out result.

Since D36 the app runs this check on every label reading and shows a
warning before the values are used.

## How far off: the size of the errors

Right or wrong hides whether a wrong value is 2 kcal or 400 kcal off. Reader
minus database, per 100 g (`score_labels.py` prints these tables). The
database itself is wrong for some products (see the check above), so these
are upper bounds on the reader's error:

| All 150 readings | Typical | Average | Worst 10% | Within 5% | Within 10% | Within 20% |
|---|---|---|---|---|---|---|
| kcal | 0 | 44 kcal | 58 kcal | 81% | 86% | 89% |
| protein | 0 | 1.5 g | 4.8 g | 74% | 79% | 84% |
| carbs | 0 | 1.8 g | 3.8 g | 80% | 85% | 94% |
| fat | 0 | 2.2 g | 6.6 g | 81% | 84% | 85% |

| The 124 readings that pass the sum check | Typical | Average | Worst 10% | Within 5% | Within 10% | Within 20% |
|---|---|---|---|---|---|---|
| kcal | 0 | **11 kcal** | 20 kcal | 88% | 94% | 96% |
| protein | 0 | 1.0 g | 1.7 g | 79% | 85% | 90% |
| carbs | 0 | 1.4 g | 3.3 g | 81% | 86% | 95% |
| fat | 0 | 1.0 g | 1.2 g | 87% | 90% | 91% |

Most readings are exact ("typical" is the median). The average is pulled up
by a few large mistakes, mostly kilojoules taken for kcal; the sum check
removes most of those. For a 100 g portion an unflagged reading is off by
about 11 kcal on average, against a daily budget near 2,000.

**The recipes' own numbers.** Recipe nutrition comes from food.com, not
from Forkcast. Whether it is *true* can't be checked without weighed,
analysed meals, but whether it is *consistent* can: for 89% of the 87,849
recipes the stated calories are within 10% of 9 × fat + 4 × (carbs +
protein) (typical gap 3%). The macros arrive as rounded "% daily value", so
they move in steps of a few grams.

**Cost and speed:** about 2,100 tokens in and 60 out per photo, about
$0.0024 at Haiku 4.5 list prices, 1.6 seconds (median).

## What this does and doesn't measure

- Contributors' photos, often of foreign-language or multi-language packs.
  German-only labels with "Nährwerte je 100 g" are probably easier.
- The reference is the database, corrected only for the 20 checked
  products; the 67% is an estimate from that check.
- Barcode reading was not tested: nutrition-table photos rarely show the
  barcode. When the barcode is read and found in Open Food Facts, the app
  uses the database values instead of the reading.

## What to do next

1. ~~**The sum check on the "add from label" screen.**~~ Done (D36).
2. **The prompt:** name the three mistakes (kcal not kJ, keep decimal
   commas, fat is the "Fett" row and not "davon gesättigte"), then measure
   again on a fresh sample.
3. **Prefer the barcode:** when a barcode is in Open Food Facts, its values
   win; scanning the barcode first avoids reading the table at all.
