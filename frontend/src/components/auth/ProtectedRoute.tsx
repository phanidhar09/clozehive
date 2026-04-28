import { useEffect } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useApp } from '@/store'

interface Props {
  children: React.ReactNode
}

/**
 * Wraps authenticated routes.
 *
 * - Redirects to /login immediately if the user is not authenticated.
 * - Listens for the `ch:unauthenticated` custom event (fired by the 401
 *   refresh interceptor in api.ts) and redirects to /login when it fires.
 */
export default function ProtectedRoute({ children }: Props) {
  const { isAuthenticated } = useApp()
  const location = useLocation()
  const navigate = useNavigate()

  useEffect(() => {
    const handler = () => {
      navigate('/login', { replace: true, state: { from: location, reason: 'session_expired' } })
    }
    window.addEventListener('ch:unauthenticated', handler)
    return () => window.removeEventListener('ch:unauthenticated', handler)
  }, [navigate, location])

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return <>{children}</>
}
