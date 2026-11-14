# Labelling guide: ingredient strings (stage 1)

Each string gets a **gold set**: the Epicure vocabulary names (`data/vocab.txt`,
1,790 entries) that a cook would accept as *having this ingredient*. That is the
question Forkcast's matcher answers, because the match decides whether a recipe
counts as cookable from your inventory.

Labels are made **without seeing Forkcast's prediction**. The shortlist in
`labeling/candidates.jsonl` comes from a naive word/trigram search, not from the
matcher, and any vocabulary name may be chosen.

## Rules

1. **Same food, different form → the food.** Chopped, sliced, canned, frozen,
   dried herbs, ground spices, peeled, organic, brand names: `dried basil leaves`
   → `basil`, `Organic Lemon` → `lemon`.
2. **Variety → the specific entry if it exists, plus the general one** when a
   recipe would accept the general food: `red bell pepper` →
   `{bell_pepper}`, `plum tomatoes` → `{tomato}`, `cherry tomatoes` → `{tomato}`.
3. **A processed product is its own ingredient.** Juice, broth, stock, sauce,
   paste, soup, powder, jam, liqueur, cereal: label the product's own vocabulary
   entry if one exists (`tomato_paste`, `chicken_broth`), otherwise the empty
   set. Mapping `tomato sauce` to `tomato` is a **wrong match**: it would make a
   recipe look cookable from something you don't have.
4. **Composite or prepared foods** (frozen meals, filled snacks, cereals by
   brand, cookies) → the empty set unless the vocabulary has the product itself.
5. **Several ingredients in one string** (`salt and pepper`) → the set of
   components; any one counts as correct, and the row is flagged `multi`.
6. **Not an ingredient** (fragments like `juice of`, equipment, water-only
   instructions) → the empty set.
7. **Settled while labelling** (the vocabulary has no finer entries):
   dried fruit → the fruit; juice, zest or rind of a fresh fruit → the fruit
   (you get it from the fruit), but a bottled juice product (`cranberry juice
   cocktail`) → `fruit_juice`; flavoured dairy (`Honey Greek Yogurt`) → the
   dairy base; a cut or organ of an animal → the animal, or the organ's own
   entry if one exists (`sheep liver` → `liver`).
8. **Unsure** → add `"unsure": true` and a short note. Unsure rows are reported
   separately and are the first ones for a human to review.

## Scoring (per row)

| Prediction | Gold set | Outcome |
|---|---|---|
| a name in the gold set | non-empty | **correct** |
| a name not in the gold set | any | **wrong match**: the costly error |
| none | non-empty | **missed**: safe, the recipe just drops out |
| none | empty | **correct abstain** |

Reported: accuracy (correct + correct abstain), **wrong-match rate**, and
recall on rows that have a gold ingredient.

# Labelling guide: "cookable now" (stage 1)

`data/kitchens.json` holds three test kitchens in plain words. For each one, the
union of the old and new engine's top 20 recipes is judged from the recipe's
**raw ingredient wording only**, without the matched names and without knowing
which version listed it.

A recipe is **cookable** if every ingredient is in the kitchen or is a pantry
staple Forkcast assumes (salt, pepper, water, sugar, oil, butter, flour). The
same food in another form counts, using the rules above (a ground spice for its
fresh form, any tomato variety, juice from a lemon you have, a different cut of
the same animal). A processed product the kitchen doesn't contain makes the
recipe **not cookable**: stock, bouillon, tomato paste, pesto, jarred sauce,
powdered sugar, extracts other than vanilla, chips. Each "no" records the
missing ingredient.

Reported: **precision@20** per kitchen and overall, the share of listed recipes
that are really cookable.

# Labelling guide: substitutions (stage 2)

`data/subs_cases.jsonl` (development) and `data/subs_holdout.jsonl` (held-out)
hold one case per recipe that a test kitchen can almost cook: the recipe, its
raw ingredient wording, the **one missing ingredient**, and the **candidates**,
which are the kitchen's items not already in the recipe (pantry staples left
out). They are exactly what the app hands to its substitution engine.

Each case gets two lists, chosen from the candidates only, **without seeing
what the engine suggests**:

- **good**: a swap a cook would make without hesitation, and the dish stays
  recognisably the same (`lime` → `lemon`, `turkey` → `chicken`, `sour cream`
  → `greek yogurt` in a dip).
- **ok**: workable, but the dish noticeably changes (`parsley` for `cilantro`,
  `honey` for `maple syrup` in a glaze).

Everything else is a bad suggestion. In particular:

1. **Judge in this recipe.** `yogurt` for `cream` can be good in a marinade
   and wrong in whipped cream.
2. **A complement is not a substitute.** Ginger goes with garlic but does not
   replace it.
3. **The role matters more than the family.** A herb for a herb is fine as a
   garnish; a different main protein in a dish named after the missing one
   (`Chicken Parmesan` without chicken) is at best ok.
4. **Read the raw wording.** If the matcher named the missing ingredient wrong
   (a stage 1 error), judge against what the recipe really needs, and flag the
   case `"mismatch": true`.
5. **Unsure** → `"unsure": true` and a short note.

## Scoring (per case)

| Engine output | Labels | Outcome |
|---|---|---|
| a candidate in good or ok | | **correct** (strict: only if in good) |
| a candidate in neither | | **bad suggestion**: the costly error |
| nothing | good or ok non-empty | **missed**: the cook loses a hint |
| nothing | both empty | **correct silence** |

Reported: **precision of shown suggestions** (lenient and strict), the
bad-suggestion rate over all cases, recall over cases that have a usable
candidate, and how often the engine suggests anything.
