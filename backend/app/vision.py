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


def extract_items(image_bytes: bytes, media_type: str) -> ScanResult:
    data = base64.standard_b64encode(image_bytes).decode()
    response = _client().messages.parse(
        model=MODEL,
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
                {"type": "text", "text": PROMPT},
            ],
        }],
        output_format=ScanResult,
    )
    return response.parsed_output
