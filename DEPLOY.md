# Deploying Forkcast

> **Status:** the public demo (D32) runs on Hugging Face Spaces at
> https://rockyyyy2397-forkcast.hf.space, built from `deploy/huggingface/`.
> No password-protected Render service exists; day-to-day use runs locally and
> on the phone through Tailscale (D18). This guide and `render.yaml` are kept
> as a ready deployment path. The Dockerfile itself is host-neutral.

Puts Forkcast on a permanent public URL behind a shared password (D15), so it
can be shared without the owner's Mac staying awake — the limitation of the
D14 Cloudflare quick tunnel, which remains the right tool for a throwaway demo.

**What this is not:** multi-user accounts. Everyone who knows the password
shares one kitchen — the same inventory, meal log, taste profile, and the same
Anthropic API credits. Share it the way you'd share a house key.

---

## How the pieces are laid out

| Thing | Where it lives | Why |
|---|---|---|
| Frontend bundle | Built into the image | Backend already serves `frontend/dist` on its own port |
| Epicure weights (~6 MB) | Baked into the image at build | Otherwise fetched from HuggingFace on every cold start |
| Recipe corpus (~130 MB) | Baked in, fetched from a public release | Read-only and identical for every deploy; too big for git |
| `forkcast.db` (user data) | Persistent disk at `/var/data` | The only thing that changes and must survive redeploys |

The corpus/user split is what makes this cheap: a 1 GB disk holds a few KB.

---

## Public demo mode (D32)

For a link anyone can open, set `FORKCAST_DEMO=1` and no password:

- Every visitor gets a private copy of the demo kitchen (the README screenshots'
  kitchen), so nobody sees or breaks anyone else's changes.
- A kitchen unused for a day is deleted, and at most 300 exist at once.
  With `FORKCAST_KITCHENS_DIR` set (D34, below) that only clears the live
  copy; the saved one comes back on the next visit.
- Photo and label scanning are off, so **don't set `ANTHROPIC_AUTH_TOKEN`**:
  the demo needs no secret at all. Barcode lookup still works.
- No persistent disk is needed: without `FORKCAST_KITCHENS_DIR` kitchens are
  throwaway. A free host works.
- The app runs the recipe feed once on the demo kitchen while it starts, so
  the first visitor after a wake-up doesn't pay for its one-off preparation.

On Hugging Face Spaces: [`deploy/huggingface/`](deploy/huggingface/) holds
the whole Space, a `README.md` (Space settings) and a `Dockerfile` that builds
Forkcast from this repo at one pinned commit. Create a public Docker Space,
add those two files, and it builds. To update the demo, change
`FORKCAST_COMMIT` in the Space's Dockerfile.

**Usage totals (D33).** With `FORKCAST_STATS_DIR` also set, the demo keeps
anonymous daily totals there (one JSON file per UTC day, written every 5
minutes) and shows them at `/stats`: visitors, what they did, how far they
get, and how the app runs (response times and errors per action, start times). Nothing personal is stored: no IPs,
browser details, typed text, profile values or per-visitor records. On
Hugging Face, attach a **private storage bucket** to the Space at `/data`
(Space settings, Volumes); the Dockerfile points `FORKCAST_STATS_DIR` at
`/data/forkcast-stats`. Without a bucket the totals still work but reset on
every restart.

**Saved kitchens (D34).** With `FORKCAST_KITCHENS_DIR` also set, a visitor's
kitchen survives restarts and updates. The live copy stays on local disk
(SQLite there is fast and safe); a changed kitchen is copied to
`FORKCAST_KITCHENS_DIR` within 30 seconds and on shutdown, and a visitor whose
live copy is gone gets the saved one back. A saved kitchen is deleted 30 days
after the last visit, at most 5,000 are kept, and the banner's "Delete my
data" removes both copies at once. What is saved: the kitchen, the meals and
the profile (sex, age, height, weight, activity, goal), under a random id that
only the visitor's browser knows; no name, email or IP. On Hugging Face the
Dockerfile points it at `/data/forkcast-kitchens`, in the same private bucket
as the usage totals.

Try it locally:

```bash
FORKCAST_DEMO=1 FORKCAST_DATA_DIR=$(mktemp -d) \
  .venv/bin/uvicorn app.main:app --app-dir backend --port 8000
```

---

## One-time setup

### 1. Build and publish the corpus

The corpus is too big for git, and Render warns that Docker build args can end
up in image layers, so the build fetches it without a token from a separate
**public** data repo. It contains nothing private: recipes
from the public food.com dataset (see the README for its terms), normalized
against the public Epicure vocabulary.

```bash
source dev.sh
python backend/scripts/split_corpus.py          # data/forkcast.db -> data/corpus.db
gh repo create rocky2397/forkcast-corpus --public -d "Forkcast recipe corpus releases"
ops/publish-corpus.sh                           # uploads as a release asset
```

The script prints the URL to use in step 3, e.g.
`https://github.com/rocky2397/forkcast-corpus/releases/download/corpus-20260801/corpus.db`

### 2. Push the repo

```bash
git push origin main
```

### 3. Create the Render service

Render → **New → Blueprint** → pick the `forkcast` repo. It reads `render.yaml`
and provisions a Docker web service on the Starter plan with a 1 GB disk.

Then set the three secrets in the dashboard (they are `sync: false`, so they
are deliberately not in the repo):

| Variable | Value |
|---|---|
| `FORKCAST_PASSWORD` | The shared password. Pick something long; it's the only lock. |
| `ANTHROPIC_AUTH_TOKEN` | Same token as in local `.env` — powers photo/label scanning |
| `FORKCAST_CORPUS_URL` | The release URL printed in step 1 |

`FORKCAST_SECRET_KEY` is generated automatically and keeps login sessions valid
across redeploys.

First build takes a while — it downloads the corpus and the Epicure weights.
Subsequent builds reuse the layers unless `FORKCAST_CORPUS_URL` changes.

### 4. Carry over existing data (optional)

A fresh disk starts with an empty inventory and no profile. To bring across
what's already on the dev volume:

```bash
python backend/scripts/split_corpus.py --user-db data/user-seed.db
```

Then upload `data/user-seed.db` to the disk as `/var/data/forkcast.db` via
Render's shell. Skip this and just re-enter the profile if it's easier — it's
a handful of numbers.

---

## Cost

Persistent disks require a paid instance, so the free plan is out: it has an
ephemeral filesystem (every redeploy wipes the inventory), spins down after
15 minutes idle with a ~1 minute cold start, and its free Postgres would expire
after 30 days anyway. Starter instance + 1 GB disk is the realistic floor —
check Render's pricing page for current figures.

Anthropic usage is unchanged from D9's estimate (well under €1/month), but note
it is now billed against whoever is using the link.

---

## Updating

With a service deployed, pushing to `main` makes Render rebuild and redeploy.
The disk survives.

Re-import of the recipe corpus is the exception: rerun
`backend/scripts/import_recipes.py`, then `split_corpus.py`,
then `ops/publish-corpus.sh` with a new tag, and update `FORKCAST_CORPUS_URL`.

An **ingredient-matcher change** needs the same republish but no re-import. The
stored canonicals are what ranking, substitutions and taste learning read, so a
matcher fix stays invisible until the data is rewritten:

```bash
# stop the backend first — these rewrite databases the server holds open
python backend/scripts/renormalize_corpus.py data/corpus.db --apply
python backend/scripts/renormalize_corpus.py data/forkcast.db --apply   # dev copy
ops/publish-corpus.sh corpus-$(date +%Y%m%d)
```

Then point the README’s download URL at the new tag, and `FORKCAST_CORPUS_URL`
too if a service is deployed.
Both scripts back the database up before writing, and dry-run without `--apply`.

---

## Rotating the password

Change `FORKCAST_PASSWORD` in the dashboard. Existing sessions stay valid
because `FORKCAST_SECRET_KEY` is independent — to force everyone out, change
that too.

---

## Local development is unaffected

None of this changes `dev.sh`. With `FORKCAST_PASSWORD` unset the login gate is
skipped entirely, and with no `data/corpus.db` present the app reads the single
combined `data/forkcast.db` exactly as before.

To exercise the deployed configuration locally:

```bash
FORKCAST_PASSWORD=test FORKCAST_INSECURE_COOKIE=1 \
  .venv/bin/uvicorn app.main:app --app-dir backend --port 8000
```

`FORKCAST_INSECURE_COOKIE` drops the `Secure` cookie flag, which is only needed
because local dev is plain HTTP. Never set it on the deployed service.
