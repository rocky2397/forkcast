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


def _parse(image_bytes: bytes, media_type: str, prompt: str, output_format):
    data = base64.standard_b64encode(image_bytes).decode()
    response = _client().messages.parse(
        model=MODEL,
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
                {"type": "text", "text": prompt},
            ],
        }],
        output_format=output_format,
    )
    return response.parsed_output


def extract_items(image_bytes: bytes, media_type: str) -> ScanResult:
    return _parse(image_bytes, media_type, PROMPT, ScanResult)


PRODUCT_PROMPT = """This is a photo of a packaged food product (or its label).

Extract:
- barcode: the digits printed under/near the barcode (EAN-13/EAN-8/UPC), only if
  every digit is clearly legible; otherwise null. Never guess digits.
- product_name: the product's name from the packaging (keep the original language).
- per_100g: values from the nutrition table (in Germany: "Nährwerte je 100 g/ml" —
  Brennwert in kcal NOT kJ, Eiweiß = protein, Kohlenhydrate = carbs, Fett = fat).
  Use the per-100g column, not the per-portion column. null for anything unreadable."""


class NutritionPer100g(BaseModel):
    calories: float | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None


class ProductScan(BaseModel):
    barcode: str | None = None
    product_name: str | None = None
    per_100g: NutritionPer100g | None = None


def extract_product(image_bytes: bytes, media_type: str) -> ProductScan:
    return _parse(image_bytes, media_type, PRODUCT_PROMPT, ProductScan)
