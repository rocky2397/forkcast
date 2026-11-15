"""Photo intake (D8): groceries photo -> structured item list via Claude vision.

Model is claude-haiku-4-5 per decision D8 (pure read-into-schema work; the
mandatory confirm screen makes occasional misreads cheap). Structured outputs
guarantee validated JSON. Results are proposals — nothing is written to the
inventory here; the client confirms and calls POST /api/inventory.
"""

import base64
from functools import lru_cache

import anthropic
from pydantic import BaseModel

MODEL = "claude-haiku-4-5"

PROMPT = """List every distinct food item you can identify in this photo.

Rules:
- One entry per distinct item type (e.g. "bell pepper", not one entry per pepper).
- Use the item's generic English food name, even if packaging text is in German
  (e.g. a "Sahne" carton -> "cream").
- Include quantity as a rough count or amount when clearly visible, else null.
- confidence: how sure you are the item is identified correctly (0-1).
- Ignore non-food objects, brands, and preparation words."""


class SeenItem(BaseModel):
    name: str
    quantity: str | None = None
    confidence: float


class ScanResult(BaseModel):
    items: list[SeenItem]


@lru_cache(maxsize=1)
def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic()  # ANTHROPIC_AUTH_TOKEN / ANTHROPIC_API_KEY from env


def _parse(image_bytes: bytes, media_type: str, prompt: str, output_format, model: str = MODEL, **options):
    """One vision call. `model` and `options` (e.g. output_config) exist for the eval."""
    data = base64.standard_b64encode(image_bytes).decode()
    response = _client().messages.parse(
        model=model,
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
                {"type": "text", "text": prompt},
            ],
        }],
        output_format=output_format,
        **options,
    )
    return response.parsed_output


def extract_items(image_bytes: bytes, media_type: str, model: str = MODEL, **options) -> ScanResult:
    return _parse(image_bytes, media_type, PROMPT, ScanResult, model, **options)


# D37: the label part names the mistakes eval stage 5 found, most damaging
# first (eval/RESULTS-stage5.md): kJ read as kcal, a value taken from the next
# row, a lost decimal comma, and the per-portion column.
PRODUCT_PROMPT = """This is a photo of a packaged food product (or its label).

Extract:
- barcode: the digits printed under/near the barcode (EAN-13/EAN-8/UPC), only if
  every digit is clearly legible; otherwise null. Never guess digits.
- product_name: the product's name from the packaging (keep the original language).
- per_100g: calories, protein, carbs and fat per 100 g (or 100 ml) from the
  nutrition table. Labels are often in several languages at once; the rules are
  the same. null for anything you can't read.

First write out the table in `table`: every row from top to bottom, its name as
printed (one language is enough) and the value in the 100 g column exactly as
printed, unit included ("1463 kJ / 350 kcal", "<0,5 g", "3,7 g"). Then fill
per_100g from those rows.

How to read the nutrition table:
1. Column: use the "100 g" / "100 ml" column ("je 100 g", "pour 100 g", "per
   100 g"), never the portion, serving, slice or piece column, even when it is
   larger or easier to read.
2. Energy: the label gives kJ and kcal, often as "1463 kJ / 350 kcal". Report the
   kcal number, the one marked kcal. The kJ number is about 4.2 times larger.
3. Decimal commas: "1,2 g" is 1.2, not 12. "0,5" is 0.5.
4. Rows: take each value from its own row, not the row below or above.
   - fat is the "Fett" / "Fat" / "Matières grasses" line itself, never "davon
     gesättigte Fettsäuren" / "of which saturates".
   - carbs is "Kohlenhydrate" / "Carbohydrate", never "davon Zucker" / "sugars".
   - protein is "Eiweiß" / "Protein", never "Ballaststoffe" / "fibre" or "Salz" /
     "salt".
   On curved or crumpled packs the numbers can sit lower than their names; match
   them by order, counting the rows.
5. Check: calories should be close to 9 × fat + 4 × (carbs + protein). If they
   are far apart, you have probably read a kJ value, lost a decimal comma or
   taken a value from the wrong row: read the table again."""


class NutritionPer100g(BaseModel):
    calories: float | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None


class TableRow(BaseModel):
    """One row of the nutrition table, as printed (D37)."""

    name: str
    per_100g: str | None = None  # the value in the 100 g / 100 ml column, as printed


class ProductScan(BaseModel):
    barcode: str | None = None
    product_name: str | None = None
    # D37: written out before per_100g, so each value is matched to its row by
    # name rather than by position. The app itself only uses per_100g.
    table: list[TableRow] | None = None
    per_100g: NutritionPer100g | None = None


def extract_product(image_bytes: bytes, media_type: str) -> ProductScan:
    return _parse(image_bytes, media_type, PRODUCT_PROMPT, ProductScan)
