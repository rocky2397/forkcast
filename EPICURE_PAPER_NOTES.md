# Epicure: Navigating the Emergent Geometry of Food Ingredient Embeddings

**Authors:** Jakub Radzikowski, Josef Chen (KAIKAKU.AI)
**Source:** arXiv:2605.22391v1 [cs.AI], 21 May 2026
**Local copy:** `paper/epicure_embeddings.pdf`

---

## TL;DR

Word2vec for food ingredients, trained three ways so you can control what "similar"
means, plus a set of geometric operators (nearest-neighbour pairings, mode lookup,
SLERP rotation) for navigating the resulting space.

Every ingredient becomes a 300-D vector. There are two fundamentally different
reasons ingredients can be "similar":

1. **Recipe context** — they appear in the same recipes together (co-occurrence).
2. **Chemistry** — they share aroma molecules (from FlavorDB).

Prior work (FlavorGraph, Park et al. 2021) fused both signals with a fixed,
uncontrollable mix. Epicure makes that mix a **dial**: three sibling models with
identical architecture, hyperparameters, vocabulary, and graph backbone, differing
*only* in which random walks the skip-gram objective sees.

---

## The three models

| Model | Walks seen during training | Intuition |
|---|---|---|
| **Epicure-Cooc** | Ingredient–ingredient co-occurrence graph only (203,508 NPMI-weighted edges) | "What is cooked together" |
| **Epicure-Core** | Compound-mediated walks **+** ingredient–ingredient walks injected at 10× | Blend of both signals |
| **Epicure-Chem** | Ingredient→compound→ingredient typed walks only (80,019 edges to 2,247 flavor-compound nodes) | "What shares flavour chemistry" |

Training method: Metapath2Vec — skip-gram with negative sampling where the
"sentences" are typed random walks on a heterogeneous graph. All three: 300 dims,
100 walks/node, walk length 50, context window 7, 5 negative samples, 20 epochs,
seed 42, PyTorch + SparseAdam.

---

## Data pipeline

- **Corpus:** 4.14M recipes from 11 public datasets, 7 languages
  (~54% English RecipeNLG, ~37% Chinese XiaChuFang, plus Russian, Vietnamese,
  Spanish, Turkish, Indonesian, German, Indian-English).
- **Vocabulary:** ~200,000 raw NER ingredient strings collapsed to
  **1,790 canonical ingredients** via an LLM-augmented pipeline (Claude Opus for
  classification/translation at temperature 0, Gemini embeddings for dedup
  clustering, final manual pass). This cleanup is a major win over FlavorGraph,
  whose 6,653-item vocabulary is polluted with brand names and prep modifiers.
- **Graphs:** a 203,508-edge NPMI ingredient–ingredient graph (shared by all
  three models) and an 80,019-edge typed ingredient–compound graph (Core/Chem
  only). Compounds carry 15 flavour-category tags (citrus, fatty, floral, meaty,
  spicy, woody, …). Only 523 of the 1,790 ingredients have direct compound edges
  ("hubs"); the other 1,267 reach chemistry signal indirectly through
  hub–compound–hub walk paths.
- **Cuisine taxonomy:** 8 macro-regions (East Asian, Japanese, Southeast Asian,
  South Asian, Latin American, Mediterranean, Eastern European, Western Atlantic),
  LLM-tagged with a "distinctive marker" prompt — universal staples (salt, onion,
  egg) stay untagged.

---

## Key findings

### 1. Structure emerges without supervision
Ingredients self-organise by USDA food group (NMI ≈ 0.20–0.24) and even more
strongly by cuisine (soft NMI ≈ 0.43–0.46). **Cultural tradition shapes the
space about twice as cleanly as nutritional category.** UMAP projections show
clean East Asian / South Asian / Mediterranean / Latin American regions in all
three models.

### 2. Linear directions work (king − man + woman style)
27 continuous probes (sensory categories like citrus/fatty, USDA macronutrients)
and 8 cuisine-region probes are all linearly recoverable in all three models,
with a consistent quality ordering **Cooc < Core < Chem**:

- Baked-in sensory probes: mean Spearman ρ = 0.28 / 0.40 / 0.46
- Held-out basic tastes: 0.32 / 0.42 / 0.47
- USDA macronutrients: 0.41 / 0.45 / 0.49
- Cuisine separability (Cohen's d): 2.43 / 2.70 / 3.07

Surprising bit: **Chem wins even on probes its training schema never saw**
(basic tastes, nutrients, cuisines). Routing walks through shared aroma
compounds acts as a structural prior that sharpens everything.

### 3. Unsupervised axes are meaningful
Multi-seed-stable FastICA recovers 20 interpretable factors per model;
GMM partitioning of each factor's top quartile yields **150–200 named "modes"**
per model — coherent culinary neighbourhoods like *South Asian whole spice
blends* or *Mexican & Latin American pantry*. Mode coherence is 5–6× above
random-pair baselines (0.611/0.833/0.703 vs 0.097/0.348/0.115).

### 4. Geometry quirk
Core is much more concentrated (participation ratio 94/300 dims vs ~174 for
Cooc and ~183 for Chem) — a side effect of the 10× walk injection. It coincides
with Core's strongest clustering and tightest modes, so it's a design lever,
not a defect.

---

## The operators

Two query families run on the same 300-D space:

1. **Pairings** — top-K cosine neighbours + "which named mode does this
   ingredient live in." The sibling you query changes the *kind* of answer
   (see usage guide below).
2. **SLERP direction arithmetic** — spherical interpolation rotating a seed
   vector toward a target direction by a continuous angle θ:
   - 0° = the unmodified seed; 60° = the target's neighbourhood dominates
     (cosine to seed ≈ 0.5). The angle is a continuous explore/refine dial.
   - Targets can be **supervised** pole vectors (cuisine, food group, NOVA
     processing class) or **emergent** factor-mode poles.
   - Hero examples: `rice + South_Asian @ 30°` → curry leaf, masoor dal, urad
     dal, chana dal, fenugreek seed. `corn + Latin_American @ 30°` → salsa
     verde, tomatillo, queso fresco. `chicken + processed + Western_Atlantic
     @ 60°` → swiss cheese, steak sauce, ranch dressing.

---

## Which model to use, where, and in what context

### Availability — released on HuggingFace (post-paper)

The paper (21 May 2026) says *"code and trained artefacts are not released at
this time"* — but on **27 May 2026** KAIKAKU released everything on
HuggingFace under the `Kaikaku` org, all **CC BY 4.0**:

| Artefact | HuggingFace ID | Notes |
|---|---|---|
| **Epicure-Cooc** weights | [`Kaikaku/epicure-cooc`](https://huggingface.co/Kaikaku/epicure-cooc) | 1,790 × 300 embeddings + modes/factors/poles |
| **Epicure-Core** weights | [`Kaikaku/epicure-core`](https://huggingface.co/Kaikaku/epicure-core) | Same layout; most-downloaded of the three |
| **Epicure-Chem** weights | [`Kaikaku/epicure-chem`](https://huggingface.co/Kaikaku/epicure-chem) | Same layout |
| Companion dataset | [`Kaikaku/epicure-corpus-resources`](https://huggingface.co/datasets/Kaikaku/epicure-corpus-resources) | Canonical vocab (parquet), mode atlases, factor alignments, probe/SLERP result tables, cuisine taxonomy, supplement PDF (~16.5 MB) |
| Live demo (Gradio Space) | [`Kaikaku/epicure-explorer`](https://huggingface.co/spaces/Kaikaku/epicure-explorer) | All three models + the operators, interactive |
| Paper page | [huggingface.co/papers/2605.22391](https://huggingface.co/papers/2605.22391) | Links all of the above |

**Not included** (source-licensing restrictions): raw recipe corpora, the
co-occurrence graphs, and compound embeddings. The underlying public sources
remain available separately: FlavorDB (Garg et al. 2017), FooDB (foodb.ca),
USDA FoodData Central (fdc.nal.usda.gov), and the recipe datasets listed in
the paper's references.

### Each model repo contains

- `embeddings.safetensors` — 1,790 × 300 float32 skip-gram vectors
- `vocab.json` / `itos.json` — ingredient ↔ index mappings
- `modes.json` — the GMM modes (150–200) with labels and pole vectors
- `factor_poles.npy` + `factor_pole_index.json` — the 20 ICA factor poles
- `supervised_poles.json` — sensory + cuisine direction vectors for SLERP
- `epicure.py` — custom loader implementing the three operators
- `config.json`, `paper_slerp_results.csv` — hyperparameters and verification table

### How to use (from the model cards)

```bash
pip install huggingface_hub safetensors numpy
```

```python
from epicure import Epicure   # epicure.py ships in each model repo

m = Epicure.from_pretrained("Kaikaku/epicure-cooc")   # or -core / -chem

# Operator 1: nearest-neighbour pairings
m.neighbors("chicken", k=5)

# Operator 2: closest emergent mode / supervised property
m.closest_mode("miso", kind="factor", k=3)

# Operator 3: SLERP direction arithmetic (theta = explore/refine dial)
m.slerp("corn", "cuisine:Latin_American", theta_deg=30, k=5)
```

Same API across all three siblings — swap the repo ID to change which
"similarity" you're querying (see cheat sheet below).

### Per-model usage guide

| | **Epicure-Cooc** | **Epicure-Core** | **Epicure-Chem** |
|---|---|---|---|
| **Signal** | Pure recipe co-occurrence | Chemistry + 10× recipe context | Pure shared-compound chemistry |
| **Question it answers** | "What else do I **cook with** this?" | Balanced blend of both | "What **shares the flavour profile** of this?" |
| **Neighbour type** (chicken example) | Recipe companions: garlic, onion, black pepper | Chemistry peers w/ context: pork, beef, chicken broth | Flavour relatives: beef, pork, cream of chicken soup |
| **Geometry** | Isotropic (PR 173.6) | Concentrated (PR 94.2) | Isotropic (PR 183.1) |
| **Probe quality** | Weakest (still usable) | Middle | **Best on 26–27 of 27 probes + all 8 cuisines** |
| **Mode tightness** | 0.611 coherence | **0.833** (tightest clusters) | 0.703 |
| **Use for…** | Complement / pairing suggestions ("what goes with miso"); grounding in real cooking practice | Cluster-based browsing, mode atlases, tight named neighbourhoods | **Substitution** ("what can replace basil"), sensory/nutrient axes, cuisine steering, linear-probe features |

### Context → model cheat sheet

- **"What pairs with X?" (side-by-side on the plate)** → **Cooc**. Its
  neighbours are co-occurrence companions (basil → parsley, olive oil,
  parmesan).
- **"What substitutes for X?" (same role/flavour)** → **Chem** (or Core).
  Their neighbours are flavour-profile peers (basil → tarragon, oregano,
  rosemary).
- **"Make X more ⟨cuisine⟩ / more ⟨sensory quality⟩" (SLERP steering)** →
  **Chem** has the sharpest supervised directions; all three work.
- **"Which culinary neighbourhood is X in?" (named-mode lookup, KG-style)** →
  **Core** has the tightest, most coherent modes.
- **Downstream ML features (predict nutrition, cuisine, taste)** → **Chem**;
  it leads on nearly every linear probe.
- **Exploration UI** → expose all three as a user-facing "chemistry ↔ recipe
  context" toggle plus the SLERP angle as an explore/refine slider — this is
  exactly the chef-facing interface the paper proposes in its conclusion.

---

## Limitations (paper's own)

- **Corpus imbalance:** ~half East Asian, ~10% Mediterranean, single-digit
  shares for South Asian / Eastern European / Latin American → wide confidence
  intervals for small regions (ranking across models stays stable).
- **Hub coverage:** only 523/1,790 ingredients have direct FlavorDB compound
  edges; the rest get chemistry second-hand through graph paths.
- **LLM dependence:** vocabulary, cuisine tags, and mode labels are
  LLM-generated (Claude, deterministic decoding). The embeddings themselves are
  LLM-free — skip-gram only ever sees walk token sequences.
- **Release:** the paper said "not released at this time," but weights, loader
  code, companion data, and a demo Space were published on HuggingFace on
  27 May 2026 (see Availability section above). Raw recipe corpora and graphs
  remain unreleased due to source licensing.

---

## Future directions the paper suggests

1. A continuous mixing parameter at the walker (turn the 3 siblings into a
   parameterised family — tune the chemistry↔context trade-off instead of
   choosing).
2. Richer operators: intra-mode interpolation, multi-direction blends,
   constrained traversal ("rotate toward Mediterranean but stay in dairy").
3. Cross-modal grounding: share the canonical vocabulary with recipe-text,
   image, or sensory-descriptor spaces so SLERP can cross modalities.
4. A single chef-facing interface exposing model choice + mode lookup + SLERP
   angle, then measuring what real users do with it.
