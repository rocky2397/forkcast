# Stage 1 results: ingredient matching and "cookable now"

Run on 2026-11-14 against three versions:

| Version | Code | Corpus |
|---|---|---|
| **old** | `96c1f04` | `corpus-20260811` |
| **cur** | `fc3bec4` (D24–D26 matcher fixes) | `corpus-20261114` |
| **fixed** | D27 product phrases | `corpus-20261114` re-normalized with D27, published byte-identical as `corpus-20261114-d27` |

The fix was designed after looking at the **development** set, so the
**held-out** set is the number to trust. It was sampled with a different seed,
excludes every development text, and was labelled before the fixed matcher
was run on it. The fourth kitchen was likewise not looked at during design.

## "Cookable now": precision@20

Share of the base engine's top 20 recipes (fewest missing, then most
ingredients) that a cook could actually make from the kitchen plus the pantry
staples. Judged from each recipe's raw ingredient wording.

| Kitchen | old | cur | fixed |
|---|---|---|---|
| Mediterranean (dev) | 12/20 | 13/20 | 19/20 |
| Student (dev) | 12/20 | 12/20 | 18/20 |
| Baking (dev) | 12/20 | 12/20 | 19/20 |
| **Stir-fry (held-out)** | **13/20 = 65%** | **13/20 = 65%** | **16/20 = 80%** |
| Vegetarian (held-out 2) | | | 17/20 |
| Grill (held-out 2) | | | 15/20 |
| Italian (held-out 2) | | | 17/20 |
| **All four held-out kitchens** | | | **65/80 = 81%** (95% CI 71–88%) |

On the development kitchens precision goes from 61.7% (cur) to 93.3% (fixed),
which overstates the effect: the fix was built from those false positives.
The three "held-out 2" kitchens were added later (see "Tightening" below) and
were judged for the current engine only.

## Ingredient matching

Accuracy / **wrong-match rate** / recall, in %. A wrong match is the costly
error, because it makes a recipe look cookable. A miss only drops it.

| Set | n | old | cur | fixed |
|---|---|---|---|---|
| held-out A: food.com rows | 50 | 86.0 / **6.0** / 85.7 | 86.0 / **6.0** / 85.7 | 86.0 / **4.0** / 85.7 |
| held-out B: food.com tail | 50 | 54.0 / **30.0** / 59.1 | 58.0 / **26.0** / 63.6 | 60.0 / **24.0** / 63.6 |
| held-out C: grocery names | 50 | 76.0 / **24.0** / 78.3 | 80.0 / **20.0** / 82.6 | 82.0 / **14.0** / 84.8 |
| **held-out, all** | 150 | 72.0 / **20.0** / 74.8 | 74.7 / **17.3** / 77.7 | **76.0 / 14.0 / 78.4** |
| dev, all | 275 | 75.3 / **17.5** / 77.6 | 76.0 / **16.7** / 78.4 | 79.3 / **9.5** / 81.1 |

## What the eval found

**One error class caused 22 of the 23 false "cookable" recipes in the
development kitchens.** When the vocabulary has no entry for a processed
product, the matcher fell back to the food word inside it: powdered sugar became
the sugar staple (3,451 rows including "confectioners sugar"), chicken stock
became chicken (1,703), tomato paste became tomato (1,448), bouillon became
chicken or beef. Sometimes the right entry existed and still lost: `basil pesto`
→ basil, `sun-dried tomato packed in oil` → tomato.

**The fix (D27)** makes such a phrase match the product or nothing: `basil
pesto` → pesto, `Vanilla Skyr Nonfat Yogurt` → yogurt, `chicken stock` → no
match. Across the whole corpus it moves 765 strings (18,843 rows) to "no match"
and 229 strings (3,315 rows) to a different name.

**The cost is coverage.** Fully matched recipes, the only ones the feed
considers, drop from 64,375 to 52,367. The 12,008 that leave mostly need tomato
sauce, stock or powdered sugar, which an inventory of base foods doesn't
contain. That trade is deliberate: a short honest list beats a long one that
lies.

## What is still wrong

- **Remaining false "cookable"** (fixed): instant potato flakes, potato chips,
  French fried onions, unsweetened chocolate, chicken sausage, and "peas and
  carrots" counted as satisfied by carrots alone.
- **Remaining wrong matches** are mostly prepared foods matched by their first
  food word (`Organic Raisin Bread` → raisin, `Chicken Flavor Top Ramen Noodles`
  → chicken, `Macaroni & Cheese` → cheese) and flavoured products (`chocolate
  syrup` → chocolate, `vanilla wafer` → vanilla).
- **New misses from D27**, found on the held-out set and left unfixed so the
  held-out numbers stay honest: `sofrito sauce`, `… Balsamic Vinaigrette …
  Dressing`, and the plural `sun-dried tomatoes packed in oil`.

## Tightening: a second marker, a human review, more kitchens

Added on 2026-11-14, after the results above, to address the two weak spots:
one labeller, and a held-out kitchen of only 20 recipes.

**A second, independent marker.** Codex (GPT-6 Astra) relabelled all 425
ingredient strings and judged all 108 recipes from scratch. It worked in a
separate private repository that contained only the questions, the rules and
a format checker: no first-marker labels, no app answers, and no Forkcast
code. Its labels are kept in `data/*_labeled.jsonl` (`marker_b`) and
[`labeling/marker_b/`](labeling/marker_b/).

| Agreement between the two markers | |
|---|---|
| Ingredient strings, identical answer | 362/425 = 85% |
| Ingredient strings, compatible (share a name, or both "no ingredient") | 396/425 = 93% |
| Cookable judgements | 95/108 = 88%, Cohen's kappa 0.75 |

**A human settled the disagreements** with four policy decisions, now rules
9–12 in [`data/LABELING.md`](data/LABELING.md): dried and seasoned forms count
(garlic powder or garlic salt is satisfied by fresh garlic), a branded product
takes the broad entry (cereal, candy, syrup), half-and-half counts as cream,
and two defensible entries are both correct. Twelve of the thirteen recipe
disagreements were the garlic-powder question alone. It matters: had it gone
the other way, the held-out stir-fry kitchen would score 14/20 instead of
16/20, and the development kitchens 46/60 instead of 56/60. Every label now
records how it was settled, and none is left unsure. The headline numbers
above are unchanged by the review.

**Three more held-out kitchens** (vegetarian, grill, italian) were written and
committed before the engine ran on them. Both markers judged their 60 recipes
blind and agreed on all 60. One caveat: the second marker's rules for this
round were written after the first marker had judged, and besides the human
decisions they spell out a few examples that follow from the existing rules
(canned tomatoes count as tomatoes, another pasta shape counts, a bottled juice
is a product). That may have pulled the markers closer.

What the new kitchens add: **65 of 80 held-out recipes are really cookable
(81%, 95% CI 71–88%)**, close to the single kitchen's 80% but with half the
uncertainty. Of the 11 new false "cookable" recipes, nine need a ready-made
product the kitchen doesn't have: tomato juice (twice, once with carrot
juice), diced tomatoes with chilies, creamed corn, pork and beans,
Rice-a-Roni, corn flake crumbs and chicken sausage. The other two need a bell
pepper the kitchen lacks, written in a way the matcher misreads: "sweet green
pepper" becomes the black-pepper staple, "red pepper" the chili flakes. The
product misses are D27's error class again, for words D27 doesn't list:
`tomato juice` → tomato, `creamed corn` → corn, `chicken sausage` → chicken.
That is the obvious next fix, to be judged on yet another fresh kitchen.

## Caveats

- **Two model markers and one human decision-maker, no human marker.** The
  labels come from Claude (Opus) and Codex (GPT-6 Astra) working blind and
  apart; a human only decided the policy questions where they disagreed.
- **Small samples.** The before/after comparison still rests on the stir-fry
  kitchen alone (n = 20, 95% interval roughly 58–92% around 80%), so read
  "65% → 80%" as a direction. The current engine's level is better pinned:
  81% over 80 held-out recipes (71–88%).
- **The old matcher was not deterministic** (fixed by D24): equal-length names
  were tie-broken by hash order, so "old" numbers wobble by about a point
  between runs.
- **Base ranking only.** The app re-orders the same pool by taste and macros.
  That changes which recipes come first, not whether a listed recipe is
  cookable.

## Reproduce

From this directory, with a Forkcast checkout and its dependencies:

```bash
python scripts/sample_strings.py <corpus.db> <instacart_dir> data/strings.jsonl
python scripts/sample_strings.py <corpus.db> <instacart_dir> data/holdout.jsonl \
    --seed 1114 --sizes 50,50,50 --exclude data/strings.jsonl
python scripts/candidates.py data/strings.jsonl data/vocab.txt > labeling/candidates.jsonl
python scripts/build_labels.py      # and with the holdout arguments
python scripts/run_cookable.py <checkout> <corpus.db> data/kitchens.json labeling/cookable_<v>.json
python scripts/run_cookable.py <checkout> <corpus.db> data/kitchens_holdout.json labeling/holdout_cookable_<v>.json
python scripts/score.py old=<checkout> cur=<checkout> fixed=<checkout> --details
```

**Sources:**
- **food.com strings:** from the published Forkcast corpus releases.
- **Grocery names:** from the Instacart Market Basket dataset (Hugging Face
  mirror `attik/Instacart-Market-Basket-Analysis`), weighted by purchases in
  `order_products__train`.
- **Label space:** Epicure's vocabulary (CC BY 4.0).
