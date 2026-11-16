"""German names for common ingredients (D47).

Forkcast's ingredient names are English (the Epicure vocabulary). A tester
typing German got nothing for "Zwiebel" and the wrong thing for "Zitrone"
(citron, a different fruit). These tables translate German into English
words, and the English matcher takes it from there, so "Hähnchenbrust" goes
the same way as "chicken breast" does.

Written as _clean() leaves them: lower case, umlauts spelled out (ä -> ae,
ö -> oe, ü -> ue, ß -> ss). Only words that aren't English are here; a word
both languages use, like "orange", "butter" or "paprika", is left to the
English matcher (the tests check this), and so is "Speck", which English
recipes use for the Italian ham.

Each word translates to the plain English name, never a coarser one, so it
behaves exactly as the English does: "Tomatenmark" is tomato paste, which on
purpose matches nothing (D27: counting it as tomato made recipes look
cookable that weren't). "Paprika" is the hard one: the spice
in English, usually the vegetable in German. Alone it stays the spice;
"rote Paprika" or "Paprikaschote" is a bell pepper.
"""

# Whole phrases first: "rote paprika" must not become "red paprika".
PHRASES = {
    "rote paprika": "red bell pepper",
    "gelbe paprika": "yellow bell pepper",
    "gruene paprika": "green bell pepper",
    "rote zwiebel": "red onion",
    "rote zwiebeln": "red onion",
    "rote bete": "beet",
    "gruene bohnen": "green bean",
    "saure sahne": "sour cream",
    "brauner zucker": "brown sugar",
    "passierte tomaten": "canned tomato",
    "griechischer joghurt": "yogurt",
}

WORDS = {
    # vegetables
    "tomate": "tomato", "tomaten": "tomato",
    "zwiebel": "onion", "zwiebeln": "onion",
    "fruehlingszwiebel": "scallion", "fruehlingszwiebeln": "scallion",
    "lauchzwiebel": "scallion", "lauchzwiebeln": "scallion",
    "knoblauch": "garlic", "knoblauchzehe": "garlic", "knoblauchzehen": "garlic",
    "kartoffel": "potato", "kartoffeln": "potato",
    "suesskartoffel": "sweet potato", "suesskartoffeln": "sweet potato",
    "karotte": "carrot", "karotten": "carrot", "moehre": "carrot", "moehren": "carrot",
    "gurke": "cucumber", "gurken": "cucumber", "salatgurke": "cucumber",
    "paprikaschote": "bell pepper", "paprikaschoten": "bell pepper", "gemuesepaprika": "bell pepper",
    "pilze": "mushroom", "champignon": "mushroom", "champignons": "mushroom",
    "spinat": "spinach", "blattspinat": "spinach",
    "brokkoli": "broccoli", "blumenkohl": "cauliflower",
    "kohl": "cabbage", "weisskohl": "cabbage", "rotkohl": "red cabbage",
    "gruenkohl": "kale", "lauch": "leek", "porree": "leek",
    "sellerie": "celery", "staudensellerie": "celery",
    "kuerbis": "pumpkin", "mais": "corn", "erbsen": "pea", "bohnen": "bean",
    "kichererbsen": "chickpea", "linsen": "lentil",
    "kopfsalat": "lettuce", "eisbergsalat": "lettuce",
    "radieschen": "radish", "spargel": "asparagus", "fenchel": "fennel",
    "ingwer": "ginger", "oliven": "olive", "kapern": "caper", "meerrettich": "horseradish",
    "auberginen": "eggplant",
    # fruit
    "zitrone": "lemon", "zitronen": "lemon", "limette": "lime", "limetten": "lime",
    "apfel": "apple", "aepfel": "apple", "birne": "pear", "birnen": "pear",
    "erdbeere": "strawberry", "erdbeeren": "strawberry",
    "himbeere": "raspberry", "himbeeren": "raspberry",
    "heidelbeere": "blueberry", "heidelbeeren": "blueberry",
    "blaubeere": "blueberry", "blaubeeren": "blueberry",
    "banane": "banana", "bananen": "banana", "orangen": "orange",
    "kirsche": "cherry", "kirschen": "cherry", "pfirsich": "peach", "pfirsiche": "peach",
    "pflaume": "plum", "pflaumen": "plum", "weintrauben": "grape", "trauben": "grape",
    "aprikose": "apricot", "aprikosen": "apricot", "ananas": "pineapple",
    "rosinen": "raisin", "datteln": "date", "feigen": "fig", "kokosnuss": "coconut",
    # meat and fish
    "haehnchen": "chicken", "huhn": "chicken", "huehnchen": "chicken",
    "haehnchenbrust": "chicken breast", "haehnchenbrustfilet": "chicken breast",
    "haehnchenschenkel": "chicken thigh",
    "pute": "turkey", "putenbrust": "turkey breast", "truthahn": "turkey",
    "rindfleisch": "beef", "rinderhack": "ground beef", "hackfleisch": "ground beef",
    "schweinefleisch": "pork", "schinken": "ham",
    "wurst": "sausage", "wuerstchen": "sausage",
    "lachs": "salmon", "thunfisch": "tuna", "garnelen": "shrimp", "krabben": "shrimp",
    "fisch": "fish", "kabeljau": "cod", "forelle": "trout", "ente": "duck", "lamm": "lamb",
    # dairy and eggs
    "ei": "egg", "eier": "egg", "milch": "milk",
    "sahne": "cream", "schlagsahne": "cream", "schmand": "sour cream",
    "kaese": "cheese", "frischkaese": "cream cheese",
    "joghurt": "yogurt", "naturjoghurt": "yogurt", "magerquark": "quark",
    # pantry
    "mehl": "flour", "zucker": "sugar", "puderzucker": "powdered sugar",
    "salz": "salt", "pfeffer": "pepper", "reis": "rice", "nudeln": "pasta",
    "brot": "bread", "toastbrot": "bread", "vollkornbrot": "bread",
    "semmelbroesel": "bread crumbs", "paniermehl": "bread crumbs",
    "haferflocken": "oats", "hefe": "yeast", "trockenhefe": "yeast",
    "backpulver": "baking powder", "natron": "baking soda",
    "honig": "honey", "oel": "oil", "speiseoel": "oil", "rapsoel": "oil",
    "sonnenblumenoel": "oil", "olivenoel": "olive oil",
    "essig": "vinegar", "balsamico": "balsamic vinegar", "senf": "mustard",
    "sojasosse": "soy sauce", "sojasauce": "soy sauce",
    "bruehe": "broth", "gemuesebruehe": "vegetable stock",
    "huehnerbruehe": "chicken broth", "rinderbruehe": "beef broth",
    "tomatenmark": "tomato paste", "dosentomaten": "canned tomato",
    "kokosmilch": "coconut milk", "erdnussbutter": "peanut butter",
    "schokolade": "chocolate", "zartbitterschokolade": "dark chocolate", "kakao": "cocoa powder",
    "vanille": "vanilla", "vanillezucker": "vanilla sugar",
    "zimt": "cinnamon", "muskat": "nutmeg", "muskatnuss": "nutmeg",
    "kreuzkuemmel": "cumin", "kuemmel": "caraway seed",
    "petersilie": "parsley", "basilikum": "basil", "schnittlauch": "chives",
    "minze": "mint", "rosmarin": "rosemary", "thymian": "thyme", "koriander": "coriander",
    "lorbeer": "bay leaf", "lorbeerblatt": "bay leaf", "lorbeerblaetter": "bay leaf",
    "mandeln": "almond", "walnuss": "walnut", "walnuesse": "walnut",
    "haselnuesse": "hazelnut", "erdnuesse": "peanut", "cashewkerne": "cashew",
    "sonnenblumenkerne": "sunflower seed", "sesam": "sesame seed",
    "wasser": "water", "weisswein": "white wine", "rotwein": "red wine",
    "marmelade": "jam", "ahornsirup": "maple syrup",
    "speisestaerke": "cornstarch", "maisstaerke": "cornstarch",
    # a few describing words, so "frische Petersilie" works
    "rot": "red", "rote": "red", "roter": "red", "rotes": "red",
    "gruen": "green", "gruene": "green", "gruener": "green",
    "gelb": "yellow", "gelbe": "yellow",
    "frisch": "fresh", "frische": "fresh", "frischer": "fresh",
    "getrocknet": "dried", "getrocknete": "dried",
    "gemahlen": "ground", "gemahlener": "ground",
}


# Words German names never use but French, Spanish or Italian ones do: a
# phrase with one is another language's name, like the liqueur "creme de
# banane", which word by word would have become a banana.
NOT_GERMAN = frozenset({"de", "di", "du", "des", "la", "le", "con", "al", "alla"})


def translate(t: str) -> str | None:
    """English for a cleaned German phrase, or None when nothing in it is German."""
    if t in PHRASES:
        return PHRASES[t]
    words = t.split()
    if not any(w in WORDS for w in words) or any(w in NOT_GERMAN for w in words):
        return None
    return " ".join(WORDS.get(w, w) for w in words)
