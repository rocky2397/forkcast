import { useEffect, useState } from "react";
import { Today } from "./screens/Today";
import { Inventory } from "./screens/Inventory";
import { Recipes } from "./screens/Recipes";
import { Login } from "./screens/Login";
import { Intro } from "./screens/Intro";
import { api, isDemo, keepsStats, savesKitchens, setUnauthorizedHandler } from "./api";
import { KitchenIcon, RecipesIcon, TodayIcon } from "./Icons";
import "./App.css";

type Tab = "today" | "inventory" | "recipes";

const TABS: { id: Tab; label: string; Icon: typeof TodayIcon }[] = [
  { id: "today", label: "Today", Icon: TodayIcon },
  { id: "inventory", label: "Kitchen", Icon: KitchenIcon },
  { id: "recipes", label: "Recipes", Icon: RecipesIcon },
];
type Gate = "checking" | "locked" | "open";

// Bump the suffix to show the walkthrough again after the loop changes.
const INTRO_SEEN = "forkcast.intro.v1";

async function deleteMyData() {
  const sure = window.confirm(
    "Delete your demo kitchen, meals and profile from the server? This can't be undone. You'll start again with the demo kitchen.",
  );
  if (!sure) return;
  try {
    await api.deleteMyData();
  } catch (e) {
    window.alert(`Couldn't delete: ${e instanceof Error ? e.message : e}`);
    return;
  }
  window.location.reload();
}

export default function App() {
  const [tab, setTab] = useState<Tab>("today");
  // D58: tapping the tab you're on starts it over (a recipe back to the list).
  const [tabKey, setTabKey] = useState(0);
  function go(id: Tab) {
    if (id === tab) setTabKey((k) => k + 1);
    else setTab(id);
    window.scrollTo(0, 0); // a new screen starts at its top, not where the last one was
  }
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
      <header className="topbar">
        <div className="topbar-inner">
          <p className="brand">Forkcast</p>
          {/* Desktop navigation; phones get the tab bar at the bottom. */}
          <nav className="topnav" aria-label="Main">
            {TABS.map(({ id, label }) => (
              <button key={id} aria-current={tab === id ? "page" : undefined} onClick={() => go(id)}>
                {label}
              </button>
            ))}
          </nav>
        </div>
      </header>
      {isDemo() && (
        // D58: one short line that scrolls away, rather than three pinned to the top.
        <p className="demo-banner">
          {savesKitchens()
            ? "Demo: private to this browser, deleted after 30 days unused. "
            : "Demo: private to you, reset after a day. "}
          {savesKitchens() && (
            <>
              <button type="button" className="link-button" onClick={deleteMyData}>
                Delete my data
              </button>
              {" · "}
            </>
          )}
          {keepsStats() && (
            <>
              <a href="/stats">Anonymous usage</a>
              {" · "}
            </>
          )}
          <a href="https://github.com/rocky2397/forkcast">Code</a>
        </p>
      )}
      <main className="main">
        {tab === "today" ? (
          <Today key={tabKey} />
        ) : tab === "inventory" ? (
          <Inventory key={tabKey} />
        ) : (
          <Recipes key={tabKey} />
        )}
      </main>
      <nav className="tabbar" aria-label="Main">
        {TABS.map(({ id, label, Icon }) => (
          <button key={id} aria-current={tab === id ? "page" : undefined} onClick={() => go(id)}>
            <Icon />
            {label}
          </button>
        ))}
      </nav>
    </div>
  );
}
