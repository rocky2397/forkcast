# Stage 8: a photo of the whole fridge

**Question:** you take one photo of your open fridge. How much of what is in
it does Forkcast find, how much does it add that isn't there, and is checking
its list quicker than typing the list yourself?

**Short answer:** the model the app uses today, Claude Haiku 4.5, finds only
**half** of what is in the photo, much worse than its 76% on single
groceries (Test 4). The newer **Claude Haiku 5.5 finds 77%**, at a fifth of
the price, and Claude Sonnet 5.5 finds 80% for twenty times Haiku 5.5's
price. With Haiku 5.5, and keeping only what it is at least 70% sure of, a
scan leaves about **3 fixes** (an item to untick or one to add) where typing
the list means 11 items. Unlike in Test 4, the newer models' confidence is
worth showing: what they are sure of is almost always right.

## What was tested

- **Photos:** the 51 photos in the test split of the
  [aicook dataset](https://universe.roboflow.com/karel-cornelis-q2qqg/aicook-lcv4d)
  (Karel Cornelis, Erasmus Brussels, MIT licence): one real fridge, door
  open, filled at random from 30 kinds of ingredient for each photo, with
  every item boxed and labelled. 9 to 14 kinds per photo, 11 on average.
- **System under test:** the app's scanner exactly as shipped
  (`backend/app/vision.py`: its prompt and output schema), with only the
  model swapped, then the app's own ingredient matcher, as in the app. Two
  runs per photo and model, to see whether the same photo gives the same list.
- **Answer key:** each of the 30 labels mapped to the Forkcast ingredients
  that count as right, written from the ingredient list alone before any
  scan ([`build_aicook_truth.py`](scripts/build_aicook_truth.py)). Where the
  label is general ("cheese", "mushrooms"), naming a kind of it counts.
- **Scoring:** *found* is the share of the photo's items that some proposal
  matched. *Wrong* is a proposal for something not in the photo. *Fixes* is
  wrong proposals plus missed items: what you would correct after the scan.

Scripts: [`run_fridge.py`](scripts/run_fridge.py) (with a hard dollar cap
per run), [`score_fridge.py`](scripts/score_fridge.py). Every proposal is in
`labeling/fridge/`. The photos are not in the repo. The whole test cost
$1.64.

## One fix to the answer key, after looking

Two "mistakes" turned up in nearly every photo: every model said *soy milk*
where the key said milk, and *margarine* where it said butter. Crops of the
labelled boxes showed the models were right: the "butter" is a tub of Planta
margarine and some "milk" cartons are Alpro Soya. The corrected key accepts
margarine and soy milk for those two labels and changes nothing else. Since
the change came after seeing results, both are reported; the text uses the
corrected key.

## Results

| | Haiku 4.5 (today) | Haiku 5.5 | Sonnet 5.5 |
|---|---|---|---|
| **Items found** | **50%** (47 to 53) | **77%** (75 to 80) | **80%** (78 to 83) |
| with the key as first written | 47% | 72% | 75% |
| Wrong proposals per scan | 2.5 | 2.1 | 2.2 |
| Fixes per scan, everything kept | 8.0 | 4.6 | 4.4 |
| Fixes per scan, only 70% sure or more | 7.9 | **3.4** | 3.4 |
| Same list on a second try | 76% | 90% | 96% |
| Cost per scan | $0.003 | **$0.0006** | $0.012 |
| Seconds per scan (median) | 2.7 | 2.2 | 3.2 |

Typing the list yourself would be 11 items per photo. The ranges are 95%
intervals; they are a little too narrow, because items in the same photo
aren't independent.

**What the models miss:**

| Item | Why |
|---|---|
| Thin-sliced beef in a tray | called "meat", "ground meat" or "smoked salmon": a fair misread of red slices in a black tray, and "meat" is too vague for recipes |
| Flour | a crumpled paper bag on a shelf, often not named at all |
| Corn | a closed can, called "canned food" |
| Shrimp | a frozen bag, often skipped |

The wrong proposals are mostly those vague names ("meat") plus a few things
seen in shadows: nuts, ham, sausage.

**Confidence now means something.** Keeping only what the model is at least
70% sure of drops most wrong proposals and few right ones:

| Kept | Haiku 5.5: found | wrong per scan | fixes per scan |
|---|---|---|---|
| everything | 77% | 2.1 | 4.6 |
| 70% sure or more | 73% | 0.5 | **3.4** |
| 80% sure or more | 68% | 0.2 | 3.8 |
| 90% sure or more | 41% | 0.0 | 6.6 |

Haiku 4.5's confidence barely helps (7.9 fixes at its best), as Test 4 found.

## What this decides

1. **The fridge scan uses Claude Haiku 5.5** (D69). Sonnet finds 3 points
   more for twenty times the price, within the range of chance on 51 photos.
   At the demo's cap of 200 scans a day, Haiku 5.5 costs about $0.12 a day.
2. **The confirm screen splits at 70%:** "Confident" items are kept, "Not
   sure" ones are kept only if tapped, plus "Missed something? Add".
3. **Worth checking next:** Test 4's grocery photos with Haiku 5.5 (about
   $0.25), before moving the existing grocery scan off Haiku 4.5 too.

## Limits

- **One staged fridge.** 30 kinds of food, mostly loose, no sauces,
  leftovers, door shelves or German packs. A lived-in fridge is harder, so
  these numbers are an upper bound. Photos of a real household fridge
  ([how](data/fridge/README.md)) would test that.
- **The 70% line was chosen on these same photos.** It needs checking on
  other photos before it is trusted.
- **Two fixes to the key were made after seeing results** (above); both
  scores are reported.
