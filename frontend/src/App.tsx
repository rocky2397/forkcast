import { useState } from "react";
import { Today } from "./screens/Today";
import { Inventory } from "./screens/Inventory";
import { Recipes } from "./screens/Recipes";
import "./App.css";

type Tab = "today" | "inventory" | "recipes";

export default function App() {
  const [tab, setTab] = useState<Tab>("today");

  return (
    <div className="app">
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
