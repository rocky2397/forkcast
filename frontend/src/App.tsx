import { useEffect, useState } from "react";
import { Today } from "./screens/Today";
import { Inventory } from "./screens/Inventory";
import { Recipes } from "./screens/Recipes";
import { Login } from "./screens/Login";
import { Intro } from "./screens/Intro";
import { api, setUnauthorizedHandler } from "./api";
import "./App.css";

type Tab = "today" | "inventory" | "recipes";
type Gate = "checking" | "locked" | "open";

// Bump the suffix to show the walkthrough again after the loop changes.
const INTRO_SEEN = "forkcast.intro.v1";

export default function App() {
  const [tab, setTab] = useState<Tab>("today");
  const [gate, setGate] = useState<Gate>("checking");
  // Remounts the tabs after login so screens refetch with the session cookie.
  const [sessionKey, setSessionKey] = useState(0);
  // Private-mode Safari throws on localStorage; the walkthrough is not worth
  // a blank app, so treat any failure as "already seen".
  const [introDone, setIntroDone] = useState(() => {
    try {
      return localStorage.getItem(INTRO_SEEN) === "1";
    } catch {
      return true;
    }
  });

  useEffect(() => {
    setUnauthorizedHandler(() => setGate("locked"));
    api
      .session()
      .then((s) => setGate(s.authenticated ? "open" : "locked"))
      // No session endpoint reachable (offline PWA launch, backend down):
      // fall through to the app, which shows its own error state.
      .catch(() => setGate("open"));
  }, []);

  if (gate === "checking") return <div className="app" />;
  if (gate === "locked")
    return (
      <div className="app">
        <Login
          onAuthenticated={() => {
            setSessionKey((k) => k + 1);
            setGate("open");
          }}
        />
      </div>
    );

  // After the gate, so a stranger with the link meets the password first.
  if (!introDone)
    return (
      <div className="app">
        <Intro
          onStart={() => {
            try {
              localStorage.setItem(INTRO_SEEN, "1");
            } catch {
              // Unwritable storage just means it shows again next launch.
            }
            setIntroDone(true);
          }}
          // "for now" is literal: skipping does not record it as seen.
          onSkip={() => setIntroDone(true)}
        />
      </div>
    );

  return (
    <div className="app" key={sessionKey}>
      <header>
        <h1>Forkcast 🍴</h1>
      </header>
      <main>
        {tab === "today" ? <Today /> : tab === "inventory" ? <Inventory /> : <Recipes />}
      </main>
      <nav className="tabs">
        <button className={tab === "today" ? "active" : ""} onClick={() => setTab("today")}>
          Today
        </button>
        <button className={tab === "inventory" ? "active" : ""} onClick={() => setTab("inventory")}>
          Inventory
        </button>
        <button className={tab === "recipes" ? "active" : ""} onClick={() => setTab("recipes")}>
          Recipes
        </button>
      </nav>
    </div>
  );
}
