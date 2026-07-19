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
