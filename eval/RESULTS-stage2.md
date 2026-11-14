# Stage 2 results: substitutions

When a recipe is missing one ingredient, Forkcast shows a hint like "needs
lime, try lemon", with the stand-in taken from your inventory (D13). Stage 2
asks: **would a cook actually use what it suggests?**

Run on 2026-11-14 against `main` at `e69129b` (substitution engine unchanged
since D13) and corpus `corpus-20261114-d27`.

## Method

- **Cases.** For each test kitchen, the base "Missing ≤ 1" list (fewest
  missing, then most ingredients) is walked from the top, keeping recipes that
  miss exactly one ingredient, at most 3 per missing ingredient so no single
  item dominates. 30 per kitchen.
- **Candidates** are what the app hands the engine: the kitchen's items not
  already in the recipe. Pantry staples are left out, since the engine never
  offers them.
- **Labels.** For each case, every candidate a cook would use instead is
  marked **good** (dish stays the same) or **ok** (workable, but the dish
  changes), following [`data/LABELING.md`](data/LABELING.md). All 150 cases
  were labelled and committed (`9face0f`) before the engine was run on any of
  them.
- **Development:** the three stage 1 kitchens (90 cases). **Held-out:** the
  stage 1 stir-fry kitchen plus a new taqueria kitchen (60 cases).

## Scorecard

| | development | held-out |
|---|---|---|
| Cases where a suggestion is shown | 81/90 (90%) | 51/60 (85%) |
| **Precision of shown suggestions** (good or ok) | 29/81 = 35.8% | **23/51 = 45.1%** (95% CI 32–59%) |
| Precision, strict (good only) | 12/81 = 14.8% | 12/51 = 23.5% |
| **Bad suggestions**, share of all cases | 52/90 = 57.8% | **28/60 = 46.7%** |
| Recall, cases with a usable stand-in | 29/40 = 72.5% | 23/40 = 57.5% |

Nothing was tuned, so both columns are a baseline. The held-out column checks
that the result isn't an artefact of the first three kitchens.

**In plain words:** the engine almost always says something, and more often
than not what it says is wrong. The D13 docstring promises "precision over
recall"; on the cases the app actually shows, it is the other way round.

## What the eval found

**The class gate works; the fallback doesn't.** D13 has two paths:

| Path | development | held-out |
|---|---|---|
| Missing ingredient is in one of the 8 hand-made classes (herb, citrus, meat, …) | 19/22 acceptable | 9/12 acceptable |
| No class, so only the embedding rank gate decides | **10/59** acceptable | **14/39** acceptable |

Only 23 of the 90 development and 17 of the 60 held-out missing ingredients
have a class. Everything else (spices, nuts, fruit, most vegetables, broths,
vinegars, sauces, leaveners, fats) falls through to the rank gate: cooc rank
≤ 200 and chem rank ≤ 400 out of 1,790. In a 20-item kitchen, something
almost always passes.

**Ranks can't tell a substitute from a complement.** The closest pairs are
often foods that go *together*: `coconut → banana` (cooc rank 1, chem rank 2),
`coffee → chocolate` (2, 2), `pecan → chocolate` (5, 4). That is the effect
D13 itself documents for duck and ginger. The class map was the fix for it, but
it only covers 8 classes.

**Typical bad suggestions:**
- broths → vegetables: `chicken broth → bell pepper` (4 times across both
  sets), `beef broth → carrot`;
- leaveners and fats → whatever is in the cupboard: `baking powder → oats`,
  `shortening → oats`, `lard → mayonnaise`;
- spices → baking ingredients: `nutmeg → apple`, `nutmeg → raisins`,
  `cloves → baking powder`;
- sauces → starches: `hoisin sauce → rice noodles`, `salsa → corn tortillas`,
  `enchilada sauce → monterey jack`.

D13 was validated on 17 hand-picked regression pairs, which still pass. They
just aren't the pairs the app meets in practice.

## What a fix would look like (not done)

1. **Cover more of the vocabulary with classes:** spices, nuts and seeds,
   fresh and dried fruit, vegetables by role, broths and stocks, vinegars,
   fats, leaveners, flours, sauces.
2. **Make the unclassed path silent,** or far stricter. A missing hint costs a
   suggestion; a bad one costs trust.

As a rough guide, on the development set alone: if the unclassed path were
silent, precision would be 19/22 = 86% and recall 19/40 = 48%.

**A fix must be checked on a fresh held-out kitchen.** The held-out bad
suggestions above were read for this write-up, so that set is no longer blind
for a fix designed now.

## Caveats

- **One labeller.** All labels are by Claude (Opus), following the written
  rules. 9 cases are flagged unsure. "Ok" is a judgement call (is oregano ok
  for parsley in chili?), and the strict row shows how much rides on it.
- **Single swaps only.** A stand-in that only works combined with another
  item (milk plus lemon for buttermilk) counts as "ok" at best.
- **The matcher's mistakes carry over.** `taqueria-16` needs red bell peppers,
  but the matcher named it `red_pepper` and the engine offered jalapeño.
  Stage 1 errors upstream make some stage 2 cases harder.
- **Small samples.** n = 51 suggestions on the held-out set gives a 95%
  interval of about 32–59% around 45%.

## Reproduce

From this directory, with a Forkcast checkout and its dependencies:

```bash
python scripts/build_sub_cases.py <checkout> <corpus.db> data/kitchens.json data/subs_cases.jsonl
python scripts/build_sub_cases.py <checkout> <corpus.db> data/kitchens_subs_holdout.json data/subs_holdout.jsonl
python scripts/run_subs.py <checkout> data/subs_cases.jsonl labeling/subs/engine_cases.json
python scripts/run_subs.py <checkout> data/subs_holdout.jsonl labeling/subs/engine_holdout.json
python scripts/score_subs.py labeling/subs/labels_dev.tsv dev=labeling/subs/engine_cases.json --details
python scripts/score_subs.py labeling/subs/labels_holdout.tsv holdout=labeling/subs/engine_holdout.json
```
