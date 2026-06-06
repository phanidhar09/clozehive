import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'
import Button from '@/components/ui/Button'
import GlassCard from '@/components/ui/GlassCard'

interface ErrorBoundaryProps {
  children: ReactNode
  fallback?: ReactNode
  onReset?: () => void
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

export default class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Always log — production React crashes are invisible without this.
    console.error('[ErrorBoundary]', error.name, error.message, info.componentStack?.split('\n')[1]?.trim())
    // Forward to Sentry if it has been initialised (optional dependency).
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const sentry = (window as any).__SENTRY__
      if (sentry?.hub?.captureException) {
        sentry.hub.captureException(error, { extra: { componentStack: info.componentStack } })
      }
    } catch { /* Sentry not loaded — no-op */ }
  }

  private reset = () => {
    this.setState({ hasError: false, error: null })
    this.props.onReset?.()
  }

  render() {
    if (!this.state.hasError) return this.props.children
    if (this.props.fallback) return this.props.fallback

    return (
      <div className="min-h-[320px] flex items-center justify-center p-6">
        <GlassCard padding="lg" className="max-w-md w-full text-center space-y-4">
          <div className="w-12 h-12 rounded-2xl bg-red-50 dark:bg-red-900/20 flex items-center justify-center mx-auto">
            <AlertTriangle size={24} className="text-red-500" />
          </div>
          <div>
            <h2 className="font-display font-bold text-lg text-slate-800 dark:text-white">Something went wrong</h2>
            <p className="text-sm text-slate-500 dark:text-white/50 mt-1">This section failed to load. Try refreshing.</p>
          </div>
          <div className="flex flex-col sm:flex-row gap-2 justify-center">
            <Button variant="secondary" onClick={this.reset}>Try Again</Button>
            <Button
              variant="primary"
              type="button"
              onClick={() => {
                window.location.reload()
              }}
            >
              Reload page
            </Button>
          </div>
        </GlassCard>
      </div>
    )
  }
}
