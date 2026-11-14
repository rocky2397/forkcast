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
| `data/kitchens.json`, `data/kitchens_holdout.json` | test kitchens in plain words (3 development, 1 held-out) |
| `data/vocab.txt` | Epicure's 1,790 ingredient names, the label space |
| `data/subs_cases.jsonl`, `data/subs_holdout.jsonl` | 90 development and 60 held-out substitution cases |
| `data/kitchens_subs_holdout.json` | first stage 2 held-out kitchens (stir-fry, taqueria) |
| `data/kitchens_subs_holdout2.json`, `data/subs_holdout2.jsonl` | fresh held-out kitchens (brunch, curry) and their 60 cases, for judging the D28 fix |
| [`data/LABELING.md`](data/LABELING.md) | labelling rules for all three tasks |
| `labeling/` | shortlists, raw labels, engine outputs, cookable judgements |
| `scripts/` | sampling, labelling helpers, engine runner, scorer |

**Stages:**
1. Ingredient matching and "cookable now" precision: **done**.
   Still to tighten: a human pass over the 34 unsure labels, and a second
   held-out kitchen to narrow the interval around 80%.
2. Substitutions: **done**, fixed by D28 (see
   [`RESULTS-stage2.md`](RESULTS-stage2.md)).
3. Taste ranking.
4. Photo scanning.
