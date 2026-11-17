"""Packaged-food nutrition (D9): Open Food Facts lookup + products cache.

Barcode-first: an OFF hit costs nothing and has strong German coverage.
Values are per 100 g (the EU-mandated reference on every Nährwerttabelle).
"""

import json
import sqlite3
import urllib.error
import urllib.request

OFF_URL = (
    "https://world.openfoodfacts.org/api/v2/product/{code}.json"
    "?fields=product_name,brands,nutriments"
)
# OFF asks API users to identify themselves.
USER_AGENT = "Forkcast/0.1 (personal food-inventory app)"


class OffUnavailable(Exception):
    """Open Food Facts could not be reached."""


def _num(nutriments: dict, key: str) -> float | None:
    v = nutriments.get(key)
    return float(v) if isinstance(v, (int, float)) else None


def fetch_off(code: str) -> dict | None:
    """Look up a barcode on Open Food Facts. None = not in the database."""
    req = urllib.request.Request(OFF_URL.format(code=code), headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise OffUnavailable(str(e))
    except (urllib.error.URLError, TimeoutError) as e:
        raise OffUnavailable(str(e))
    if data.get("status") != 1:
        return None
    p = data["product"]
    n = p.get("nutriments", {})
    return {
        "barcode": code,
        "name": p.get("product_name") or None,
        "brand": p.get("brands") or None,
        "calories_100g": _num(n, "energy-kcal_100g"),
        "protein_g_100g": _num(n, "proteins_100g"),
        "carbs_g_100g": _num(n, "carbohydrates_100g"),
        "fat_g_100g": _num(n, "fat_100g"),
        "source": "openfoodfacts",
    }


def cached(con: sqlite3.Connection, code: str) -> dict | None:
    row = con.execute("SELECT * FROM products WHERE barcode = ?", (code,)).fetchone()
    return dict(row) if row else None


def cache(con: sqlite3.Connection, product: dict) -> None:
    con.execute(
        """INSERT OR REPLACE INTO products
           (barcode, name, brand, calories_100g, protein_g_100g, carbs_g_100g, fat_g_100g, source)
           VALUES (:barcode, :name, :brand, :calories_100g, :protein_g_100g,
                   :carbs_g_100g, :fat_g_100g, :source)""",
        product,
    )
    con.commit()


def lookup(con: sqlite3.Connection, code: str) -> dict | None:
    """Cache-first barcode lookup; OFF hits are cached so each product costs once."""
    hit = cached(con, code)
    if hit is not None:
        return hit
    product = fetch_off(code)
    if product is not None:
        cache(con, product)
    return product


# D36: calories follow from the macros (about 9 kcal per gram of fat, 4 per
# gram of carbs or protein). On 150 Open Food Facts products (eval stage 5) a
# reading that broke this sum by more than 20% (and 40 kcal) was a misreading
# in 8 of 13 checked mistakes, and only 1 of 74 right readings tripped it.
SUM_TOLERANCE = 0.20
SUM_MIN_GAP_KCAL = 40


MISREADINGS = (
    "The usual misreadings are kJ instead of kcal, a lost decimal comma or a value from the next row."
)
KCAL_PER_G = {"protein": 4, "carbs": 4, "fat": 9}


def _names(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def label_check(calories, protein_g, carbs_g, fat_g) -> str | None:
    """A warning for values read off a label that are missing or don't add up."""
    if calories is None:
        return "The calories couldn't be read from the photo. Please check them against the label."
    values = {"protein": protein_g, "carbs": carbs_g, "fat": fat_g}
    missing = [n for n, v in values.items() if v is None]
    read = [n for n, v in values.items() if v is not None]
    expected = sum(KCAL_PER_G[n] * values[n] for n in read)
    # With a value missing, the ones read are only a lower bound: they can
    # still give away a misreading by making more kcal than the label has.
    gap = max(expected - calories, 0) if missing else abs(calories - expected)
    adds_up = not (gap > SUM_TOLERANCE * max(calories, expected) and gap > SUM_MIN_GAP_KCAL)
    if not missing:
        if adds_up:
            return None
        return (
            f"These numbers don't add up: {round(calories)} kcal, but the fat, carbs and protein "
            f"make about {round(expected)} kcal. Please check them against the label. {MISREADINGS}"
        )
    unread = _names(missing).capitalize()
    if adds_up:
        return f"{unread} couldn't be read from the photo. Please check against the label."
    return (
        f"{unread} couldn't be read from the photo, and the rest don't add up: {round(calories)} kcal "
        f"is less than the {_names(read)} alone would give (about {round(expected)} kcal). "
        f"Please check them against the label. {MISREADINGS}"
    )
