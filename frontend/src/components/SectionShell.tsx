import type { ReactNode } from "react"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

type Props = {
  index: number
  id: string
  title: string
  caption: string
  status?: { label: string; tone: "idle" | "active" | "done" | "alert" }
  className?: string
  children: ReactNode
}

// Darker foregrounds than the dark-theme equivalents, so the tinted pills still clear
// contrast requirements against a light surface.
const toneClass: Record<string, string> = {
  idle: "bg-white/50 text-muted-foreground border-white/60",
  active: "bg-amber-100/70 text-amber-900 border-amber-300/70",
  done: "bg-emerald-100/70 text-emerald-900 border-emerald-300/70",
  alert: "bg-red-100/70 text-red-900 border-red-300/70",
}

// One glass panel per section. On the desk layout the panel is sized by its grid cell,
// so the body is a shrinkable flex column and anything long scrolls inside it.
export function SectionShell({ index, id, title, caption, status, className, children }: Props) {
  return (
    <section
      id={id}
      className={cn(
        "flex min-h-0 scroll-mt-20 flex-col rounded-2xl bg-card text-card-foreground shadow-(--glass-shadow) ring-1 ring-(--glass-edge) backdrop-blur-xl backdrop-saturate-150 desk:overflow-hidden",
        className,
      )}
    >
      <div className="shrink-0 border-b border-primary/10 px-4 pt-3 pb-2.5 desk:pt-2.5 desk:pb-2">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs font-semibold text-primary/70 tabular-nums">
            {String(index).padStart(2, "0")}
          </span>
          <h2 className="truncate text-base font-semibold tracking-tight">{title}</h2>
          {status && (
            <Badge
              variant="outline"
              className={`ms-auto shrink-0 font-mono text-xs uppercase backdrop-blur-sm ${toneClass[status.tone]}`}
            >
              {status.label}
            </Badge>
          )}
        </div>
        <p className="mt-0.5 text-xs text-muted-foreground desk:truncate">{caption}</p>
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-3 p-4 desk:p-3">{children}</div>
    </section>
  )
}
