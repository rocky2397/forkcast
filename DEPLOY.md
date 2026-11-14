# Deploying Forkcast

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

## One-time setup

### 1. Build and publish the corpus

The app repo is private, and Render warns that Docker build args can end up in
image layers — so the build can't use a GitHub token. The corpus goes to a
separate **public** data repo instead. It contains nothing private: recipes
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

Push to `main` — Render rebuilds and redeploys. The disk survives.

Re-import of the recipe corpus is the exception: rerun
`backend/scripts/import_recipes.py`, then `split_corpus.py`,
then `ops/publish-corpus.sh` with a new tag, and update `FORKCAST_CORPUS_URL`.

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
