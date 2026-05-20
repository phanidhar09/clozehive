import { Suspense, lazy, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { AnimatePresence } from 'framer-motion'
import { AppContext, useCreateAppState, useApp } from '@/store'
import Layout from '@/components/layout/Layout'
import ProtectedRoute from '@/components/auth/ProtectedRoute'
import ErrorBoundary from '@/components/ErrorBoundary'
import PageTransition from '@/components/PageTransition'
import { PageLoadingState } from '@/components/system/PageLoadingState'
import { hideNonMvpUi } from '@/config/features'

// Auth pages (no layout wrapper)
const Login = lazy(() => import('@/auth/Login'))
const Signup = lazy(() => import('@/auth/Signup'))
const OAuthCallback = lazy(() => import('@/auth/OAuthCallback'))
const StyleProfileOnboarding = lazy(() => import('@/pages/onboarding/StyleProfileOnboarding'))

// App pages
const Dashboard = lazy(() => import('@/pages/Dashboard'))
const Closet = lazy(() => import('@/pages/Closet'))
const OutfitBuilder = lazy(() => import('@/pages/OutfitBuilder'))
const Upload = lazy(() => import('@/pages/Upload'))
const AIStylist = lazy(() => import('@/pages/AIStylist'))
const AIStylistChat = lazy(() => import('@/pages/AIStylistChat'))
const TravelPlanner = lazy(() => import('@/pages/TravelPlanner'))
const AvatarBuilder = lazy(() => import('@/pages/AvatarBuilder'))
const Analytics = lazy(() => import('@/pages/Analytics'))
const Groups = lazy(() => import('@/pages/Groups'))
const Profile = lazy(() => import('@/pages/Profile'))
const PurchaseGaps = lazy(() => import('@/pages/PurchaseGaps'))
const SavedOutfits = lazy(() => import('@/pages/SavedOutfits'))

import { useWebSocket } from '@/hooks/useWebSocket'

// Loads closet data + initialises WebSocket once authenticated
function DataLoader() {
  const { fetchClosetItems, isAuthenticated } = useApp()
  useWebSocket()  // connects/disconnects WS based on auth state
  useEffect(() => {
    if (isAuthenticated) fetchClosetItems()
  }, [isAuthenticated, fetchClosetItems])
  return null
}

function AppProvider({ children }: { children: React.ReactNode }) {
  const state = useCreateAppState()
  return <AppContext.Provider value={state}>{children}</AppContext.Provider>
}

// Redirect to /dashboard if already logged in
function AuthGuard({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useApp()
  return isAuthenticated ? <Navigate to="/dashboard" replace /> : <>{children}</>
}

function RouteFallback() {
  return (
    <div className="min-h-screen flex items-center justify-center p-8">
      <PageLoadingState title="Loading page…" description="Hang tight while we open this screen." className="w-full max-w-md" />
    </div>
  )
}

function PageBoundary({ children }: { children: React.ReactNode }) {
  return <ErrorBoundary><PageTransition>{children}</PageTransition></ErrorBoundary>
}

function NonMvpPlaceholder() {
  return <Navigate to="/dashboard" replace />
}


function AnimatedRoutes() {
  const location = useLocation()
  return (
    <AnimatePresence mode="wait">
      <Routes location={location} key={location.pathname}>
        {/* ── Auth routes (no sidebar/navbar) ─────────────── */}
        <Route path="/login" element={
          <AuthGuard><Login /></AuthGuard>
        } />
        <Route path="/signup" element={
          <AuthGuard><Signup /></AuthGuard>
        } />
        <Route path="/oauth/callback" element={<OAuthCallback />} />
        <Route
          path="/onboarding/style-profile"
          element={
            <ProtectedRoute>
              <Suspense fallback={<RouteFallback />}>
                <StyleProfileOnboarding />
              </Suspense>
            </ProtectedRoute>
          }
        />

        {/* ── Protected app routes (with Layout) ──────────── */}
        <Route path="/" element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard"  element={<PageBoundary><Dashboard /></PageBoundary>} />
          <Route path="closet"     element={<PageBoundary><Closet /></PageBoundary>} />
          <Route path="outfit-builder" element={<PageBoundary><OutfitBuilder /></PageBoundary>} />
          <Route path="upload"     element={<PageBoundary><Upload /></PageBoundary>} />
          {/* Redirect old /fashion-analysis deep-links to unified Add to Closet hub */}
          <Route path="fashion-analysis" element={<Navigate to="/upload" replace />} />
          {/* AI Stylist — new structured chat (always enabled) */}
          <Route path="ai-stylist" element={<PageBoundary><AIStylistChat /></PageBoundary>} />
          {/* Legacy basic chat — preserved for backward compat */}
          <Route
            path="ai-stylist-classic"
            element={
              hideNonMvpUi()
                ? <NonMvpPlaceholder />
                : <PageBoundary><AIStylist /></PageBoundary>
            }
          />
          <Route path="travel"     element={<PageBoundary><TravelPlanner /></PageBoundary>} />
          <Route
            path="avatar"
            element={
              hideNonMvpUi()
                ? <NonMvpPlaceholder />
                : <PageBoundary><AvatarBuilder /></PageBoundary>
            }
          />
          <Route path="analytics"  element={<PageBoundary><Analytics /></PageBoundary>} />
          <Route
            path="groups"
            element={
              hideNonMvpUi()
                ? <NonMvpPlaceholder />
                : <PageBoundary><Groups /></PageBoundary>
            }
          />
          <Route path="profile"    element={<PageBoundary><Profile /></PageBoundary>} />
          <Route path="purchase-gaps" element={<PageBoundary><PurchaseGaps /></PageBoundary>} />
          <Route path="saved-outfits" element={<PageBoundary><SavedOutfits /></PageBoundary>} />
        </Route>

        {/* Catch-all → login */}
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </AnimatePresence>
  )
}

export default function App() {
  return (
    <AppProvider>
      <BrowserRouter>
        <DataLoader />
        <ErrorBoundary>
          <Suspense fallback={<RouteFallback />}>
            <AnimatedRoutes />
          </Suspense>
        </ErrorBoundary>
      </BrowserRouter>
    </AppProvider>
  )
}
