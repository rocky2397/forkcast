import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      // Registered in main.tsx instead of an injected script, so the page
      // reloads once when a new version takes over (see there).
      injectRegister: false,
      workbox: {
        // A new version takes over as soon as it has installed; main.tsx then
        // reloads the page once. Stated explicitly: with injectRegister off,
        // the plugin otherwise builds a worker that waits to be told.
        skipWaiting: true,
        clientsClaim: true,
        // include the zxing barcode decoder so scanning works offline (Safari path)
        globPatterns: ["**/*.{js,css,html,svg,png,ico,wasm}"],
        // D66: not the page itself: precached files are served before the
        // network-first rule below could fetch the newest one.
        globIgnores: ["**/index.html"],
        // Server pages, not app routes: the demo's usage totals (D33) and the API.
        navigateFallbackDenylist: [/^\/stats/, /^\/api\//, /^\/health/],
        // D66: the page itself comes from the network first, so a returning
        // visitor gets the newest version straight away instead of the cached
        // one followed by a reload; the cached copy is the fallback offline.
        navigateFallback: null,
        maximumFileSizeToCacheInBytes: 4_000_000,
        // Fonts ship one file per script subset; the browser fetches only the
        // ones it needs, so cache those on first use instead of precaching all.
        runtimeCaching: [
          {
            urlPattern: ({ request, url }) =>
              request.mode === "navigate" && !/^\/(stats|api|health)/.test(url.pathname),
            handler: "NetworkFirst",
            options: { cacheName: "pages", networkTimeoutSeconds: 3 },
          },
          {
            urlPattern: ({ request }) => request.destination === "font",
            handler: "CacheFirst",
            options: { cacheName: "fonts", expiration: { maxEntries: 30 } },
          },
        ],
      },
      manifest: {
        name: "Forkcast",
        short_name: "Forkcast",
        description: "What should I cook next?",
        theme_color: "#f6f1e8",
        background_color: "#f6f1e8",
        display: "standalone",
        icons: [
          { src: "icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "icon-512.png", sizes: "512x512", type: "image/png" },
        ],
      },
    }),
  ],
  server: {
    host: true, // reachable from the phone on the LAN
    proxy: {
      "/api": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
});
