/**
 * v2-mock plugin — home page bundle (pre-built ESM).
 *
 * This is a hand-authored stub for Step 2 PoC validation only.
 * A real v2 plugin would produce this file via `vite build` (lib mode, es format).
 *
 * Exports a default React component that the host mounts inside
 * PluginErrorBoundary + Suspense.  The component receives { slug } as a prop.
 *
 * To test PluginErrorBoundary: replace the return with `throw new Error('boom')`
 * and confirm the fallback renders without crashing the dashboard.
 */

import { createElement as h } from 'react'

function HomePage({ slug }) {
  return h(
    'div',
    {
      style: {
        padding: 32,
        fontFamily: 'Inter, sans-serif',
        color: '#c9d1d9',
      },
    },
    h(
      'h1',
      { style: { fontSize: 20, marginBottom: 8, color: '#00FFA7' } },
      'v2 Mock Plugin — home'
    ),
    h('p', { style: { fontSize: 14, color: '#5a6b7f' } }, 'slug: ' + slug),
    h(
      'p',
      {
        style: {
          marginTop: 16,
          fontSize: 12,
          color: '#3d4f61',
          fontStyle: 'italic',
        },
      },
      'Step 2 PoC: Shadow DOM deleted, React component mounted via dynamic import().'
    )
  )
}

export default HomePage
