import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/fraunces/opsz.css'
import '@fontsource-variable/fraunces/opsz-italic.css'
import '@fontsource-variable/inter/wght.css'
import './index.css'
import App from './App.tsx'
import { registerSW } from 'virtual:pwa-register'
import { watchInstall } from './install'

// The service worker keeps an offline copy of the app. When a new version is
// deployed, it installs in the background on the next launch and takes over;
// without this, the open page kept showing the old copy until the app was
// closed and opened again. In "autoUpdate" mode, registerSW reloads the page
// once when an updated worker takes over (never on the very first install).
// D66: only when the open page really is an old copy. Pages now load from the
// network first, so usually it's already the new version, and a reload would
// only throw away what someone had started typing.
registerSW({
  immediate: true,
  onNeedReload: async () => {
    try {
      const html = await fetch('/', { cache: 'no-store' }).then((r) => r.text())
      const latest = html.match(/assets\/index-[\w-]+\.js/)?.[0]
      if (!latest || [...document.scripts].some((s) => s.src.includes(latest))) return
    } catch {
      return // offline: keep what's open
    }
    window.location.reload()
  },
})

// D73: the browser's install offer can come before any screen is drawn.
watchInstall()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
