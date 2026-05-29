import { ReactNode } from 'react'

interface SectionHeaderProps {
  /** Small lucide icon, e.g. <Palette size={16} />. */
  icon?: ReactNode
  title: string
  /** Right-aligned actions (e.g. "View all"). */
  actions?: ReactNode
  className?: string
}

/**
 * Consistent in-page section heading: small accent icon + semibold title,
 * optional right-aligned actions. Pairs with PageHeader for a clean hierarchy.
 */
export default function SectionHeader({ icon, title, actions, className }: SectionHeaderProps) {
  return (
    <div className={`flex items-center gap-2 mb-4 ${className ?? ''}`}>
      {icon && <span className="text-brand-500 shrink-0 flex items-center">{icon}</span>}
      <h2 className="font-semibold text-slate-800 dark:text-white">{title}</h2>
      {actions && <div className="ml-auto flex items-center gap-2">{actions}</div>}
    </div>
  )
}
