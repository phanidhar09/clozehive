import { Navigate, useLocation } from 'react-router-dom'
import { useApp } from '@/store'

export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useApp()
  const location = useLocation()

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return <>{children}</>
}
