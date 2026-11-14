import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      workbox: {
        // include the zxing barcode decoder so scanning works offline (Safari path)
        globPatterns: ["**/*.{js,css,html,svg,png,ico,wasm}"],
        maximumFileSizeToCacheInBytes: 4_000_000,
        // Fonts ship one file per script subset; the browser fetches only the
        // ones it needs, so cache those on first use instead of precaching all.
        runtimeCaching: [
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
