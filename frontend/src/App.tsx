import { useEffect, useState } from "react";
import { Today } from "./screens/Today";
import { Inventory } from "./screens/Inventory";
import { Recipes } from "./screens/Recipes";
import { Cook } from "./screens/Cook";
import { Login } from "./screens/Login";
import { Intro } from "./screens/Intro";
import { api, isDemo, keepsStats, savesKitchens, setUnauthorizedHandler } from "./api";
import { RecipesIcon, TodayIcon } from "./Icons";
import "./App.css";

// D72: two tabs. Cook is home; the kitchen and the full recipe list open from
// it ("See what's in your fridge", "See all meals"). Progress is your day.
type Tab = "cook" | "inventory" | "recipes" | "today";

const TABS: { id: Tab; label: string; Icon: typeof TodayIcon; owns: Tab[] }[] = [
  { id: "cook", label: "Cook", Icon: RecipesIcon, owns: ["cook", "inventory", "recipes"] },
  { id: "today", label: "Progress", Icon: TodayIcon, owns: ["today"] },
];
const tabOf = (t: Tab) => TABS.find((x) => x.owns.includes(t))!.id;
type Gate = "checking" | "locked" | "open";

// D68: whether this browser has been through the first two welcome screens.
// Without a profile it comes back at the profile step; with one, never.
const WELCOMED = "forkcast.welcome.v2";
type FirstVisit = "checking" | "welcome" | "done";

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
  // A reload stays where you were (the browser keeps the history entry).
  const [tab, setTab] = useState<Tab>(() => {
    const was = history.state?.tab as Tab | undefined;
    return was && TABS.some((x) => x.owns.includes(was)) ? was : "cook";
  });
  // D72: Progress opened from Cook's "Log it" starts with the meal form open.
  const [startLogging, setStartLogging] = useState(false);
  // D72: a scan started on Cook, handed to the Kitchen screen to read and confirm.
  const [startScan, setStartScan] = useState<{ file: File } | { sample: true } | null>(null);
  // D58: tapping the tab you're on starts it over (a recipe back to the list).
  const [tabKey, setTabKey] = useState(0);
  function go(id: Tab, opts: { log?: boolean } = {}) {
    setStartLogging(!!opts.log);
    if (id === tab) {
      // Starting the tab over closes an open recipe for good, not just until Back.
      if (history.state?.recipe != null) history.replaceState({ tab: id }, "");
      setTabKey((k) => k + 1);
    } else {
      setTab(id);
      // D66: each tab is a step in the browser's history, so the phone's back
      // button goes back to the last tab instead of leaving Forkcast.
      history.pushState({ tab: id }, "");
    }
    window.scrollTo(0, 0); // a new screen starts at its top, not where the last one was
  }
  /** D70: open a recipe from anywhere (the "Cooking now" card on Cook or Progress). */
  function openRecipe(id: number) {
    setTab("recipes");
    history.pushState({ tab: "recipes", recipe: id }, "");
    setTabKey((k) => k + 1);
    window.scrollTo(0, 0);
  }
  useEffect(() => {
    if (!history.state?.tab) history.replaceState({ tab: "cook" }, "");
    const onPop = (e: PopStateEvent) => {
      const next = (e.state?.tab as Tab | undefined) ?? "cook";
      setTab(TABS.some((x) => x.owns.includes(next)) ? next : "cook");
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  const [gate, setGate] = useState<Gate>("checking");
  // Remounts the tabs after login so screens refetch with the session cookie.
  const [sessionKey, setSessionKey] = useState(0);
  const [firstVisit, setFirstVisit] = useState<FirstVisit>("checking");
  // Private-mode Safari throws on localStorage; then the welcome starts at its
  // first screen each time, which is harmless.
  const [welcomed] = useState(() => {
    try {
      return localStorage.getItem(WELCOMED) === "1";
    } catch {
      return false;
    }
  });

  // D68: the welcome is for anyone without a profile, since nothing can fit
  // their day until they have one. Checked once the gate is open.
  useEffect(() => {
    if (gate !== "open" || firstVisit !== "checking") return;
    api
      .profile()
      .then((p) => setFirstVisit(p.profile ? "done" : "welcome"))
      .catch(() => setFirstVisit("done")); // offline or down: the tabs show their own errors
  }, [gate, firstVisit]);

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
  if (firstVisit === "checking") return <div className="app" />;
  if (firstVisit === "welcome")
    return (
      <div className="app">
        <Intro
          startAt={welcomed ? "profile" : "value"}
          onWelcomed={() => {
            try {
              localStorage.setItem(WELCOMED, "1");
            } catch {
              // Unwritable storage just means it starts at the beginning next time.
            }
          }}
          onDone={(next) => {
            setTab(next);
            history.replaceState({ tab: next }, "");
            window.scrollTo(0, 0);
            setFirstVisit("done");
          }}
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
              <button key={id} aria-current={tabOf(tab) === id ? "page" : undefined} onClick={() => go(id)}>
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
          <Today key={tabKey} onOpenRecipe={openRecipe} startLogging={startLogging} />
        ) : tab === "cook" ? (
          <Cook
            key={tabKey}
            onOpenRecipe={openRecipe}
            onKitchen={() => go("inventory")}
            onScan={(start) => {
              setStartScan(start);
              go("inventory");
            }}
            onAllMeals={() => go("recipes")}
            onLog={() => go("today", { log: true })}
            onDay={() => go("today")}
          />
        ) : (
          tab === "inventory" ? (
            <Inventory key={tabKey} onBack={() => go("cook")} start={startScan} onStarted={() => setStartScan(null)} />
          ) : (
            <Recipes key={tabKey} onBack={() => go("cook")} />
          )
        )}
      </main>
      <nav className="tabbar" aria-label="Main">
        {TABS.map(({ id, label, Icon }) => (
          <button key={id} aria-current={tabOf(tab) === id ? "page" : undefined} onClick={() => go(id)}>
            <Icon />
            {label}
          </button>
        ))}
      </nav>
    </div>
  );
}
