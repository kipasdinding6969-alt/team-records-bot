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
            path="permissions"
            element={
              <AdminRoute>
                <PermissionManager />
              </AdminRoute>
            }
          />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
