import { ReactNode } from 'react'

interface PageHeaderProps {
  /** Lucide icon element, e.g. <BarChart3 size={18} />. Rendered inside a tinted chip. */
  icon?: ReactNode
  title: string
  subtitle?: string
  /** Right-aligned actions (buttons, links). */
  actions?: ReactNode
  /** Tailwind text color for the icon (default brand). */
  iconColor?: string
  /** Tailwind bg for the icon chip (default brand tint). */
  chipClassName?: string
}

/**
 * Standard premium page header — tinted icon chip + display title + subtitle,
 * with optional right-aligned actions. Used across all service pages for a
 * consistent, clean, premium feel.
 */
export default function PageHeader({
  icon,
  title,
  subtitle,
  actions,
  iconColor = 'text-brand-500',
  chipClassName = 'bg-brand-50 dark:bg-brand-500/10',
}: PageHeaderProps) {
  return (
    <div className="flex items-start justify-between gap-4 mb-6">
      <div className="min-w-0">
        <h1 className="font-display font-bold text-2xl text-slate-800 dark:text-slate-100 flex items-center gap-2.5">
          {icon && (
            <span className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${chipClassName} ${iconColor}`}>
              {icon}
            </span>
          )}
          <span className="truncate">{title}</span>
        </h1>
        {subtitle && (
          <p className="text-sm text-slate-400 dark:text-white/40 mt-1.5 ml-0.5">{subtitle}</p>
        )}
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
    </div>
  )
}
