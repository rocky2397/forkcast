"""Nutrition per ingredient, for meals built from ingredients and grams (D49).

The values come from the USDA's FoodData Central (SR Legacy, public domain),
mapped onto Forkcast's ingredients by scripts/build_ingredient_nutrition.py:
ingredient_nutrition.json holds each ingredient's USDA food, calories and
macros per 100 g, the USDA's portions (1 medium banana, 118 g) and, for rice,
pasta, beans and a few others, the cooked form as well.

The 300 ingredients used most in recipes, plus 80 sampled from the rest, were
checked by hand ("picked": "hand"). The others were matched by name and a
sample of 80 was about 84% right, so the app shows which USDA food it used
and says when it was matched by name only.
"""

import json
import re
from functools import lru_cache
from pathlib import Path

from . import embeddings
from .normalize import _clean
from .recipes import STAPLES

TABLE = Path(__file__).with_name("ingredient_nutrition.json")
MACROS = ("calories", "protein_g", "carbs_g", "fat_g")


@lru_cache(maxsize=1)
def table() -> dict[str, dict]:
    with open(TABLE) as f:
        return json.load(f)


# D55: how a food reads in the meal form and the meal list, where it isn't
# the ingredient name a recipe uses ("oat" is a recipe word; people eat oats).
# PLURALS are how they read in the kitchen too (D60).
PLURALS = {
    "oat": "oats", "lentil": "lentils", "pea": "peas", "chickpea": "chickpeas", "bean": "beans",
    "black_bean": "black beans", "kidney_bean": "kidney beans", "almond": "almonds", "walnut": "walnuts",
    "hazelnut": "hazelnuts", "cashew": "cashews", "peanut": "peanuts", "raisin": "raisins",
    "chia_seed": "chia seeds", "sunflower_seed": "sunflower seeds", "sesame_seed": "sesame seeds",
    "pumpkin_seed": "pumpkin seeds", "flaxseed": "flaxseeds", "pine_nut": "pine nuts", "pecan": "pecans",
    "pistachio": "pistachios", "caper": "capers", "olive": "olives",
}
DISPLAY = {
    **PLURALS,
    "oat_milk": "oat drink", "quark": "low-fat quark", "greek_yogurt": "Greek yogurt",
    "french_fries": "fries", "hazelnut_spread": "chocolate hazelnut spread",
    "low_fat_milk": "low-fat milk", "skim_milk": "skimmed milk", "low_fat_yogurt": "low-fat yogurt",
}

# D63: milk and yogurt come in fat levels on German shelves, and the label
# differs by a third. Each is its own food; the meal form switches between them.
FAT_FAMILIES = [["milk", "low_fat_milk", "skim_milk"], ["yogurt", "low_fat_yogurt", "greek_yogurt"]]
VARIANT_NAMES = {"milk": "whole milk", "yogurt": "whole-milk yogurt"}  # in the fat-level menu
_FAT = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")

# D55: what people type when logging, where the recipe matcher would get it
# wrong or find nothing. Written as they're typed; cleaned like the matcher
# cleans. In a meal, "Paprika" is the vegetable German shoppers mean, not the
# spice recipes mean; "Whey" is protein powder, not liquid whey.
_ALIASES = {
    "bell_pepper": ["paprika", "paprikas", "paprikaschote", "rote paprika", "gelbe paprika"],
    "paprika": ["paprikapulver", "paprika powder", "paprika spice", "edelsuess paprika"],
    "protein_powder": ["protein powder", "proteinpulver", "eiweisspulver", "eiweiss pulver", "whey",
                       "whey protein", "proteinshake", "protein shake", "eiweissshake"],
    "greek_yogurt": ["greek yogurt", "greek yoghurt", "griechischer joghurt", "griechischer jogurt",
                     "joghurt griechischer art"],
    "skyr": ["skyr"],
    "quark": ["quark", "magerquark", "speisequark mager"],
    "oat_milk": ["haferdrink", "hafermilch", "oat drink", "oat milk", "oatly"],
    "almond_milk": ["mandeldrink", "mandelmilch"],
    "soy_milk": ["sojadrink", "sojamilch"],
    "muesli": ["muesli", "musli", "muesli", "mussli", "bircher muesli", "fruechtemuesli", "schokomuesli"],
    "granola": ["granola", "knuspermuesli", "knusper muesli", "crunchy muesli"],
    "oat": ["oatmeal", "porridge", "haferbrei", "rolled oats"],
    "coffee": ["kaffee", "filterkaffee", "coffee", "black coffee", "schwarzer kaffee"],
    "espresso": ["espresso"],
    "toast": ["toast", "toastbrot", "toasted bread"],
    "whole_wheat_bread": ["vollkornbrot", "vollkorntoast", "whole wheat bread", "wholemeal bread",
                          "wholegrain bread", "graubrot"],
    "pizza": ["pizza", "pizza margherita", "margherita"],
    "french_fries": ["pommes", "pommes frites", "fritten", "fries", "french fries", "chips uk"],
    "lettuce": ["salat", "blattsalat", "kopfsalat", "gruener salat", "salad", "green salad"],
    "hazelnut_spread": ["nutella", "nuss nougat creme", "nussnougatcreme", "schokocreme",
                        "chocolate spread", "hazelnut spread"],
    "scrambled_egg": ["ruehrei", "ruehreier", "scrambled egg", "scrambled eggs"],
    "chia_seed": ["chiasamen", "chia", "chia seeds"],
    "flaxseed": ["leinsamen", "flax", "flax seeds", "linseed", "linseeds"],
    "beer": ["bier", "pils", "weizenbier", "helles"],
    "low_fat_milk": ["fettarme milch", "halbfettmilch", "teilentrahmte milch", "milch fettarm",
                     "low fat milk", "lowfat milk", "semi skimmed milk", "reduced fat milk"],
    "skim_milk": ["magermilch", "entrahmte milch", "skim milk", "skimmed milk", "fat free milk", "nonfat milk"],
    "low_fat_yogurt": ["fettarmer joghurt", "fettarmer jogurt", "joghurt fettarm", "fettarmjoghurt",
                       "low fat yogurt", "lowfat yogurt", "low fat yoghurt", "magerjoghurt"],
}

# Words that say a food was weighed cooked: "Reis gekocht", "cooked rice".
COOKED_WORDS = {"gekocht", "gekochte", "gekochter", "gekochtes", "gegart", "cooked", "boiled"}
# D64: words that say it came from a can: "Kichererbsen aus der Dose", "canned chickpeas".
_CANNED = re.compile(r"\b(dose|dosen|canned|tinned|konserve|from a can|aus der dose)\b", re.I)
_CANNED_FILLER = {"aus", "der", "dose", "dosen", "canned", "tinned", "konserve", "from", "can"}

# Drinks get a glass as a portion; grams and millilitres are near enough the same.
DRINKS = {"milk", "low_fat_milk", "skim_milk", "oat_milk", "almond_milk", "soy_milk", "rice_milk", "buttermilk", "kefir",
          "fruit_juice", "orange_juice", "apple_juice", "beer", "coffee", "tea"}
GLASS = {"label": "1 glass", "grams": 250.0}

# D62: dishes people log by name, as the foods in one typical serving, so each
# part keeps its own values and can be changed ("less pasta"). Amounts are
# typical servings, not measured: a single espresso is 30 ml, a cappuccino cup
# about 150 ml, a portion of pasta 100 g dry (about 250 g cooked), a Döner a
# 100 g flatbread with about 120 g cooked meat. The app says it's a typical
# one. (name, names people type, [(food, grams, weighed cooked)])
_DISHES = [
    ("Cappuccino", ["cappuccino", "cappucino", "capuccino"],
     [("espresso", 30, False), ("milk", 120, False)]),
    ("Latte macchiato", ["latte macchiato", "latte", "caffe latte", "cafe latte", "milchkaffee mit espresso"],
     [("espresso", 30, False), ("milk", 200, False)]),
    ("Flat white", ["flat white"], [("espresso", 60, False), ("milk", 110, False)]),
    ("Coffee with milk", ["coffee with milk", "kaffee mit milch", "milchkaffee", "white coffee", "cafe au lait"],
     [("coffee", 200, False), ("milk", 50, False)]),
    ("Spaghetti bolognese", ["spaghetti bolognese", "spaghetti bolognaise", "spaghetti bolo", "pasta bolognese",
                             "nudeln bolognese", "spaghetti mit bolognese", "bolognese", "spag bol"],
     [("pasta", 250, True), ("beef", 75, True), ("pasta_sauce", 150, False), ("onion", 30, False),
      ("olive_oil", 5, False), ("parmesan_cheese", 10, False)]),
    ("Döner", ["doener", "doener kebab", "doenerkebab", "doner", "doner kebab", "kebab", "kebap", "doener kebap",
               "doener im brot", "doener sandwich"],
     [("pita_bread", 100, False), ("beef", 120, True), ("lettuce", 20, False), ("tomato", 30, False),
      ("onion", 20, False), ("cabbage", 30, False), ("yogurt", 30, False), ("mayonnaise", 10, False)]),
]

# D61: amounts typed with the food: "2 Eier", "150 g Reis", "Haferflocken, 50 g".
_NUMBER_WORDS = {"a": 1, "an": 1, "one": 1, "ein": 1, "eine": 1, "einen": 1, "two": 2, "zwei": 2,
                 "three": 3, "drei": 3, "four": 4, "vier": 4, "five": 5, "fuenf": 5, "half": 0.5,
                 "halb": 0.5, "halbe": 0.5, "halber": 0.5, "halbes": 0.5, "eineinhalb": 1.5, "anderthalb": 1.5}
_UNITS = {"g": 1, "gr": 1, "gramm": 1, "gram": 1, "grams": 1, "grammes": 1, "ml": 1, "kg": 1000, "l": 1000,
          "liter": 1000, "litre": 1000, "litres": 1000, "liters": 1000}
_NUM = r"(\d+(?:[.,]\d+)?|½|¼|¾)"
_UNIT = r"(kg|grams|grammes|gramm|gram|gr|g|ml|liters|litres|liter|litre|l)\b\.?"
_LEADING = re.compile(rf"^{_NUM}(?![\d.,]|\s*%)\s*(?:{_UNIT})?\s*(?:x|×)?\s*(.*)$", re.I)  # not "1,5% Milch"
_TRAILING = re.compile(rf"^(.*?)\s+{_NUM}\s*(?:{_UNIT})?$", re.I)
_ONLY_AMOUNT = re.compile(rf"^{_NUM}\s*(?:{_UNIT})?$", re.I)
# Commas and semicolons separate foods, but not in "1,5 l".
_SEPARATORS = re.compile(r"(?<!\d),|,(?!\d)|;|\n")
_JOINERS = re.compile(r"\s+(?:with|and|mit|und|plus|&|\+)\s+", re.I)


# D60: what a food starts at when you add it, in this order: a whole piece
# (1 medium banana, 1 large egg, whichever the USDA lists first), a slice
# (bread, toast, ham), a spoon (butter, oil, honey, jam); else 100 g. "Toast
# mit Butter" was 100 g of each, 1,000 kcal; a slice and a spoon are what
# people have. Drinks stay in grams: "200" next to "× glass" would be 50 litres.
_STARTS = [r"^1 (medium|large)$", r"^1 slice$", r"^1 slice\b", r"^1 (tbsp|tablespoon)$"]


def default_portion(portions: list[dict]) -> str | None:
    labels = [p["label"] for p in portions]
    for pattern in _STARTS:
        found = next((lab for lab in labels if re.match(pattern, lab)), None)
        if found:
            return found
    return None


def label(canonical: str) -> str:
    return DISPLAY.get(canonical) or canonical.replace("_", " ")


def kitchen_label(canonical: str) -> str:
    """How an ingredient reads in the kitchen list: "oats", not "oat" (D60)."""
    return PLURALS.get(canonical) or canonical.replace("_", " ")


def kitchen_match(normalizer, raw: str) -> str | None:
    """A typed kitchen item -> a recipe ingredient (D60).

    The recipe matcher first, as before; where it finds nothing, the words
    people log with (D55) when they name a recipe ingredient: "Leinsamen" is
    flaxseed. Only as a fallback, so "paprika" in a kitchen stays the spice
    recipes mean, while in a meal it's the vegetable.
    """
    found = normalizer.match(raw)
    if found is not None:
        return found
    key = {_clean(n): k for k, names in _ALIASES.items() for n in names}.get(_clean(raw))
    if key and normalizer.match(key.replace("_", " ")) == key:
        return key
    return None


def food(canonical: str) -> dict | None:
    """What the app shows for one ingredient, or None without USDA values."""
    row = table().get(canonical)
    if row is None:
        return None

    def form(r: dict) -> dict:
        portions = [{"label": p[0], "grams": p[1]} for p in r["portions"]]
        if canonical in DRINKS:
            portions = [GLASS, *portions]
        return {
            "default_portion": None if canonical in DRINKS else default_portion(portions),
            "usda": r["usda"],
            # D55: where the numbers come from: the USDA's tables, or the
            # median of German packs on Open Food Facts.
            "source": r.get("source", "usda"),
            "fdc_id": r["fdc_id"],
            "per_100g": {"calories": r["kcal"], "protein_g": r["protein_g"],
                         "carbs_g": r["carbs_g"], "fat_g": r["fat_g"]},
            "portions": portions,
        }

    out = {"canonical": canonical, "name": label(canonical), "checked": row["picked"] == "hand", **form(row)}
    out["cooked"] = form(row["cooked"]) if "cooked" in row else None
    out["canned"] = form(row["canned"]) if "canned" in row else None  # D64
    family = next((f for f in FAT_FAMILIES if canonical in f), None)
    out["variants"] = [{"canonical": k, "name": VARIANT_NAMES.get(k) or label(k), "fat_g": table()[k]["fat_g"]}
                       for k in family if k in table()] if family else None
    return out


def _by_fat(canonical: str, pct: float) -> str:
    """"Milch 1,5%" -> the family member nearest that fat (D63)."""
    family = next((f for f in FAT_FAMILIES if canonical in f), None)
    if not family:
        return canonical
    return min((k for k in family if k in table()), key=lambda k: abs(table()[k]["fat_g"] - pct))


def lookup(normalizer, raw: str) -> dict:
    """A typed food name -> {"food": ... | None, "canonical": ..., "suggestions": [...]}.

    canonical is what the name matched even when there are no USDA values for
    it, so the app can say "no nutrition for quark yet" rather than "unknown".
    Suggestions are other ingredients the name could mean, with values.
    """
    words = _clean(raw).split()
    cooked = any(w in COOKED_WORDS for w in words)
    canned = bool(_CANNED.search(raw))
    drop = COOKED_WORDS | (_CANNED_FILLER if canned else set())
    text = " ".join(w for w in words if w not in drop)
    canonical = aliases().get(text) or (normalizer.match(text) if text else None)
    if canonical and (fat := _FAT.search(raw)):
        canonical = _by_fat(canonical, float(fat.group(1).replace(",", ".")))
    found = food(canonical) if canonical else None
    if found is not None:
        # D55: "Reis gekocht" starts as cooked rice, where there is a cooked form.
        found["start_cooked"] = cooked and found["cooked"] is not None
        found["start_canned"] = canned and found["canned"] is not None  # D64
    suggestions = [
        {"canonical": c, "name": label(c)}
        for c in normalizer.suggest(raw, limit=5)
        if c != canonical and c in table()
    ][:3]
    return {"query": raw, "canonical": canonical, "food": found, "suggestions": suggestions}


@lru_cache(maxsize=1)
def dishes() -> dict[str, tuple[str, list[tuple[str, float, bool]]]]:
    """Cleaned typed name -> (dish name, parts), for dishes whose parts all have values."""
    out = {}
    for name, typed, parts in _DISHES:
        if all(c in table() and (not cooked or "cooked" in table()[c]) for c, _, cooked in parts):
            for t in typed:
                out[_clean(t)] = (name, parts)
    return out


def _number(text: str) -> float:
    return {"½": 0.5, "¼": 0.25, "¾": 0.75}.get(text) or float(text.replace(",", "."))


def _amount(text: str) -> tuple[str, dict | None]:
    """Split an amount off a typed food: "150 g Reis" -> ("Reis", {"grams": 150})."""
    t = text.strip()
    m = _LEADING.match(t)
    if m and m.group(3).strip():
        n, unit, rest = _number(m.group(1)), m.group(2), m.group(3).strip()
    elif (m := _TRAILING.match(t)) and m.group(1).strip():
        rest, n, unit = m.group(1).strip(), _number(m.group(2)), m.group(3)
    else:
        first, _, rest = t.partition(" ")
        word = _clean(first)
        if rest.strip() and word in _NUMBER_WORDS:
            return rest.strip(), {"count": _NUMBER_WORDS[word]}
        return t, None
    if n <= 0:
        return rest, None
    if unit:
        return rest, {"grams": n * _UNITS[unit.lower().rstrip(".")]}
    return rest, {"count": n}


def _piece(food_: dict) -> str | None:
    """The portion a count means: "2 eggs" is 2 of "1 large", "2 Toast" 2 slices,
    a glass for drinks; else the first "1 ..." portion there is."""
    form = (food_["canned"] if food_.get("start_canned") else
            food_["cooked"] if food_.get("start_cooked") and food_["cooked"] else food_)
    return form["default_portion"] or next(
        (p["label"] for p in form["portions"] if p["label"].startswith("1 ")), None)


def _known_whole(text: str) -> bool:
    """Whether a phrase with "and" or "with" names one food: "sweet and sour sauce"."""
    t = _clean(text)
    return t in dishes() or t in aliases() or t.replace(" ", "_") in table()


def parse(normalizer, raw: str) -> dict:
    """What a typed line in Log a meal adds (D61, D62).

    "2 Eier, Toast, 150 g Reis gekocht" is three foods with their amounts;
    "Kaffee mit Milch und Zucker" is three foods too, unless the words name one
    food or dish ("sweet and sour sauce", "Spaghetti Bolognese"). Each part:
    {food, grams | count + portion | none, cooked}; dish parts carry the dish's
    name. What isn't found comes back in missing, as lookup() describes it.
    """
    segments: list[tuple[str, dict | None]] = []
    for seg in (x.strip() for x in _SEPARATORS.split(raw)):
        if not seg:
            continue
        if _ONLY_AMOUNT.match(seg) and segments:  # "Haferflocken, 50 g"
            prev, _ = segments[-1]
            segments[-1] = (prev, _amount(f"{seg} {prev}")[1])
            continue
        text, amount = _amount(seg)
        if _JOINERS.search(text) and not _known_whole(text):
            subs = [x for x in _JOINERS.split(text) if x.strip()]
            segments.append((subs[0], amount))  # "2 Toast mit Butter": the 2 is the toast
            segments += [_amount(x) for x in subs[1:]]
        else:
            segments.append((text, amount))
    parts, missing, dish_names = [], [], []
    for text, amount in segments:
        dish = dishes().get(_clean(text))
        if dish is not None:
            name, items = dish
            times = amount["count"] if amount and "count" in amount else 1
            dish_names.append(name)
            parts += [{"food": food(c), "grams": round(g * times, 1), "cooked": cooked, "canned": False, "dish": name}
                      for c, g, cooked in items]
            continue
        found = lookup(normalizer, text)
        if found["food"] is None:
            missing.append(found)
            continue
        f = found["food"]
        part = {"food": f, "cooked": f["start_cooked"], "canned": f["start_canned"]}
        if amount and "grams" in amount:
            part["grams"] = amount["grams"]
        elif amount and (portion := _piece(f)):
            part["count"], part["portion"] = amount["count"], portion
        parts.append(part)
    return {"query": raw, "parts": parts, "missing": missing, "dishes": dish_names}


@lru_cache(maxsize=1)
def aliases() -> dict[str, str]:
    """Cleaned typed name -> table key, for names the recipe matcher gets wrong."""
    return {_clean(name): key for key, names in _ALIASES.items() for name in names if key in table()}


def totals(items: list[dict]) -> dict[str, float]:
    """Sum of [{canonical, grams, cooked, canned}] -> calories and macros, rounded.

    Raises KeyError naming the first ingredient without values, and
    ValueError(canonical, form) for a cooked or canned form it doesn't have.
    """
    acc = dict.fromkeys(MACROS, 0.0)
    for it in items:
        row = table().get(it["canonical"])
        if row is None:
            raise KeyError(it["canonical"])
        form = "canned" if it.get("canned") else "cooked" if it.get("cooked") else None
        if form:
            if form not in row:
                raise ValueError(it["canonical"], form)
            row = row[form]
        f = it["grams"] / 100
        acc["calories"] += row["kcal"] * f
        acc["protein_g"] += row["protein_g"] * f
        acc["carbs_g"] += row["carbs_g"] * f
        acc["fat_g"] += row["fat_g"] * f
    return {k: round(v, 1) for k, v in acc.items()}


MIN_TASTE_INGREDIENTS = 2


def taste_ingredients(canonicals: list[str]) -> list[str]:
    """The foods of a built meal the recipe feed can learn from, in order.

    The feed compares recipes with dishes through the recipe ingredients' vectors,
    so only ingredients that recipes use count, and staples (salt, oil, flour...)
    don't. Skyr or protein powder can be logged (D55) but aren't recipe words.
    """
    out: list[str] = []
    for c in canonicals:
        if c and c not in STAPLES and c not in out and embeddings.ingredient_vector(c, "cooc") is not None:
            out.append(c)
    return out


def teaches_taste(canonicals: list[str]) -> bool:
    """Whether a built meal says something about what you like to eat.

    One food on its own (a banana) isn't a dish: it would make every banana
    recipe "Like your banana". Two or more recipe ingredients are.
    """
    candidates = {c for c in canonicals if c and c not in STAPLES}
    if len(candidates) < MIN_TASTE_INGREDIENTS:  # no need to load the vectors
        return False
    return len(taste_ingredients(canonicals)) >= MIN_TASTE_INGREDIENTS


def rate_note(ingredients: list[dict]) -> str:
    """Why a built or typed meal can't be rated, in the words the meal list shows (D60)."""
    if not ingredients:
        return "No rating: Forkcast can't tell what's in a meal typed as numbers. Add it by ingredients to rate it."
    if len(ingredients) == 1:
        return ("No rating: a single food doesn't say what you like to cook. "
                "Meals with two or more ingredients can be rated.")
    usable = taste_ingredients([i["canonical"] for i in ingredients if i.get("canonical")])
    if not usable:
        return ("No rating: none of these foods are recipe ingredients, so the recipe feed "
                "has nothing to learn from.")
    return (f"No rating: only {label(usable[0])} is a recipe ingredient here, and the recipe feed "
            "needs two to learn what you like. Basics like oil or salt don't count.")
