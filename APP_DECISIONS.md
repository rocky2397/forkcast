# Forkcast — Product & Architecture Decisions

**Date:** 2026-07-18
**Status:** Prototyping. Update this file whenever a decision changes.
**Repo:** https://github.com/rocky2397/forkcast (this clone on the RecipesDev volume is canonical)
**Companion doc:** `EPICURE_PAPER_NOTES.md` (the embeddings this app builds on)

---

## 1. Vision

A personal **food inventory app** that:

1. Tracks what ingredients I have at home.
2. Suggests **recipes I can cook right now** from that inventory.
3. **Learns my taste** from what I log (dishes cooked, meals eaten) and ranks
   suggestions accordingly.
4. Tracks **calories and macros** of everything I eat, suggests daily targets
   based on my fitness goals, and steers recipe suggestions toward hitting
   those targets.
5. Runs on my **phone**; a login-based **website first** is acceptable
   → built as a **PWA** so the website is installable on the phone with no
   rewrite later.

---

## 2. Honest assessment (Claude's opinion, agreed as framing)

- The idea is solid and buildable, but it is **four products in one**:
  inventory tracker, recipe recommender, taste learner, macro coach.
  The main risk is scope, not feasibility → we phase it (Section 5).
- The **Epicure embeddings are an unusually good fit** for the taste-learning
  and substitution features — they were literally built for "what pairs with /
  substitutes for X" queries.
- Epicure **does not solve** recipes, quantities, or goal-setting. Those are
  separate subsystems we build conventionally.

### Where Epicure helps directly

| Feature | Mechanism | Model |
|---|---|---|
| Taste profile | User taste vector = time-decayed mean of embeddings of ingredients in liked/cooked dishes; rank recipes by cosine similarity | Cooc (recipe-context is the right notion of "my kind of cooking") |
| Substitutions | "Recipe needs basil, you have tarragon" → Chem nearest neighbours filtered to inventory | Chem |
| Shopping suggestions | "Buy X to unlock N more recipes" → Cooc neighbours of current inventory | Cooc |
| Cuisine exploration | SLERP steering ("more Mediterranean this week") | Any; Chem has sharpest directions |
| Nutrition vocabulary | The 1,790 canonical ingredients are already anchored to USDA FoodData Central | All (shared vocab) |

### Gaps Epicure does NOT cover (we build these)

1. **No recipes** — it is ingredient-level only. We need a recipe corpus
   normalized to the 1,790-ingredient vocabulary. *This normalization is the
   single biggest data-engineering task in the project.*
2. **No quantities** — macro tracking needs portion parsing
   ("200g chicken breast") + USDA per-100g nutrient data.
3. **No input normalization** — mapping free-text user input ("half a jar of
   passata") to canonical ingredients needs an LLM call (Claude Haiku-class,
   cheap) with fuzzy string matching as fallback/cache.
4. **No goal logic** — daily calorie/macro targets come from standard formulas
   (Mifflin-St Jeor BMR × activity factor, protein by g/kg bodyweight,
   cut/bulk adjustment). Transparent formulas, no ML — a feature, not a gap.

---

## 3. Decisions (agreed 2026-07-18)

| # | Decision | Choice | Rationale / alternatives rejected |
|---|---|---|---|
| D1 *(amended 2026-07-18 after prototype)* | Recipe source | **Curated dataset: food.com dump** (`AkashPS11/recipes_data_food.com` on HuggingFace, 1M+ recipes, CSV) — parsed ingredient lists **plus per-serving nutrition already included** (kcal, fat, sat. fat, carbs, sugar, fiber, protein, sodium), servings, ratings, categories. RecipeNLG demoted to fallback (its HF mirror needs a legacy loading script / manual download, and it carries no nutrition) | Validated by prototype (`prototype/recipe_coverage.py`, n=1,228): **94.9% of ingredient mentions map to Epicure's 1,790 vocab; 95.1% of recipes match at ≥80%; 68.5% fully** — with a small alias table (pepper→black_pepper, cilantro→coriander, gingerroot→ginger, …) expected ~97%+. Built-in nutrition removes the per-recipe USDA computation from Phase 1 entirely. Rejected: LLM-generated recipes (cost, unstable, unverified nutrition) |
| D2 | Stack | **FastAPI (Python) backend + React PWA frontend** | Backend uses `epicure.py` + numpy directly and pandas for USDA data — the whole data side stays in its native ecosystem. Rejected: full-TS Next.js (would need embedding export + operator reimplementation); Python+HTMX (weaker phone/app-like UX for logging and charts) |
| D3 | MVP focus | **Inventory → recipe suggestions first** | The novel, Epicure-powered part; macros shown per recipe from day one; taste data starts accumulating as soon as cooks are logged. Rejected: macro-tracker-first (commodity feature, delays the differentiator) |
| D4 | Platform path | **PWA website with login first**, installable on phone; native app only if PWA proves limiting | Matches "website first, phone later" with zero rewrite |
| D5 | Embeddings | Use released **`Kaikaku/epicure-cooc` / `-core` / `-chem`** weights (CC BY 4.0, attribution required) — do not retrain | 1,790×300 matrices are tiny; load all three in memory |
| D6 | Taste model | **Embedding-centroid ranking** (cosine to time-decayed user taste vector), not collaborative filtering / trained recommender | Single-user app = no collaborative data; centroid approach is explainable and works from the first logged meal |
| D7 | Goal targets | **Formula-based** (Mifflin-St Jeor + activity + goal), user-overridable | Transparent; fitness users want to see the math |
| D8 *(added 2026-07-18, amended same day)* | Inventory input | **Photo-based logging is a core input method** (not just text): snap a picture of groceries → Claude vision extracts a structured item list → user confirms/edits → items committed to inventory. **Vision model: `claude-haiku-4-5`** with structured outputs (`messages.parse()` + Pydantic schema) so extraction returns validated JSON, never free text; optional "rescan with better model" button falls back to `claude-opus-4-8` for garbled results | User requirement. Haiku chosen for cost (~$0.005/scan vs ~$0.02–0.06 on Opus — ~€0.50/month at daily use); the extraction is pure read-into-schema work with no reasoning, and the mandatory confirm screen makes occasional misreads cheap to catch. Always show the confirm screen before committing — counting/occlusion errors in photos are expected |
| D9 *(added 2026-07-18, amended same day)* | Label nutrition | **Barcode-first, vision-fallback** for packaged food: (1) scan the barcode in-browser (free JS library, no API call) → look up **Open Food Facts** (free, open database, strong German coverage) → per-100g nutrition saved to `products`; (2) only if the product is missing or has no barcode, photograph the **Nährwerttabelle** → `claude-haiku-4-5` extracts per-100g values (kJ/kcal, Fett, davon gesättigte Fettsäuren, Kohlenhydrate, davon Zucker, Eiweiß, Salz) + portion size → confirm → cached in `products` so each product is handled once | EU regulation 1169/2011 standardizes the table format, so even a small vision model reads it reliably; barcode-first makes the majority of packaged-product lookups cost exactly zero. Complements USDA rather than replacing it: USDA covers whole ingredients (chicken, lentils), products cover branded/packaged foods (protein bars, sauces, quark) that USDA maps poorly. Rejected: self-hosted vision models / Tesseract OCR (pennies saved, real ops burden, worse accuracy). *Shipped 2026-07-19:* in-browser detection uses the native `BarcodeDetector` API (no JS library needed) where available, with a self-hosted zxing WASM fallback (code-split, ~1 MB, loaded on first scan, precached for offline) for Safari/iOS which lacks the API — so the barcode read is free on every browser; only when neither decodes does the photo go to `/api/nutrition/scan`, where Haiku reads the printed EAN digits (only when fully legible — never guessed) and/or the Nährwerttabelle in one call. A resolved barcode makes Open Food Facts authoritative and caches into `products`; verified live (Nutella EAN → OFF exact; label photo → 539/6.3/57.5/30.9 per 100 g, matching OFF digit-for-digit) |
| D10 *(added 2026-07-18)* | Storage policy | **Everything lives on the external SSD — no persistent storage on the internal PC drive, including caches.** All tool caches are redirected via env vars (see Section 8): HuggingFace model downloads (`HF_HOME`), pip (`PIP_CACHE_DIR`), npm (`npm_config_cache`), Python venv and `node_modules` inside the project, database file(s) and recipe corpus in a project `data/` dir | User requirement. Without redirection, the Epicure weights alone would land in `~/.cache/huggingface` on the internal disk. Honest caveat: small *ephemeral* OS temp files during process runtime (`/tmp`) can't be fully avoided at the OS level — the policy covers all persistent storage |
| D11 *(added 2026-07-18)* | Dev volume | **APFS sparse-bundle disk image stored on the ExFAT SSD**, mounted as the working volume for development | The SSD is ExFAT (verified via `diskutil`), which lacks symlinks and Unix permissions — breaking Python venvs and npm's `node_modules/.bin`. A `.sparsebundle` file lives on the SSD (all bytes stay physically there), is non-destructive, keeps the SSD Windows-readable, and mounts as a real APFS volume where all tooling works. Rejected: reformatting to APFS (destructive, kills Windows compat); staying on ExFAT with workarounds (fragile). Trade-off accepted: the image must be mounted before working (scripted in `dev.sh`) |
| D12 *(added 2026-07-19)* | Calorie/macro targets | **Mifflin-St Jeor BMR × activity factor = TDEE, adjusted by goal (cut −15% / maintain / bulk +10%). Macros: protein 1.8 g/kg body weight, fat 25% of kcal, carbs the remainder. Metric units.** Profile is a single local row (sex, age, height, weight, activity, goal). Recipe cooks derive macros from the recipe row (per serving); ad-hoc meals are quick-added with manual macros | Mifflin-St Jeor is the standard, best-validated resting-energy equation for the general population; 1.8 g/kg protein sits in the evidence-backed 1.6–2.2 range for training people; fat at 25% kcal keeps hormones happy while leaving carbs for training fuel. Manual quick-add is the honest MVP until D9 (barcode + Nährwerttabelle scan) feeds the same path automatically |
| D13 *(added 2026-07-19)* | Substitution suggestions | **Rank-gated, class-guarded stand-ins from the inventory** for a recipe's missing ingredients: candidate must rank within the missing ingredient's top-200 cooc AND top-400 chem neighbors (forward direction only); a hand-curated coarse food-class map (meat, seafood, herb, allium, citrus, dairy, sweetener, grain) must agree — same class relaxes the gate to cooc ≤ 400 (class already vouches for "same kind"), class mismatch rejects outright, both-unclassed uses the strict dual gate. Staples excluded on both sides. Shown as "needs X — try Y" chips in the feed and hints in the recipe detail | Ranks, not raw cosines: cosines aren't comparable across ingredients (hub effects, §8) — yogurt~sour_cream scores 0.084 while carrot~salmon scores 0.136. Embeddings alone can't separate complements from substitutes across food kinds: duck↔ginger passes every rank gate in both directions (fwd 17/85, rev 70/44) because they genuinely share flavor chemistry — the class map is the missing orthogonal signal, and it also recovers within-class pairs the chem gate missed (rice→couscous, beef→lamb, scallion→onion, maple_syrup→honey). Precision over recall throughout: a wrong suggestion costs trust, a missed one costs nothing. Validated on 17 regression pairs (all pass) + live probe (turkey/duck/pork→chicken, celery→carrot, lemongrass→ginger; salt→ginger bug fixed by excluding staple missings) |
| D14 *(added 2026-07-19)* | Demo sharing | **Cloudflare quick tunnel** (`share.sh`) exposing the local backend — which now also serves the built frontend — as a temporary public `*.trycloudflare.com` URL. `cloudflared` binary lives on the dev volume (D10). Accepted for trusted-friend demos only: all visitors share the single-user data (inventory, profile, meal log, taste), vision endpoints run on the owner's API key, the URL is random per run and dies when the tunnel stops, and the Mac must stay awake. `data/forkcast.db` is backed up before demo sessions | Free, no account, one command, nothing deployed. Rejected for now: real hosting (Fly.io/Railway) — that properly requires the deferred auth + per-user data slice first, so strangers can't mutate the owner's data or spend their API credits |
| D15 *(added 2026-08-01)* | Permanent hosting | **Render, Docker web service on a paid instance with a 1 GB persistent disk**, gated by a **single shared password** — not per-user accounts. Password in `FORKCAST_PASSWORD`; an HMAC-signed, HttpOnly, 30-day session cookie (`backend/app/auth.py`, stdlib `hmac` — no new dependency) guards every `/api/*` route except login/session/health; the static bundle stays open so the login screen can render; login attempts are rate-limited 10/5 min per client IP (`--proxy-headers` so the bucket is the real caller, not Render's balancer). Unset `FORKCAST_PASSWORD` disables the gate entirely, so `dev.sh` is untouched. The database is **split in two** (`backend/scripts/split_corpus.py`): `corpus.db` (87.9k recipes + 794k ingredient rows, ~130 MB, read-only, baked into the image, published as a release asset on a separate **public** data repo) and `forkcast.db` (inventory, meal log, profile, products — a few KB, on the persistent disk). `db.py` ATTACHes the corpus read-only; unqualified table names resolve across both, so no query changed. Epicure weights are prefetched at build time. See `DEPLOY.md` | Supersedes D14 for sharing that outlives a session: the tunnel needs the Mac awake and hands out a URL that dies on exit. Shared password chosen over full multi-user because per-user data slicing means a `user_id` migration across every table and query — real work, deferred until someone actually needs their own kitchen; one password already fixes the two things that made D14 unsafe to leave running (strangers mutating data, strangers spending API credits). Free tier rejected: ephemeral filesystem wipes user data on every redeploy, 15-min spin-down costs a ~1 min cold start, free Postgres expires after 30 days. Corpus split rejected alternatives: Postgres migration (rewrites all SQLite queries to move 12 rows of actual user data), Git LFS (111 MB per version against GitHub's 1 GB free bandwidth, drained by a handful of builds), rebuilding the corpus during the Docker build (pulls RecipeNLG through `datasets` — slow and over the build budget). Public data repo rather than a token in a build arg, which Render explicitly warns against since build args can persist in image layers; the corpus is derived entirely from public sources, so publishing it costs nothing |
| D16 *(added 2026-08-11)* | First-run explanation | **A dismissible three-step walkthrough** (`frontend/src/screens/Intro.tsx`) shown once before the tabs, after the D15 password gate. Each step pairs the action with its result — photograph groceries → a checklist you confirm; a stocked kitchen → 87,861 recipes ranked by what's cookable now; rating cooks → ranking that follows your taste, and barcode/Nährwerttabelle scans that feed the macro targets. Dismissal is recorded in `localStorage` under a versioned key (`forkcast.intro.v1`), so changing the loop can re-show it; `skip for now` deliberately does *not* record, matching what the words promise. Unreadable storage (private-mode Safari) is treated as "already seen" rather than blocking the app | The app is unusable until the inventory is stocked, but the D14/D15 share links drop a newcomer straight onto an empty Today tab that explains none of that — and the payoff (ranked feed, substitutions, learned taste) is invisible until something is in the kitchen. Rejected inline hints under each control: they answer "what does this button do" but never "why is this app empty", which is the actual first-run failure. Server-side persistence rejected — with one shared account, one person dismissing it would hide it from everyone |

---

## 4. Architecture sketch

```
┌────────────────────────────  React PWA (login)  ───────────────────────────┐
│  Inventory UI · Recipe feed · Meal log · Macro dashboard · Goals           │
└─────────────────────────────────┬──────────────────────────────────────────┘
                                  │ REST/JSON
┌─────────────────────────────────▼──────────────────────────────────────────┐
│                          FastAPI backend (Python)                          │
│                                                                            │
│  Epicure service      Recipe matcher        Nutrition service              │
│  - 3 embedding sets   - inventory ∩ recipe  - USDA per-100g lookups        │
│    in memory (numpy)    ingredient sets     - portion parsing              │
│  - neighbors/slerp/   - substitution-aware  - daily totals vs targets      │
│    mode lookup          "almost cookable"                                  │
│                                                                            │
│  Taste service        Normalizer            Goal service                   │
│  - user taste vector  - free text → 1,790   - Mifflin-St Jeor + activity   │
│    (time-decayed        canonical (fuzzy      + goal → kcal/protein/       │
│    centroid)            match, LLM fallback,   carb/fat targets            │
│  - recipe ranking       cached)                                            │
│                                                                            │
│  Vision intake service (Claude API, claude-haiku-4-5; opus-4-8 rescan)     │
│  - grocery photo → structured item list (messages.parse + Pydantic)        │
│  - barcode → Open Food Facts lookup (free, no LLM call) → products cache   │
│  - Nährwerttabelle photo (fallback) → per-100g record → products cache     │
│  - extracted names run through the Normalizer → canonical ingredients      │
│  - nothing committed without user confirmation in the UI                   │
└─────────────────────────────────┬──────────────────────────────────────────┘
                                  │
                    Postgres (SQLite acceptable for MVP)
     users · inventory_items · recipes (normalized) · meal_log · goals
     · products (label-scanned packaged foods)
```

**Recipe ranking score (Phase 2+):** weighted blend of
`cookability` (fraction of ingredients in inventory, substitutions counted at
a discount) + `taste` (cosine to user vector) + `macro fit` (how well the
recipe fills the remaining daily budget). Weights tunable; start 50/30/20.

### Data model (first cut)

- `users` — auth, bodyweight, height, age, sex, activity level, goal (cut/maintain/bulk)
- `ingredients` — the 1,790 canonical entries + USDA nutrient anchors (per 100g)
- `inventory_items` — user, ingredient_id, quantity (optional at first), added_at
- `recipes` — title, source, servings, normalized ingredient list (ids + amounts), per-serving macros (computed), cuisine tags
- `products` — label-scanned packaged foods: name, brand, optional barcode, per-100g macros (kcal, fat, saturates, carbs, sugars, protein, salt), portion size, link to nearest canonical ingredient, source photo reference
- `meal_log` — user, timestamp, recipe_id OR ad-hoc ingredient list OR product_id + amount, servings, computed macros, liked (bool/rating)
- `goals` — computed targets + user overrides, effective_from

---

## 5. Roadmap (phased)

### Phase 1 — "What can I cook?" (MVP)
- [ ] Login (single user is fine; simple email+password or magic link)
- [ ] Data pipeline: import recipe corpus subset → normalize ingredients to
      canonical vocab → compute per-serving macros via USDA (**biggest task**)
- [ ] Inventory CRUD (text input with normalizer; no quantities required yet)
- [ ] **Photo inventory intake (D8):** upload/camera capture → Claude vision
      extraction → confirm/edit screen → commit to inventory
- [ ] Recipe suggestions: exact-match cookability ranking, macros displayed
- [ ] "Log that I cooked this" button (starts collecting taste data immediately)

### Phase 2 — Taste + fitness
- [ ] Meal logging (recipes + ad-hoc foods with portions)
- [ ] **Packaged-product intake (D9):** in-browser barcode scan → Open Food
      Facts lookup (free); fallback: photograph the Nährwerttabelle →
      Haiku vision extraction → confirm → saved to `products`; logging a
      product thereafter costs zero API calls (cache hit)
- [ ] Goal onboarding → suggested kcal/macro targets (overridable)
- [ ] Macro dashboard: today/week vs targets
- [ ] Taste vector from logged cooks/likes → taste-aware ranking
- [ ] Macro-fit term in ranking ("high-protein suggestions when protein is behind")

### Phase 3 — The clever stuff
- [ ] Substitution-aware "almost cookable" recipes (Chem neighbours ∩ inventory)
- [ ] Shopping suggestions ("buy X to unlock N recipes") (Cooc neighbours)
- [ ] Cuisine exploration dial (SLERP; explore ↔ refine slider)
- [ ] Inventory depletion on logged cooks; expiry nudges
- [ ] PWA polish: offline cache, install prompt, mobile-first layout pass
- [ ] Revisit D1: LLM recipe-gap-filling if dataset coverage disappoints

---

## 6. Open questions (decide when they block work)

1. Which recipe corpus subset and how large? (Quality/curation vs coverage —
   decide during Phase 1 pipeline work after inspecting RecipeNLG.)
2. Quantity tracking in inventory: full amounts, or just have/have-not with
   staples flagged? (Start have-not + staples; amounts only if depletion
   tracking proves wanted.)
3. Barcode scanning / photo input for logging? (Phase 3+ at the earliest.)
4. Multi-user from the start or hardcode single user? (Schema supports users;
   UI can stay single-user.)
5. LLM budget: vision intake (D8/D9 fallback) and normalizer fallback are the
   only paid calls. On `claude-haiku-4-5` a scan is ~$0.005; expected total
   vision cost well under €1/month, since barcode + Open Food Facts resolves
   most packaged products for free and the `products` cache means each item
   is handled only once. (Barcode-first was promoted from open question to
   decided — see D9.)

---

## 7. Storage & environment setup (SSD-only, D10/D11)

### One-time: create the APFS dev volume (sparse bundle on the ExFAT SSD)

```bash
# 100 GB is a *ceiling* — a sparse bundle only occupies what's actually written
hdiutil create -size 100g -type SPARSEBUNDLE -fs APFS \
  -volname "RecipesDev" "/Volumes/Extreme SSD/RecipesDev.sparsebundle"
```

### Every session: mount before working (goes in `dev.sh`)

```bash
hdiutil attach "/Volumes/Extreme SSD/RecipesDev.sparsebundle"
# → mounts at /Volumes/RecipesDev  (code, venv, node_modules, data all live here)
cd /Volumes/RecipesDev/recipes_app
```

Unmount with `hdiutil detach /Volumes/RecipesDev` (or Finder eject) before
unplugging the SSD.

### Cache redirection (exported by `dev.sh` / `.envrc`, never set globally)

| Env var | Points to | Keeps off the internal disk |
|---|---|---|
| `HF_HOME` | `/Volumes/RecipesDev/caches/huggingface` | Epicure model weights + HF hub cache (default `~/.cache/huggingface`) |
| `PIP_CACHE_DIR` | `/Volumes/RecipesDev/caches/pip` | pip wheel/download cache (default `~/Library/Caches/pip`) |
| `npm_config_cache` | `/Volumes/RecipesDev/caches/npm` | npm package cache (default `~/.npm`) |

Additionally, by construction inside the dev volume: the Python venv
(`.venv/`), `node_modules/`, the SQLite database, the recipe corpus, and all
build artifacts. If Postgres is ever adopted (Section 4), its data directory
must be created on the dev volume (`initdb -D /Volumes/RecipesDev/pgdata`).

**Placement note:** the paper and these planning docs currently sit in
`/Volumes/Extreme SSD/stuff/recipes_app` (ExFAT side) — fine for documents.
The *code* project gets created inside the mounted APFS volume, with the
planning docs copied or moved in when scaffolding starts.

**Known limitation (accepted):** truly ephemeral OS temp files written to
`/tmp` during process runtime cannot be redirected wholesale; no *persistent*
data lands on the internal drive.

---

## 8. Prototype findings (2026-07-18)

Environment is live: APFS dev volume mounted, venv (Python 3.12, pinned — the
system `python3` is Anaconda's 3.8 via PATH shadowing), Epicure-Cooc weights
downloaded to the SSD HF cache, loader smoke-tested.

1. **Epicure loader verified.** `neighbors("chicken")` reproduces the paper's
   Table 6 exactly (garlic .39, onion .37, black_pepper .36, turkey .35,
   carrot .34). Vocab confirmed at 1,790.
2. **Recipe coverage validated** — see amended D1. The main risk of the
   curated-dataset plan is retired.
3. **⚠️ Shipped cuisine poles ≠ paper's.** `supervised_poles.json` contains
   "heuristically constructed" cuisine directions (model card's own words).
   SLERP toward them works mechanically but the top ranks are dominated by
   universal staples (salt, onion, garlic) — the paper's hero results
   (rice+South_Asian → dals) sit at ranks 14–25. Mean-centering does not fix
   it. **Consequence for Phase 3 (cuisine dial):** filter universal staples
   from steering results (build our own "universal" list, e.g. top-N by
   corpus frequency) or re-derive cuisine poles from tagged ingredients.
   The 0° case and plain neighbors are unaffected.
4. **Companion dataset gaps:** `vocab.csv` ships name + node IDs only — **no
   USDA/FlavorDB anchor columns** (despite the paper's claim), and no
   per-ingredient universal/cuisine tags. Ingredient-level nutrition mapping
   (needed for ad-hoc whole-food logging in Phase 2) is our own task —
   mitigated by food.com per-recipe nutrition (D1) and label scanning (D9).
5. **Alias table** is the cheapest next quality win for the normalizer:
   ~10–20 entries fix the bulk of unmatched terms (pepper, green pepper,
   cilantro, cornflour, gingerroot, cayenne, catsup, bay leaves, …), plus
   proper plural handling for multi-word terms ("bay leaves" → bay_leaf).

---

## 9. Attribution

Epicure embeddings: Radzikowski & Chen (KAIKAKU.AI), arXiv:2605.22391,
weights CC BY 4.0 via HuggingFace (`Kaikaku/epicure-{cooc,core,chem}`).
Attribution must appear in the app's about/credits page.
