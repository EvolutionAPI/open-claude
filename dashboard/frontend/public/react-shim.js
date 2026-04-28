// React shim for plugin bundles loaded via dynamic import().
// Plugin pages are built with `external: ['react']` — Rollup emits bare-specifier
// `import ... from 'react'` in the ESM output. The importmap below resolves that
// specifier to this file, which re-exports React from the host's window.React.
//
// This guarantees every plugin page shares the SAME React instance as the host
// application, which is required for React context (useToast, usePluginNavigation,
// etc.) to cross the bundle boundary correctly.

const R = window.React
export default R
export const {
  createElement,
  Component,
  PureComponent,
  Fragment,
  StrictMode,
  Suspense,
  Children,
  cloneElement,
  createContext,
  createRef,
  forwardRef,
  isValidElement,
  memo,
  useCallback,
  useContext,
  useDebugValue,
  useDeferredValue,
  useEffect,
  useId,
  useImperativeHandle,
  useInsertionEffect,
  useLayoutEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
  useSyncExternalStore,
  useTransition,
  startTransition,
  version,
} = R
