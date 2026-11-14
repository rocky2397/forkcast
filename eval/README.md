# Forkcast evaluation

Datasets, labels and scripts that measure whether Forkcast does what it
claims. The data comes from **outside the app's code**: ingredient strings
sampled from the published recipe corpus, and real grocery product names from
the Instacart Market Basket dataset. It is labelled **blind**, without seeing
what Forkcast's matcher predicts. The scripts import the app only to run it as
the system under test.

| Path | What it is |
|---|---|
| [`RESULTS.md`](RESULTS.md) | stage 1 scorecard and findings |
| [`RESULTS-stage2.md`](RESULTS-stage2.md) | stage 2 (substitutions) scorecard and findings |
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
   [`RESULTS.md`](RESULTS.md)).
2. Substitutions: **done**, fixed by D28 (see
   [`RESULTS-stage2.md`](RESULTS-stage2.md)).
3. Taste ranking: **parked.** The plan is to replay real food.com users'
   ratings: log part of a user's history as cooks, then check that the recipes
   they rated highly rank above the rest. The ratings are public
   (`peterpeeterspeter/recipe-interactions` on Hugging Face), but they are
   keyed by food.com recipe ids, which the corpus doesn't store. Joining them
   needs the original recipe table with ids (`RAW_recipes.csv` from Kaggle's
   *Food.com Recipes and User Interactions*, sign-in required). The free
   copies checked were broken or had the ids removed.
4. Photo scanning.
