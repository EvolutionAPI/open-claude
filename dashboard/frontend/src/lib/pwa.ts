export function registerServiceWorker() {
  if (!('serviceWorker' in navigator)) return
  if (!import.meta.env.PROD) return

  const register = () => {
    navigator.serviceWorker.register('/sw.js').catch((error) => {
      console.warn('[pwa] service worker registration failed', error)
    })
  }

  if (document.readyState === 'complete') {
    register()
    return
  }

  window.addEventListener('load', register, { once: true })
}

