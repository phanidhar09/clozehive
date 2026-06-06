import { WifiOff } from 'lucide-react'
import type { ReactNode } from 'react'
import { PageLoadingState } from '@/components/system/PageLoadingState'
import { ErrorState } from '@/components/system/ErrorState'
import EmptyState from '@/components/ui/EmptyState'

type Action = { label: string; href?: string; onClick?: () => void }

interface Props {
  loading?: boolean
  error?: string | null
  offline?: boolean
  empty?: boolean
  loadingTitle?: string
  loadingDescription?: string
  errorTitle?: string
  emptyIcon: ReactNode
  emptyTitle: string
  emptyDescription: string
  emptyPrimaryAction?: Action
  emptySecondaryAction?: Action
  onRetry?: () => void
}

export function PageStatePanel({
  loading,
  error,
  offline,
  empty,
  loadingTitle,
  loadingDescription,
  errorTitle,
  emptyIcon,
  emptyTitle,
  emptyDescription,
  emptyPrimaryAction,
  emptySecondaryAction,
  onRetry,
}: Props) {
  if (loading) {
    return <PageLoadingState title={loadingTitle} description={loadingDescription} />
  }
  if (offline) {
    return (
      <EmptyState
        icon={<WifiOff />}
        title="You're offline"
        description="Reconnect to load the latest data and continue where you left off."
        primaryAction={{ label: 'Retry', onClick: onRetry }}
        variant="card"
      />
    )
  }
  if (error) {
    return <ErrorState title={errorTitle} message={error} onRetry={onRetry} />
  }
  if (empty) {
    return (
      <EmptyState
        icon={emptyIcon}
        title={emptyTitle}
        description={emptyDescription}
        primaryAction={emptyPrimaryAction}
        secondaryAction={emptySecondaryAction}
        variant="card"
      />
    )
  }
  return null
}
