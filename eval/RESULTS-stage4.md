# Stage 4: photo scanning

**Question:** you photograph your groceries. Does Forkcast end up proposing
the right ingredient?

**Short answer:** at first for 65% of photos (95% interval 61 to 70%).
About a third of the misses were not the camera's fault: the model named the
item correctly and Forkcast's ingredient matcher then turned it into the
wrong ingredient, most often "orange juice" into *orange*. After fixing the
matcher (D35), on 289 photos not used to design the fix: **76%** (71 to 81),
with vegetables at 85%, fruit 76% and cartons 69%. What is left is mostly the
camera: similar-looking fruit and look-alike cartons. Nothing is saved
without you ticking it on the confirm screen, but that screen shows the
matched ingredient, so a wrong match still looks just like a right one.

## What was tested

- **Photos:** 405 from the [Grocery Store Dataset](https://github.com/marcusklasson/GroceryStoreDataset)
  (Klasson et al., WACV 2019, MIT licence): phone photos taken in Swedish
  grocery stores, 5 for each of its 81 kinds of fruit, vegetables and carton
  products (milk, juice, yoghurt, sour cream), from its test split.
- **System under test:** the app's scanner exactly as shipped
  (`backend/app/vision.py`: Claude Haiku 4.5, its prompt and output schema),
  then the app's own matcher, as in the app.
- **Answer key:** [`data/vision_gold.json`](data/vision_gold.json). For each
  of the 81 products, the Forkcast ingredient names that count as right, for
  example *apple* for any apple variety, *fruit juice* for every juice (the
  ingredient list has no orange or apple juice, and *orange* would claim you
  have oranges), *bell pepper* for every pepper colour. Written from the
  ingredient list alone, before any scanner output was seen.
- **Scoring:** a photo counts as found when one of the proposals is a right
  ingredient. Store photos often show neighbouring products too, so extra
  proposals (2.0 per photo on average) are not counted against it.

Scripts: [`scripts/run_vision.py`](scripts/run_vision.py),
[`scripts/score_vision.py`](scripts/score_vision.py),
[`scripts/rematch_vision.py`](scripts/rematch_vision.py) (re-match a run's
answers with the current matcher). Every proposal is in `labeling/vision/`:
`haiku-4-5_test5.jsonl` as run, `_test5_d35` re-matched, and the validation
run `_val5_before` / `_val5_d35`.

## Results

| | Photos | Right ingredient proposed |
|---|---|---|
| **All** | 405 | **65%** (61 to 70) |
| Vegetables | 110 | 85% (77 to 90) |
| Fruit | 140 | 65% (57 to 72) |
| Cartons | 155 | 52% (44 to 60) |

Where the 140 misses come from:

| Cause | Photos | Examples |
|---|---|---|
| **Named right, matched wrong** (matcher) | 43 | "orange juice" → *orange* (27 of the 50 juice photos), "juice" → nothing, "soya milk" → *milk*, "kiwi fruit" → *fruit* |
| **Seen as something similar** (vision) | most of the other 97 | nectarine → apple, papaya → mango, passion fruit → plum, satsuma and red grapefruit → orange, sweet potato → potato |
| **Carton read as a neighbour** (vision) | | Swedish sour cream and soy yoghurt cartons read as "cream" or "milk" |

**The model's confidence doesn't warn you.** Every one of the 140 misses
had a proposal the model was at least 80% sure of, so the "% sure" on the
confirm screen can't separate right from wrong here.

**Cost and speed:** about $0.001 per scan and 1.1 seconds (median) on these
small photos (348 × 348 pixels, about 700 tokens in, 50 out). A full-size
phone photo is resized by the API to roughly 1,600 image tokens, so a real
scan costs nearer $0.002: about $2 per 1,000 scans.

## After the matcher fix (D35)

The fix changes only how names are matched, so it can be judged on the
model's existing answers. To keep it honest it was judged on photos it was
not designed on: 289 from the dataset's separate validation split (5 per
product where there are 5), run through the scanner once and then scored
with the old and the new matcher.

| Validation photos (289) | Old matcher | **New matcher** |
|---|---|---|
| **All** | 71% (65 to 76) | **76%** (71 to 81) |
| Vegetables | 85% | 85% |
| Fruit | 74% | 76% |
| Cartons | 55% | **69%** |
| Named right, matched wrong | 25 photos | 9 photos |

The 9 left are camera mistakes the word check can't tell apart: soy and oat
yoghurt cartons read as "soy milk" or "oat milk". On the test photos the fix
was designed on, 65% became 75%; that number flatters it, so it isn't the
headline.

What changed: a carton read as "orange juice" (or any citrus juice, or just
"juice") is now *fruit juice* rather than the fruit. A recipe's "juice of 2
oranges" is still orange, because there the juice does come from the fruit.
British and European names now match (yoghurt, soya milk, aubergine,
courgette, beetroot, kiwi fruit, satsuma, mandarin), and flavoured milk is
milk rather than its flavour. Checks that it breaks nothing: the 575
labelled ingredient strings from stages 1 and 2 (one better, none worse),
and the whole recipe corpus (25 strings in 511 of 794,000 recipe rows move,
all to the right name; published in corpus release `corpus-20261115-d35`).

## What this does and doesn't measure

- **Harder than your kitchen in some ways:** small, low-resolution photos
  taken in a shop, often with other products in view, and Swedish
  packaging (*gräddfil*, *filmjölk*). The prompt was written for German
  packaging.
- **Easier in others:** one kind of item per photo. Forkcast's real use is
  a photo of a whole shopping haul, several items at once. This set says
  nothing about that, so it needs the planned second half: 20 to 30 photos
  of real shopping, labelled blind.
- **One model:** Claude Haiku 4.5, the one the app uses. Claude Haiku 5.5 is
  newer and a tenth of the price, but the API credential used here was
  refused for it (rate limited on every request), so it is not compared yet.

## What to fix first

1. ~~**The matcher, for drinks and dairy.**~~ Done (D35), see above.
2. **The confirm screen:** show what the model saw next to the matched
   ingredient ("orange juice → Orange"), so a wrong match is visible.
3. **The real-shopping set,** before calling scanning done.
