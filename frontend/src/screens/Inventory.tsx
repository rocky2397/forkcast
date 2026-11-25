import { useEffect, useRef, useState } from "react";
import { api, isDemo, pretty, scansOn, type InventoryItem, type ScanProposal } from "../api";
import { ScanConfirm, type ScanOutcome } from "./ScanConfirm";
import { ShoppingList } from "./ShoppingList";
import { Leftovers } from "./Leftovers";
import { foodColor, kitchenGroup, KITCHEN_GROUPS } from "../format";
import { Guide, GuideHint, HelpButton } from "../Guide";
import { useGuide } from "../useGuide";
import { LoadError, errorText } from "../LoadError";
import { BackIcon, CloseIcon, ScanIcon } from "../Icons";

type Feedback =
  | { added: string[]; already?: string[]; unknown: string[]; suggestions: Record<string, string[]>; removed?: string[] }
  | { error: string };

/** D69: what the confirm screen shows: the proposals and the photo they came from. */
type Scan = { proposals: ScanProposal[]; photo: string | null; credit: string | null; sample?: boolean };

export function Inventory({
  onBack,
  start,
  onStarted,
}: {
  onBack?: () => void;
  /** D72: a scan started on Cook: a photo to read, or the sample fridge. */
  start?: { file: File } | { sample: true } | null;
  onStarted?: () => void;
} = {}) {
  const [items, setItems] = useState<InventoryItem[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [input, setInput] = useState("");
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [busy, setBusy] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [scan, setScan] = useState<Scan | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const guide = useGuide("forkcast.kitchenguide.v1");

  const [loadError, setLoadError] = useState<string | null>(null);
  const refresh = () =>
    api
      .inventory()
      .then((r) => {
        setItems(r.items);
        setLoaded(true);
        setLoadError(null);
      })
      .catch((e) => setLoadError(errorText(e)));
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
      setFeedback({
        added: res.added_names ?? res.added.map(pretty),
        already: res.already ?? [],
        unknown: res.unknown,
        suggestions: res.suggestions ?? {},
      });
      setInput("");
      await refresh();
    } catch (e) {
      setFeedback({ error: errorText(e) });
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
      setFeedback({ error: errorText(e) });
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
      setScan({ proposals: res.proposals, photo: URL.createObjectURL(file), credit: null });
    } catch (e) {
      setFeedback({ error: `The scan didn't work: ${errorText(e)}` });
    } finally {
      setScanning(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  /** D69: the demo's recorded scan of a public fridge photo. */
  async function sampleFridge() {
    setScanning(true);
    setFeedback(null);
    try {
      const res = await api.sampleScan();
      setScan({ proposals: res.proposals, photo: `${import.meta.env.BASE_URL}${res.photo}`, credit: res.credit, sample: true });
    } catch (e) {
      setFeedback({ error: `The sample didn't load: ${errorText(e)}` });
    } finally {
      setScanning(false);
    }
  }

  // D72: take over a scan started on Cook, once the kitchen has loaded (D69:
  // the confirm screen compares with it).
  const started = useRef(false);
  useEffect(() => {
    if (!start || !loaded || started.current) return;
    started.current = true;
    onStarted?.();
    if ("file" in start) onPhoto(start.file);
    else sampleFridge();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [start, loaded]);

  if (scan) {
    return (
      <ScanConfirm
        proposals={scan.proposals}
        kitchen={items}
        photo={scan.photo}
        credit={scan.credit}
        compare={!scan.sample}
        onDone={async (outcome: ScanOutcome | null) => {
          // Reload first, so the note and the updated list show together.
          await refresh();
          if (scan.photo?.startsWith("blob:")) URL.revokeObjectURL(scan.photo);
          setScan(null);
          if (outcome) setFeedback(outcome);
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
      {onBack && (
        <button className="back" onClick={onBack}>
          <BackIcon size={20} /> Cook
        </button>
      )}
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
              term: "Scan your fridge",
              text: "Photograph your open fridge, or your shopping. You get a checklist: what the reader is sure of is ticked, what it isn't sure of isn't, and nothing changes until you confirm. A later scan also lists what looks used up.",
            },
            {
              term: "Add by name",
              text: "Type ingredients, several at once with commas. Each is matched to Forkcast's list of 1,790 ingredients; anything it can't match is shown so you can rephrase it.",
            },
            {
              term: "Shopping list",
              text: "What ran out after “I ate it”, what a recipe is missing and Worth buying picks can go on it, or type things in. Tick what you bought and it moves into your kitchen.",
            },
            {
              term: "No need to add basics",
              text: "Salt, pepper, oil, butter, flour and sugar are assumed in every kitchen.",
            },
            {
              term: "When something runs out",
              text: "After you eat a recipe, “I ate it” asks what ran out and takes it off this list. On a recipe, “Don't have it” and “Have it” fix this list too.",
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
        <div className="scan-block">
        <button
          className="btn scan-primary"
          onClick={() => fileRef.current?.click()}
          disabled={scanning || !scansOn()}
          aria-describedby={isDemo() ? "scan-note" : undefined}
        >
          <ScanIcon size={20} />
          {scanning ? "Reading your photo…" : "Scan your fridge"}
        </button>
        {isDemo() && (
          <button className="btn secondary sample-fridge" onClick={sampleFridge} disabled={scanning}>
            Use a sample fridge
          </button>
        )}
        {isDemo() && !scansOn() && (
          <p id="scan-note" className="feedback">
            Photo scanning is off in this demo, because it calls a paid AI model. Try the sample fridge, or add
            ingredients by name.
          </p>
        )}
        {isDemo() && scansOn() && (
          <p id="scan-note" className="feedback">
            A photo of your open fridge or your shopping. It's sent to Anthropic's Claude to be read; Forkcast
            doesn't keep it. Up to 10 scans a day in this demo, or try the sample fridge.
          </p>
        )}
        </div>
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
              {(feedback.removed?.length ?? 0) > 0 && <p>Removed {feedback.removed?.join(", ")}.</p>}
              {/* D66: re-adding something isn't "added" twice. */}
              {(feedback.already?.length ?? 0) > 0 && <p>Already in your kitchen: {feedback.already?.join(", ")}.</p>}
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

      <Leftovers where="kitchen" />
      <ShoppingList onKitchenChange={refresh} />

      {loadError && <LoadError error={loadError} onRetry={refresh} />}
      {loaded && items.length === 0 && (
        <p className="empty-note">Nothing here yet. Scan your fridge or add a few ingredients to see what you can cook.</p>
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
