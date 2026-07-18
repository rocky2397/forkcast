"""Epicure embedding service: loads the three sibling models and exposes
the operators (neighbors, closest mode, SLERP) plus the vocabulary.

Models are lazy-loaded on first use and kept in memory (1,790 x 300 floats
each — trivial). The upstream loader class ships inside each model repo as
`epicure.py`; we import it from the snapshot of the first model requested.
"""

import importlib.util
import sys
from functools import lru_cache

from huggingface_hub import snapshot_download

MODELS = {
    "cooc": "Kaikaku/epicure-cooc",   # "what is cooked together" — pairings
    "core": "Kaikaku/epicure-core",   # blend — tightest modes
    "chem": "Kaikaku/epicure-chem",   # "what shares flavour chemistry" — substitutions
}


def _load_upstream_class(snapshot_path: str):
    spec = importlib.util.spec_from_file_location("epicure_upstream", f"{snapshot_path}/epicure.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["epicure_upstream"] = mod
    spec.loader.exec_module(mod)
    return mod.Epicure


@lru_cache(maxsize=None)
def get_model(name: str):
    if name not in MODELS:
        raise KeyError(f"unknown model {name!r}; expected one of {sorted(MODELS)}")
    path = snapshot_download(MODELS[name])
    Epicure = _load_upstream_class(path)
    return Epicure.from_pretrained(MODELS[name])


@lru_cache(maxsize=1)
def vocabulary() -> list[str]:
    return sorted(get_model("cooc").vocab.keys())


def neighbors(ingredient: str, model: str = "cooc", k: int = 5):
    return [
        {"ingredient": name, "similarity": round(float(sim), 4)}
        for name, sim in get_model(model).neighbors(ingredient, k=k)
    ]
