"""The public /stats page: the demo's anonymous usage totals (D33), as plain HTML.

No script, no external assets; colours follow the app's palette (D30), light
and dark. Every value is escaped.
"""

from html import escape

STEPS = {
    "visited": "Opened the demo",
    "added": "Added an ingredient",
    "opened": "Opened a recipe",
    "cooked": "Marked a recipe as cooked",
}
ACTIONS = {
    "ingredient_added": "Ingredients added",
    "ingredient_removed": "Ingredients removed",
    "recipe_opened": "Recipes opened",
    "recipe_cooked": "Recipes marked as cooked",
    "rated_liked": "Dishes rated Liked",
    "rated_not_for_me": "Dishes rated Not for me",
    "rating_cleared": "Ratings cleared",
    "profile_saved": "Profiles changed",
    "meal_typed": "Meals typed in",
    "photo_scan_tried": "Tried photo scanning (off in the demo)",
    "label_scan_tried": "Tried label scanning (off in the demo)",
    "barcode_lookup": "Barcode lookups",
}

_CSS = """
:root{--bg:#f6f1e8;--surface:#fbf8f2;--ink:#1e1a16;--ink-2:#5c534b;--line:#e2d9cb;--accent:#b23a24;--herb:#3f5f2e;--herb-soft:#e3ead8}
@media (prefers-color-scheme:dark){:root{--bg:#171411;--surface:#1f1b17;--ink:#f1eae0;--ink-2:#cfc5b8;--line:#342e27;--accent:#ec8a6f;--herb:#a6c486;--herb-soft:#253020}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 -apple-system,system-ui,"Segoe UI",sans-serif}
main{max-width:760px;margin:0 auto;padding:32px 16px 64px}
h1{font:600 2rem/1.2 Georgia,"Times New Roman",serif;margin:0 0 8px}
h2{font:600 1.25rem/1.3 Georgia,"Times New Roman",serif;margin:40px 0 12px}
p{margin:0 0 12px;color:var(--ink-2)}
a{color:var(--accent)}
.big{display:flex;flex-wrap:wrap;gap:12px;margin:24px 0}
.big div{flex:1 1 160px;background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px}
.big strong{display:block;font:600 2rem/1.1 Georgia,serif;color:var(--ink)}
.row{display:grid;grid-template-columns:minmax(0,13rem) 1fr 4.5rem;gap:12px;align-items:center;margin:8px 0}
.bar{height:12px;border-radius:6px;background:var(--herb-soft);overflow:hidden}
.bar span{display:block;height:100%;background:var(--herb)}
.num{text-align:right;font-variant-numeric:tabular-nums}
table{width:100%;border-collapse:collapse}
td{padding:8px 0;border-bottom:1px solid var(--line)}
td:last-child{text-align:right;font-variant-numeric:tabular-nums}
.note{font-size:14px}
@media (max-width:480px){.row{grid-template-columns:1fr 3.5rem}.row .bar{grid-column:1/-1;grid-row:2}}
"""


def _pretty(name: str | None) -> str:
    return " ".join(w[:1].upper() + w[1:] for w in (name or "").split())


def _row(label: str, value: float, display: str) -> str:
    width = max(0.0, min(1.0, value)) * 100
    return (
        f'<div class="row"><span>{escape(label)}</span>'
        f'<div class="bar" aria-hidden="true"><span style="width:{width:.1f}%"></span></div>'
        f'<span class="num">{escape(display)}</span></div>'
    )


def _table(rows: list[tuple[str, int]]) -> str:
    if not rows:
        return "<p>Nothing yet.</p>"
    body = "".join(f"<tr><td>{escape(k)}</td><td>{v:,}</td></tr>" for k, v in rows)
    return f"<table><tbody>{body}</tbody></table>"


def render(s: dict) -> str:
    visitors = s["visitors"]
    last7 = sum(d["visitors"] for d in s["per_day"][-7:])
    peak = max((d["visitors"] for d in s["per_day"]), default=0) or 1

    funnel = "".join(
        _row(label, s["funnel"][step]["share"] or 0,
             f'{round((s["funnel"][step]["share"] or 0) * 100)}%')
        for step, label in STEPS.items()
    )
    per_day = "".join(
        _row(d["day"], d["visitors"] / peak, f'{d["visitors"]:,}') for d in reversed(s["per_day"])
    ) or "<p>Nothing yet.</p>"
    actions = _table([(label, s["events"][k]) for k, label in ACTIONS.items() if s["events"].get(k)])
    ingredients = _table([(_pretty(i["ingredient"]), i["times"]) for i in s["top_ingredients_added"]])
    recipes = _table([(_pretty(r["name"]) or f'Recipe {r["id"]}', r["times"]) for r in s["top_recipes_opened"]])
    since = f" since {escape(s['since'])}" if s["since"] else ""

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Forkcast demo: usage</title><style>{_CSS}</style></head>
<body><main>
<h1>How the Forkcast demo is used</h1>
<p>Anonymous totals{since}, updated live. <a href="/">Try the demo</a> · <a href="https://github.com/rocky2397/forkcast">Code on GitHub</a></p>

<div class="big">
<div><strong>{visitors:,}</strong>visitors in total</div>
<div><strong>{last7:,}</strong>in the last 7 days</div>
</div>

<h2>How far visitors get</h2>
<p>Share of visitors who did each at least once.</p>
{funnel}

<h2>Visitors per day</h2>
{per_day}

<h2>What people did</h2>
{actions}

<h2>Ingredients added most</h2>
{ingredients}

<h2>Recipes opened most</h2>
{recipes}

<h2>How this is counted</h2>
<p class="note">A visitor is a new demo kitchen. Someone who clears their browser or switches device counts twice,
and a server restart can count a step twice. Days are UTC.</p>
<p class="note">Nothing personal is stored: no IP addresses, no browser details, no times finer than the day,
nothing anyone typed, no profile values and nothing per visitor. Only these totals, one small file per day.</p>
</main></body></html>"""
