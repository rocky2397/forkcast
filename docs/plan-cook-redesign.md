# Plan: from three tabs to "fridge, pick, ate it"

*21 November 2026. Step 0 and Stage 1 built. Based on a clickable prototype
and feedback from a growth PM, and on the demo's usage numbers.*

## Why

A growth PM tried the demo and found three problems:

1. The first screen explains how to set the app up, not what you get.
2. The profile can be skipped, but without it the app can't pick meals that
   fit your day.
3. The app's promise is that it does the work for you, yet keeping the
   kitchen list and the food log up to date is still manual.

The demo's [usage page](https://rockyyyy2397-forkcast.hf.space/stats) points
the same way: of 212 visitors, 2% added an ingredient and 5% opened a
recipe, although the demo starts with a stocked kitchen.

The prototype answers with three taps: photograph the fridge, pick a meal,
say you ate it. Logging and the kitchen then update themselves.

## What stays the same

The engine: the ingredient matching, the 87,861 recipes, ranking by what you
have and by what fits your day, swaps, the learned burn, confirm before
saving (D8), Undo, and logging by photo, barcode, label or description. This
plan changes the order of the screens and who does the typing, not the logic.

## Rules for every stage

- **Value before setup.** Say what you get before asking for anything.
- **Guess, then let people fix it in one tap.** A guess is fine when it is
  visible and cheap to correct where you notice it. This changes the trade-off
  in D27 ("wrong is worse than missing"), which was about mistakes nobody
  could see; the new decision says so.
- **The demo works without a fridge.** A recruiter on a laptop must reach
  the main screen with a sample kitchen in under a minute.
- **Measure each stage** on the usage page, before and after.

## Step 0: a clean starting number (small)

- Find out where the 137 visitors on 19 November came from (one share, a
  bot, a link preview). Decide whether to count that day.
- Add the missing steps to the anonymous funnel: welcome finished, profile
  saved, picks seen, "I ate it". Totals only, like the rest of the page.
- Note the baseline in this file.

**Done (21 November 2026).** The 19 November spike was not a share or a bot.
That day's file shows 16 app opens and ordinary use, but 137 new kitchens: seven
updates restarted the demo, each restart lost kitchens nobody had changed, and
every request a browser already had on the way with its old id made, and
counted, a new kitchen. Fixed in D68 (a lost kitchen comes back under the same
id and isn't a new visitor). Earlier days had restarts too, so their counts are
a little high as well.

Baseline, 15 to 21 November, from /stats:

| | All days | Without 19 November |
|---|---|---|
| Visitors | 219 | 82 |
| Added an ingredient | 5 (2%) | 3 (4%) |
| Opened a recipe | 12 (5%) | 9 (11%) |
| Marked a recipe as cooked | 3 (1%) | 1 (1%) |
| Profiles changed (event) | 12 | 9 |

So without the double counts, about one visitor in nine opened a recipe and
about one in eleven or twelve changed a profile (a count of saves, not of
people). The new steps (finished the welcome, saved a profile, saw meal picks)
are counted from the D68 deploy on.

## Stage 1: welcome and profile (D68, small)

**Built 21 November 2026, not yet deployed.** As planned, with one change:
the demo's profile form still starts empty (D60) and offers a separate "Use a
sample person" button, so made-up numbers never look like yours.

- **Screen 1** says what you get: "Meals that fit your fridge and your goal."
  One line under it and a Get started button. No "Skip for now".
- **Screen 2** shows the three taps: fridge, pick, ate it.
- **Screen 3** is the profile, now required (sex, age, height, weight,
  activity, goal, pace, optional goal weight). In the demo it is filled with
  clearly labelled sample values, so one tap goes through.
- **Screen 4** is the payoff: "Here's your day", with calories, protein and the
  goal date from the plan that already exists (D39, D44). It says the number
  is a formula's guess until the app learns from you (D45).
- People who already have a profile skip all of this.
- **Done when:** tests and the smoke test cover the new first visit, and the
  funnel shows how many finish the profile.

## Stage 2: the fridge scan (D69, medium)

**First a small test (Test 8),** because a whole fridge is much harder than
the single groceries of Test 4 (76%):

- About 10 photos of a real fridge on different days, each with a written list
  of what is really in it.
- Run the current model (Haiku 4.5) and Sonnet. Look up the current prices
  first: Sonnet costs several times more per scan, and the demo's limit of
  200 scans a day runs on a pay-per-use key.
- Measure how many items it finds, how many wrong ones it adds, and whether
  checking its list is quicker than typing. Choose the model and the
  confidence line from this, and put the result in the README.

**Then build it:**

- The scan returns a confidence for each item. The confirm screen shows
  "Confident" (kept) and "Not sure" (kept only if tapped), plus "Missed
  something? Add".
- Cupboard food (pasta, rice, tins, spices) isn't in a fridge photo: basics
  stay assumed as now, and the confirm screen offers quick chips for common
  cupboard items.
- A later scan shows only what changed: "New" and "Looks gone", with "Still
  have it" for things just out of shot.
- The demo gets a "Use a sample fridge" button.
- **Done when:** Test 8 is written up, and the confirm and re-scan screens are
  in the smoke test (with a stand-in for the model).

## Stage 3: the Cook screen (D70, large)

- **Two tabs: Cook and Progress.** The kitchen list moves behind "See what's
  in your fridge" on Cook.
- **Cook** shows what's left of today, the "Update my fridge" card, the three
  meals that fit best, "See all", and "Ate something else? Log it" (the
  existing ways to log).
- **On a recipe:** each ingredient gets a one-tap "Don't have it" / "Have it",
  so a wrong guess about the kitchen is fixed where it shows.
- **"I'm cooking this"** pins the recipe on Cook while you cook.
- **"I ate it"** logs the servings and updates the kitchen. Forkcast doesn't
  know amounts (food.com lists none, D59), so what ran out is a guess. Main
  fresh items (meat, fish, leafy greens) are pre-ticked as "ran out", the rest
  as "some left", and one tap changes either. Undo stays.
- What ran out can go on a shopping list. That list is new: "Worth buying"
  ranks what to buy, but doesn't keep a list.
- **Done when:** tests and the smoke test cover cook, eat and correct;
  the funnel is compared with Step 0.

## Stage 4: the case study (small)

One page: the growth PM's feedback, the funnel before, the three decisions (D68–D70),
Test 8, the funnel after, and what's still weak.

## Left out on purpose

- **Tracking amounts.** Recipes have none, so the app guesses and you correct.
- **"The only thing you ever type is your weight."** Not true for meals
  eaten out or for cupboard food. We don't promise it.
- **From the prototype, for later:** meal size (small/regular/big) and
  freshness ("spinach, day 6"). Both need data the app doesn't keep yet.
- **Later idea:** reading supermarket receipts to add what you bought,
  cupboard food included.

## Open questions

1. Sonnet for fridge scans in the demo: is the cost acceptable within the
   200-scans-a-day cap?
2. Hide the Kitchen tab completely, or keep it one tap away?
3. Ask the reviewer whether they may be credited by name in the decision log
   and case study.
