import { useState } from "react";
import { api } from "../api";

/** Shared-password gate for public deployments (D15). Everyone who gets past
 *  this shares the same kitchen — it keeps strangers out, nothing more. */
export function Login({ onAuthenticated }: { onAuthenticated: () => void }) {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.login(password);
      onAuthenticated();
    } catch (err) {
      setError(String(err).replace(/^Error:\s*/, ""));
      setPassword("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="login" onSubmit={submit}>
      <h1>Forkcast</h1>
      <p className="login-intro">What should I cook next?</p>
      <label className="field" htmlFor="password">
        Password
      </label>
      <input
        id="password"
        type="password"
        value={password}
        autoFocus
        autoComplete="current-password"
        onChange={(e) => setPassword(e.target.value)}
      />
      <button type="submit" className="btn" disabled={busy || password.length === 0}>
        {busy ? "Checking…" : "Enter"}
      </button>
      {error && <p className="feedback login-error">{error}</p>}
      <p className="field-hint">This is a shared demo: everyone with the password sees the same kitchen.</p>
    </form>
  );
}
