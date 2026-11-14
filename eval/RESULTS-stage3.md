# Stage 3: taste ranking

**Question:** once you've logged a few meals, Forkcast moves recipes that
"suit your taste" up the list. Does that ranking know what a real person
likes?

**Short answer: barely.** It picks up a little about *what kind of food* you
cook, and nothing about *which* dishes you'll love. Ranking by what's popular,
or by what other people rated a recipe, does much better on both questions.
Nothing in the app has been changed yet; this page records the measurement.

## How it was tested

No hand labels this time: real people's ratings are the answer key.

- **Data:** Kaggle's *Food.com Recipes and User Interactions* (Majumder et
  al., EMNLP 2019): 1.13 million ratings from 2000 to 2018. All 87,861 corpus
  recipes link to it by name, cooking time and number of steps (14 ties broken
  by the description). The raw files are not in this repo; download them from
  Kaggle (sign-in required).
- **People:** the 5,419 food.com users who rated at least 10 corpus recipes.
  A seeded shuffle split them into 2,709 "dev" users, used only to check the
  pipeline, and 2,710 "test" users, whose numbers are reported below. The split
  ([`data/taste_users.json`](data/taste_users.json)) was committed before the
  engine scored anyone.
- **Replay:** each person's earliest 70% of ratings becomes their cooking
  history in the app's own meal log: 5 stars counts as *liked*, 3 or fewer as
  *disliked*, 4 as cooked without a rating. The dates are shifted so that the
  day of their next rating is "today", and the app's unchanged taste code
  builds their profile and scores recipes. The remaining 30% stay hidden.
- **Two questions about the hidden 30%:**
  1. **What will they cook next?** Mix the recipes they went on to rate with
     100 random recipes. How often does a recipe they chose rank above a
     random one?
  2. **Which will they love?** Among the hidden recipes they rated, how often
     does a 5-star one rank above one they gave 3 stars or fewer? (830 test
     users had both kinds.)
- **Reading the score:** each is "out of 100 pairs, how many were in the right
  order". 50 is a coin flip, 100 is perfect. Scores are averaged per person,
  so heavy raters don't dominate, with a 95% range from resampling people.
- **Comparisons that ignore the person:**
  - *Popular:* how many ratings the recipe has, counted only from people
    outside the test group.
  - *Crowd stars:* the recipe's average rating from those same people.
  - *Average recipe:* the same maths as taste, but measuring closeness to the
    average of all recipes instead of to your own cooking. Taste must beat
    this to show it learned anything about *you*.

## Results (2,710 test users)

| | Forkcast taste | Popular | Crowd stars | Average recipe |
|---|---|---|---|---|
| **What they cook next** (of 100 pairs, in order) | **55** (54.5–55.6) | 78 | 49 | 49 |
| **Which they'll love** | **48** (46–51) | 59 | 63 | 48 |

Taste beats a coin flip for 63% of people on the first question and 43% on
the second. The dev users gave the same picture (55 and 48).

## What it means

- **It knows a little about your kind of food.** 55 against 49 for the
  average-recipe version is a real difference (5 to 6 points, range 5.1 to
  6.3), so taste does carry something personal. But it is small: a person's
  next recipes rank above random ones only slightly more often than not.
- **It knows nothing about what you'll love.** 48 is a coin flip, the same as
  the version that ignores you. Among dishes you'd cook anyway, closeness to
  your past cooking does not separate favourites from disappointments.
- **Simple signals win.** People mostly cook and rate popular recipes (78),
  and a recipe other people loved is one you'll probably love too (63). Neither
  is personal, and both beat taste by a wide margin.

## Why, as far as we can tell

- **Averages blur.** Someone who cooks curries and cakes gets a profile
  halfway between the two, close to neither. The "average recipe" comparison
  scoring 49 shows how little an average of ingredients says on its own.
- **Ingredients aren't quality.** Two chicken curries share almost every
  ingredient; one is great and one is bland. The ingredient map can't see
  that, but other people's stars can.
- **Not the fading.** The app lets meals fade over 30 days. Switching that off,
  ignoring dislikes, or both moved the dev scores by at most a point (55.0 to
  at best 56.0, and 47.8 to at best 48.4), so they aren't the problem. (Checked
  by changing the two constants in `backend/app/taste.py` and rerunning on dev
  only.)

## How much to trust this

- **The sample is large,** so the ranges are narrow: the gaps above are real,
  not noise.
- **A food.com rating is not a logged meal.** People rate what they chose to
  cook and mostly give 5 stars (72% of all ratings), which makes "which will
  they love" a hard question for any method. The crowd-stars comparison shows
  it can still be answered better than a coin flip.
- **"Popular" has a head start.** People review popular recipes, and most
  random recipes are obscure, so popularity is an easy win on the first
  question. That is also true in the app, though: a popular recipe is a safer
  suggestion.
- **Replay is not the app.** In the app you'd log meals day by day. On
  food.com, a person's history is spread over months or years. The date
  shift keeps the gaps as they were, and turning fading off didn't help, so
  this is unlikely to change the picture.

## Files

| Path | What it is |
|---|---|
| [`data/taste_users.json`](data/taste_users.json) | the frozen dev/test split of food.com user ids |
| [`scripts/taste_data.py`](scripts/taste_data.py) | links the Kaggle files to the corpus and splits each history |
| [`scripts/taste_freeze.py`](scripts/taste_freeze.py) | builds the frozen split |
| [`scripts/run_taste.py`](scripts/run_taste.py) | replays the users through the app's taste code and scores it |
| [`labeling/taste_dev.json`](labeling/taste_dev.json), [`labeling/taste_test.json`](labeling/taste_test.json) | full results, with ranges and per-baseline differences |

To reproduce: download `RAW_recipes.csv` and `RAW_interactions.csv` from
Kaggle, then from `eval/scripts`:

```bash
python run_taste.py ../.. <kaggle_dir> <corpus.db> ../data/taste_users.json test ../labeling/taste_test.json
```
