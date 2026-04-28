// react/jsx-runtime shim for plugin bundles.
// When built with jsxRuntime: 'classic', Rollup emits React.createElement() calls
// directly (no import from react/jsx-runtime). This file exists as a safety net
// for any future plugin that uses the automatic JSX transform.
//
// Re-exports jsx-runtime from the host's already-loaded React.

const R = window.React
export const jsx = R.createElement
export const jsxs = R.createElement
export const jsxDEV = R.createElement
export const Fragment = R.Fragment
