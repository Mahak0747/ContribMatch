import type { LucideIcon } from 'lucide-react'
import { Inbox } from 'lucide-react'
import type { ReactNode } from 'react'

interface Props {
  title: string
  description?: string
  icon?: LucideIcon
  action?: ReactNode
}

export function EmptyState({ title, description, icon: Icon = Inbox, action }: Props) {
  return (
    <div className="panel animate-fade-up flex flex-col items-center px-6 py-12 text-center">
      <span className="mb-4 grid h-12 w-12 place-items-center rounded-xl border border-white/10 bg-white/5 text-violet-300">
        <Icon className="h-6 w-6" aria-hidden />
      </span>
      <h2 className="text-lg font-semibold text-slate-100">{title}</h2>
      {description && <p className="mt-2 max-w-md text-sm text-slate-400">{description}</p>}
      {action && <div className="mt-5 flex flex-wrap justify-center gap-3">{action}</div>}
    </div>
  )
}
