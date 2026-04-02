import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { getAuthState, isAuthenticated } from './api'
import ErrorBoundary from './components/ErrorBoundary'
import Layout from './components/Layout'
import { Spinner } from './components/SharedUI'

const Login = lazy(() => import('./pages/Login'))
const Setup = lazy(() => import('./pages/Setup'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Pipeline = lazy(() => import('./pages/Pipeline'))
const Team = lazy(() => import('./pages/Team'))
const Clients = lazy(() => import('./pages/Clients'))
const ClientDetail = lazy(() => import('./pages/ClientDetail'))
const Reports = lazy(() => import('./pages/Reports'))
const Performance = lazy(() => import('./pages/Performance'))
const PerformanceDetail = lazy(() => import('./pages/PerformanceDetail'))
const UserManagement = lazy(() => import('./pages/UserManagement'))
const NumberLookup = lazy(() => import('./pages/NumberLookup'))
const OrgChart = lazy(() => import('./pages/OrgChart'))
const PermissionManager = lazy(() => import('./pages/PermissionManager'))
const Templates = lazy(() => import('./pages/Templates'))
const Contests = lazy(() => import('./pages/Contests'))
const FrontdeskEntry = lazy(() => import('./pages/FrontdeskEntry'))
const GroupOverview = lazy(() => import('./pages/GroupOverview'))
const MaintainerDash = lazy(() => import('./pages/MaintainerDash'))
const CustomerService = lazy(() => import('./pages/CustomerService'))
const Exams = lazy(() => import('./pages/Exams'))
const CSFinance = lazy(() => import('./pages/CSFinance'))
const GroupInteractions = lazy(() => import('./pages/GroupInteractions'))

function Lazy({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<Spinner />}>{children}</Suspense>
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  return isAuthenticated() ? <>{children}</> : <Navigate to="/login" replace />
}

function AdminRoute({ children }: { children: React.ReactNode }) {
  if (!isAuthenticated()) return <Navigate to="/login" replace />
  const auth = getAuthState()
  if (!auth || auth.role === 'member') return <Navigate to="/" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Lazy><Login /></Lazy>} />
        <Route path="/setup" element={<Lazy><Setup /></Lazy>} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <ErrorBoundary>
                <Layout />
              </ErrorBoundary>
            </ProtectedRoute>
          }
        >
          <Route index element={<Lazy><Dashboard /></Lazy>} />
          <Route path="pipeline" element={<Lazy><Pipeline /></Lazy>} />
          <Route path="team" element={<Lazy><Team /></Lazy>} />
          <Route path="clients" element={<Lazy><Clients /></Lazy>} />
          <Route path="clients/:id" element={<Lazy><ClientDetail /></Lazy>} />
          <Route path="reports" element={<Lazy><Reports /></Lazy>} />
          <Route path="performance" element={<Lazy><Performance /></Lazy>} />
          <Route path="performance-detail" element={<Lazy><PerformanceDetail /></Lazy>} />
          <Route path="users" element={<AdminRoute><Lazy><UserManagement /></Lazy></AdminRoute>} />
          <Route path="phone-lookup" element={<ProtectedRoute><Lazy><NumberLookup /></Lazy></ProtectedRoute>} />
          <Route path="org-chart" element={<AdminRoute><Lazy><OrgChart /></Lazy></AdminRoute>} />
          <Route path="permissions" element={<AdminRoute><Lazy><PermissionManager /></Lazy></AdminRoute>} />
          <Route path="templates" element={<AdminRoute><Lazy><Templates /></Lazy></AdminRoute>} />
          <Route path="contests" element={<ProtectedRoute><Lazy><Contests /></Lazy></ProtectedRoute>} />
          <Route path="frontdesk" element={<ProtectedRoute><Lazy><FrontdeskEntry /></Lazy></ProtectedRoute>} />
          <Route path="groups" element={<AdminRoute><Lazy><GroupOverview /></Lazy></AdminRoute>} />
          <Route path="maintainer" element={<AdminRoute><Lazy><MaintainerDash /></Lazy></AdminRoute>} />
          <Route path="cs" element={<ProtectedRoute><Lazy><CustomerService /></Lazy></ProtectedRoute>} />
          <Route path="exams" element={<ProtectedRoute><Lazy><Exams /></Lazy></ProtectedRoute>} />
          <Route path="cs-finance" element={<ProtectedRoute><Lazy><CSFinance /></Lazy></ProtectedRoute>} />
          <Route path="group-interactions" element={<ProtectedRoute><Lazy><GroupInteractions /></Lazy></ProtectedRoute>} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
