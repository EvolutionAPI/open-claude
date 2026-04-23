import { Suspense, type ReactNode } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import { NotificationProvider } from './context/NotificationContext'
import Sidebar from './components/Sidebar'
import { FullPageLoader, SectionBoundary, SectionLoader } from './components/PageStates'
import { lazyDefault, lazyNamed } from './lib/lazyImport'

const Setup = lazyDefault(() => import('./pages/Setup'))
const Login = lazyDefault(() => import('./pages/Login'))
const ShareView = lazyDefault(() => import('./pages/ShareView'))
const Docs = lazyDefault(() => import('./pages/Docs'))
const Overview = lazyDefault(() => import('./pages/Overview'))
const Agents = lazyDefault(() => import('./pages/Agents'))
const AgentDetail = lazyDefault(() => import('./pages/AgentDetail'))
const Routines = lazyDefault(() => import('./pages/Routines'))
const Skills = lazyDefault(() => import('./pages/Skills'))
const SkillDetail = lazyDefault(() => import('./pages/SkillDetail'))
const Costs = lazyDefault(() => import('./pages/Costs'))
const Integrations = lazyDefault(() => import('./pages/Integrations'))
const Templates = lazyDefault(() => import('./pages/Templates'))
const Scheduler = lazyDefault(() => import('./pages/Scheduler'))
const Tasks = lazyDefault(() => import('./pages/Tasks'))
const Memory = lazyDefault(() => import('./pages/Memory'))
const Systems = lazyDefault(() => import('./pages/Systems'))
const Users = lazyDefault(() => import('./pages/Users'))
const Audit = lazyDefault(() => import('./pages/Audit'))
const Roles = lazyDefault(() => import('./pages/Roles'))
const MemPalace = lazyDefault(() => import('./pages/MemPalace'))
const Triggers = lazyDefault(() => import('./pages/Triggers'))
const Backups = lazyDefault(() => import('./pages/Backups'))
const Providers = lazyDefault(() => import('./pages/Providers'))
const Workspace = lazyDefault(() => import('./pages/Workspace'))
const Settings = lazyDefault(() => import('./pages/Settings'))
const ShareLinks = lazyDefault(() => import('./pages/ShareLinks'))
const HeartbeatsList = lazyDefault(() => import('./pages/Heartbeats'))
const HeartbeatDetail = lazyNamed(() => import('./pages/Heartbeats'), 'HeartbeatDetail')
const Activity = lazyDefault(() => import('./pages/Activity'))
const Goals = lazyDefault(() => import('./pages/Goals'))
const Topics = lazyDefault(() => import('./pages/Topics'))
const TicketDetail = lazyDefault(() => import('./pages/TicketDetail'))
const KnowledgeLayout = lazyDefault(() => import('./pages/Knowledge/KnowledgeLayout'))
const ConnectionLayout = lazyDefault(() => import('./pages/Knowledge/ConnectionLayout'))
const KnowledgeConnections = lazyDefault(() => import('./pages/Knowledge/Connections/List'))
const ConnectionDetail = lazyDefault(() => import('./pages/Knowledge/Connections/Detail'))
const KnowledgeSettings = lazyDefault(() => import('./pages/Knowledge/Settings'))
const KnowledgeSpaces = lazyDefault(() => import('./pages/Knowledge/Spaces'))
const KnowledgeUnits = lazyDefault(() => import('./pages/Knowledge/Units'))
const KnowledgeUpload = lazyDefault(() => import('./pages/Knowledge/Upload'))
const KnowledgeBrowse = lazyDefault(() => import('./pages/Knowledge/Browse'))
const KnowledgeSearch = lazyDefault(() => import('./pages/Knowledge/Search'))
const KnowledgeApiKeys = lazyDefault(() => import('./pages/Knowledge/ApiKeys'))

function FullPageRoute({
  locationKey,
  sectionName,
  children,
}: {
  locationKey: string
  sectionName: string
  children: ReactNode
}) {
  return (
    <div className="min-h-screen bg-[#0C111D]">
      <SectionBoundary key={locationKey} sectionName={sectionName}>
        <Suspense fallback={<FullPageLoader label={`Loading ${sectionName}...`} />}>
          {children}
        </Suspense>
      </SectionBoundary>
    </div>
  )
}

function DashboardRouteFrame({
  locationKey,
  children,
}: {
  locationKey: string
  children: ReactNode
}) {
  return (
    <SectionBoundary key={locationKey} sectionName="dashboard section">
      <Suspense fallback={<SectionLoader label="Loading page..." />}>
        {children}
      </Suspense>
    </SectionBoundary>
  )
}

function AppContent() {
  const location = useLocation()
  const routeKey = location.key || location.pathname
  const isDocs = location.pathname === '/docs' || location.pathname.startsWith('/docs/')
  const isShare = location.pathname.startsWith('/share/')
  const isAgentDetail = /^\/agents\/[^/]+$/.test(location.pathname)
  const isTicketDetail = /^\/tickets\/[^/]+$/.test(location.pathname)
  const isWorkspace = location.pathname === '/workspace' || location.pathname.startsWith('/workspace/')
  const { user, loading, needsSetup, hasPermission } = useAuth()

  // Share links are public - render without auth or sidebar
  if (isShare) {
    return (
      <FullPageRoute locationKey={routeKey} sectionName="share page">
        <Routes>
          <Route path="/share/:token" element={<ShareView />} />
        </Routes>
      </FullPageRoute>
    )
  }

  // Docs are public - render without auth
  if (isDocs) {
    // Redirect .txt files to API directly
    if (location.pathname.endsWith('.txt')) {
      const apiBase = import.meta.env.DEV ? 'http://localhost:8080' : ''
      window.location.replace(`${apiBase}/api/docs/llms-full.txt`)
      return null
    }

    return (
      <FullPageRoute locationKey={routeKey} sectionName="docs">
        <Routes>
          <Route path="/docs" element={<Docs />} />
          <Route path="/docs/*" element={<Docs />} />
        </Routes>
      </FullPageRoute>
    )
  }

  if (loading) {
    return <FullPageLoader label="Loading dashboard..." />
  }

  if (needsSetup) {
    return (
      <FullPageRoute locationKey={routeKey} sectionName="setup">
        <Setup />
      </FullPageRoute>
    )
  }

  if (!user) {
    return (
      <FullPageRoute locationKey={routeKey} sectionName="login">
        <Login />
      </FullPageRoute>
    )
  }

  return (
    <NotificationProvider>
      <div className="flex min-h-screen bg-[#0C111D]">
        <Sidebar />

        {/* Pages - responsive margin */}
        <main
          className={
            isAgentDetail || isWorkspace || isTicketDetail
              ? 'flex-1 ml-0 lg:ml-60 pt-14 lg:pt-0 h-screen overflow-hidden'
              : 'flex-1 ml-0 lg:ml-60 p-4 lg:p-8 pt-16 lg:pt-8 overflow-auto'
          }
        >
          <DashboardRouteFrame locationKey={routeKey}>
            <Routes>
              <Route path="/" element={<Overview />} />
              <Route path="/workspace/*" element={<Workspace />} />
              <Route path="/agents" element={<Agents />} />
              <Route path="/agents/:name" element={<AgentDetail />} />
              <Route path="/routines" element={<Routines />} />
              {hasPermission('scheduler', 'view') && <Route path="/activity" element={<Activity />} />}
              <Route path="/tasks" element={<Tasks />} />
              {hasPermission('triggers', 'view') && <Route path="/triggers" element={<Triggers />} />}
              <Route path="/skills" element={<Skills />} />
              <Route path="/skills/:name" element={<SkillDetail />} />
              <Route path="/costs" element={<Costs />} />
              <Route path="/integrations" element={<Integrations />} />
              <Route path="/templates" element={<Templates />} />
              <Route path="/scheduler" element={<Scheduler />} />
              {hasPermission('heartbeats', 'view') && <Route path="/heartbeats" element={<HeartbeatsList />} />}
              {hasPermission('heartbeats', 'view') && <Route path="/heartbeats/:id" element={<HeartbeatDetail />} />}
              <Route path="/memory" element={<Memory />} />
              <Route path="/mempalace" element={<MemPalace />} />
              <Route path="/systems" element={<Systems />} />
              {hasPermission('config', 'view') && <Route path="/settings" element={<Settings />} />}
              {hasPermission('config', 'view') && <Route path="/backups" element={<Backups />} />}
              <Route path="/config" element={<Navigate to="/settings" replace />} />
              <Route path="/providers" element={<Providers />} />
              {hasPermission('users', 'view') && <Route path="/users" element={<Users />} />}
              {hasPermission('audit', 'view') && <Route path="/audit" element={<Audit />} />}
              {hasPermission('users', 'manage') && <Route path="/roles" element={<Roles />} />}
              {hasPermission('workspace', 'manage') && <Route path="/shares" element={<ShareLinks />} />}
              <Route path="/goals" element={<Goals />} />
              {hasPermission('tickets', 'view') && <Route path="/topics" element={<Topics />} />}
              {hasPermission('tickets', 'view') && <Route path="/issues" element={<Navigate to="/topics" replace />} />}
              {hasPermission('tickets', 'view') && <Route path="/tickets/:id" element={<TicketDetail />} />}
              {hasPermission('knowledge', 'view') && (
                <>
                  {/* Top-level Knowledge shell: only Connections + Settings */}
                  <Route path="/knowledge" element={<KnowledgeLayout />}>
                    <Route index element={<KnowledgeConnections />} />
                    <Route path="settings" element={<KnowledgeSettings />} />
                  </Route>
                  {/* Per-connection scope: tabs appear only inside a connection */}
                  <Route path="/knowledge/connections/:id" element={<ConnectionLayout />}>
                    <Route index element={<ConnectionDetail />} />
                    <Route path="spaces" element={<KnowledgeSpaces />} />
                    <Route path="units" element={<KnowledgeUnits />} />
                    <Route path="upload" element={<KnowledgeUpload />} />
                    <Route path="browse" element={<KnowledgeBrowse />} />
                    <Route path="search" element={<KnowledgeSearch />} />
                    <Route path="api-keys" element={<KnowledgeApiKeys />} />
                  </Route>
                </>
              )}
            </Routes>
          </DashboardRouteFrame>
        </main>
      </div>
    </NotificationProvider>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  )
}
