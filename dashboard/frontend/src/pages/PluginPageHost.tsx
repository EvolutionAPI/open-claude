/**
 * PluginPageHost — Step 2 (v2 host renderer).
 *
 * Serves plugin pages at /plugins-ui/:slug/*.  Each page bundle is a pre-built
 * ESM module that exports a default React component; the host loads it via
 * dynamic import() and mounts it inside a PluginErrorBoundary.
 *
 * Shadow DOM and custom-element mounting have been removed entirely.
 * Navigation is provided through PluginNavigationContext (usePluginNavigation
 * from @evonexus/ui), not through window.EvoNexus globals.
 */

import { lazy, Suspense, useState, useEffect, type ComponentType } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  getAllPluginPages,
  hydratePluginUiRegistry,
  isPluginUiRegistryHydrated,
} from '../lib/plugin-ui-registry'
import { PluginErrorBoundary } from '../components/PluginErrorBoundary'

// ---------------------------------------------------------------------------
// Module-level cache: slug+pageId → lazy React component
// Prevents redundant dynamic imports across navigations.
// ---------------------------------------------------------------------------
const componentCache = new Map<string, ComponentType<{ slug: string }>>()

function getOrCreateLazyComponent(
  cacheKey: string,
  bundleUrl: string
): ComponentType<{ slug: string }> {
  const cached = componentCache.get(cacheKey)
  if (cached) return cached

  // lazy() requires a function that returns a Promise<{ default: Component }>.
  // Plugin bundles must export their page component as the default export.
  const LazyComponent = lazy(
    () =>
      // @vite-ignore — bundle URL is not statically analyzable
      import(/* @vite-ignore */ bundleUrl).then(
        (mod: { default?: ComponentType<{ slug: string }> }) => {
          if (!mod.default || typeof mod.default !== 'function') {
            throw new Error(
              `Plugin bundle at "${bundleUrl}" does not export a default React component. ` +
                'Ensure your vite.config.ts uses lib mode with format: "es".'
            )
          }
          return { default: mod.default }
        }
      )
  )

  componentCache.set(cacheKey, LazyComponent)
  return LazyComponent
}

// ---------------------------------------------------------------------------
// PluginPageHost — main export
// ---------------------------------------------------------------------------
export default function PluginPageHost() {
  const { slug, '*': splat } = useParams<{ slug: string; '*': string }>()
  const navigate = useNavigate()

  const pageSubPath = splat ?? ''

  // Wait for the registry before declaring "not found".  On hard refresh the
  // App-level hydrate effect may not have completed; trigger it here too.
  const [registryReady, setRegistryReady] = useState(isPluginUiRegistryHydrated())
  useEffect(() => {
    if (registryReady) return
    let cancelled = false
    hydratePluginUiRegistry().then(() => {
      if (!cancelled) setRegistryReady(isPluginUiRegistryHydrated())
    })
    return () => {
      cancelled = true
    }
  }, [registryReady])

  // Resolve the matching page declaration from the registry.
  const allPages = getAllPluginPages()
  const page =
    allPages.find(
      (p) =>
        p.slug === slug &&
        (p.path === pageSubPath || p.path === pageSubPath.replace(/\/$/, ''))
    ) ??
    allPages.find(
      (p) => p.slug === slug && (p.path === '' || p.path === 'index')
    )

  if (!slug) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-[#5a6b7f] text-sm">Invalid plugin URL.</p>
      </div>
    )
  }

  if (!page) {
    if (!registryReady) {
      return (
        <div className="flex items-center justify-center h-full">
          <div className="text-[#5a6b7f] text-sm">Loading plugin...</div>
        </div>
      )
    }
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <p className="text-[#5a6b7f] text-sm mb-2">
            Plugin page{' '}
            <code className="text-xs bg-[#21262d] px-1 rounded">
              {slug}/{pageSubPath || '(index)'}
            </code>{' '}
            not found.
          </p>
          <button
            onClick={() => navigate('/plugins')}
            className="text-xs text-[#00FFA7] hover:underline"
          >
            Go to Plugins
          </button>
        </div>
      </div>
    )
  }

  const cacheKey = `${page.slug}::${page.id}`
  const PluginComponent = getOrCreateLazyComponent(cacheKey, page.bundle_url)

  return (
    <div className="w-full h-full flex flex-col">
      <PluginErrorBoundary slug={slug}>
        <Suspense
          fallback={
            <div className="flex items-center justify-center h-full">
              <div className="text-[#5a6b7f] text-sm">Loading plugin...</div>
            </div>
          }
        >
          <PluginComponent slug={slug} />
        </Suspense>
      </PluginErrorBoundary>
    </div>
  )
}
