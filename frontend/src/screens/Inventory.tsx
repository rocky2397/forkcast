import { useEffect, useRef, useState } from "react";
import { api, isDemo, pretty, scansOn, type InventoryItem, type ScanProposal } from "../api";
import { ScanConfirm } from "./ScanConfirm";
import { foodColor, kitchenGroup, KITCHEN_GROUPS } from "../format";
import { Guide, GuideHint, HelpButton } from "../Guide";
import { useGuide } from "../useGuide";
import { CloseIcon, ScanIcon } from "../Icons";

type Feedback = { added: string[]; unknown: string[]; suggestions: Record<string, string[]> } | { error: string };

export function Inventory() {
  const [items, setItems] = useState<InventoryItem[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [input, setInput] = useState("");
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [busy, setBusy] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [proposals, setProposals] = useState<ScanProposal[] | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const guide = useGuide("forkcast.kitchenguide.v1");

  const refresh = () =>
    api.inventory().then((r) => {
      setItems(r.items);
      setLoaded(true);
    });
  useEffect(() => {
    refresh();
  }, []);

  async function add() {
    const raw = input.trim();
    if (!raw || busy) return;
    setBusy(true);
    try {
      // comma-separated batch entry supported
      const parts = raw.split(",").map((s) => s.trim()).filter(Boolean);
      const res = await api.addInventory(parts);
      setFeedback({ added: res.added_names ?? res.added.map(pretty), unknown: res.unknown, suggestions: res.suggestions ?? {} });
      setInput("");
      await refresh();
    } catch (e) {
      setFeedback({ error: String(e) });
    } finally {
      setBusy(false);
    }
  }

  /** D46: the user picked a "Did you mean…?" suggestion for something typed. */
  async function addSuggestion(typed: string, name: string) {
    if (busy) return;
    setBusy(true);
    try {
      const res = await api.addInventory([pretty(name)]);
      setFeedback((f) =>
        f && !("error" in f)
          ? { added: [...f.added, ...(res.added_names ?? res.added.map(pretty))], unknown: f.unknown.filter((u) => u !== typed), suggestions: f.suggestions }
          : f,
      );
      await refresh();
    } catch (e) {
      setFeedback({ error: String(e) });
    } finally {
      setBusy(false);
    }
  }

  async function remove(name: string) {
    await api.removeInventory(name);
    await refresh();
  }

  async function onPhoto(file: File | undefined) {
    if (!file) return;
    setScanning(true);
    setFeedback(null);
    try {
      const res = await api.scanPhoto(file);
      setProposals(res.proposals);
    } catch (e) {
      setFeedback({ error: `The scan didn't work: ${e}` });
    } finally {
      setScanning(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  if (proposals) {
    return (
      <ScanConfirm
        proposals={proposals}
        onDone={() => {
          setProposals(null);
          refresh();
        }}
      />
    );
  }

  const groups = KITCHEN_GROUPS.map((g) => ({
    name: g,
    items: items.filter((it) => kitchenGroup(it.canonical, it.family) === g),
  })).filter((g) => g.items.length > 0);

  return (
    <div className="screen">
      <p className="kicker">Your kitchen</p>
      <div className="title-row">
        <h1 className="display">Kitchen</h1>
        <HelpButton open={guide.open} onToggle={guide.toggle} label="How your kitchen works" controls="kitchen-guide" />
      </div>
      <p className="lead">
        {loaded && items.length > 0
          ? `${items.length} ingredient${items.length === 1 ? "" : "s"}. Recipes are matched against this list.`
          : "What you have at home. Recipes are matched against this list."}
      </p>

      {guide.hint && <GuideHint onOpen={guide.show} onDismiss={guide.dismiss} />}
      {guide.open && (
        <Guide
          id="kitchen-guide"
          title="How your kitchen works"
          onClose={guide.close}
          items={[
            {
              term: "Scan groceries",
              text: "Photograph your shopping. You get a checklist of what was recognised and nothing is saved until you confirm.",
            },
            {
              term: "Add by name",
              text: "Type ingredients, several at once with commas. Each is matched to Forkcast's list of 1,790 ingredients; anything it can't match is shown so you can rephrase it.",
            },
            {
              term: "No need to add basics",
              text: "Salt, pepper, oil, butter, flour and sugar are assumed in every kitchen.",
            },
            {
              term: "When something runs out",
              text: "After you cook, “I cooked this” asks what ran out and takes it off this list.",
            },
          ]}
        />
      )}

      <div className="kitchen-actions">
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          capture="environment"
          hidden
          onChange={(e) => onPhoto(e.target.files?.[0])}
        />
        <button
          className="btn scan-primary"
          onClick={() => fileRef.current?.click()}
          disabled={scanning || !scansOn()}
          aria-describedby={isDemo() ? "scan-note" : undefined}
        >
          <ScanIcon size={20} />
          {scanning ? "Reading your photo…" : "Scan groceries"}
        </button>
        {isDemo() && !scansOn() && (
          <p id="scan-note" className="feedback">
            Photo scanning is off in this demo, because it calls a paid AI model. Add ingredients by name instead.
          </p>
        )}
        {isDemo() && scansOn() && (
          <p id="scan-note" className="feedback">
            Your photo is sent to Anthropic's Claude to be read; Forkcast doesn't keep it. Up to 10 scans a day in
            this demo.
          </p>
        )}
        <form
          className="add-form"
          onSubmit={(e) => {
            e.preventDefault();
            add();
          }}
        >
          <label className="field" htmlFor="add-ingredient">
            Add by name
          </label>
          <div className="add-row">
            <input
              id="add-ingredient"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="e.g. chicken, rice, Zwiebeln"
              aria-describedby="add-hint"
            />
            <button type="submit" className="btn" disabled={busy || !input.trim()}>
              Add
            </button>
          </div>
          <p id="add-hint" className="field-hint">
            Separate several with commas. English or German names both work.
          </p>
        </form>
      </div>

      {feedback && (
        <div className="notice" role="status">
          {"error" in feedback ? (
            <p className="error">{feedback.error}</p>
          ) : (
            <>
              {feedback.added.length > 0 && <p>Added {feedback.added.join(", ")}.</p>}
              {feedback.unknown
                .filter((u) => feedback.suggestions[u]?.length)
                .map((u) => (
                  <div key={u} className="did-you-mean">
                    <p>Couldn't match “{u}”. Add instead:</p>
                    <div className="suggest-chips">
                      {feedback.suggestions[u].map((name) => (
                        <button
                          key={name}
                          type="button"
                          className="suggest-chip"
                          disabled={busy}
                          onClick={() => addSuggestion(u, name)}
                        >
                          + {pretty(name)}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              {feedback.unknown.some((u) => !feedback.suggestions[u]?.length) && (
                <p className="error">
                  Couldn't match{" "}
                  {feedback.unknown
                    .filter((u) => !feedback.suggestions[u]?.length)
                    .map((u) => `“${u}”`)
                    .join(", ")}
                  . Try the plain food, like “chicken” or “tomatoes”; a few products, such as tomato paste or
                  coffee, aren't on Forkcast's list of recipe ingredients.
                </p>
              )}
            </>
          )}
        </div>
      )}

      {loaded && items.length === 0 && (
        <p className="empty-note">Nothing here yet. Scan your shopping or add a few ingredients to see what you can cook.</p>
      )}

      <div className="kitchen-groups">
        {groups.map((g) => (
          <section key={g.name} aria-labelledby={`group-${g.name}`} className="kitchen-group">
            <h2 id={`group-${g.name}`} className="group-label">
              {g.name}
            </h2>
            <ul className="inventory-list">
              {g.items.map((it) => (
                <li key={it.canonical}>
                  <span className="item-name">
                    <span className="dot" aria-hidden="true" style={{ background: foodColor(it.canonical, it.family ?? null) }} />
                    {it.name ?? pretty(it.canonical)}
                  </span>
                  <button className="remove" onClick={() => remove(it.canonical)} aria-label={`Remove ${it.name ?? pretty(it.canonical)}`}>
                    <CloseIcon size={18} />
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
