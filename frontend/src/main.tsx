import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/fraunces/opsz.css'
import '@fontsource-variable/fraunces/opsz-italic.css'
import '@fontsource-variable/inter/wght.css'
import './index.css'
import App from './App.tsx'
import { registerSW } from 'virtual:pwa-register'

// The service worker keeps an offline copy of the app. When a new version is
// deployed, it installs in the background on the next launch and takes over;
// without this, the open page kept showing the old copy until the app was
// closed and opened again. In "autoUpdate" mode, registerSW reloads the page
// once when an updated worker takes over (never on the very first install).
registerSW({ immediate: true })

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
