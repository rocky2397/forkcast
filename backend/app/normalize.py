"""Map free-text ingredient strings to Epicure's canonical vocabulary.

Cascade (cheap first):
  1. alias table (common synonyms the vocabulary spells differently)
  2. exact match after cleanup, over singular/plural variants
  3. descriptor stripping ("fresh chopped cilantro" -> "cilantro"), retry
  4. longest canonical name contained as a whole-word span

All variant generation is membership-checked against the vocabulary, so a
wrong guess ("chives" -> "chif") is harmless — it simply doesn't match.
"""

import difflib
import re
from collections.abc import Iterable

from .food_classes import NAME_TO_CLASS

# Synonyms -> canonical Epicure name. Targets are validated against the
# vocabulary at build time; entries whose target is missing are dropped.
ALIASES = {
    "pepper": "black_pepper",
    "peppercorn": "black_pepper",
    "green pepper": "bell_pepper",
    "cilantro": "coriander",
    "cornflour": "cornstarch",
    "corn flour": "cornstarch",
    "gingerroot": "ginger",
    "cayenne": "cayenne_pepper",
    "catsup": "ketchup",
    "spaghetti": "pasta",
    "fettuccine": "pasta",
    "linguine": "pasta",
    "macaroni": "pasta",
    "nam pla": "fish_sauce",
    "hamburger": "ground_beef",
    "half and half": "cream",
    "tabasco sauce": "hot_sauce",
    "tabasco": "hot_sauce",
    "cool whip": "whipped_cream",
    "pimiento": "bell_pepper",
    "pimento": "bell_pepper",
    "roma tomato": "tomato",
    "plum tomato": "tomato",
    "cherry tomato": "tomato",
    "grape tomato": "tomato",
    "campari tomato": "tomato",
    "baking potato": "potato",
    "confectioners sugar": "powdered_sugar",
    "icing sugar": "powdered_sugar",
    "caster sugar": "sugar",
    "superfine sugar": "sugar",
    "green onion": "scallion",
    "spring onion": "scallion",
    "long bean": "green_bean",
    "capsicum": "bell_pepper",
    "red capsicum": "bell_pepper",
    "elbow macaroni": "pasta",
    "black peppercorn": "black_pepper",
    "cracked pepper": "black_pepper",
    "applesauce": "apple_sauce",
    # D46: a tester couldn't add skyr; it cooks like a thick yogurt.
    "skyr": "yogurt",
    "soymilk": "soy_milk",
    "oatmeal": "oats",
    "red chili": "chili_pepper",
    "ketjap manis": "sweet_soy_sauce",
    # bare cheese names -> the vocab's *_cheese entries
    "parmesan": "parmesan_cheese",
    "cheddar": "cheddar_cheese",
    "mozzarella": "mozzarella_cheese",
    "gouda": "gouda_cheese",
    "feta": "feta_cheese",
    "gruyere": "gruyere_cheese",
    # Products the D27 guard would otherwise abstain on, but which the
    # vocabulary does name: vanilla is used as extract, and the vocabulary's
    # pasta_sauce is what a jar of spaghetti sauce is.
    "vanilla extract": "vanilla",
    "spaghetti sauce": "pasta_sauce",
    "hot pepper sauce": "hot_sauce",
    "ice cube": "ice",
    "sriracha sauce": "sriracha",
    "vinaigrette dressing": "vinaigrette",
    "preserves": "fruit_preserves",
    # D29: names the product words below need to land on. A juice that comes
    # in a bottle is its own ingredient; citrus juice stays the fruit.
    "tomato juice": "vegetable_juice",
    "carrot juice": "vegetable_juice",
    "vegetable juice": "vegetable_juice",
    "apple juice": "fruit_juice",
    "pineapple juice": "fruit_juice",
    "cranberry juice": "fruit_juice",
    "grape juice": "fruit_juice",
    "white grape juice": "fruit_juice",
    "pomegranate juice": "fruit_juice",
    "cherry juice": "fruit_juice",
    "pickle": "pickled_cucumber",
    "hommus": "hummus",
    "jell o": "gelatin",
    "jello": "gelatin",
    "bologna": "sausage",
    "pork and beans": "baked_beans",
    "corn flake crumbs": "corn_flakes",
    "cornflake crumbs": "corn_flakes",
    "zucchini noodle": "zucchini",
    "bread flour": "flour",
    "half half": "cream",
    # Stage 4 (D35): British and European names, as a scanner reads them off
    # European packaging. "yoghurt" is handled as a spelling in _clean().
    "aubergine": "eggplant",
    "courgette": "zucchini",
    "beetroot": "beet",
    "kiwifruit": "kiwi",
    "kiwi fruit": "kiwi",
    "satsuma": "tangerine",
    "mandarin": "tangerine",
    "mandarin orange": "tangerine",
    "soya milk": "soy_milk",
    "soya yogurt": "soy_yogurt",
    "soya drink": "soy_milk",
    "soy drink": "soy_milk",
    "oat drink": "oat_milk",
    # sweet peppers are bell peppers; a bare "red pepper" stays ambiguous
    "sweet pepper": "bell_pepper",
    "yellow pepper": "bell_pepper",
    "orange pepper": "bell_pepper",
}

DESCRIPTORS = {
    "fresh", "freshly", "chopped", "diced", "minced", "sliced", "grated",
    "shredded", "ground", "dried", "frozen", "canned", "cooked", "raw",
    "large", "small", "medium", "boneless", "skinless", "lean", "extra",
    "light", "low-fat", "lowfat", "nonfat", "fat-free", "reduced-fat",
    "unsalted", "salted", "sweetened", "unsweetened", "hot", "cold", "warm",
    "ripe", "baby", "whole", "plain", "instant", "quick-cooking", "prepared",
    "packed", "firmly", "finely", "coarsely", "thinly", "roughly", "of",
}


# Spellings of the same word (D35): the vocabulary uses the American one.
_SPELLINGS = {"yoghurt": "yogurt", "yoghurts": "yogurts"}


def _clean(term: str) -> str:
    t = term.lower().strip()
    t = re.sub(r"\(.*?\)", " ", t)
    t = re.sub(r"[^a-z ]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return " ".join(_SPELLINGS.get(w, w) for w in t.split())


def _word_variants(w: str) -> list[str]:
    """Singular candidates for one word; checked against vocab, so guesses are safe."""
    out = [w]
    if w.endswith("ies"):
        out.append(w[:-3] + "y")
    if w.endswith("ves"):
        out.append(w[:-3] + "f")       # leaves -> leaf
        out.append(w[:-1])             # olives -> olive... (via generic -s too)
    if w.endswith("es"):
        out.append(w[:-2])             # tomatoes -> tomato
    if w.endswith("s") and not w.endswith("ss"):
        out.append(w[:-1])
    return out


# Words after which the rest of the string describes what an ingredient comes
# packed with, not the ingredient: "diced tomatoes with green chilies".
# Deliberately short. "and" joins two ingredients of equal standing, and
# cutting there rewrote "salt and black pepper" across 327 rows. "packed" cuts
# the wrong way round in "water-packed artichoke hearts"; "in" already handles
# the "tomatoes packed in oil" order.
_CONNECTORS = frozenset({"with", "in"})

# "no salt added", "salt free": the negated word is the one thing the product
# does *not* contain, yet it was being matched ("no-salt-added tomatoes" ->
# salt). Hyphens are already spaces by the time this runs.
_NEGATIONS = (
    re.compile(r"\bno [a-z]+ added\b"),
    re.compile(r"\b[a-z]+ free\b"),
)


def _strip_negations(t: str) -> str:
    for pattern in _NEGATIONS:
        t = pattern.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()


def _head_segment(t: str) -> str | None:
    """The phrase up to its first connector word, if there is one."""
    words = t.split()
    for i, w in enumerate(words):
        if w in _CONNECTORS and i > 0:
            head = words[:i]
            # D29: "sun-dried tomatoes packed in oil" -> "sun dried tomatoes",
            # so the plural is the last word again and singularizes.
            while len(head) > 1 and head[-1] in DESCRIPTORS:
                head.pop()
            return " ".join(head)
    return None


def _phrase_variants(t: str) -> Iterable[str]:
    """The phrase itself, plus last-word singularizations."""
    yield t
    words = t.split()
    if not words:
        return
    for v in _word_variants(words[-1]):
        yield " ".join(words[:-1] + [v])


# Aliases allowed to override a narrower word they contain (see
# Normalizer._compound_upgrade). Opt-in, not opt-out: letting every multi-word
# alias upgrade moves 177 strings and 2610 recipe rows, turning "wheat flour"
# into wheat and "tuna fish" into fish. Each entry here is one measured with
# backend/scripts/normalizer_diff.py. "corn flour" is deliberately absent —
# right on its own, but as an upgrade it rewrites "masa corn flour" to
# cornstarch.
_COMPOUND_UPGRADES = {
    "cherry tomato", "grape tomato", "campari tomato", "plum tomato",
    "roma tomato", "green onion",
    # D29: products whose name starts with a food word
    "pork and beans", "corn flake crumbs", "cornflake crumbs",
}


# Words that name a *product made from* the food in front of them (D27):
# "chicken stock" is not chicken, "basil pesto" is not basil. When one of these
# appears after the matched food, the match must cover the product word itself
# ("basil pesto" -> pesto, "vanilla yogurt" -> yogurt). If no vocabulary name
# does, the matcher abstains instead of falling back to the food word: a missed
# match only drops a recipe from "cookable now", a wrong one lists a recipe you
# can't make. Found by forkcast-evals stage 1, where this one class caused 22 of
# 23 false "cookable" recipes. Deliberately absent: "chips" (chocolate chips is
# the ingredient), "powder" (garlic powder is garlic), "juice" (lemon juice is
# lemon), "meal" (almond meal), "granules" (garlic granules is garlic). A
# matched name that is itself a product ("pesto sauce", "pudding mix", "taco
# seasoning mix") is kept.
_PRODUCT_WORDS = frozenset({
    "stock", "broth", "bouillon", "cube", "concentrate", "base", "bun",
    "paste", "puree", "sauce", "soup", "gravy", "pesto", "salsa", "dressing",
    "marinade", "extract", "mix", "spread", "jam", "jelly", "preserve",
    "cereal", "pudding", "yogurt", "yoghurt",
    # D29, found by the stage 1 tightening: "tomato juice" is not tomatoes,
    # "chicken sausage" is not chicken, "raisin bread" is not raisins.
    "juice", "nectar", "syrup", "wafer", "cookie", "cracker", "bread", "bagel",
    "roll", "tortilla", "sausage", "bologna", "pickle", "hummus", "hommus",
    "tea", "noodle", "spaghetti", "gelatin", "jell", "jello", "candy",
    # D35: flavoured milk is milk (labelling rule 7), "strawberry milk" is
    # not strawberries. Plant milks are their own names and match whole.
    "milk",
    # prepared foods named after their filling
    "pizza", "nugget", "sandwich", "wrap", "snack",
})

# Juice squeezed from these is the fruit itself (rule 7 of the eval's
# labelling guide): "lemon juice" is lemon, "tomato juice" is a product.
_JUICED_FRUIT = frozenset({
    "lemon", "lime", "orange", "grapefruit", "tangerine", "mandarin",
    "clementine", "yuzu", "citrus", "blood orange", "key lime",
})

# Products the vocabulary has no name for, whose last word is nonetheless a
# food it does have: powdered sugar is not the sugar staple. Abstain on them.
_ABSTAIN_PHRASES = (
    "powdered sugar", "confectioners sugar", "confectioner sugar", "icing sugar",
    "seasoning salt", "seasoned salt",
    # D29: products named with the food word last or in front
    "creamed corn", "cream style corn", "potato flake", "instant potato",
    "instant mashed potato", "instant mashed potatoe", "potato chip", "fried onion",
    "macaroni and cheese", "macaroni cheese", "mac and cheese", "mac cheese",
    "rice a roni",
)


def _singular_words(t: str) -> list[set[str]]:
    """Each word of the phrase with its singular candidates."""
    return [set(_word_variants(w)) for w in t.split()]


class Normalizer:
    def __init__(self, vocab_names: Iterable[str]):
        names = set(vocab_names)
        self._canon = {n.replace("_", " "): n for n in names}
        self._aliases = {
            k: v for k, v in ALIASES.items() if v in names
        }
        # Longest first, then alphabetical. The second key is not cosmetic:
        # keying on length alone left equal-length spans to be broken by set
        # iteration order, so "bread flour" matched bread or flour depending
        # on the process's hash seed. Arbitrary but stable beats arbitrary.
        self._by_len = sorted(self._canon, key=lambda c: (-len(c), c))
        # Every word in a known name or alias, for spelling suggestions (D46).
        self._words = sorted({w for phrase in [*self._canon, *self._aliases] for w in phrase.split()})
        # Compound names that may override a narrower word they contain.
        self._compounds = {
            k: v for k, v in self._aliases.items() if k in _COMPOUND_UPGRADES
        }

    def _lookup(self, phrase: str) -> str | None:
        for v in _phrase_variants(phrase):
            if v in self._aliases:
                return self._aliases[v]
            if v in self._canon:
                return self._canon[v]
        return None

    def suggest(self, raw: str, limit: int = 3) -> list[str]:
        """Known names close to something match() didn't recognise (D46).

        Spelling only: difflib over the vocabulary and the aliases, so
        "tomatoe" or "chiken" get an offer. A name it has nothing close to,
        like a brand, gets none, which beats a confident wrong guess.
        """
        t = _clean(raw)
        if not t:
            return []
        out: list[str] = []
        # First, each misspelled word corrected to a known one, and the
        # phrase matched as usual: "chiken breast" -> "chicken breast".
        fixed = [w if w in self._words else next(iter(difflib.get_close_matches(w, self._words, n=1, cutoff=0.85)), w)
                 for w in t.split()]
        if fixed != t.split():
            hit = self.match(" ".join(fixed))
            if hit:
                out.append(hit)
        # Then whole names spelled alike: "mozarella" -> mozzarella cheese.
        for key in difflib.get_close_matches(t, [*self._canon, *self._aliases], n=limit * 3, cutoff=0.75):
            name = self._canon.get(key) or self._aliases[key]
            if name not in out:
                out.append(name)
        return out[:limit]

    def match(self, raw: str) -> str | None:
        t = _clean(raw)
        if not t:
            return None
        # Before any rewriting: a name that *is* the whole phrase wins outright.
        # "gluten free flour" is its own ingredient, and stripping the negation
        # out of it would leave plain flour.
        hit = self._lookup(t)
        if hit:
            return hit

        t = _strip_negations(t)
        if not t:
            return None
        # "X with Y" names an ingredient plus whatever it comes packed with, so
        # the head segment is the ingredient: "diced tomatoes with green
        # chilies" is tomatoes. Only trusted when the head actually matches —
        # otherwise the whole phrase is tried, exactly as before.
        head = _head_segment(t)
        # ...unless the whole phrase is a soup (D29): "condensed chicken with
        # rice soup" is not chicken. Only soup: "tomatoes with juice" and
        # "peaches in syrup" are still the fruit, packed in its liquid.
        if head and t.split()[-1] in ("soup", "soups"):
            head = None
        if head:
            hit = self._match_phrase(head)
            if hit is not None:
                # "" is a deliberate abstain (D27): "tomato sauce with basil"
                # names a sauce, so it must not fall through to match basil.
                return hit or None
        return self._match_phrase(t) or None

    def _match_phrase(self, t: str) -> str | None:
        hit = self._lookup(t)
        if hit:
            return hit
        stripped = " ".join(w for w in t.split() if w not in DESCRIPTORS)
        if stripped and stripped != t:
            hit = self._lookup(stripped)
            if hit:
                return hit
        base = stripped or t
        if any(f" {p} " in f" {x} " or f" {p}s " in f" {x} "
               for p in _ABSTAIN_PHRASES for x in (base, t)):
            return ""
        found = self._containment(base)
        # Descriptor stripping can break a longer name apart: "dried" is a
        # descriptor, so "sun dried tomato" became "sun tomato" and matched
        # tomato. A longer name in the unstripped phrase wins (D27).
        unstripped = self._containment(t) if base != t else None
        if unstripped and (found is None or len(unstripped[0]) > len(found[0])):
            found, base = unstripped, t
        if found is None:
            return None
        matched, target = found
        product = self._product_guard(base, matched, target)
        if product is not None:
            return product  # "" means abstain; match() turns it into None
        return self._compound_upgrade(base, matched) or target

    def _product_guard(self, base: str, matched: str, target: str | None = None) -> str | None:
        """The product a phrase names, "" to abstain, or None if no product word.

        Looks for a product word (stock, paste, pesto, ...) after the matched
        span. If one is there, the answer must be a name that covers it: the
        longest canonical name or alias in the phrase that contains that
        word. Without one, "" tells the caller to abstain.
        """
        words = _singular_words(base)
        span = matched.split()
        # A matched name that is itself a product stays ("pesto sauce"). Not
        # for milk (D35): "coconut milk vanilla yogurt" goes on to the yogurt.
        if set(_word_variants(span[-1])) & ((_PRODUCT_WORDS - {"milk"}) | {"seasoning"}):
            return None
        juiced = matched in _JUICED_FRUIT
        start = next(
            (i for i in range(len(words) - len(span) + 1)
             if all(span[j] in words[i + j] for j in range(len(span)))),
            None,
        )
        if start is None:
            return None
        after = range(start + len(span), len(words))
        k = next((i for i in reversed(after)
                  if words[i] & _PRODUCT_WORDS and not (juiced and "juice" in words[i])), None)
        if k is None:
            return None
        best = None
        names = list(self._canon.items()) + list(self._aliases.items())
        for name, product in names:
            n = name.split()
            for i in range(max(0, k - len(n) + 1), min(k, len(words) - len(n)) + 1):
                if all(n[j] in words[i + j] for j in range(len(n))):
                    if best is None or len(name) > len(best[0]):
                        best = (name, product)
        if best is None:
            return ""
        # D29: a food already of the product's kind stays itself. "chorizo
        # sausage" is chorizo and "spaghetti noodles" is pasta: both share a
        # food class (D28) with the product word's own entry.
        cls = NAME_TO_CLASS.get(target) if target else None
        if cls is not None and cls == NAME_TO_CLASS.get(best[1]):
            return None
        return best[1]

    def _containment(self, base: str) -> tuple[str, str] | None:
        """Canonical span in the phrase, as (matched text, canonical).

        Within one spelling of the phrase, the longest canonical name wins,
        and aliases are only tried when there is none: an alias overriding a
        canonical word is opt-in (_COMPOUND_UPGRADES), or "salt and pepper"
        becomes pepper. Phrase variants (last word singularized) expose plural
        tails: "red bell peppers" still contains "bell pepper".

        D29: a later variant replaces the earlier match only when its span
        *extends* it. Returning the first variant's hit let "flour" beat
        "flour tortilla" and "kidney" beat "kidney bean"; letting any longer
        span win instead turned "spaghetti noodles" (pasta) into noodle and
        "kiwi fruits" into fruit.
        """
        best = None
        for pv in _phrase_variants(base):
            hit = self._span_in(f" {pv} ")
            if hit is None:
                continue
            if best is None:
                best = hit
            elif len(hit[0]) > len(best[0]) and f" {best[0]} " in f" {hit[0]} ":
                best = hit
        return best

    def _span_in(self, hay: str) -> tuple[str, str] | None:
        """Longest canonical name in one spelling, else the longest alias."""
        for c in self._by_len:
            if len(c) >= 3 and c in hay and f" {c} " in hay:
                return c, self._canon[c]
        best = None
        for a, target in self._aliases.items():
            if f" {a} " in hay and (best is None or len(a) > len(best[0])):
                best = (a, target)
        return best

    def _compound_upgrade(self, base: str, matched: str) -> str | None:
        """A compound name beats the narrower word it contains.

        "cherry tomatoes" hits "cherry" first, because "tomatoes" is not
        itself a canonical name — but the phrase also contains the compound
        "cherry tomato", which names the actual ingredient and contains the
        word already matched. Narrow by design: a compound only wins over a
        word it fully contains, so "garlic clove" and "salt and pepper" are
        untouched. Phrase variants are checked too, so the singular spelling
        is seen in "yellow cherry tomatoes".
        """
        for pv in _phrase_variants(base):
            hay = f" {pv} "
            for compound, target in self._compounds.items():
                if compound == matched:
                    continue
                if f" {compound} " in hay and f" {matched} " in f" {compound} ":
                    return target
        return None


def packaged(normalizer: "Normalizer", name: str) -> str | None:
    """Match a name read off a product (a photo of groceries), not a recipe line.

    Labelling rule 7: juice squeezed from a fresh fruit is the fruit, but a
    bottled juice product is fruit_juice. A recipe's "orange juice" is the
    first kind; a carton the scanner reads as "orange juice" is the second,
    and mapping it to orange would claim you have oranges (D35).
    """
    hit = normalizer.match(name)
    words = set(_clean(name).split())
    if words & {"juice", "juices"} and (hit is None or hit in _JUICED_FRUIT):
        return "fruit_juice" if "fruit juice" in normalizer._canon else None
    return hit
