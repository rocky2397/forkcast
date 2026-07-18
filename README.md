# Forkcast 🍴

**What should I cook next?** A personal food-inventory app that suggests
recipes from what's actually in your kitchen, learns your taste over time,
and keeps your calories and macros on target.

Built on the [Epicure ingredient embeddings](https://huggingface.co/papers/2605.22391)
(Radzikowski & Chen, KAIKAKU.AI) — 300-dimensional food-ingredient vectors that
answer both *"what pairs with this?"* and *"what substitutes for this?"*.

## Planned features

- 📦 **Inventory** — log groceries by taking a photo (Claude vision extraction),
  by scanning barcodes (Open Food Facts), or by typing
- 🍳 **Recipe suggestions** — ranked by what you can cook *right now*,
  substitution-aware ("your tarragon can stand in for basil")
- 👅 **Taste learning** — your taste profile is an embedding centroid of what
  you cook and like; suggestions get more *you* over time
- 💪 **Macros & goals** — German Nährwerttabelle scanning, USDA nutrition data,
  formula-based daily targets (Mifflin-St Jeor), and suggestions that help you
  hit them
- 📱 **PWA** — web-first, installable on your phone

## Status

Planning phase. See:

- [`APP_DECISIONS.md`](APP_DECISIONS.md) — product & architecture decision log
- [`EPICURE_PAPER_NOTES.md`](EPICURE_PAPER_NOTES.md) — notes on the paper this builds on

Stack (decided): FastAPI + React PWA, Epicure embeddings
([`Kaikaku/epicure-*`](https://huggingface.co/Kaikaku/epicure-core), CC BY 4.0),
RecipeNLG-derived recipe corpus, Claude Haiku for vision intake.

## Attribution

Epicure embeddings: Jakub Radzikowski & Josef Chen (KAIKAKU.AI),
[arXiv:2605.22391](https://arxiv.org/abs/2605.22391), weights CC BY 4.0.
