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
| `data/strings.jsonl`, `data/holdout.jsonl` | 275 development and 150 held-out ingredient strings |
| `data/*_labeled.jsonl` | the same rows with gold labels |
| `data/kitchens.json`, `data/kitchens_holdout.json` | test kitchens in plain words (3 development, 1 held-out) |
| `data/vocab.txt` | Epicure's 1,790 ingredient names, the label space |
| [`data/LABELING.md`](data/LABELING.md) | labelling rules for both tasks |
| `labeling/` | shortlists, raw labels, engine outputs, cookable judgements |
| `scripts/` | sampling, labelling helpers, engine runner, scorer |

**Stages:**
1. Ingredient matching and "cookable now" precision: **done**.
2. Substitutions.
3. Taste ranking.
4. Photo scanning.
