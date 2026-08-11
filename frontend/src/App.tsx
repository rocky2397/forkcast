import { useEffect, useState } from "react";
import { Today } from "./screens/Today";
import { Inventory } from "./screens/Inventory";
import { Recipes } from "./screens/Recipes";
import { Login } from "./screens/Login";
import { api, setUnauthorizedHandler } from "./api";
import "./App.css";

type Tab = "today" | "inventory" | "recipes";
type Gate = "checking" | "locked" | "open";

export default function App() {
  const [tab, setTab] = useState<Tab>("today");
  const [gate, setGate] = useState<Gate>("checking");
  // Remounts the tabs after login so screens refetch with the session cookie.
  const [sessionKey, setSessionKey] = useState(0);

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
