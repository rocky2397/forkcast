# Stage 7: typed foods against EU labels

**Question:** you type "Haferflocken, 50 g" into Log a meal (D49). Do
Forkcast's calories, protein, carbs and fat match the label on the pack you
actually bought?

**Short answer:** after two fixes, the calories of **76%** of held-out
products are within 10% of their label (64% before), and carbs within 3 g for
**76%** (36% before). Every typed word now finds a food (85% before). The
values came from US tables, which count fibre as carbohydrate; EU labels
don't. And German compound words ("Vollmilch", "Weizenmehl") found nothing.
What is left is real: one milk and one yogurt where German shelves have
several fat levels, and canned beans that hold more water than boiled ones.
On 12 more kinds fetched later, the carb fix held (31% to 50% within 3 g),
but calories didn't move: their gain came from the words the app now finds.

## What was tested

- **Products:** single-ingredient foods sold in Germany, from
  [Open Food Facts](https://world.openfoodfacts.org) (data © Open Food Facts
  contributors, [ODbL](https://opendatacommons.org/licenses/odbl/1-0/)),
  frozen in [`data/foods_off.json`](data/foods_off.json). For each kind of
  food: the 4 most-scanned products with all four values per 100 g and one
  or two ingredients (salt allowed).
- **The answer key came first.** [`scripts/sample_foods.py`](scripts/sample_foods.py)
  lists 33 kinds, each with the German word a person would type
  ("Haferflocken", "fettarme Milch") and whether it's bought ready to eat
  (canned chickpeas: the app's "weighed cooked"). The words were fixed before
  any value was compared, and a word the app can't find counts as wrong.
- **Two halves.** The kinds were split at random (fixed seed) into a dev half
  and a held-out half before anything was scored. Fixes were designed on dev
  and are judged on held-out.
- **System under test:** the app as in Log a meal: the matcher (German
  included, D47), then `backend/app/ingredient_nutrition.json` (D49).
- **Reference:** the label values in Open Food Facts. A product counts as
  right when its calories are within 10% of the label; carbs separately when
  within 3 g per 100 g.

### Only 21 of the 33 kinds at first

Open Food Facts throttled the search after 21 kinds (instant "503
temporarily unavailable" for every search, for more than half an hour).
The 21 were frozen as they were, before any value was compared, each keeping
its half from the split of all 33: 12 dev kinds, 9 held-out. Not fetched:
walnuts, hazelnuts, raisins, honey, frozen spinach, frozen peas, passata,
low-fat quark, couscous, quinoa, coconut milk, flaxseed.

Two dev kinds have no products: gouda and whipping cream list milk, salt,
cultures and rennet or a stabiliser, more than the one-or-two-ingredient
rule allows, and mozzarella and canned kidney beans have only one each. That
leaves **70 products in 19 kinds**: 37 dev, 33 held-out.

## Results

| | Dev before | Dev after | **Held-out before** | **Held-out after** |
|---|---|---|---|---|
| Typed word finds a food | 78% | 100% | 85% | **100%** |
| Calories within 10% of the label | 65% | 86% | 64% | **76%** |
| Carbs within 3 g | 57% | 84% | 36% | **76%** |
| Median calories off (per 100 g) | 16 kcal | 12 kcal | 13 kcal | **10 kcal** |

Scripts: [`scripts/sample_foods.py`](scripts/sample_foods.py),
[`scripts/score_foods.py`](scripts/score_foods.py). Every comparison is in
`labeling/foods/before.jsonl` and `labeling/foods/after.jsonl` (the fresh
kinds below: `fresh_before.jsonl`, `fresh_after.jsonl`).

## What was wrong, and the two fixes (D53)

**1. US carbohydrate includes fibre; EU labels don't.** The USDA gives
carbohydrate "by difference", fibre included. An EU label lists fibre on its
own line and leaves it out of carbohydrate, and counts its energy at 2 kcal
per gram (Regulation 1169/2011, Annex XIV). Oats had 67.7 g carbs in the app
and 58 to 60 on German packs; lentils 14 g too many, almonds 17. The fix
converts every USDA value to EU labelling: carbohydrate minus fibre, energy
from the EU factors (4 per g of protein and carbohydrate, 9 per g of fat,
2 per g of fibre, 7 per g of alcohol). This is a rule, not a fit: it was
chosen from the regulation before any value was scored.

**2. German compound words found nothing.** "Vollmilch", "Weizenmehl",
"Basmatireis", "Kidneybohnen": German writes the main noun last, in one word.
The matcher now splits a word it doesn't know before the longest known German
word at its end and translates both parts: "Vollmilch" is "whole milk",
"Mandelmilch" "almond milk". It never matches the main noun alone, which would
make almond milk plain milk.

**3. One wrong food.** Checking the typed words showed "Haselnüsse"
reaching a US coffee creamer (SILK Hazelnut Creamer, 140 kcal per 100 g),
one of the rarer ingredients the word match had picked automatically (D49).
It now has real hazelnuts (654 kcal). Hazelnuts were among the 12 kinds not
yet fetched, so when they are scored they don't count as unseen. A check of
every automatic pick that names a brand found six more wrong foods (ray the
fish had a barbecue sauce, honeycomb a breakfast cereal), now fixed by hand
or left without values.

Designed on the dev words (Vollmilch, Weizenmehl). The held-out ones
(Basmatireis, Kidneybohnen) had been seen not to match when the words were
checked, but not their values, and nothing was written for them.

## A second check: 12 fresh kinds

Once Open Food Facts answered again, the 12 missing kinds were fetched
([`data/foods_off_fresh.json`](data/foods_off_fresh.json), `sample_foods.py
--fresh-after`). No fix was designed on them, so they judge D53 a second
time. Frozen peas and passata had no products with all four values and one
or two ingredients, which leaves 40 products in 10 kinds. Hazelnuts are left
out below: their wrong match (a coffee creamer) was fixed before they were
scored.

| 36 fresh products, 9 kinds | Before | After |
|---|---|---|
| Typed word finds a food | 78% | 78% |
| Calories within 10% of the label | 67% | 64% |
| Carbs within 3 g | 31% | **50%** |

**The fibre correction holds; the calorie part doesn't help here.** On
these foods the matcher found the same thing before and after, so only the
values changed: carbs within 3 g rose from 31% to 50%, calories within 10%
moved by one product (a frozen spinach). Recomputing energy from the EU
factors put honey at 330 kcal, the top of its labels (302 to 333), and
quinoa at 354, below its labels (371 to 390). So the gain in calories on
the first held-out half came from the words the app now finds, not from the
conversion. It stays: it is what EU labels do, and it makes a meal of
typed and scanned foods add up one way.

Still missing on fresh kinds: **quark** (no USDA values; scanning the pack
works, D51) and **"Leinsamen"** (flaxseed), a compound whose main noun,
Samen, isn't in the German word list. One raisin entry is a database error
(181 kcal and 1 g carbs for raisins).

## Kind by kind

Median difference from the label, per 100 g (app minus label).

| Kind | Typed | Half | Before | kcal | carbs | After | kcal | carbs |
|---|---|---|---|---|---|---|---|---|
| rolled oats | Haferflocken | held-out | oat | +7 | +9 | oat | −10 | −1 |
| basmati rice | Basmatireis | held-out | not found | | | basmati rice | −1 | +1 |
| dry pasta | Nudeln | held-out | pasta | +14 | +4 | pasta | 0 | +1 |
| canned chickpeas | Kichererbsen | held-out | chickpea | +44 | +12 | chickpea | +34 | +4 |
| canned kidney beans | Kidneybohnen | held-out | not found | | | kidney bean | +12 | +2 |
| sugar | Zucker | held-out | sugar | −13 | 0 | sugar | 0 | 0 |
| rapeseed oil | Rapsöl | held-out | oil | +56 | 0 | oil | +72 | 0 |
| plain yogurt | Naturjoghurt | held-out | yogurt | −13 | 0 | yogurt | −12 | 0 |
| feta | Feta | held-out | feta | −9 | +3 | feta | −8 | +3 |
| whole milk | Vollmilch | dev | not found | | | milk | −4 | 0 |
| semi-skimmed milk | fettarme Milch | dev | milk | +14 | 0 | milk | +14 | 0 |
| rice | Reis | dev | rice | +11 | +2 | rice | −2 | +1 |
| dry lentils | Linsen | dev | lentil | +14 | +14 | lentil | +2 | +3 |
| wheat flour | Weizenmehl | dev | not found | | | flour | +2 | +2 |
| butter | Butter | dev | butter | −18 | 0 | butter | −1 | 0 |
| olive oil | Olivenöl | dev | olive oil | +58 | 0 | olive oil | +74 | 0 |
| sunflower oil | Sonnenblumenöl | dev | oil | +56 | 0 | oil | +72 | 0 |
| mozzarella | Mozzarella | dev | mozzarella | −2 | −1 | mozzarella | −4 | −1 |
| almonds | Mandeln | dev | almond | −42 | +17 | almond | −26 | +4 |

**The oils are a reference problem, not an app one.** 10 of the 12 oil labels
in Open Food Facts say 824 to 828 kcal "per 100 g", 2 say 900: German oil
labels usually give values per 100 ml (100 ml of oil weighs about 92 g), and
those were typed into the per-100 g field. The app's 900 kcal per 100 g is what
an EU label per 100 g says, and all 12 oils are within 10% either way.

## The 13 products still off by more than 10%

Each was checked against the other products of its kind and its name. None is
a typo in the database:

| Cause | Products |
|---|---|
| **Another fat level than the app's one entry** | **9** |
| … semi-skimmed milk, 1.5% fat (the app has one milk, US whole, 3.25%) | 4 |
| … whole milk at 3.8% | 1 |
| … yogurt at 3.8% (2), low-fat at 1.8% (1), Greek style at 10% (1) | 4 |
| **Canned beans, which hold more water than beans boiled from dry** | **4** |
| … chickpeas: 113 to 122 kcal on the can, 153 in the app | 3 |
| … kidney beans: 104 against 116 | 1 |

Both are fixable, and neither was attempted here, since the held-out half has
now been used:

- **Fat levels:** milk and yogurt as German shelves have them (1.5%, 3.5 to
  3.8%, Greek style). The ingredient list (Epicure's 1,790 names) has one
  milk, so this needs a choice in the app, like the dry or cooked switch.
- **Canned beans:** a third form next to dry and cooked, from the USDA's
  canned and drained entries.

## How much to trust this

- **70 products is small.** One product moves a held-out number by 3 points.
- **Open Food Facts is the reference,** typed in by volunteers; the oils show
  it mixes per 100 g and per 100 ml.
- **Single-ingredient foods only.** What a person types is usually that
  (oats, rice, milk), but cheeses and creams, which list several
  ingredients, mostly fell out of the sample.
- **Germany only,** though Open Food Facts lists many of the same products
  across the EU, and EU labelling rules are the same everywhere.
