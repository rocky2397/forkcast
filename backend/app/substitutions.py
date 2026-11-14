"""Substitution suggestions (D13, D28): can something in the inventory stand
in for a recipe's missing ingredient?

A stand-in must share a food class with the missing ingredient, and then rank
within its top SAME_CLASS_COOC_MAX cooc neighbours (used in similar recipes).
Outside the class map the engine stays silent.

D13 also accepted unclassed pairs that passed a dual rank gate (cooc and chem).
The stage 2 eval (eval/RESULTS-stage2.md) showed that path was wrong four
times out of five: embedding ranks can't tell a substitute from a complement
(coconut -> banana, coffee -> chocolate, chicken broth -> bell pepper). Classes
are the signal that can, so D28 widened the map from 8 to 47 classes and
dropped the unclassed path. A missing hint costs nothing; a bad one costs trust.
"""

from functools import lru_cache

import numpy as np

from . import embeddings
from .recipes import STAPLES

SAME_CLASS_COOC_MAX = 400  # class vouches for "same kind"; cooc keeps it plausible

# Food classes: things that can take each other's place in a dish. Built from
# what the foods are used for, not from what the embeddings say, and kept
# narrow where the role splits (melting vs grating cheese, fresh vs dried
# chili, solid fat vs oil). One class per name. Names not in the vocabulary
# are harmless: they never match.
CLASSES: dict[str, set[str]] = {
    # proteins
    "meat": {"chicken", "turkey", "duck", "beef", "ground_beef", "pork", "lamb",
             "veal", "steak", "venison", "rabbit", "goat"},
    "cured_meat": {"bacon", "canadian_bacon", "ham", "pancetta", "prosciutto",
                   "serrano_ham", "iberico_ham", "salami", "pepperoni", "chorizo",
                   "sausage", "italian_sausage", "andouille_sausage", "kielbasa",
                   "turkey_sausage", "summer_sausage", "chinese_sausage"},
    "seafood": {"salmon", "tuna", "cod", "trout", "halibut", "tilapia", "shrimp",
                "prawn", "crab", "lobster", "scallop", "mussel", "clam", "squid",
                "octopus", "anchovy", "sardine", "mackerel", "haddock", "catfish"},
    "egg": {"egg", "egg_white", "egg_yolk", "egg_substitute", "duck_egg", "quail_egg"},
    "bean": {"bean", "black_bean", "pinto_bean", "kidney_bean", "cannellini_bean",
             "navy_bean", "white_bean", "borlotti_bean", "flageolet_bean",
             "red_bean", "black_eyed_pea", "chickpea", "lentil"},
    # dairy and cheese
    "dairy": {"yogurt", "sour_cream", "cream", "creme_fraiche", "quark",
              "buttermilk", "milk", "kefir", "evaporated_milk",
              "mascarpone_cheese", "cream_cheese", "neufchatel_cheese"},
    "melting_cheese": {"cheese", "cheddar_cheese", "monterey_jack_cheese",
                       "colby_cheese", "mozzarella_cheese", "swiss_cheese",
                       "emmental_cheese", "gruyere_cheese", "gouda_cheese",
                       "provolone_cheese", "fontina_cheese", "havarti_cheese",
                       "muenster_cheese", "jarlsberg_cheese", "edam_cheese",
                       "american_cheese", "velveeta_cheese", "chihuahua_cheese",
                       "oaxaca_cheese", "brick_cheese", "raclette_cheese"},
    "hard_cheese": {"parmesan_cheese", "pecorino_cheese", "romano_cheese",
                    "asiago_cheese", "manchego_cheese", "queso_anejo",
                    "ricotta_salata"},
    "crumbly_cheese": {"feta_cheese", "goat_cheese", "cotija_cheese", "queso_fresco",
                       "queso_blanco", "panela_cheese"},
    "soft_cheese": {"ricotta_cheese", "cottage_cheese", "farmer_cheese"},
    # vegetables
    "allium": {"onion", "garlic", "shallot", "leek", "scallion", "chive",
               "garlic_chive", "red_onion", "pearl_onion"},
    "green_veg": {"broccoli", "broccolini", "chinese_broccoli", "broccoli_rabe",
                  "cauliflower", "brussels_sprout", "asparagus", "green_bean",
                  "pea", "snow_pea", "sugar_snap_pea", "zucchini", "squash"},
    "aromatic_root": {"carrot", "celery", "parsnip", "celeriac", "fennel"},
    "starchy_root": {"potato", "sweet_potato", "yam", "purple_sweet_potato",
                     "butternut_squash", "acorn_squash"},
    "cooking_green": {"spinach", "kale", "swiss_chard", "collard_green",
                      "mustard_green", "turnip_green", "malabar_spinach",
                      "water_spinach"},
    "salad_green": {"lettuce", "salad_greens", "arugula", "endive", "watercress"},
    "cabbage": {"cabbage", "napa_cabbage", "bok_choy"},
    "mushroom": {"mushroom", "shiitake_mushroom", "porcini_mushroom",
                 "portobello_mushroom", "oyster_mushroom", "king_oyster_mushroom",
                 "chanterelle_mushroom", "enoki_mushroom", "maitake_mushroom",
                 "morel_mushroom", "straw_mushroom"},
    "fresh_chili": {"jalapeno", "serrano_pepper", "habanero_pepper", "green_chili",
                    "chili_pepper", "birds_eye_chili", "anaheim_chile", "hatch_chile"},
    "dried_chili": {"cayenne_pepper", "chili_powder", "red_pepper", "paprika",
                    "smoked_paprika", "chipotle_pepper", "ancho_chile",
                    "guajillo_chile", "chile_de_arbol", "kashmiri_chili",
                    "new_mexico_chile", "pasilla_chile", "hot_sauce", "sriracha",
                    "chili_paste"},
    "olive_caper": {"olive", "black_olive", "green_olive", "caper", "caperberry"},
    # herbs and spices
    "herb": {"basil", "thai_basil", "oregano", "thyme", "rosemary", "parsley",
             "coriander", "dill", "sage", "tarragon", "mint", "marjoram",
             "bay_leaf", "chervil", "savory", "herb", "italian_seasoning"},
    "warm_spice": {"cinnamon", "nutmeg", "mace", "allspice", "clove",
                   "pumpkin_pie_spice", "apple_pie_spice", "gingerbread_spice"},
    "spice_blend": {"curry_powder", "garam_masala"},
    "ginger": {"ginger", "galangal", "sand_ginger"},
    # fruit
    "citrus": {"lemon", "lime", "orange", "grapefruit", "yuzu", "tangerine",
               "mandarin", "clementine", "kaffir_lime", "lemongrass"},
    "berry": {"berry", "blueberry", "raspberry", "strawberry", "blackberry",
              "boysenberry", "huckleberry", "mulberry", "loganberry"},
    "stone_fruit": {"peach", "nectarine", "apricot", "plum", "cherry"},
    "pome_fruit": {"apple", "pear", "asian_pear"},
    "tropical_fruit": {"pineapple", "mango", "papaya"},
    "dried_fruit": {"raisin", "prune", "date", "fig", "red_date"},
    "nut": {"nut", "almond", "walnut", "pecan", "cashew", "hazelnut", "pistachio",
            "macadamia_nut", "brazil_nut", "peanut", "pine_nut"},
    "seed": {"sesame_seed", "black_sesame_seed", "sunflower_seed", "pumpkin_seed",
             "flaxseed", "chia_seed", "hemp_seed", "poppy_seed"},
    # starches
    "grain": {"rice", "basmati_rice", "couscous", "quinoa", "bulgur", "barley",
              "farro", "millet", "orzo", "polenta"},
    "noodle": {"pasta", "noodle", "egg_noodle", "rice_noodle", "ramen_noodle",
               "udon_noodle", "somen_noodle", "vermicelli", "glass_noodle"},
    "flatbread": {"tortilla", "flour_tortilla", "corn_tortilla", "pita_bread",
                  "naan", "flatbread"},
    "bread": {"bread", "english_muffin", "bagel", "rye_bread", "milk_bread"},
    "flour": {"flour", "all_purpose_flour", "whole_wheat_flour", "gluten_free_flour"},
    # pantry
    "sweetener": {"honey", "maple_syrup", "sugar", "brown_sugar", "agave_nectar",
                  "molasses", "corn_syrup", "golden_syrup"},
    "chocolate": {"chocolate", "milk_chocolate", "cocoa_powder", "cocoa_mass"},
    "vinegar": {"vinegar", "white_vinegar", "rice_vinegar", "apple_cider_vinegar",
                "red_wine_vinegar", "white_wine_vinegar", "balsamic_vinegar",
                "sherry_vinegar", "champagne_vinegar", "malt_vinegar"},
    "broth": {"broth", "chicken_broth", "meat_stock", "vegetable_stock",
              "consomme", "turkey_stock", "pork_stock", "duck_stock",
              "game_stock", "mushroom_stock"},
    "cooking_wine": {"white_wine", "vermouth", "sherry", "shaoxing_wine",
                     "rice_wine", "sake", "marsala_wine", "madeira_wine"},
    "umami_sauce": {"soy_sauce", "light_soy_sauce", "dark_soy_sauce", "tamari",
                    "white_soy_sauce", "mushroom_soy_sauce", "fish_sauce",
                    "worcestershire_sauce"},
    "thick_sauce": {"hoisin_sauce", "oyster_sauce", "vegetarian_oyster_sauce",
                    "teriyaki_sauce", "sweet_soy_sauce"},
    "solid_fat": {"margarine", "shortening", "lard", "ghee", "coconut_oil",
                  "duck_fat", "chicken_fat", "goose_fat"},
    "oil": {"oil", "vegetable_oil", "canola_oil", "corn_oil", "peanut_oil",
            "sunflower_oil", "safflower_oil", "grapeseed_oil", "avocado_oil",
            "soybean_oil", "rice_bran_oil"},
}

_NAME_TO_CLASS: dict[str, str] = {}
for _cls, _names in CLASSES.items():
    for _name in _names:
        assert _name not in _NAME_TO_CLASS, f"{_name} is in two classes"
        _NAME_TO_CLASS[_name] = _cls


@lru_cache(maxsize=1)
def _index() -> dict[str, int]:
    return {name: i for i, name in enumerate(embeddings.vocabulary())}


@lru_cache(maxsize=512)
def _cooc_ranks(name: str) -> np.ndarray | None:
    """Per-vocab-entry cooc neighbour rank of `name` (0 = itself)."""
    idx = _index().get(name)
    if idx is None:
        return None
    M = embeddings.unit_matrix("cooc")
    sims = M @ M[idx]
    ranks = np.empty(len(sims), dtype=np.int32)
    ranks[np.argsort(-sims)] = np.arange(len(sims))
    return ranks


def _pair_score(a: str, b: str) -> int | None:
    """Gate a->b, returning a sort score (lower = better) or None.

    Both in the same class: cooc rank within SAME_CLASS_COOC_MAX.
    Anything else is rejected: a class mismatch is the complement risk
    (duck->ginger), and an unclassed pair has nothing to vouch for it.
    """
    cls_a = _NAME_TO_CLASS.get(a)
    if cls_a is None or cls_a != _NAME_TO_CLASS.get(b):
        return None
    ranks = _cooc_ranks(a)
    if ranks is None:
        return None
    rc = int(ranks[_index()[b]])
    return rc if rc <= SAME_CLASS_COOC_MAX else None


def suggest(missing: str, candidates: list[str]) -> str | None:
    """Best in-inventory stand-in for `missing`, or None if nothing passes.

    Forward direction only: the cooc rank is read from the missing
    ingredient's side, so an occasional asymmetric miss is accepted. Staples
    are excluded as sources (hub ingredients; and they are assumed present
    anyway), as should be anything already in the recipe (callers pass
    candidates accordingly).
    """
    idx = _index()
    # Staples are hubs on both sides: as a missing ingredient they'd match
    # half the pantry (salt->ginger), and they're assumed present anyway.
    if missing not in idx or missing in STAPLES:
        return None
    best, best_score = None, None
    for cand in candidates:
        if cand == missing or cand in STAPLES or cand not in idx:
            continue
        score = _pair_score(missing, cand)
        if score is None:
            continue
        if best_score is None or score < best_score:
            best, best_score = cand, score
    return best
