# Test 8 photos: a real fridge

About ten photos of one real fridge, each with a list of what is really in
it. The photos stay out of git (see `.gitignore`); the lists and the answer
key are committed.

## Taking the photos

- **Ten photos on different days**, so the contents change: after shopping,
  mid-week, nearly empty.
- **Door open, whole fridge in frame,** the way someone would actually use the
  app: one photo, standing in front of it, no rearranging. Two or three of the
  ten may show only the door shelves or one drawer.
- **Name them** `fridge-01.jpg`, `fridge-02.jpg`, ... Phone photos as they
  are; no editing. JPEG or PNG (iPhone: "Most Compatible" in camera settings,
  or AirDrop, which sends JPEG).
- **Check each photo for anything personal** (notes on the door, a
  reflection, a letter on top) before saving it here.

## Writing the list (before any scan)

Right after taking each photo, write `fridge-01.txt` next to it, one item per
line, in plain words. Two parts:

```
# visible
milk
eggs
half a red pepper
Gouda

# hidden
butter
yoghurt at the back
```

- **visible:** you can point at it in the photo, even partly (a carton
  corner counts).
- **hidden:** in the fridge, but not in the photo (behind something, in a
  closed drawer). The scanner isn't marked down for missing these, but naming
  one counts as right.
- Leave out drinks you'd never cook with only if you'd leave them out of the
  app too. Sauces and condiments (ketchup, mustard, jam) count.

Write the lists **before** running any scan, and don't change them after
seeing scanner output: that keeps the answer key blind, as in Test 4.

`python eval/scripts/build_fridge_truth.py` then turns the lists into
`eval/data/fridge_truth.json` (Forkcast ingredient names), which is checked
by hand before the first run.
