"""Map free-text ingredient strings to Epicure's canonical vocabulary.

Cascade (cheap first):
  1. alias table (common synonyms the vocabulary spells differently)
  2. exact match after cleanup, over singular/plural variants
  3. descriptor stripping ("fresh chopped cilantro" -> "cilantro"), retry
  4. longest canonical name contained as a whole-word span

All variant generation is membership-checked against the vocabulary, so a
wrong guess ("chives" -> "chif") is harmless — it simply doesn't match.
"""

import re
from collections.abc import Iterable

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


def _clean(term: str) -> str:
    t = term.lower().strip()
    t = re.sub(r"\(.*?\)", " ", t)
    t = re.sub(r"[^a-z ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


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
            return " ".join(words[:i])
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
})

# Products the vocabulary has no name for, whose last word is nonetheless a
# food it does have: powdered sugar is not the sugar staple. Abstain on them.
_ABSTAIN_PHRASES = (
    "powdered sugar", "confectioners sugar", "confectioner sugar", "icing sugar",
    "seasoning salt", "seasoned salt",
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
        if any(f" {p} " in f" {base} " or f" {p}s " in f" {base} " for p in _ABSTAIN_PHRASES):
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
        product = self._product_guard(base, matched)
        if product is not None:
            return product  # "" means abstain; match() turns it into None
        return self._compound_upgrade(base, matched) or target

    def _product_guard(self, base: str, matched: str) -> str | None:
        """The product a phrase names, "" to abstain, or None if no product word.

        Looks for a product word (stock, paste, pesto, ...) after the matched
        span. If one is there, the answer must be a name that covers it: the
        longest canonical name or alias in the phrase that contains that
        word. Without one, "" tells the caller to abstain.
        """
        words = _singular_words(base)
        span = matched.split()
        if set(_word_variants(span[-1])) & (_PRODUCT_WORDS | {"seasoning"}):
            return None
        start = next(
            (i for i in range(len(words) - len(span) + 1)
             if all(span[j] in words[i + j] for j in range(len(span)))),
            None,
        )
        if start is None:
            return None
        after = range(start + len(span), len(words))
        k = next((i for i in reversed(after) if words[i] & _PRODUCT_WORDS), None)
        if k is None:
            return None
        best = None
        names = list(self._canon.items()) + list(self._aliases.items())
        for name, target in names:
            n = name.split()
            for i in range(max(0, k - len(n) + 1), min(k, len(words) - len(n)) + 1):
                if all(n[j] in words[i + j] for j in range(len(n))):
                    if best is None or len(name) > len(best[0]):
                        best = (name, target)
        return best[1] if best else ""

    def _containment(self, base: str) -> tuple[str, str] | None:
        """First canonical span in the phrase, as (matched text, canonical).

        Scans every phrase variant, so plural tails like "red bell peppers"
        still expose "bell pepper" as a span.
        """
        for pv in _phrase_variants(base):
            hay = f" {pv} "
            for c in self._by_len:
                if len(c) >= 3 and f" {c} " in hay:
                    return c, self._canon[c]
            for a, target in self._aliases.items():
                if f" {a} " in hay:
                    return a, target
        return None

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
