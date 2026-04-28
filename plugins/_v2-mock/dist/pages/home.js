/**
 * v2-mock plugin — home page bundle (pre-built ESM, Step 2 PoC).
 *
 * This bundle intentionally avoids bare module specifiers (react, react-dom)
 * because the browser cannot resolve them without an importmap.
 *
 * The host window already loads React globally (window.React) as part of its
 * own bundle.  This PoC accesses it via window.React to avoid importmap
 * complexity in Step 2.
 *
 * A production v2 plugin would either:
 *   (a) declare React as an external in vite.config (lib mode) and rely on
 *       the host importmap (Step 3 concern), or
 *   (b) use a CDN URL import e.g. import React from 'https://esm.sh/react@18'
 *
 * The default export must be a React component (function or class).
 * The host mounts it as: <PluginComponent slug={slug} />
 *
 * To test PluginErrorBoundary: replace the return with throw new Error('boom')
 * and confirm the fallback renders without crashing the dashboard.
 */

// Access host-provided React — the main bundle exposes it on window.React
// via vite's globalThis shim when optimizeDeps is configured (Step 3 concern).
// For Step 2 PoC, window.React must be present.
const React = window.React

if (!React) {
  throw new Error(
    '[v2-mock] window.React not found. ' +
    'The host must expose React globally for out-of-bundle plugin pages.'
  )
}

const { createElement: h, useState } = React

function HomePage({ slug }) {
  const [count, setCount] = useState(0)

  return h(
    'div',
    {
      style: {
        padding: '2rem',
        fontFamily: 'Inter, sans-serif',
        color: '#c9d1d9',
      },
    },
    h(
      'h1',
      { style: { fontSize: 20, marginBottom: 8, color: '#00FFA7' } },
      'v2 Mock Plugin — home'
    ),
    h(
      'p',
      { style: { fontSize: 14, color: '#5a6b7f', marginBottom: 16 } },
      'Loaded as React route via dynamic import(). slug: ' + slug
    ),
    h(
      'p',
      { style: { fontSize: 12, color: '#3d4f61', marginBottom: 12 } },
      'Counter (tests useState inside plugin): ' + count
    ),
    h(
      'button',
      {
        onClick: function () { setCount(function (n) { return n + 1 }) },
        style: {
          background: '#00FFA7',
          color: '#0d1117',
          border: 'none',
          borderRadius: 6,
          padding: '6px 16px',
          cursor: 'pointer',
          fontSize: 13,
          fontWeight: 600,
        },
      },
      'Increment'
    ),
    h(
      'p',
      {
        style: {
          marginTop: 24,
          fontSize: 11,
          color: '#3d4f61',
          fontStyle: 'italic',
        },
      },
      'Step 2 PoC: Shadow DOM deleted. React component mounted via dynamic import() ' +
      'inside PluginErrorBoundary + Suspense.'
    )
  )
}

export default HomePage
