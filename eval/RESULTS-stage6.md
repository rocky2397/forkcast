# Stage 6: learning what you burn (D45)

**Question:** after a few weeks of meals and weigh-ins, does Forkcast know
what you burn better than the formula it starts with?

**Answer, on simulated people:** yes, if the log is complete. After four
weeks the typical error falls from 186 to 74 kcal a day. When the log misses
10% of what was eaten, the learned number reads low, yet the plan built on it
still ends up much closer, because the miss is in the log the person eats by.

## Why simulated

A fair test needs people whose true daily burn is known, with weeks of food
logs and weigh-ins. No public dataset has that: burn is measured in labs
(doubly labelled water) over two weeks, without food logs that match. So the
test simulates people and runs the app's own estimator
(`backend/app/adaptive.py`, `estimate`) on them. Script:
[`scripts/sim_burn.py`](scripts/sim_burn.py), 2,000 people per row, a fixed
seed, a few seconds to run.

Each simulated person:

- has a random body and activity level; the formula gives their burn, but
  their true burn differs from it by anything up to 15% either way;
- eats around a plan (a deficit of 300 or 500 kcal, maintenance, or a 250
  kcal surplus) with 12% day-to-day scatter, and logs 85% of days
  completely; the rest are left out, as the app leaves out forgotten days;
- weighs in on about 60% of mornings. Weight follows energy balance (7,700
  kcal per kg), plus water swings that carry over from one day to the next
  (about 0.4 kg spread). That's harder than the independent noise the
  estimator's error bars assume.

## Results

Two errors, in kcal a day:

- **Burn error:** how far the burn estimate is from the true burn.
- **Plan error:** how far the person's real eating is from what the plan
  needs, if they eat to the target built on that estimate. With honest logs
  the two are the same. When a log always misses 10%, eating to a logged
  target means really eating more, so a burn that reads 10% low is the right
  number for that person's plan.

| Logs | Weeks | Learned yet | Burn error: formula | Burn error: learned | Plan error: formula | Plan error: learned | Plan error, worst 10%: formula | Plan error, worst 10%: learned | Held at the 15% limit |
|---|---|---|---|---|---|---|---|---|---|
| honest | 2 | 63% | 181 | 147 | 181 | 147 | 351 | 332 | 4% |
| honest | 3 | 100% | 184 | 105 | 184 | 105 | 360 | 265 | 7% |
| honest | 4 | 100% | 186 | 74 | 186 | 74 | 365 | 197 | 8% |
| miss 10% | 2 | 61% | 188 | 173 | 269 | 195 | 607 | 514 | 8% |
| miss 10% | 3 | 100% | 182 | 165 | 261 | 128 | 595 | 307 | 20% |
| miss 10% | 4 | 100% | 185 | 179 | 272 | 104 | 614 | 239 | 26% |

Medians unless marked. "Learned yet" is the share with enough data for the
estimate to start (10 complete days, weigh-ins spanning 12 days); the others
still use the formula.

**The cost:** for people whose formula was already within 3%, the learned
burn is 39 kcal further off (median) after four weeks. That's the noise in
four weeks of weigh-ins, and the price of correcting everyone else.

**The 15% limit** holds back a quarter of the people whose log misses 10%:
their plan would be closer still without it. It stays, because a log that
misses much more than that (forgotten snacks, drinks) would otherwise pull
the target down with it. The Weight card says when the limit applies and why.

## One choice made after looking

At two weeks the first version never started learning: it asked for
weigh-ins spanning 14 days, which two weeks of data can't quite reach. With
12 days, 63% start learning at two weeks and their error drops from 181 to
147; three and four weeks are unchanged. The 12 was chosen on these results,
so the two-week row is a little flattering.

## What this doesn't test

- **Real people.** The simulation is ours; real logs fail in other ways.
- **Water at the start of a diet.** The first week or two of a deficit
  sheds water and stored carbohydrate, so weight falls faster than 7,700
  kcal per kg says. That makes the burn look higher at first. Not simulated.
- **Missing meals on some days only** (weekends, eating out). The 10% case
  misses the same share every day, which a learned number can absorb;
  uneven gaps add noise instead.
- **Burn changing over time.** Burn falls a little as weight falls. The
  four-week window follows that, but it lags.
