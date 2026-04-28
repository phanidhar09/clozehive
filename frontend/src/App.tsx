import { Suspense, lazy, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AppContext, createAppState, useApp } from '@/store'
import Layout from '@/components/layout/Layout'
import ProtectedRoute from '@/components/auth/ProtectedRoute'

// Auth pages (no layout wrapper)
const Login = lazy(() => import('@/auth/Login'))
const Signup = lazy(() => import('@/auth/Signup'))

// App pages
const Dashboard = lazy(() => import('@/pages/Dashboard'))
const Closet = lazy(() => import('@/pages/Closet'))
const Upload = lazy(() => import('@/pages/Upload'))
const AIStylist = lazy(() => import('@/pages/AIStylist'))
const TravelPlanner = lazy(() => import('@/pages/TravelPlanner'))
const AvatarBuilder = lazy(() => import('@/pages/AvatarBuilder'))
const Analytics = lazy(() => import('@/pages/Analytics'))
const Groups = lazy(() => import('@/pages/Groups'))
const Profile = lazy(() => import('@/pages/Profile'))

// Loads closet data once the user is authenticated
function DataLoader() {
  const { fetchClosetItems, isAuthenticated } = useApp()
  useEffect(() => {
    if (isAuthenticated) fetchClosetItems()
  }, [isAuthenticated, fetchClosetItems])
  return null
}

function AppProvider({ children }: { children: React.ReactNode }) {
  const state = createAppState()
  return <AppContext.Provider value={state}>{children}</AppContext.Provider>
}

// Redirect to /dashboard if already logged in
function AuthGuard({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useApp()
  return isAuthenticated ? <Navigate to="/dashboard" replace /> : <>{children}</>
}

function RouteFallback() {
  return (
    <div className="min-h-screen flex items-center justify-center text-sm text-slate-500 dark:text-slate-400">
      Loading...
    </div>
  )
}

export default function App() {
  return (
    <AppProvider>
      <BrowserRouter>
        <DataLoader />
        <Suspense fallback={<RouteFallback />}>
          <Routes>
            {/* ── Auth routes (no sidebar/navbar) ─────────────── */}
            <Route path="/login" element={
              <AuthGuard><Login /></AuthGuard>
            } />
            <Route path="/signup" element={
              <AuthGuard><Signup /></AuthGuard>
            } />

            {/* ── Protected app routes (with Layout) ──────────── */}
            <Route path="/" element={
              <ProtectedRoute>
                <Layout />
              </ProtectedRoute>
            }>
              <Route index element={<Navigate to="/dashboard" replace />} />
              <Route path="dashboard"  element={<Dashboard />} />
              <Route path="closet"     element={<Closet />} />
              <Route path="upload"     element={<Upload />} />
              <Route path="ai-stylist" element={<AIStylist />} />
              <Route path="travel"     element={<TravelPlanner />} />
              <Route path="avatar"     element={<AvatarBuilder />} />
              <Route path="analytics"  element={<Analytics />} />
              <Route path="groups"     element={<Groups />} />
              <Route path="profile"    element={<Profile />} />
            </Route>

            {/* Catch-all → login */}
            <Route path="*" element={<Navigate to="/login" replace />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </AppProvider>
  )
}
