import { useEffect, useRef, useState } from "react";
import { api, pretty, type InventoryItem, type ScanProposal } from "../api";
import { ScanConfirm } from "./ScanConfirm";
import { foodColor, kitchenGroup, KITCHEN_GROUPS } from "../format";
import { Guide, HelpButton } from "../Guide";
import { useGuide } from "../useGuide";
import { CloseIcon, ScanIcon } from "../Icons";

type Feedback = { added: string[]; unknown: string[] } | { error: string };

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
      setFeedback({ added: res.added, unknown: res.unknown });
      setInput("");
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
        <button className="btn scan-primary" onClick={() => fileRef.current?.click()} disabled={scanning}>
          <ScanIcon size={20} />
          {scanning ? "Reading your photo…" : "Scan groceries"}
        </button>
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
              placeholder="e.g. chicken breasts, rice, soy sauce"
              aria-describedby="add-hint"
            />
            <button type="submit" className="btn" disabled={busy || !input.trim()}>
              Add
            </button>
          </div>
          <p id="add-hint" className="field-hint">
            Separate several with commas.
          </p>
        </form>
      </div>

      {feedback && (
        <div className="notice" role="status">
          {"error" in feedback ? (
            <p className="error">{feedback.error}</p>
          ) : (
            <>
              {feedback.added.length > 0 && <p>Added {feedback.added.map(pretty).join(", ")}.</p>}
              {feedback.unknown.length > 0 && (
                <p className="error">
                  Couldn't match {feedback.unknown.map((u) => `“${u}”`).join(", ")}. Try a simpler name, like
                  "chicken" instead of a brand.
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
                    {pretty(it.canonical)}
                  </span>
                  <button className="remove" onClick={() => remove(it.canonical)} aria-label={`Remove ${pretty(it.canonical)}`}>
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
