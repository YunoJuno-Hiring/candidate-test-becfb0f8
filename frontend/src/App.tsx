import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './hooks/useAuth'
import { Nav } from './components/Nav'
import Login from './pages/Login'
import ContractList from './pages/ContractList'
import NewContract from './pages/NewContract'
import ContractDetail from './pages/ContractDetail'
import SubmitHours from './pages/SubmitHours'
import Billing from './pages/Billing'
import InvoiceDetail from './pages/InvoiceDetail'
import DeveloperSettings from './pages/DeveloperSettings'
import WebhookEndpointDetail from './pages/WebhookEndpointDetail'
import { ReactNode } from 'react'

function RequireAuth({ children }: { children: ReactNode }) {
  const { token } = useAuth()
  if (!token) return <Navigate to="/login" replace />
  return <>{children}</>
}

function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-slate-50">
      <Nav />
      <main className="max-w-6xl mx-auto px-6 py-8">{children}</main>
    </div>
  )
}

function AppRoutes() {
  const { token } = useAuth()
  return (
    <Routes>
      <Route path="/login" element={token ? <Navigate to="/contracts" replace /> : <Login />} />
      <Route
        path="/contracts"
        element={
          <RequireAuth>
            <Layout>
              <ContractList />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/contracts/new"
        element={
          <RequireAuth>
            <Layout>
              <NewContract />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/contracts/:id"
        element={
          <RequireAuth>
            <Layout>
              <ContractDetail />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/contracts/:id/submit"
        element={
          <RequireAuth>
            <Layout>
              <SubmitHours />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/billing"
        element={
          <RequireAuth>
            <Layout>
              <Billing />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/billing/invoices/:id"
        element={
          <RequireAuth>
            <Layout>
              <InvoiceDetail />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/developers"
        element={
          <RequireAuth>
            <Layout>
              <DeveloperSettings />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/developers/webhooks/:id"
        element={
          <RequireAuth>
            <Layout>
              <WebhookEndpointDetail />
            </Layout>
          </RequireAuth>
        }
      />
      <Route path="/" element={<Navigate to="/contracts" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  )
}
