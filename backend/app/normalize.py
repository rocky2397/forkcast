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
        hit = self._lookup(t)
        if hit:
            return hit
        stripped = " ".join(w for w in t.split() if w not in DESCRIPTORS)
        if stripped and stripped != t:
            hit = self._lookup(stripped)
            if hit:
                return hit
        base = stripped or t
        found = self._containment(base)
        if found is None:
            return None
        matched, target = found
        return self._compound_upgrade(base, matched) or target

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
