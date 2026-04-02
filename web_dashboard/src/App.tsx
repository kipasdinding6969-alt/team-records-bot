import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { getAuthState, isAuthenticated } from './api'
import Layout from './components/Layout'
import ClientDetail from './pages/ClientDetail'
import Clients from './pages/Clients'
import Dashboard from './pages/Dashboard'
import Login from './pages/Login'
import Pipeline from './pages/Pipeline'
import Reports from './pages/Reports'
import Setup from './pages/Setup'
import Team from './pages/Team'
import UserManagement from './pages/UserManagement'
import NumberLookup from './pages/NumberLookup'
import PermissionManager from './pages/PermissionManager'
import Performance from './pages/Performance'
import OrgChart from './pages/OrgChart'
import Templates from './pages/Templates'
import Contests from './pages/Contests'
import FrontdeskEntry from './pages/FrontdeskEntry'
import GroupOverview from './pages/GroupOverview'
import MaintainerDash from './pages/MaintainerDash'
import CustomerService from './pages/CustomerService'
import PerformanceDetail from './pages/PerformanceDetail'
import Exams from './pages/Exams'
import CSFinance from './pages/CSFinance'

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
        <Route path="/login" element={<Login />} />
        <Route path="/setup" element={<Setup />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route index element={<Dashboard />} />
          <Route path="pipeline" element={<Pipeline />} />
          <Route path="team" element={<Team />} />
          <Route path="clients" element={<Clients />} />
          <Route path="clients/:id" element={<ClientDetail />} />
          <Route path="reports" element={<Reports />} />
          <Route path="performance" element={<Performance />} />
          <Route path="performance-detail" element={<PerformanceDetail />} />
          <Route
            path="users"
            element={
              <AdminRoute>
                <UserManagement />
              </AdminRoute>
            }
          />
          <Route
            path="phone-lookup"
            element={
              <ProtectedRoute>
                <NumberLookup />
              </ProtectedRoute>
            }
          />
          <Route
            path="org-chart"
            element={
              <AdminRoute>
                <OrgChart />
              </AdminRoute>
            }
          />
          <Route
            path="permissions"
            element={
              <AdminRoute>
                <PermissionManager />
              </AdminRoute>
            }
          />
          <Route
            path="templates"
            element={
              <AdminRoute>
                <Templates />
              </AdminRoute>
            }
          />
          <Route
            path="contests"
            element={
              <ProtectedRoute>
                <Contests />
              </ProtectedRoute>
            }
          />
          <Route
            path="frontdesk"
            element={
              <ProtectedRoute>
                <FrontdeskEntry />
              </ProtectedRoute>
            }
          />
          <Route
            path="groups"
            element={
              <AdminRoute>
                <GroupOverview />
              </AdminRoute>
            }
          />
          <Route
            path="maintainer"
            element={
              <AdminRoute>
                <MaintainerDash />
              </AdminRoute>
            }
          />
          <Route
            path="cs"
            element={
              <ProtectedRoute>
                <CustomerService />
              </ProtectedRoute>
            }
          />
          <Route
            path="exams"
            element={
              <ProtectedRoute>
                <Exams />
              </ProtectedRoute>
            }
          />
          <Route
            path="cs-finance"
            element={
              <ProtectedRoute>
                <CSFinance />
              </ProtectedRoute>
            }
          />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
