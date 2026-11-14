"""Food classes (D28): things that can take each other's place in a dish.

Shared by the substitution engine (a stand-in must share a class with the
missing ingredient) and the matcher (D29: a food already of the product's
class is not rewritten to it, so "chorizo sausage" stays chorizo).
No imports, so the matcher stays free of numpy and the embeddings.
"""

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

NAME_TO_CLASS: dict[str, str] = {}
for _cls, _names in CLASSES.items():
    for _name in _names:
        assert _name not in NAME_TO_CLASS, f"{_name} is in two classes"
        NAME_TO_CLASS[_name] = _cls
