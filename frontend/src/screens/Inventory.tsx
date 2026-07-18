import { useEffect, useRef, useState } from "react";
import { api, pretty, type InventoryItem, type ScanProposal } from "../api";
import { ScanConfirm } from "./ScanConfirm";

export function Inventory() {
  const [items, setItems] = useState<InventoryItem[]>([]);
  const [input, setInput] = useState("");
  const [feedback, setFeedback] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [proposals, setProposals] = useState<ScanProposal[] | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const refresh = () => api.inventory().then((r) => setItems(r.items));
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
      const msgs: string[] = [];
      if (res.added.length) msgs.push(`added: ${res.added.map(pretty).join(", ")}`);
      if (res.unknown.length) msgs.push(`not recognized: ${res.unknown.join(", ")}`);
      setFeedback(msgs.join(" · "));
      setInput("");
      await refresh();
    } catch (e) {
      setFeedback(String(e));
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
      setFeedback(`scan failed: ${e}`);
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

  return (
    <div className="screen">
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        capture="environment"
        hidden
        onChange={(e) => onPhoto(e.target.files?.[0])}
      />
      <button className="scan-btn" onClick={() => fileRef.current?.click()} disabled={scanning}>
        {scanning ? "Scanning photo…" : "📷 Scan groceries"}
      </button>
      <div className="add-row">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
          placeholder="e.g. chicken breasts, rice, soy sauce"
          autoFocus
        />
        <button onClick={add} disabled={busy || !input.trim()}>
          Add
        </button>
      </div>
      {feedback && <p className="feedback">{feedback}</p>}
      <ul className="inventory-list">
        {items.map((it) => (
          <li key={it.canonical}>
            <span>{pretty(it.canonical)}</span>
            <button className="remove" onClick={() => remove(it.canonical)} aria-label={`remove ${it.canonical}`}>
              ×
            </button>
          </li>
        ))}
      </ul>
      {items.length === 0 && <p className="empty">Nothing in your kitchen yet — add what you have.</p>}
    </div>
  );
}
