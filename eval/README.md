# Forkcast evaluation

Datasets, labels and scripts that measure whether Forkcast does what it
claims. The data comes from **outside the app's code**: ingredient strings
sampled from the published recipe corpus, and real grocery product names from
the Instacart Market Basket dataset. It is labelled **blind**, without seeing
what Forkcast's matcher predicts. Stage 3 needs no labels: real food.com
users' ratings are the answer key. The scripts import the app only to run it
as the system under test.

| Path | What it is |
|---|---|
| [`RESULTS.md`](RESULTS.md) | stage 1 scorecard and findings |
| [`RESULTS-stage2.md`](RESULTS-stage2.md) | stage 2 (substitutions) scorecard and findings |
| [`RESULTS-stage3.md`](RESULTS-stage3.md) | stage 3 (taste ranking) results and findings |
| [`RESULTS-stage4.md`](RESULTS-stage4.md) | stage 4 (photo scanning) results and findings |
| `data/vision_gold.json` | stage 4 answer key: the right ingredients for each of the 81 Grocery Store Dataset products |
| `data/taste_users.json` | the frozen dev/test split of 5,419 food.com users for stage 3 |
| `data/strings.jsonl`, `data/holdout.jsonl` | 275 development and 150 held-out ingredient strings |
| `data/*_labeled.jsonl` | the same rows with gold labels |
| `data/kitchens.json`, `data/kitchens_holdout.json`, `data/kitchens_holdout2.json` | test kitchens in plain words (3 development, 1 + 3 held-out) |
| `data/vocab.txt` | Epicure's 1,790 ingredient names, the label space |
| `data/subs_cases.jsonl`, `data/subs_holdout.jsonl` | 90 development and 60 held-out substitution cases |
| `data/kitchens_subs_holdout.json` | first stage 2 held-out kitchens (stir-fry, taqueria) |
| `data/kitchens_subs_holdout2.json`, `data/subs_holdout2.jsonl` | fresh held-out kitchens (brunch, curry) and their 60 cases, for judging the D28 fix |
| [`data/LABELING.md`](data/LABELING.md) | labelling rules for all three tasks |
| `labeling/` | shortlists, raw labels, engine outputs, cookable judgements; `labeling/marker_b/` holds the second marker's judgements |
| `scripts/` | sampling, labelling helpers, engine runner, scorer |

**Stages:**
1. Ingredient matching and "cookable now" precision: **done**, then tightened
   with a blind second marker (GPT-6 Astra), a human review of every disagreement
   and three more held-out kitchens (see "Tightening" in
   [`RESULTS.md`](RESULTS.md)). A second matcher fix (D29) was judged on a
   further fresh set: 150 strings and three kitchens (`data/holdout3*.jsonl`,
   `data/kitchens_holdout3.json`), double-marked like the rest.
2. Substitutions: **done**, fixed by D28 (see
   [`RESULTS-stage2.md`](RESULTS-stage2.md)).
3. Taste ranking: **done.** 2,710 real food.com users replayed through the
   app (see [`RESULTS-stage3.md`](RESULTS-stage3.md)). The first version, one
   average of everything you cooked, barely beat a coin flip; comparing with
   your nearest dishes (D31) raised "what they cook next" from 55 to 61 but
   still doesn't pick favourites.
4. Photo scanning: **first half done.** Store photos from a public
   dataset through the app's scanner and matcher (see
   [`RESULTS-stage4.md`](RESULTS-stage4.md)): 65% at first, a third of the
   misses the matcher's. The matcher fix (D35), judged on 289 validation
   photos it wasn't designed on, raised it from 71% to 76%. Still to do: real
   shopping photos.
